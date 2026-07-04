#!/usr/bin/env python3
"""Sanity tests for normal and easy difficulty modes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.puzzle_hints import finalize_puzzle_hints, prefilled_letters_from_hints, validate_puzzle_hints
from crossword.render import _build_grid_svg
from crossword.solver import CrosswordGenerationError, generate_crossword


def _run(size: int, seed: int, difficulty: str) -> dict:
    result = generate_crossword(data_dir=ROOT / "data", size=size, seed=seed)
    if difficulty == "easy":
        result = finalize_puzzle_hints(result, difficulty="easy")
    else:
        validate_puzzle_hints(result)

    hints = result.puzzle_hints
    letters = prefilled_letters_from_hints(result)
    svg = _build_grid_svg(
        result.grid,
        prefilled_letters=letters,
        primary_helper_cells=set(hints.primary_helper.helper_cells) if hints else set(),
        secondary_helper_cells=(
            set(hints.secondary_helper.helper_cells)
            if hints and hints.secondary_helper
            else set()
        ),
        hint_letter_cells=set(hints.extra_hint_cells) if hints else set(),
        easy_mode=difficulty == "easy",
    )

    info = {
        "size": size,
        "seed": seed,
        "difficulty": difficulty,
        "primary": hints.primary_helper.helper_word if hints else None,
        "secondary": (
            hints.secondary_helper.helper_word
            if hints and hints.secondary_helper
            else None
        ),
        "helper_words": hints.helper_word_count if hints else 1,
        "extra_letters": hints.extra_letter_count if hints else 0,
        "clue_words": len(result.clue_words or []),
        "svg_ok": bool(letters) and any(ch.isalpha() or ord(ch) > 127 for ch in svg),
    }
    return info


def main() -> int:
    cases = [
        (7, 7001, "normal"),
        (10, 88001, "normal"),
        (7, 7002, "easy"),
        (10, 88002, "easy"),
    ]
    print("=== difficulty mode tests ===\n")
    for size, seed, difficulty in cases:
        try:
            info = _run(size, seed, difficulty)
        except CrosswordGenerationError as exc:
            print(f"FAIL {size}x{size} {difficulty} seed={seed}: {exc}")
            return 1

        print(f"{size}x{size} {difficulty} seed={seed}")
        print(f"  primary helper: {info['primary']}")
        if difficulty == "easy":
            print(f"  secondary helper: {info['secondary']}")
            print(f"  helper words: {info['helper_words']}")
            print(f"  extra letters: {info['extra_letters']}")
        print(f"  clue words: {info['clue_words']}")
        print(f"  rendering ok: {info['svg_ok']}")
        print()

        if difficulty == "easy" and info["helper_words"] < 2:
            print("WARN: easy mode expected 2 helper words when possible")
        if not info["svg_ok"]:
            print("FAIL: prefilled letters missing from SVG")
            return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
