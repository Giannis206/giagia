#!/usr/bin/env python3
"""Generate sample puzzles and verify large-print HTML output."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.difficulty import parse_difficulty
from main import do_generate, OUTPUT_DIR

CASES = [
    (7, 7001, "normal"),
    (7, 7002, "easy"),
    (10, 88001, "normal"),
    (10, 88002, "easy"),
]


def main() -> int:
    out_dir = OUTPUT_DIR / "large_print_samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    for size, seed, difficulty in CASES:
        path = out_dir / f"crossword_{size}x{size}_{difficulty}.html"
        # do_generate writes to default HTML_PATH; copy after each run
        from crossword.render import render_printable_html
        from crossword.puzzle_hints import finalize_puzzle_hints, prefilled_letters_from_hints, validate_puzzle_hints
        from crossword.solver import generate_crossword
        from main import DATA_DIR

        result = generate_crossword(data_dir=DATA_DIR, size=size, seed=seed)
        diff = parse_difficulty(difficulty)
        if diff == "easy":
            result = finalize_puzzle_hints(result, difficulty="easy")
        else:
            validate_puzzle_hints(result)
        render_printable_html(
            result.grid,
            result.clue_words or result.words,
            path,
            project_root=ROOT,
            helper=result.helper,
            puzzle_hints=result.puzzle_hints,
            prefilled_letters=prefilled_letters_from_hints(result),
            difficulty=diff,
        )
        html = path.read_text(encoding="utf-8")
        assert "difficulty-" + difficulty in html
        assert "font-size:" in html or "words-title" in html
        assert re.search(r'font-size="[5-9][0-9]\.', html), "SVG letter font too small"
        print(f"OK {size}x{size} {difficulty} -> {path.name}")

    print("\nLarge-print samples written to", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
