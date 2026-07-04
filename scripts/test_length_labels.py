#!/usr/bin/env python3
"""Manual check: start cells show word lengths (not clue ordinals)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.puzzle_hints import validate_puzzle_hints
from crossword.render import assign_start_cell_length_labels, render_printable_html
from crossword.slots import extract_slots
from crossword.solver import generate_crossword

CASES = [(7, 7001), (10, 88001)]


def main() -> int:
    out = ROOT / "output" / "length_labels"
    out.mkdir(parents=True, exist_ok=True)

    for size, seed in CASES:
        result = generate_crossword(data_dir=ROOT / "data", size=size, seed=seed)
        validate_puzzle_hints(result)
        slots = extract_slots(result.grid)
        labels = assign_start_cell_length_labels(slots)
        dual = [f"({r},{c})={v}" for (r, c), v in sorted(labels.items()) if "/" in v]
        path = out / f"len_{size}x{size}.html"
        render_printable_html(
            result.grid,
            result.clue_words or result.words,
            path,
            project_root=ROOT,
            helper=result.helper,
            puzzle_hints=result.puzzle_hints,
            difficulty="normal",
        )
        svg = path.read_text(encoding="utf-8")
        assert "start-length-label" in svg
        assert re.search(r'start-length-label">[3-9]', svg) or re.search(
            r'start-length-label">\d+/\d+', svg
        )
        print(f"OK {size}x{size} seed={seed} dual_starts={dual[:6]}")
        if not dual:
            print(f"  (no dual-start cells in this puzzle)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
