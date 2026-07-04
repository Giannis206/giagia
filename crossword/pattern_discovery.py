"""Offline discovery of valid symmetric crossword patterns."""

from __future__ import annotations

import random
from typing import Any

from crossword.domain_propagation import check_arc_consistency
from crossword.grid import BLACK, generate_symmetric_pattern
from crossword.pattern_scoring import (
    block_density,
    evaluate_pattern_layout,
    score_pattern_histogram,
)
from crossword.slots import extract_slots
from crossword.slot_policy import slot_length_histogram
from crossword.validate import validate_pattern


def pattern_fingerprint(grid, size: int) -> tuple:
    return tuple(
        tuple(1 if grid.get(r, c) == BLACK else 0 for c in range(size))
        for r in range(size)
    )


def grid_to_pattern(grid, size: int) -> list[list[int]]:
    return [
        [1 if grid.get(r, c) == BLACK else 0 for c in range(size)]
        for r in range(size)
    ]


def discover_patterns(
    size: int,
    *,
    max_seed: int = 10_000,
    black_ratios: tuple[float, ...] | None = None,
    max_attempts_per_seed: int = 120,
    dictionary: dict[int, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Search seeds for unique valid symmetric patterns."""
    if black_ratios is None:
        if size <= 7:
            black_ratios = (0.16, 0.18, 0.20)
        elif size <= 8:
            black_ratios = (0.14, 0.16, 0.18)
        elif size <= 10:
            black_ratios = (0.13, 0.15, 0.17)
        else:
            black_ratios = (0.14, 0.16, 0.18, 0.20)

    seen: dict[tuple, dict[str, Any]] = {}
    use_policy = size == 12

    for seed in range(max_seed):
        for ratio in black_ratios:
            rng = random.Random(seed * 17 + int(ratio * 1000))
            try:
                grid = generate_symmetric_pattern(
                    size,
                    rng=rng,
                    black_ratio=ratio,
                    max_attempts=max_attempts_per_seed,
                )
            except RuntimeError:
                continue
            fp = pattern_fingerprint(grid, size)
            if fp in seen:
                continue
            slots = extract_slots(grid)
            try:
                validate_pattern(grid, slots)
            except ValueError:
                continue
            lengths = [slot.length for slot in slots]
            blacks = grid.black_count()
            ev = evaluate_pattern_layout(
                lengths,
                grid_size=size,
                black_square_count=blacks,
                strict=False,
                use_slot_policy=use_policy,
            )
            if not ev.accepted:
                continue
            if dictionary is not None:
                ac3_ok, _, _ = check_arc_consistency(slots, dictionary)
                if not ac3_ok:
                    continue
            hist = slot_length_histogram(lengths)
            short = sum(hist.get(l, 0) for l in (3,))
            mid = sum(hist.get(l, 0) for l in range(4, min(9, size + 1)))
            long_slots = sum(hist.get(l, 0) for l in range(max(7, size - 2), size + 1))
            seen[fp] = {
                "seed": seed,
                "ratio": ratio,
                "score": ev.score,
                "grid": grid_to_pattern(grid, size),
                "black_count": blacks,
                "block_density": round(block_density(size, blacks), 4),
                "histogram": hist,
                "total_slots": len(slots),
                "short_slots": short,
                "mid_slots": mid,
                "long_slots": long_slots,
                "max_slot_length": ev.max_slot_length,
            }

    return sorted(seen.values(), key=lambda row: -row["score"])


def tier_split(
    rows: list[dict[str, Any]],
    *,
    primary_count: int,
    fallback_count: int,
) -> list[dict[str, Any]]:
    """Assign primary/fallback tiers by score rank."""
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        tier = "primary" if idx < primary_count else "fallback"
        if idx >= primary_count + fallback_count:
            break
        out.append({**row, "tier": tier})
    return out
