"""Per-grid-size slot length policies and pattern evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class SlotLengthPolicy:
    grid_size: int
    max_slot_length: int
    prefer_min: int = 3
    prefer_max: int = 10
    allow_length_max: int = 12
    max_long_slot_ratio: float = 0.22
    max_twelve_letter_slots: int = 4


@dataclass(frozen=True)
class PatternEvaluation:
    accepted: bool
    reason: str
    score: float
    histogram: dict[int, int]
    max_slot_length: int


_DEFAULT = SlotLengthPolicy(
    grid_size=0,
    max_slot_length=15,
    prefer_max=12,
    allow_length_max=15,
    max_long_slot_ratio=1.0,
    max_twelve_letter_slots=99,
)


def get_slot_policy(grid_size: int) -> SlotLengthPolicy:
    if grid_size == 12:
        return SlotLengthPolicy(
            grid_size=12,
            max_slot_length=12,
            prefer_min=3,
            prefer_max=10,
            allow_length_max=12,
            max_long_slot_ratio=0.22,
            max_twelve_letter_slots=4,
        )
    return SlotLengthPolicy(
        grid_size=grid_size,
        max_slot_length=grid_size,
        prefer_min=3,
        prefer_max=grid_size,
        allow_length_max=grid_size,
        max_long_slot_ratio=0.35,
        max_twelve_letter_slots=99,
    )


def slot_length_histogram(slot_lengths: list[int]) -> dict[int, int]:
    return dict(sorted(Counter(slot_lengths).items()))


def evaluate_pattern(
    policy: SlotLengthPolicy,
    slot_lengths: list[int],
    *,
    strict_long: bool = False,
) -> PatternEvaluation:
    """Score and accept/reject a pattern by slot-length policy."""
    hist = slot_length_histogram(slot_lengths)
    if not slot_lengths:
        return PatternEvaluation(False, "no_slots", 0.0, hist, 0)

    max_len = max(slot_lengths)
    total = len(slot_lengths)

    if max_len > policy.max_slot_length:
        return PatternEvaluation(
            False,
            f"max_slot_length={max_len}>{policy.max_slot_length}",
            0.0,
            hist,
            max_len,
        )

    long_11_12 = sum(hist.get(length, 0) for length in range(11, policy.allow_length_max + 1))
    twelve_count = hist.get(12, 0)

    if strict_long and long_11_12 / total > policy.max_long_slot_ratio:
        return PatternEvaluation(
            False,
            f"too_many_long_slots={long_11_12}/{total}",
            0.0,
            hist,
            max_len,
        )

    if twelve_count > policy.max_twelve_letter_slots:
        return PatternEvaluation(
            False,
            f"too_many_12_letter_slots={twelve_count}",
            0.0,
            hist,
            max_len,
        )

    score = _pattern_score(policy, hist, total, max_len)

    if strict_long and score < 0:
        return PatternEvaluation(False, "low_balance_score", score, hist, max_len)

    return PatternEvaluation(True, "ok", score, hist, max_len)


def _pattern_score(
    policy: SlotLengthPolicy,
    hist: dict[int, int],
    total: int,
    max_len: int,
) -> float:
    mid = sum(hist.get(length, 0) for length in range(4, 9))
    prefer = sum(
        hist.get(length, 0)
        for length in range(policy.prefer_min, policy.prefer_max + 1)
    )
    long_slots = sum(hist.get(length, 0) for length in range(11, policy.allow_length_max + 1))
    very_long = sum(hist.get(length, 0) for length in range(13, 20))

    score = prefer / total * 5.0 + mid / total * 3.0
    score += len(hist) / max(1, min(10, total)) * 2.0
    score -= max(0.0, hist.get(3, 0) / total - 0.42) * 6.0
    score -= long_slots / total * 4.0
    score -= max(0, max_len - policy.prefer_max) * 1.5
    score -= very_long * 10.0
    return score


def slot_selection_key(
    policy: SlotLengthPolicy,
    *,
    domain_size: int,
    crossing_count: int,
    slot_length: int,
) -> tuple:
    """MRV key: smaller domain first; penalize very long slots on 12x12."""
    if policy.grid_size == 12:
        length_penalty = 0
        if slot_length >= 11:
            length_penalty = (slot_length - 10) * 30
        elif slot_length > 8:
            length_penalty = (slot_length - 8) * 6
        elif 3 <= slot_length <= 8:
            length_penalty = -4
        return (domain_size, length_penalty, -crossing_count, slot_length)

    return (domain_size, -crossing_count, -slot_length)
