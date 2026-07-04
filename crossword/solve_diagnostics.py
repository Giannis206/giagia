"""Structured diagnostics for crossword fill attempts and pre-search rejection."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from crossword.domain_propagation import (
    bottleneck_slots,
    check_arc_consistency,
    enforce_node_consistency,
)
from crossword.slots import Slot, extract_slots
from crossword.slot_policy import slot_length_histogram

FailureClass = Literal[
    "success",
    "ac3_fail",
    "presearch_reject",
    "early_dead_end",
    "late_nodes",
    "late_time",
    "unknown",
]


@dataclass
class SolveTrace:
    """Mutable trace collected during backtracking."""

    nodes: int = 0
    backtracks: int = 0
    max_depth: int = 0
    deepest_failure_depth: int = 0
    assigned_at_deepest_failure: int = 0
    restarts_used: int = 0
    hit_max_nodes: bool = False
    hit_deadline: bool = False

    def merge_restart(self, other: SolveTrace) -> None:
        self.nodes += other.nodes
        self.backtracks += other.backtracks
        self.max_depth = max(self.max_depth, other.max_depth)
        self.deepest_failure_depth = max(
            self.deepest_failure_depth, other.deepest_failure_depth
        )
        if other.deepest_failure_depth >= self.deepest_failure_depth:
            self.assigned_at_deepest_failure = other.assigned_at_deepest_failure
        self.hit_max_nodes = self.hit_max_nodes or other.hit_max_nodes
        self.hit_deadline = self.hit_deadline or other.hit_deadline
        self.restarts_used += 1


@dataclass
class PresearchAnalysis:
    pattern_id: str
    grid_size: int
    slot_histogram: dict[int, int]
    slot_count: int
    ac3_ok: bool
    ac3_domain_collapse: bool
    initial_min_domain: int
    initial_median_domain: float
    initial_max_domain: int
    post_ac3_min_domain: int
    post_ac3_median_domain: float
    post_ac3_max_domain: int
    bottleneck_slot_ids: list[int]
    bottleneck_domain_sizes: list[int]
    short_narrow_slots: int
    crossing_letter_bottlenecks: int
    estimated_difficulty: float
    estimated_fillability: float
    ac3_prune_ratio: float = 1.0
    ac3_is_uninformative: bool = False
    per_slot_initial_domains: dict[int, int] = field(default_factory=dict)
    reject: bool = False
    reject_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PatternAttemptDiagnostic:
    pattern_id: str
    grid_size: int
    success: bool
    elapsed_seconds: float
    time_cap_seconds: float
    max_nodes_budget: int
    slot_histogram: dict[int, int]
    presearch: PresearchAnalysis | None = None
    trace: SolveTrace | None = None
    failure_class: FailureClass = "unknown"
    is_late_fail: bool = False
    presearch_rejected: bool = False
    ac3_uninformative: bool = False
    quick_probe_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "pattern_id": self.pattern_id,
            "grid_size": self.grid_size,
            "success": self.success,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "time_cap_seconds": self.time_cap_seconds,
            "max_nodes_budget": self.max_nodes_budget,
            "slot_histogram": self.slot_histogram,
            "failure_class": self.failure_class,
            "is_late_fail": self.is_late_fail,
            "presearch_rejected": self.presearch_rejected,
            "ac3_uninformative": self.ac3_uninformative,
            "quick_probe_failed": self.quick_probe_failed,
        }
        if self.presearch is not None:
            out["presearch"] = self.presearch.to_dict()
        if self.trace is not None:
            out["trace"] = asdict(self.trace)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _domain_stats(domains: dict[int, set[str]]) -> tuple[int, float, int]:
    sizes = [len(d) for d in domains.values() if d]
    if not sizes:
        return 0, 0.0, 0
    return min(sizes), statistics.median(sizes), max(sizes)


def _estimate_difficulty(min_domain: int, median_domain: float) -> float:
    if min_domain <= 0:
        return 10.0
    return max(0.0, 8.0 / max(1, min_domain) + 2.0 / max(1.0, median_domain / 100.0))


def _estimate_fillability(
    *,
    ac3_ok: bool,
    min_domain: int,
    median_domain: float,
    short_narrow: int,
    slot_count: int,
    crossing_bottlenecks: int,
) -> float:
    if not ac3_ok or min_domain <= 0:
        return 0.0
    base = min(50.0, min_domain * 0.4 + median_domain * 0.08)
    narrow_ratio = short_narrow / max(1, slot_count)
    base -= narrow_ratio * 12.0
    base -= crossing_bottlenecks * 1.5
    return max(0.0, round(base, 3))


def _count_short_narrow_slots(
    slots: list[Slot],
    domains: dict[int, set[str]],
    *,
    short_max_len: int,
    narrow_threshold: int,
) -> int:
    return sum(
        1
        for slot in slots
        if slot.length <= short_max_len
        and 0 < len(domains.get(slot.slot_id, set())) < narrow_threshold
    )


def _count_crossing_letter_bottlenecks(
    slots: list[Slot],
    domains: dict[int, set[str]],
    *,
    letter_threshold: int = 6,
) -> int:
    """Crossings where both incident slots have very few letters at the crossing position."""
    from crossword.slots import slots_by_cell

    cell_slots = slots_by_cell(slots)
    count = 0
    for cell, crossing in cell_slots.items():
        if len(crossing) != 2:
            continue
        a, b = crossing
        if a.direction == b.direction:
            continue
        pos_a = a.cells.index(cell)
        pos_b = b.cells.index(cell)
        letters_a = {w[pos_a] for w in domains.get(a.slot_id, set())}
        letters_b = {w[pos_b] for w in domains.get(b.slot_id, set())}
        shared = letters_a & letters_b
        if not shared:
            count += 1
        elif len(shared) <= letter_threshold and (
            len(letters_a) <= letter_threshold or len(letters_b) <= letter_threshold
        ):
            count += 1
    return count


def quick_fill_probe(
    grid,
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
    rng: random.Random,
    *,
    grid_size: int,
    max_nodes: int = 800,
    time_cap: float = 1.5,
) -> tuple[bool, SolveTrace]:
    """Short single-restart solve when AC-3 domains are uninformative."""
    import time

    from crossword.solver import CrosswordSolver

    trace = SolveTrace()
    deadline = time.monotonic() + time_cap
    solver = CrosswordSolver(
        grid.copy(),
        slots,
        dictionary,
        word_scores=word_scores,
        rng=random.Random(rng.randint(0, 2**31 - 1)),
        deadline=deadline,
        grid_size=grid_size,
    )
    state = solver.solve(max_nodes=max_nodes, trace=trace)
    return state is not None, trace


def ac3_is_uninformative(analysis: PresearchAnalysis) -> bool:
    """AC-3 passed but did not meaningfully prune the hardest slots."""
    if not analysis.ac3_ok:
        return False
    if analysis.post_ac3_min_domain < 100:
        return False
    if analysis.initial_min_domain > 0:
        prune_ratio = analysis.post_ac3_min_domain / analysis.initial_min_domain
        if prune_ratio >= 0.97:
            return True
    if (
        analysis.bottleneck_domain_sizes
        and analysis.bottleneck_domain_sizes[0] >= 200
        and analysis.slot_histogram.get(3, 0) >= 4
    ):
        return True
    return False


def analyze_presearch(
    *,
    pattern_id: str,
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    grid_size: int,
) -> PresearchAnalysis:
    hist = slot_length_histogram([s.length for s in slots])
    initial = enforce_node_consistency(slots, dictionary)
    init_min, init_med, init_max = _domain_stats(initial)

    ac3_ok, post_domains, zero_slots = check_arc_consistency(slots, dictionary)
    collapse = bool(zero_slots) or (
        init_min > 0 and post_domains and min(len(d) for d in post_domains.values() if d) < init_min * 0.15
    )
    post_min, post_med, post_max = _domain_stats(post_domains if ac3_ok else initial)
    bottlenecks = bottleneck_slots(post_domains if ac3_ok else initial)
    bottleneck_sizes = [
        len(post_domains.get(sid, set())) for sid in bottlenecks
    ]

    short_max = 4 if grid_size <= 8 else 5
    narrow_thr = 18 if grid_size <= 8 else (22 if grid_size <= 10 else 28)
    short_narrow = _count_short_narrow_slots(
        slots, post_domains if ac3_ok else initial,
        short_max_len=short_max, narrow_threshold=narrow_thr,
    )
    crossing_bn = _count_crossing_letter_bottlenecks(
        slots, post_domains if ac3_ok else initial,
        letter_threshold=7 if grid_size <= 10 else 8,
    )
    difficulty = _estimate_difficulty(post_min, post_med)
    fillability = _estimate_fillability(
        ac3_ok=ac3_ok,
        min_domain=post_min,
        median_domain=post_med,
        short_narrow=short_narrow,
        slot_count=len(slots),
        crossing_bottlenecks=crossing_bn,
    )

    per_slot = {slot.slot_id: len(initial.get(slot.slot_id, set())) for slot in slots}
    prune_ratio = post_min / init_min if init_min > 0 else 1.0

    analysis = PresearchAnalysis(
        pattern_id=pattern_id,
        grid_size=grid_size,
        slot_histogram=hist,
        slot_count=len(slots),
        ac3_ok=ac3_ok,
        ac3_domain_collapse=collapse,
        initial_min_domain=init_min,
        initial_median_domain=round(init_med, 2),
        initial_max_domain=init_max,
        post_ac3_min_domain=post_min,
        post_ac3_median_domain=round(post_med, 2),
        post_ac3_max_domain=post_max,
        bottleneck_slot_ids=bottlenecks,
        bottleneck_domain_sizes=bottleneck_sizes,
        short_narrow_slots=short_narrow,
        crossing_letter_bottlenecks=crossing_bn,
        estimated_difficulty=round(difficulty, 3),
        estimated_fillability=fillability,
        ac3_prune_ratio=round(prune_ratio, 4),
    )
    analysis.ac3_is_uninformative = ac3_is_uninformative(analysis)
    if analysis.ac3_is_uninformative:
        # Length-3 slot pressure: many 3-letter slots compete for ~829 words.
        three_count = hist.get(3, 0)
        if grid_size >= 10 and three_count >= 4 and three_count / max(1, len(slots)) >= 0.12:
            analysis.estimated_difficulty = max(
                analysis.estimated_difficulty,
                2.5 + three_count * 0.15,
            )
            analysis.estimated_fillability = min(
                analysis.estimated_fillability,
                max(5.0, 22.0 - three_count * 1.2),
            )
    analysis.per_slot_initial_domains = per_slot
    reject, reason = should_presearch_reject(analysis)
    analysis.reject = reject
    analysis.reject_reason = reason
    return analysis


def should_apply_static_presearch_reject(
    analysis: PresearchAnalysis,
    *,
    pattern_id: str,
    pattern_entry: object | None,
) -> bool:
    """Static reject before solve; uninformative-AC3 rules vary by pattern source."""
    if not analysis.reject:
        return False
    if not analysis.reject_reason.startswith("uninformative_ac3"):
        return True
    if pattern_id.startswith("random_seed"):
        return False
    size = analysis.grid_size
    if size == 12:
        return False
    if size == 10 and pattern_entry is not None:
        return True
    return False


def should_presearch_reject(analysis: PresearchAnalysis) -> tuple[bool, str]:
    """Data-driven pre-search rejection (AC-3 may pass but fill is unlikely)."""
    if not analysis.ac3_ok:
        return True, "ac3_inconsistent"

    size = analysis.grid_size
    min_dom = analysis.post_ac3_min_domain
    med_dom = analysis.post_ac3_median_domain
    fill = analysis.estimated_fillability

    # Very tight minimum domain relative to grid size.
    min_floor = {10: 6, 12: 5}.get(size, 4)
    if min_dom < min_floor:
        return True, f"min_domain_{min_dom}_below_{min_floor}"

    # Many short slots with narrow domains — classic late-fail signature.
    short_ratio = analysis.short_narrow_slots / max(1, analysis.slot_count)
    if size >= 10 and short_ratio >= 0.28 and min_dom < 12:
        return True, f"short_narrow_ratio_{short_ratio:.2f}"

    # Crossing letter bottlenecks with low median domain.
    if size >= 10 and analysis.crossing_letter_bottlenecks >= 4 and med_dom < 80:
        return True, f"crossing_bottlenecks_{analysis.crossing_letter_bottlenecks}"

    # Low estimated fillability despite AC-3.
    fill_floor = {10: 8.0, 12: 6.0}.get(size, 5.0)
    if fill < fill_floor and min_dom < 10:
        return True, f"low_fillability_{fill:.1f}"

    # AC-3 collapsed domains aggressively (hard search ahead).
    if analysis.ac3_domain_collapse and min_dom < 10:
        return True, "ac3_aggressive_collapse"

    # Uninformative AC-3 + high difficulty estimate (from 3-letter slot pressure).
    if analysis.ac3_is_uninformative and size >= 10:
        if analysis.estimated_difficulty >= 3.0 and analysis.estimated_fillability < 18.0:
            return True, (
                f"uninformative_ac3_diff_{analysis.estimated_difficulty:.1f}"
                f"_fill_{analysis.estimated_fillability:.1f}"
            )

    return False, ""


def classify_failure(
    *,
    success: bool,
    presearch: PresearchAnalysis | None,
    trace: SolveTrace | None,
    elapsed: float,
    time_cap: float,
    max_nodes: int,
    presearch_rejected: bool,
) -> tuple[FailureClass, bool]:
    if success:
        return "success", False
    if presearch_rejected:
        return "presearch_reject", False
    if presearch is not None and not presearch.ac3_ok:
        return "ac3_fail", False

    nodes = trace.nodes if trace else 0
    depth = trace.deepest_failure_depth if trace else 0
    assigned = trace.assigned_at_deepest_failure if trace else 0
    node_ratio = nodes / max(1, max_nodes)
    time_ratio = elapsed / max(0.1, time_cap)

    late_by_nodes = node_ratio >= 0.55 or trace.hit_max_nodes if trace else False
    late_by_time = time_ratio >= 0.65 or (trace.hit_deadline if trace else False)
    early = (
        nodes < max_nodes * 0.12
        and depth <= 4
        and assigned <= 3
        and not late_by_time
    )

    if early:
        return "early_dead_end", False
    if late_by_nodes or late_by_time:
        return "late_nodes" if late_by_nodes else "late_time", True
    if nodes > max_nodes * 0.35:
        return "late_nodes", True
    return "unknown", False


def analyze_pattern_from_grid(
    *,
    pattern_id: str,
    grid,
    dictionary: dict[int, set[str]],
) -> PresearchAnalysis:
    slots = extract_slots(grid)
    return analyze_presearch(
        pattern_id=pattern_id,
        slots=slots,
        dictionary=dictionary,
        grid_size=grid.size,
    )
