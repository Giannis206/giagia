"""In-memory runtime stats, diversity protection, and SQLite persistence."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from crossword.pattern_runtime_stats import (
    PersistedPatternStats,
    get_pattern_runtime_store,
)

CatalogTier = str  # core_catalog | probation | reject


@dataclass
class PatternRuntimeStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_fill_seconds: float = 0.0
    late_failures: int = 0
    presearch_rejects: int = 0
    uninformative_ac3: int = 0

    @property
    def success_ratio(self) -> float:
        if self.attempts == 0:
            return 0.5
        return self.successes / self.attempts

    @property
    def avg_fill_seconds(self) -> float:
        if self.successes == 0:
            if self.attempts == 0:
                return 4.0
            return self.total_fill_seconds / self.attempts
        return self.total_fill_seconds / self.successes


class PatternStatsTracker:
    """Process-wide tracker with optional SQLite backing."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        self._stats: dict[str, PatternRuntimeStats] = {}
        self._persisted: dict[str, PersistedPatternStats] = {}
        self._recent_ids: deque[str] = deque(maxlen=24)
        self._lock = threading.Lock()
        self._store = get_pattern_runtime_store(db_path)
        self._catalog_tier: dict[str, CatalogTier] = {}
        self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        try:
            self._persisted = self._store.load_all()
            for pid, row in self._persisted.items():
                self._stats[pid] = PatternRuntimeStats(
                    attempts=row.attempts,
                    successes=row.successes,
                    failures=row.failures,
                    total_fill_seconds=row.total_fill_seconds,
                )
        except OSError:
            self._persisted = {}

    def record_selection(self, pattern_id: str, *, grid_size: int = 0) -> None:
        """Track pattern chosen for a fill attempt (diversity protection)."""
        with self._lock:
            self._recent_ids.append(pattern_id)
        try:
            self._store.record_selection(pattern_id, grid_size=grid_size)
        except OSError:
            pass

    def diversity_weight(self, pattern_id: str) -> float:
        """Penalize patterns used very recently when alternatives exist."""
        with self._lock:
            if not self._recent_ids:
                return 1.0
            count = sum(1 for pid in self._recent_ids if pid == pattern_id)
            if count >= 3:
                return 0.35
            if count == 2:
                return 0.55
            if count == 1 and len(self._recent_ids) >= 6:
                return 0.8
            return 1.0

    def get(self, pattern_id: str) -> PatternRuntimeStats:
        with self._lock:
            if pattern_id not in self._stats:
                self._stats[pattern_id] = PatternRuntimeStats()
            return self._stats[pattern_id]

    def record(
        self,
        pattern_id: str,
        *,
        success: bool,
        fill_seconds: float,
        grid_size: int = 0,
        late_fail: bool = False,
        presearch_reject: bool = False,
        uninformative_ac3: bool = False,
    ) -> None:
        with self._lock:
            stats = self._stats.setdefault(pattern_id, PatternRuntimeStats())
            stats.attempts += 1
            stats.total_fill_seconds += fill_seconds
            if success:
                stats.successes += 1
                self._catalog_tier[pattern_id] = "core_catalog"
            else:
                stats.failures += 1
            if late_fail:
                stats.late_failures += 1
            if presearch_reject:
                stats.presearch_rejects += 1
            if uninformative_ac3:
                stats.uninformative_ac3 += 1
        try:
            self._store.record_fill(
                pattern_id,
                grid_size=grid_size,
                success=success,
                fill_seconds=fill_seconds,
            )
        except OSError:
            pass

    def record_probe(
        self,
        pattern_id: str,
        *,
        grid_size: int,
        probe_seconds: float,
    ) -> None:
        try:
            self._store.record_probe(
                pattern_id,
                grid_size=grid_size,
                probe_seconds=probe_seconds,
            )
        except OSError:
            pass

    def has_runtime_success(self, pattern_id: str, *, min_successes: int = 1) -> bool:
        """True when a pattern has at least one recorded successful fill."""
        stats = self.get(pattern_id)
        if stats.successes >= min_successes:
            return True
        persisted = self._persisted.get(pattern_id)
        return persisted is not None and persisted.successes >= min_successes

    def runtime_success_ratio(self, pattern_id: str) -> float:
        """Best available success ratio from session or persisted stats."""
        stats = self.get(pattern_id)
        if stats.attempts > 0:
            return stats.success_ratio
        persisted = self._persisted.get(pattern_id)
        if persisted and persisted.attempts > 0:
            return persisted.successes / persisted.attempts
        return 0.0

    def runtime_weight(self, pattern_id: str) -> float:
        """Higher weight for patterns that succeed quickly and often."""
        stats = self.get(pattern_id)
        if stats.attempts == 0:
            persisted = self._persisted.get(pattern_id)
            if persisted and persisted.attempts > 0:
                ratio = (persisted.successes + 1) / (persisted.attempts + 2)
                weight = 0.55 + ratio * 1.6
                return max(0.25, weight)
            return 1.0
        ratio = (stats.successes + 1) / (stats.attempts + 2)
        weight = 0.55 + ratio * 1.6
        if stats.attempts >= 8 and stats.successes == 0:
            weight *= 0.45
        elif stats.attempts >= 5 and stats.success_ratio < 0.15:
            weight *= 0.65
        if stats.successes > 0:
            avg = stats.avg_fill_seconds
            if avg <= 3.0:
                weight *= 1.3
            elif avg <= 6.0:
                weight *= 1.1
            elif avg >= 7.5:
                weight *= 0.85
        return max(0.25, weight)

    def is_late_fail_pattern(self, pattern_id: str) -> bool:
        stats = self.get(pattern_id)
        if stats.late_failures >= 2:
            return True
        if stats.failures >= 3 and stats.late_failures >= 1 and stats.successes == 0:
            return True
        return False

    def late_fail_penalty(self, pattern_id: str) -> float:
        """Strong down-weight for patterns that burn time after AC-3."""
        stats = self.get(pattern_id)
        if not self.is_late_fail_pattern(pattern_id):
            return 1.0
        ratio = stats.late_failures / max(1, stats.failures)
        return max(0.05, 0.25 - ratio * 0.15)

    def is_uninformative_penalized(self, pattern_id: str) -> bool:
        stats = self.get(pattern_id)
        if stats.uninformative_ac3 >= 1:
            return True
        if stats.presearch_rejects >= 1 and stats.successes == 0:
            return True
        return False

    def uninformative_penalty(self, pattern_id: str) -> float:
        if not self.is_uninformative_penalized(pattern_id):
            return 1.0
        stats = self.get(pattern_id)
        return max(0.08, 0.35 - stats.uninformative_ac3 * 0.08)

    def adaptive_time_cap(self, pattern_id: str, default_cap: float) -> float:
        """Cut time budget for patterns with repeated late-fail behavior."""
        stats = self.get(pattern_id)
        if stats.presearch_rejects >= 2:
            return min(default_cap, 2.0)
        if self.is_late_fail_pattern(pattern_id):
            avg = stats.total_fill_seconds / max(1, stats.failures)
            return min(default_cap, max(3.0, avg * 0.45))
        if self.is_uninformative_penalized(pattern_id):
            return min(default_cap, 4.0)
        if stats.failures >= 4 and stats.successes == 0:
            return min(default_cap, default_cap * 0.55)
        return default_cap

    def adaptive_max_nodes(self, pattern_id: str, default_nodes: int) -> int:
        stats = self.get(pattern_id)
        if self.is_late_fail_pattern(pattern_id):
            return min(default_nodes, max(2000, default_nodes // 3))
        if self.is_uninformative_penalized(pattern_id):
            return min(default_nodes, 4000)
        return default_nodes

    def get_catalog_tier_10(self, pattern_id: str, *, presearch=None) -> CatalogTier:
        from crossword.pattern_classification import classify_pattern_10, load_profiles_from_diagnostics

        if pattern_id in self._catalog_tier:
            return self._catalog_tier[pattern_id]
        load_profiles_from_diagnostics(grid_size=10)
        tier = classify_pattern_10(pattern_id, presearch=presearch, tracker=self)
        self._catalog_tier[pattern_id] = tier
        return tier

    def get_catalog_tier_12(
        self,
        pattern_id: str,
        *,
        presearch=None,
        max_slot_length: int | None = None,
    ) -> CatalogTier:
        from crossword.pattern_classification import classify_pattern_12, load_profiles_from_diagnostics

        cache_key = f"12:{pattern_id}"
        if cache_key in self._catalog_tier:
            return self._catalog_tier[cache_key]
        load_profiles_from_diagnostics(grid_size=12)
        tier = classify_pattern_12(
            pattern_id,
            presearch=presearch,
            tracker=self,
            max_slot_length=max_slot_length,
        )
        self._catalog_tier[cache_key] = tier
        return tier

    def is_core_catalog(self, pattern_id: str, *, presearch=None, grid_size: int = 10) -> bool:
        if grid_size == 12:
            return self.get_catalog_tier_12(pattern_id, presearch=presearch) == "core_catalog"
        return self.get_catalog_tier_10(pattern_id, presearch=presearch) == "core_catalog"

    def is_probation(self, pattern_id: str, *, presearch=None, grid_size: int = 10) -> bool:
        if grid_size == 12:
            return self.get_catalog_tier_12(pattern_id, presearch=presearch) == "probation"
        return self.get_catalog_tier_10(pattern_id, presearch=presearch) == "probation"

    def is_reject_tier(self, pattern_id: str, *, presearch=None, grid_size: int = 10) -> bool:
        if grid_size == 12:
            return self.get_catalog_tier_12(pattern_id, presearch=presearch) == "reject"
        return self.get_catalog_tier_10(pattern_id, presearch=presearch) == "reject"

    def demote_to_reject(self, pattern_id: str) -> None:
        from crossword.pattern_classification import set_tier_override

        self._catalog_tier[pattern_id] = "reject"
        set_tier_override(pattern_id, "reject")

    def promote_to_core(self, pattern_id: str) -> None:
        from crossword.pattern_classification import set_tier_override

        self._catalog_tier[pattern_id] = "core_catalog"
        set_tier_override(pattern_id, "core_catalog")

    def record_quick_probe_outcome(
        self,
        pattern_id: str,
        *,
        probe_ok: bool,
        nodes: int = 0,
        max_depth: int = 0,
        hit_deadline: bool = False,
    ) -> None:
        """Demote probation patterns with clearly bad quick-probe behavior."""
        if pattern_id.startswith("p12_"):
            return
        if probe_ok:
            if nodes >= 80 or max_depth >= 5:
                return
            return
        if hit_deadline and nodes < 60:
            self.demote_to_reject(pattern_id)
        elif nodes < 30:
            self.demote_to_reject(pattern_id)

    def adaptive_time_cap_for_tier(
        self,
        pattern_id: str,
        default_cap: float,
        *,
        presearch=None,
        grid_size: int = 10,
        max_slot_length: int | None = None,
    ) -> float:
        cap = self.adaptive_time_cap(pattern_id, default_cap)
        if grid_size == 12:
            tier = self.get_catalog_tier_12(
                pattern_id, presearch=presearch, max_slot_length=max_slot_length,
            )
            if tier == "core_catalog":
                return min(default_cap, max(cap, default_cap * 0.95))
            if tier == "probation":
                return min(cap, 6.0)
            return min(cap, 2.5)
        tier = self.get_catalog_tier_10(pattern_id, presearch=presearch)
        if tier == "core_catalog":
            if pattern_id.startswith("p10_core_"):
                return min(default_cap, cap * 1.12)
            return cap
        if tier == "probation":
            return min(cap, 5.0)
        return min(cap, 2.0)

    def adaptive_max_nodes_for_tier(
        self,
        pattern_id: str,
        default_nodes: int,
        *,
        presearch=None,
        grid_size: int = 10,
        max_slot_length: int | None = None,
    ) -> int:
        nodes = self.adaptive_max_nodes(pattern_id, default_nodes)
        if grid_size == 12:
            tier = self.get_catalog_tier_12(
                pattern_id, presearch=presearch, max_slot_length=max_slot_length,
            )
            if tier == "core_catalog":
                return nodes
            if tier == "probation":
                return min(nodes, 4500)
            return min(nodes, 2000)
        tier = self.get_catalog_tier_10(pattern_id, presearch=presearch)
        if tier == "core_catalog":
            if pattern_id.startswith("p10_core_"):
                return int(min(default_nodes, nodes * 1.1))
            return nodes
        if tier == "probation":
            return min(nodes, 4000)
        return min(nodes, 2000)

    def summary(self) -> dict[str, dict]:
        with self._lock:
            out: dict[str, dict] = {}
            for pid, s in self._stats.items():
                out[pid] = {
                    "attempts": s.attempts,
                    "successes": s.successes,
                    "failures": s.failures,
                    "late_failures": s.late_failures,
                    "presearch_rejects": s.presearch_rejects,
                    "uninformative_ac3": s.uninformative_ac3,
                    "avg_fill_s": round(s.avg_fill_seconds, 2),
                    "success_ratio": round(s.success_ratio, 2),
                }
            return out


_TRACKER = PatternStatsTracker()


def get_pattern_stats_tracker() -> PatternStatsTracker:
    return _TRACKER
