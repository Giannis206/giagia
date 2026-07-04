#!/usr/bin/env python3
"""Sanity check: crossings-based helper word for all supported catalog sizes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.helper_word import (
    _CROSSING_WEIGHT,
    _FREQUENCY_WEIGHT,
    _LENGTH_WEIGHT,
    _POSITION_WEIGHT,
    prefilled_letters,
    score_all_entries,
    select_helper_entry,
    validate_helper_word,
)
from crossword.solver import CrosswordGenerationError, generate_crossword

SIZES_SEEDS = {
    7: 7001,
    8: 8001,
    10: 88001,
    12: 12001,
}


def _direction_label(direction: str) -> str:
    return "Across" if direction == "across" else "Down"


def _rationale(entry, grid_size: int) -> str:
    parts = [
        f"{entry.crossings} crossings lock neighbouring words",
        f"length {entry.slot.length}",
    ]
    if entry.position_score >= 0.6:
        parts.append("centrally placed anchor")
    if entry.frequency_score >= 0.5:
        parts.append("relatively common dictionary word")
    if grid_size <= 7 and entry.slot.length >= 4:
        parts.append("good length for 7x7")
    if grid_size >= 12 and entry.slot.length >= 6:
        parts.append("substantial word for 12x12")
    return "; ".join(parts)


def main() -> int:
    data_dir = ROOT / "data"
    print(
        "Formula: score = "
        f"{_LENGTH_WEIGHT}*length + {_CROSSING_WEIGHT}*crossings + "
        f"{_POSITION_WEIGHT}*position + {_FREQUENCY_WEIGHT}*frequency"
    )
    print()

    summary: list[tuple[int, str, str, float, int]] = []

    for size, seed in SIZES_SEEDS.items():
        try:
            result = generate_crossword(data_dir=data_dir, size=size, seed=seed)
        except CrosswordGenerationError as exc:
            print(f"FAIL {size}x{size} seed={seed}: {exc}")
            return 1

        validate_helper_word(result)
        entry = select_helper_entry(result, word_scores=result.word_scores)
        helper = result.helper
        assert helper is not None

        if helper.helper_word in (result.clue_words or []):
            print(f"FAIL {size}x{size}: helper still in clue list")
            return 1

        letters = prefilled_letters(result)
        if len(letters) != len(helper.helper_cells):
            print(f"FAIL {size}x{size}: prefilled letter mismatch")
            return 1

        direction = _direction_label(helper.helper_direction)
        rationale = _rationale(entry, size)

        print(f"=== {size}x{size} seed={seed} ===")
        print(f"  helper: {helper.helper_word} ({direction}, clue #{helper.helper_entry_id})")
        print(f"  score: {entry.total_score:.2f}")
        print(f"  crossings: {entry.crossings}")
        print(f"  breakdown: length={entry.length_score:.1f} "
              f"cross={entry.crossing_score:.0f} "
              f"pos={entry.position_score:.2f} "
              f"freq={entry.frequency_score:.2f}")
        print(f"  why: {rationale}")

        top3 = sorted(
            score_all_entries(result, word_scores=result.word_scores),
            key=lambda e: (-e.total_score, e.clue_number),
        )[:3]
        alts = ", ".join(
            f"{e.word}({e.total_score:.1f},x{e.crossings})" for e in top3
        )
        print(f"  top candidates: {alts}")
        print()

        summary.append((size, helper.helper_word, direction, entry.total_score, entry.crossings))

    print("=== Summary ===")
    for size, word, direction, score, crossings in summary:
        print(f"  {size}x{size}: {word} ({direction}) score={score:.2f} crossings={crossings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
