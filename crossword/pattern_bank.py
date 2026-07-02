"""Load pre-validated puzzle patterns from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from crossword.grid import BLACK, Grid, WHITE


def grid_from_pattern_rows(size: int, rows: list[str]) -> Grid:
    cells = [
        [BLACK if ch == "#" else WHITE for ch in row]
        for row in rows
    ]
    return Grid(size, cells)


def load_puzzle_bank(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
