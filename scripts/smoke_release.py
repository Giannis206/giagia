#!/usr/bin/env python3
"""Quick release smoke tests — no full benchmark."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.difficulty import parse_difficulty
from crossword.puzzle_hints import finalize_puzzle_hints, prefilled_letters_from_hints, validate_puzzle_hints
from crossword.render import render_printable_html
from crossword.solver import CrosswordGenerationError, generate_crossword

CASES = [
    (7, 7001, "normal"),
    (7, 7002, "easy"),
    (10, 88001, "normal"),
    (10, 88002, "easy"),
    (12, 12001, "normal"),
]

OUT = ROOT / "output" / "smoke"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    data_dir = ROOT / "data"
    ok = 0

    for size, seed, difficulty in CASES:
        label = f"{size}x{size}_{difficulty}"
        try:
            result = generate_crossword(data_dir=data_dir, size=size, seed=seed)
            diff = parse_difficulty(difficulty)
            if diff == "easy":
                result = finalize_puzzle_hints(result, difficulty="easy")
            else:
                validate_puzzle_hints(result)
            path = OUT / f"smoke_{label}.html"
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
            assert path.exists() and len(html) > 500
            assert "crossword-svg" in html
            assert f"difficulty-{difficulty}" in html
            hints = result.puzzle_hints
            if diff == "easy":
                assert hints is not None and hints.helper_word_count >= 1
            else:
                assert hints is not None and hints.primary_helper.helper_word
            print(f"OK {label} pattern={result.pattern_id} helper={hints.primary_helper.helper_word}")
            ok += 1
        except CrosswordGenerationError as exc:
            print(f"FAIL {label}: {exc}")

    print(f"\nSmoke: {ok}/{len(CASES)}")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
