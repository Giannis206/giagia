"""Size-aware pattern layout scoring and evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from crossword.slot_policy import (
    PatternEvaluation,
    evaluate_pattern,
    get_slot_policy,
    slot_length_histogram,
)


@dataclass(frozen=True)
class SizeScoringConfig:
    grid_size: int
    min_length: int = 3
    short_max: int = 3
    mid_lengths: tuple[int, ...] = (4, 5, 6)
    long_min: int = 7
    max_short_ratio: float = 0.45
    min_mid_slots: int = 2
    min_black: int = 5
    max_black: int = 20
    strict_min_score: float = 6.0


def _config_for_size(grid_size: int) -> SizeScoringConfig:
    if grid_size == 7:
        return SizeScoringConfig(
            grid_size=7,
            mid_lengths=(4, 5, 6),
            max_short_ratio=0.45,
            min_mid_slots=2,
            min_black=6,
            max_black=12,
            strict_min_score=8.0,
        )
    if grid_size == 8:
        return SizeScoringConfig(
            grid_size=8,
            mid_lengths=(4, 5, 6),
            max_short_ratio=0.42,
            min_mid_slots=3,
            min_black=7,
            max_black=14,
            strict_min_score=7.0,
        )
    if grid_size == 10:
        return SizeScoringConfig(
            grid_size=10,
            mid_lengths=(4, 5, 6, 7, 8),
            max_short_ratio=0.38,
            min_mid_slots=4,
            min_black=10,
            max_black=20,
            strict_min_score=6.5,
        )
    if grid_size == 12:
        return SizeScoringConfig(
            grid_size=12,
            mid_lengths=(4, 5, 6, 7, 8, 9, 10),
            max_short_ratio=0.35,
            min_mid_slots=6,
            min_black=12,
            max_black=28,
            strict_min_score=5.0,
        )
    return SizeScoringConfig(grid_size=grid_size)


def score_pattern_histogram(
    histogram: dict[int, int],
    *,
    grid_size: int,
    total_slots: int,
    black_square_count: int,
) -> float:
    """Reward healthy slot-length mix; penalize short-slot dominance."""
    if not total_slots:
        return 0.0
    cfg = _config_for_size(grid_size)
    hist = histogram
    cells = grid_size * grid_size
    density = black_square_count / cells

    short = sum(hist.get(length, 0) for length in range(cfg.min_length, cfg.short_max + 1))
    mid = sum(hist.get(length, 0) for length in cfg.mid_lengths if length <= grid_size)
    long_slots = sum(
        hist.get(length, 0) for length in range(cfg.long_min, grid_size + 1)
    )
    variety = len(hist)

    score = mid / total_slots * (5.0 + grid_size * 0.15)
    score += variety * (1.2 + grid_size * 0.05)
    score += min(mid, grid_size) * 0.15

    score -= max(0.0, short / total_slots - 0.28) * (8.0 + grid_size * 0.2)
    if mid < cfg.min_mid_slots:
        score -= 8.0
    if long_slots / total_slots > 0.45:
        score -= 4.0

    if black_square_count < cfg.min_black or black_square_count > cfg.max_black:
        score -= 3.0
    if density < 0.12 or density > 0.28:
        score -= 2.0

    max_len = max(hist) if hist else 0
    if max_len > grid_size:
        score -= 20.0
    elif max_len > grid_size - 1:
        score -= 1.5

    return score


def evaluate_pattern_layout(
    slot_lengths: list[int],
    *,
    grid_size: int,
    black_square_count: int,
    strict: bool = False,
    use_slot_policy: bool = False,
) -> PatternEvaluation:
    """Accept/reject and score a pattern layout for any grid size."""
    hist = slot_length_histogram(slot_lengths)
    if not slot_lengths:
        return PatternEvaluation(False, "no_slots", 0.0, hist, 0)

    total = len(slot_lengths)
    max_len = max(slot_lengths)
    cfg = _config_for_size(grid_size)
    score = score_pattern_histogram(
        hist,
        grid_size=grid_size,
        total_slots=total,
        black_square_count=black_square_count,
    )

    short_ratio = sum(
        hist.get(length, 0) for length in range(cfg.min_length, cfg.short_max + 1)
    ) / total
    mid = sum(hist.get(length, 0) for length in cfg.mid_lengths if length <= grid_size)

    if max_len > grid_size:
        return PatternEvaluation(
            False, f"max_slot_length={max_len}>{grid_size}", score, hist, max_len
        )
    if short_ratio > cfg.max_short_ratio:
        return PatternEvaluation(
            False, f"too_many_short={short_ratio:.0%}", score, hist, max_len
        )
    if mid < cfg.min_mid_slots:
        return PatternEvaluation(
            False, f"no_mid_diversity={mid}", score, hist, max_len
        )

    if use_slot_policy and grid_size == 12:
        policy_ev = evaluate_pattern(
            get_slot_policy(12), slot_lengths, strict_long=strict
        )
        if not policy_ev.accepted:
            return policy_ev
        score = max(score, policy_ev.score)

    if strict and score < cfg.strict_min_score:
        return PatternEvaluation(False, "low_layout_score", score, hist, max_len)

    return PatternEvaluation(True, "ok", score, hist, max_len)


def block_density(grid_size: int, black_square_count: int) -> float:
    return black_square_count / (grid_size * grid_size)
