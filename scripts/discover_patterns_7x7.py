#!/usr/bin/env python3
"""Discover and rank valid 7x7 symmetric crossword patterns.

Usage (from repo root):
    python scripts/discover_patterns_7x7.py
    python scripts/discover_patterns_7x7.py --seeds 15000 --top 20

Reads nothing from disk; searches via generate_symmetric_pattern(7).
Prints top patterns by histogram-aware score (same formula as crossword.pattern7).
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.grid import BLACK, generate_symmetric_pattern
from crossword.pattern7 import evaluate_pattern_7, score_pattern_histogram
from crossword.slots import extract_slots
from crossword.validate import validate_pattern


def _fingerprint(grid) -> tuple:
    return tuple(
        tuple(1 if grid.get(r, c) == BLACK else 0 for c in range(7))
        for r in range(7)
    )


def discover(*, max_seed: int, black_ratio: float) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for seed in range(max_seed):
        rng = random.Random(seed)
        try:
            grid = generate_symmetric_pattern(
                7, rng=rng, black_ratio=black_ratio, max_attempts=150
            )
        except RuntimeError:
            continue
        fp = _fingerprint(grid)
        if fp in seen:
            continue
        slots = extract_slots(grid)
        try:
            validate_pattern(grid, slots)
        except ValueError:
            continue
        lengths = [slot.length for slot in slots]
        blacks = grid.black_count()
        ev = evaluate_pattern_7(lengths, black_square_count=blacks, strict=False)
        if not ev.accepted:
            continue
        seen[fp] = {
            "seed": seed,
            "score": ev.score,
            "blacks": blacks,
            "slots": len(slots),
            "histogram": ev.histogram,
            "max_slot": ev.max_slot_length,
        }
    return sorted(seen.values(), key=lambda row: -row["score"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover ranked 7x7 patterns")
    parser.add_argument("--seeds", type=int, default=15000, help="Search seeds 0..N-1")
    parser.add_argument("--top", type=int, default=20, help="Rows to print")
    parser.add_argument("--ratio", type=float, default=0.17, help="Target black ratio")
    args = parser.parse_args(argv)

    rows = discover(max_seed=args.seeds, black_ratio=args.ratio)
    print(f"Valid unique patterns: {len(rows)}\n")
    print(f"{'rank':<5} {'seed':<6} {'score':<7} {'blacks':<7} {'slots':<6} histogram")
    for rank, row in enumerate(rows[: args.top], start=1):
        print(
            f"{rank:<5} {row['seed']:<6} {row['score']:<7.2f} "
            f"{row['blacks']:<7} {row['slots']:<6} {row['histogram']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
