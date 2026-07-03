"""7x7 pattern scoring — delegates to generalized pattern_scoring."""

from __future__ import annotations

from crossword.pattern_scoring import (
    evaluate_pattern_layout,
    score_pattern_histogram,
)
from crossword.slot_policy import PatternEvaluation


def evaluate_pattern_7(
    slot_lengths: list[int],
    *,
    black_square_count: int,
    strict: bool = False,
) -> PatternEvaluation:
    return evaluate_pattern_layout(
        slot_lengths,
        grid_size=7,
        black_square_count=black_square_count,
        strict=strict,
    )


def pattern7_selection_weight(
    *,
    layout_score: float,
    slot_histogram: dict[int, int] | None,
    total_slot_count: int,
    tier: str,
    tracker_weight: float = 1.0,
) -> float:
    """Selection weight from layout score and runtime stats."""
    weight = max(0.5, layout_score) * tracker_weight
    if tier == "primary":
        weight *= 1.15
    hist = slot_histogram or {}
    mid = sum(hist.get(length, 0) for length in (4, 5, 6))
    if mid >= 8:
        weight *= 1.1
    threes = hist.get(3, 0)
    if total_slot_count and threes / total_slot_count > 0.35:
        weight *= 0.85
    return max(0.2, weight)

