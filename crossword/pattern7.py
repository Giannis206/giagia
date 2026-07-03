"""7x7 pattern scoring, filtering, and catalog metadata."""

from __future__ import annotations

from crossword.slot_policy import PatternEvaluation, slot_length_histogram

MAX_THREE_RATIO = 0.45
MIN_MID_SLOTS = 2


def score_pattern_histogram(
    histogram: dict[int, int],
    *,
    total_slots: int,
    black_square_count: int,
) -> float:
    """Score a 7x7 layout: reward 4/5/6-letter slots and length variety."""
    if not total_slots:
        return 0.0
    hist = histogram
    mid = sum(hist.get(length, 0) for length in (4, 5, 6))
    threes = hist.get(3, 0)
    sevens = hist.get(7, 0)
    variety = len(hist)
    score = mid / total_slots * 6.0 + variety * 1.8
    score += min(hist.get(4, 0), 2) * 0.4
    score += min(hist.get(5, 0), 2) * 0.5
    score += min(hist.get(6, 0), 4) * 0.3
    score -= max(0.0, threes / total_slots - 0.30) * 10.0
    score -= max(0.0, sevens / total_slots - 0.30) * 5.0
    if mid == 0:
        score -= 10.0
    if hist.get(4, 0) + hist.get(5, 0) + hist.get(6, 0) < MIN_MID_SLOTS:
        score -= 6.0
    if black_square_count < 6 or black_square_count > 12:
        score -= 3.0
    return score


def evaluate_pattern_7(
    slot_lengths: list[int],
    *,
    black_square_count: int,
    strict: bool = False,
) -> PatternEvaluation:
    """Accept/reject and score a 7x7 pattern by slot-length distribution."""
    hist = slot_length_histogram(slot_lengths)
    if not slot_lengths:
        return PatternEvaluation(False, "no_slots", 0.0, hist, 0)

    total = len(slot_lengths)
    max_len = max(slot_lengths)
    threes = hist.get(3, 0) / total
    mid = sum(hist.get(length, 0) for length in (4, 5, 6))
    score = score_pattern_histogram(hist, total_slots=total, black_square_count=black_square_count)

    if threes > MAX_THREE_RATIO:
        return PatternEvaluation(False, f"too_many_3_letter={threes:.0%}", score, hist, max_len)
    if mid < MIN_MID_SLOTS:
        return PatternEvaluation(False, f"no_mid_length_diversity={mid}", score, hist, max_len)
    if strict and score < 8.0:
        return PatternEvaluation(False, "low_layout_score", score, hist, max_len)

    return PatternEvaluation(True, "ok", score, hist, max_len)


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

