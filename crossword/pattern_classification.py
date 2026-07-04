"""Data-driven catalog tiers from diagnostics and runtime memory (10x10 & 12x12)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from crossword.pattern_stats import PatternStatsTracker
    from crossword.solve_diagnostics import PresearchAnalysis

CatalogTier = Literal["core_catalog", "probation", "reject"]

DEFAULT_DIAGNOSTICS_PATH = (
    Path(__file__).resolve().parent.parent / "output" / "fill_diagnostics.json"
)

# Catalog patterns in top quartile by fillability may enter probation for re-probing.
_PROBATION_FILLABILITY_FLOOR = 17.0
_LATE_TIME_REJECT_AVG_S = 10.0
_LATE_TIME_REJECT_COUNT = 2
_PRESEARCH_REJECT_DEMOTE = 2

# 12x12: pattern cap is ~8s; core needs proven fills at reasonable wall time.
_LATE_TIME_REJECT_AVG_S_12 = 14.0
_CORE_MAX_AVG_FILL_S_12 = 12.0
_SLOW_SUCCESS_AVG_S_12 = 18.0
_FALLBACK_REJECT_MAX_SLOT_12 = 10


@dataclass
class PatternRuntimeProfile:
    pattern_id: str
    grid_size: int = 10
    attempts: int = 0
    successes: int = 0
    presearch_rejects: int = 0
    late_time: int = 0
    late_nodes: int = 0
    early_dead_end: int = 0
    quick_probe_fails: int = 0
    solve_elapsed: list[float] = field(default_factory=list)
    presearch_scan: dict | None = None

    @property
    def avg_solve_seconds(self) -> float:
        if not self.solve_elapsed:
            return 0.0
        return sum(self.solve_elapsed) / len(self.solve_elapsed)

    @property
    def is_random(self) -> bool:
        return self.pattern_id.startswith("random_seed")

    @property
    def is_catalog(self) -> bool:
        return self.pattern_id.startswith("p10_") or self.pattern_id.startswith("p12_")

    @property
    def is_hand_primary_12(self) -> bool:
        return self.pattern_id in _P12_HAND_PRIMARY_IDS

    @property
    def is_hand_fallback_12(self) -> bool:
        return self.pattern_id in _P12_FALLBACK_IDS


# Imported lazily in helpers to avoid circular imports at module load.
_P12_HAND_PRIMARY_IDS: frozenset[str] = frozenset()
_P12_FALLBACK_IDS: frozenset[str] = frozenset()


def _ensure_12_ids() -> None:
    global _P12_HAND_PRIMARY_IDS, _P12_FALLBACK_IDS
    if _P12_HAND_PRIMARY_IDS:
        return
    from crossword.patterns import _P12_HAND_PRIMARY_IDS as hp, _P12_FALLBACK_IDS as fb

    _P12_HAND_PRIMARY_IDS = hp
    _P12_FALLBACK_IDS = fb


_PROFILES: dict[str, PatternRuntimeProfile] = {}
_TIER_OVERRIDES: dict[str, CatalogTier] = {}


def clear_classification_cache() -> None:
    _PROFILES.clear()
    _TIER_OVERRIDES.clear()


def set_tier_override(pattern_id: str, tier: CatalogTier) -> None:
    _TIER_OVERRIDES[pattern_id] = tier


def get_tier_override(pattern_id: str) -> CatalogTier | None:
    return _TIER_OVERRIDES.get(pattern_id)


def get_profile(pattern_id: str) -> PatternRuntimeProfile | None:
    return _PROFILES.get(pattern_id)


def load_profiles_from_diagnostics(
    path: Path | None = None,
    *,
    grid_size: int = 10,
) -> dict[str, PatternRuntimeProfile]:
    """Aggregate per-pattern stats from fill_diagnostics.json schema_version=1."""
    path = path or DEFAULT_DIAGNOSTICS_PATH
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    size_key = str(grid_size)
    if size_key not in data.get("sizes", {}):
        return {}

    block = data["sizes"][size_key]
    profiles: dict[str, PatternRuntimeProfile] = {}

    for row in block.get("presearch_scan", []):
        pid = str(row["pattern_id"])
        profiles[pid] = PatternRuntimeProfile(
            pattern_id=pid,
            grid_size=grid_size,
            presearch_scan=row,
        )

    for attempt in block.get("attempts", []):
        pid = str(attempt["pattern_id"])
        prof = profiles.setdefault(
            pid, PatternRuntimeProfile(pattern_id=pid, grid_size=grid_size)
        )
        prof.attempts += 1
        fc = attempt.get("failure_class", "unknown")
        if fc == "success" or attempt.get("success"):
            prof.successes += 1
        elif fc == "presearch_reject":
            prof.presearch_rejects += 1
        elif fc == "late_time":
            prof.late_time += 1
        elif fc == "late_nodes":
            prof.late_nodes += 1
        elif fc == "early_dead_end":
            prof.early_dead_end += 1
        if attempt.get("quick_probe_failed"):
            prof.quick_probe_fails += 1
        if not attempt.get("presearch_rejected") and attempt.get("elapsed_seconds", 0) > 0:
            prof.solve_elapsed.append(float(attempt["elapsed_seconds"]))

    _PROFILES.update(profiles)
    return profiles


def _runtime_avg_fill_s(pattern_id: str, tracker: PatternStatsTracker | None) -> float | None:
    if tracker is None:
        return None
    stats = tracker.get(pattern_id)
    if stats.successes > 0:
        return stats.avg_fill_seconds
    persisted = tracker._persisted.get(pattern_id)
    if persisted and persisted.successes > 0:
        return persisted.avg_fill_seconds
    return None


def _has_proven_core_fill_12(
    pattern_id: str,
    *,
    tracker: PatternStatsTracker | None,
    prof: PatternRuntimeProfile | None,
) -> bool:
    """Core when we have successes at reasonable runtime (not slow outliers)."""
    avg = _runtime_avg_fill_s(pattern_id, tracker)
    if avg is not None and avg > _SLOW_SUCCESS_AVG_S_12:
        return False
    if tracker is not None and tracker.has_runtime_success(pattern_id):
        if avg is not None and avg <= _CORE_MAX_AVG_FILL_S_12:
            return True
        if avg is None:
            return True
    if prof is not None and prof.successes >= 1:
        if prof.avg_solve_seconds <= _CORE_MAX_AVG_FILL_S_12:
            return True
    return False


def classify_pattern_12(
    pattern_id: str,
    *,
    presearch: PresearchAnalysis | None = None,
    tracker: PatternStatsTracker | None = None,
    profiles: dict[str, PatternRuntimeProfile] | None = None,
    max_slot_length: int | None = None,
) -> CatalogTier:
    """Assign core_catalog / probation / reject for a 12x12 pattern."""
    _ensure_12_ids()
    override = get_tier_override(pattern_id)
    if override is not None:
        return override

    profiles = profiles if profiles is not None else _PROFILES
    prof = profiles.get(pattern_id)

    if _has_proven_core_fill_12(pattern_id, tracker=tracker, prof=prof):
        return "core_catalog"

    if tracker is not None:
        stats = tracker.get(pattern_id)
        if stats.presearch_rejects >= _PRESEARCH_REJECT_DEMOTE and stats.successes == 0:
            return "reject"
        if stats.late_failures >= _LATE_TIME_REJECT_COUNT and stats.successes == 0:
            return "reject"

    if prof is not None:
        if prof.late_time >= _LATE_TIME_REJECT_COUNT and prof.avg_solve_seconds >= _LATE_TIME_REJECT_AVG_S_12:
            return "reject"
        if prof.presearch_rejects >= 3 and prof.successes == 0 and prof.solve_elapsed == []:
            return "reject"
        if prof.quick_probe_fails >= 2:
            return "reject"

    if pattern_id.startswith("random_seed"):
        if prof and prof.late_time >= 2 and prof.successes == 0:
            return "reject"
        if prof and prof.successes >= 1:
            return "core_catalog"
        return "probation"

    is_hand_primary = pattern_id in _P12_HAND_PRIMARY_IDS
    is_hand_fallback = pattern_id in _P12_FALLBACK_IDS

    if is_hand_fallback and max_slot_length is not None:
        if max_slot_length > _FALLBACK_REJECT_MAX_SLOT_12 and not (
            tracker and tracker.has_runtime_success(pattern_id)
        ):
            return "reject"

    scan = (presearch.to_dict() if presearch is not None else None) or (
        prof.presearch_scan if prof else None
    )

    if scan is not None and not scan.get("ac3_ok", True):
        return "reject"

    if is_hand_primary or is_hand_fallback:
        return "probation"

    if pattern_id.startswith("p12_"):
        return "reject"

    return "probation"


def partition_catalog_entries_12(
    entries: list,
    *,
    tracker: PatternStatsTracker | None = None,
) -> tuple[list, list, list]:
    """Split PatternEntry lists into (core, probation, reject) for size 12."""
    core: list = []
    probation: list = []
    reject: list = []
    for entry in entries:
        tier = classify_pattern_12(
            entry.id,
            tracker=tracker,
            max_slot_length=getattr(entry, "max_slot_length", None),
        )
        if tier == "core_catalog":
            core.append(entry)
        elif tier == "probation":
            probation.append(entry)
        else:
            reject.append(entry)
    return core, probation, reject


def summarize_diagnostics_12(path: Path | None = None) -> dict:
    """Human-readable summary from fill_diagnostics.json for size=12."""
    profiles = load_profiles_from_diagnostics(path, grid_size=12)
    by_tier: dict[str, list[str]] = {
        "core_catalog": [],
        "probation": [],
        "reject": [],
    }
    with_success: list[str] = []

    for pid, prof in sorted(profiles.items()):
        tier = classify_pattern_12(pid, profiles=profiles)
        by_tier[tier].append(pid)
        if prof.successes > 0:
            with_success.append(pid)

    return {
        "total_patterns": len(profiles),
        "by_tier": {k: len(v) for k, v in by_tier.items()},
        "tier_patterns": by_tier,
        "with_success": with_success,
        "profiles": {
            pid: {
                "attempts": p.attempts,
                "successes": p.successes,
                "presearch_rejects": p.presearch_rejects,
                "late_time": p.late_time,
                "avg_solve_s": round(p.avg_solve_seconds, 2),
                "tier": classify_pattern_12(pid, profiles=profiles),
            }
            for pid, p in profiles.items()
        },
    }


def list_patterns_12_inventory(tracker: PatternStatsTracker | None = None) -> list[dict]:
    """Inventory of 12x12 catalog entries with kind and runtime stats (for logs)."""
    _ensure_12_ids()
    from crossword.patterns import (
        _P12_HAND_PRIMARY_ORDER,
        entry_is_discovered_12,
        get_pattern_entries,
    )

    rows: list[dict] = []
    for entry in get_pattern_entries(12):
        if entry.tier == "archive":
            kind = "discovered_archive"
        elif entry.id in _P12_HAND_PRIMARY_IDS:
            kind = "hand_primary"
        elif entry.id in _P12_FALLBACK_IDS:
            kind = "hand_fallback"
        elif entry_is_discovered_12(entry):
            kind = "discovered"
        else:
            kind = "legacy"
        stats = tracker.get(entry.id) if tracker else None
        persisted = tracker._persisted.get(entry.id) if tracker else None
        successes = (stats.successes if stats else 0) + (
            persisted.successes if persisted else 0
        )
        attempts = (stats.attempts if stats else 0) + (
            persisted.attempts if persisted else 0
        )
        avg_s = stats.avg_fill_seconds if stats and stats.successes else 0.0
        if avg_s == 0.0 and persisted and persisted.successes:
            avg_s = persisted.avg_fill_seconds
        tier = classify_pattern_12(
            entry.id,
            tracker=tracker,
            max_slot_length=entry.max_slot_length,
        )
        rows.append({
            "pattern_id": entry.id,
            "kind": kind,
            "tier": tier,
            "successes": successes,
            "attempts": attempts,
            "avg_fill_s": round(avg_s, 2),
            "max_slot_length": entry.max_slot_length,
        })
    order = {pid: idx for idx, pid in enumerate(_P12_HAND_PRIMARY_ORDER)}
    rows.sort(key=lambda r: (order.get(r["pattern_id"], 99), r["pattern_id"]))
    return rows


def _rank_catalog_probation_candidates(
    profiles: dict[str, PatternRuntimeProfile],
) -> set[str]:
    """Top-quartile catalog by fillability among uninformative layouts."""
    catalog = [
        p for p in profiles.values()
        if p.is_catalog and p.presearch_scan
    ]
    if not catalog:
        return set()

    ranked = sorted(
        catalog,
        key=lambda p: (
            -float(p.presearch_scan.get("estimated_fillability", 0)),
            float(p.presearch_scan.get("estimated_difficulty", 99)),
        ),
    )
    n_probation = max(1, len(ranked) // 4)
    return {p.pattern_id for p in ranked[:n_probation]}


def classify_pattern_10(
    pattern_id: str,
    *,
    presearch: PresearchAnalysis | None = None,
    tracker: PatternStatsTracker | None = None,
    profiles: dict[str, PatternRuntimeProfile] | None = None,
) -> CatalogTier:
    """Assign core_catalog / probation / reject for a 10x10 pattern."""
    if pattern_id.startswith("p10_core_"):
        return "core_catalog"

    override = get_tier_override(pattern_id)
    if override is not None:
        return override

    if tracker is not None and tracker.has_runtime_success(pattern_id):
        return "core_catalog"

    profiles = profiles if profiles is not None else _PROFILES
    prof = profiles.get(pattern_id)

    if prof is not None and prof.successes >= 1:
        return "core_catalog"

    if tracker is not None:
        stats = tracker.get(pattern_id)
        if stats.successes >= 1:
            return "core_catalog"
        if stats.presearch_rejects >= _PRESEARCH_REJECT_DEMOTE and stats.successes == 0:
            return "reject"
        if stats.late_failures >= _LATE_TIME_REJECT_COUNT and stats.successes == 0:
            return "reject"

    if prof is not None:
        if prof.late_time >= _LATE_TIME_REJECT_COUNT and prof.avg_solve_seconds >= _LATE_TIME_REJECT_AVG_S:
            return "reject"
        if prof.presearch_rejects >= 3 and prof.successes == 0 and prof.solve_elapsed == []:
            return "reject"
        if prof.quick_probe_fails >= 2:
            return "reject"
        if prof.successes >= 1:
            return "core_catalog"

    scan = (presearch.to_dict() if presearch is not None else None) or (
        prof.presearch_scan if prof else None
    )

    if pattern_id.startswith("random_seed"):
        if prof and prof.late_time >= 2 and prof.successes == 0:
            return "reject"
        if prof and prof.successes >= 1:
            return "core_catalog"
        return "probation"

    if scan is None:
        return "probation"

    if not scan.get("ac3_ok", True):
        return "reject"

    uninformative = bool(scan.get("ac3_is_uninformative"))
    static_reject = bool(scan.get("reject")) and str(scan.get("reject_reason", "")).startswith(
        "uninformative_ac3"
    )

    if uninformative and static_reject:
        probation_ids = _rank_catalog_probation_candidates(profiles)
        if pattern_id in probation_ids:
            fill = float(scan.get("estimated_fillability", 0))
            if fill >= _PROBATION_FILLABILITY_FLOOR:
                return "probation"
        return "reject"

    if uninformative:
        return "probation"

    return "probation"


def partition_catalog_entries_10(
    entries: list,
    *,
    tracker: PatternStatsTracker | None = None,
) -> tuple[list, list, list]:
    """Split PatternEntry lists into (core, probation, reject) for size 10."""
    core: list = []
    probation: list = []
    reject: list = []
    for entry in entries:
        tier = classify_pattern_10(entry.id, tracker=tracker)
        if tier == "core_catalog":
            core.append(entry)
        elif tier == "probation":
            probation.append(entry)
        else:
            reject.append(entry)
    return core, probation, reject


def summarize_diagnostics_10(path: Path | None = None) -> dict:
    """Human-readable summary from fill_diagnostics.json for size=10."""
    profiles = load_profiles_from_diagnostics(path, grid_size=10)
    by_tier: dict[str, list[str]] = {
        "core_catalog": [],
        "probation": [],
        "reject": [],
    }
    consistent_pre: list[str] = []
    consistent_late: list[str] = []
    with_success: list[str] = []

    for pid, prof in sorted(profiles.items()):
        tier = classify_pattern_10(pid, profiles=profiles)
        by_tier[tier].append(pid)
        if prof.attempts > 0 and prof.presearch_rejects == prof.attempts:
            consistent_pre.append(pid)
        if prof.late_time >= 2:
            consistent_late.append(pid)
        if prof.successes > 0:
            with_success.append(pid)

    return {
        "total_patterns": len(profiles),
        "by_tier": {k: len(v) for k, v in by_tier.items()},
        "tier_patterns": by_tier,
        "consistent_presearch_reject": consistent_pre,
        "consistent_late_time": consistent_late,
        "with_success": with_success,
        "profiles": {
            pid: {
                "attempts": p.attempts,
                "successes": p.successes,
                "presearch_rejects": p.presearch_rejects,
                "late_time": p.late_time,
                "late_nodes": p.late_nodes,
                "avg_solve_s": round(p.avg_solve_seconds, 2),
                "tier": classify_pattern_10(pid, profiles=profiles),
            }
            for pid, p in profiles.items()
        },
    }
