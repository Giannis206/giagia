#!/usr/bin/env python3
"""Smoke test for prefilled helper word feature."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.helper_word import prefilled_letters, validate_helper_word
from crossword.render import _build_grid_svg
from crossword.solver import CrosswordGenerationError, generate_crossword


def main() -> int:
    data_dir = ROOT / "data"
    size = 10
    seed = 88001

    try:
        result = generate_crossword(data_dir=data_dir, size=size, seed=seed)
    except CrosswordGenerationError as exc:
        print(f"FAIL: generation failed: {exc}")
        return 1

    validate_helper_word(result)
    helper = result.helper
    assert helper is not None

    letters = prefilled_letters(result)
    if len(letters) != len(helper.helper_cells):
        print("FAIL: prefilled letter count mismatch")
        return 1

    if helper.helper_word in (result.clue_words or []):
        print(f"FAIL: helper word {helper.helper_word!r} still in clue list")
        return 1

    svg = _build_grid_svg(
        result.grid,
        prefilled_letters=letters,
        helper_cells=set(helper.helper_cells),
    )
    if helper.helper_word[0] not in svg:
        print("FAIL: helper letters not rendered in grid SVG")
        return 1

    direction = "Across" if helper.helper_direction == "across" else "Down"
    print(f"OK size={size} seed={seed}")
    print(f"helper_word={helper.helper_word}")
    print(f"helper_direction={direction}")
    print(f"helper_entry_id={helper.helper_entry_id}")
    print(f"clue_words={len(result.clue_words or [])} total_words={len(result.words)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
