"""Fillability probing for crossword block patterns."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from crossword.domain_propagation import (
    bottleneck_slots,
    check_arc_consistency,
    enforce_node_consistency,
)
from crossword.grid import Grid
from crossword.slots import Slot, extract_slots


@dataclass
class FillabilityResult:
    zero_domain_detected: bool = False
    ac3_ok: bool = False
    estimated_difficulty: float = 0.0
    probe_success_rate: float = 0.0
    avg_probe_time: float = 0.0
    bottleneck_slots: list[int] = field(default_factory=list)
    min_domain_size: int = 0
    fillability_score: float = 0.0
    combined_score: float = 0.0

    @property
    def passed(self) -> bool:
        """AC-3 consistent with non-empty domains (minimum bar for catalog)."""
        return self.ac3_ok and not self.zero_domain_detected and self.min_domain_size >= 3

    @property
    def probe_verified(self) -> bool:
        return self.probe_success_rate > 0


def _estimate_difficulty(domains: dict[int, set[str]]) -> float:
    if not domains:
        return 10.0
    sizes = [len(dom) for dom in domains.values() if dom]
    if not sizes:
        return 10.0
    minimum = min(sizes)
    avg = sum(sizes) / len(sizes)
    # Lower minimum domain => harder pattern.
    return max(0.0, 8.0 / max(1, minimum) + 2.0 / max(1.0, avg / 100.0))


def _score_fillability(
    *,
    ac3_ok: bool,
    min_domain: int,
    estimated_difficulty: float,
    probe_success_rate: float,
    avg_probe_time: float,
    layout_score: float = 0.0,
) -> tuple[float, float]:
    if not ac3_ok:
        return 0.0, layout_score * 0.2
    base = min(50.0, min_domain * 0.45)
    base += probe_success_rate * 18.0
    base += max(0.0, 6.0 - avg_probe_time) * 0.8
    base -= estimated_difficulty * 0.6
    fill_score = max(0.0, base)
    combined = fill_score * 0.65 + max(0.0, layout_score) * 0.35
    return fill_score, combined


def _run_probe_fills(
    grid: Grid,
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
    rng: random.Random,
    *,
    probe_count: int,
    time_cap: float,
) -> tuple[float, float]:
    if probe_count <= 0:
        return 0.0, 0.0

    from crossword.solver import CrosswordSolver

    successes = 0
    elapsed_total = 0.0
    for _ in range(probe_count):
        probe_rng = random.Random(rng.randint(0, 2**31 - 1))
        deadline = time.monotonic() + time_cap
        solver = CrosswordSolver(
            grid.copy(),
            slots,
            dictionary,
            word_scores=word_scores,
            rng=probe_rng,
            deadline=deadline,
            grid_size=grid.size,
        )
        t0 = time.monotonic()
        state = solver.solve_with_restarts(
            restarts=2,
            max_nodes=6_000,
            deadline=deadline,
        )
        elapsed = time.monotonic() - t0
        elapsed_total += elapsed
        if state is not None:
            successes += 1
    return successes / probe_count, elapsed_total / probe_count


def fillability_probe(
    grid: Grid,
    dictionary: dict[int, set[str]],
    *,
    word_scores: dict[str, int] | None = None,
    layout_score: float = 0.0,
    probe_count: int = 2,
    probe_time_cap: float = 4.0,
    rng: random.Random | None = None,
) -> FillabilityResult:
    """Evaluate whether a pattern is likely fillable with the given lexicon."""
    slots = extract_slots(grid)
    rng = rng or random.Random(0)
    word_scores = word_scores or {}

    domains = enforce_node_consistency(slots, dictionary)
    zero_early = [sid for sid, dom in domains.items() if not dom]
    if zero_early:
        return FillabilityResult(
            zero_domain_detected=True,
            ac3_ok=False,
            estimated_difficulty=10.0,
            bottleneck_slots=zero_early[:5],
            fillability_score=0.0,
            combined_score=layout_score * 0.2,
        )

    ac3_ok, domains, zero_slots = check_arc_consistency(slots, dictionary)
    min_domain = min((len(dom) for dom in domains.values() if dom), default=0)
    bottlenecks = bottleneck_slots(domains) if ac3_ok else zero_slots[:5]
    difficulty = _estimate_difficulty(domains)

    probe_rate = 0.0
    avg_probe = 0.0
    if ac3_ok and probe_count > 0:
        probe_rate, avg_probe = _run_probe_fills(
            grid,
            slots,
            dictionary,
            word_scores,
            rng,
            probe_count=probe_count,
            time_cap=probe_time_cap,
        )

    fill_score, combined = _score_fillability(
        ac3_ok=ac3_ok,
        min_domain=min_domain,
        estimated_difficulty=difficulty,
        probe_success_rate=probe_rate,
        avg_probe_time=avg_probe,
        layout_score=layout_score,
    )

    return FillabilityResult(
        zero_domain_detected=bool(zero_slots),
        ac3_ok=ac3_ok,
        estimated_difficulty=round(difficulty, 3),
        probe_success_rate=round(probe_rate, 3),
        avg_probe_time=round(avg_probe, 3),
        bottleneck_slots=bottlenecks,
        min_domain_size=min_domain,
        fillability_score=round(fill_score, 3),
        combined_score=round(combined, 3),
    )
