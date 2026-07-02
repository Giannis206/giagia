"""Fast render smoke-test (pattern only, no solver)."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.grid import generate_symmetric_pattern
from crossword.render import render_printable_html, _build_grid_svg, PRINT_GRID_MM

for size in (7, 8, 10, 12, 15):
    grid = generate_symmetric_pattern(size, rng=random.Random(size))
    svg = _build_grid_svg(grid)
    assert "crossword-svg" in svg
    assert svg.count("<line") == 2 * (size + 1)
    path = ROOT / "output" / f"test_{size}.html"
    render_printable_html(
        grid,
        ["ΛΕΞΗ"] * size,
        path,
        project_root=ROOT,
        css_href="/static/print.css",
    )
    html = path.read_text(encoding="utf-8")
    pages = html.count('class="page ')
    print(f"OK {size}x{size} pages={pages} grid_mm={PRINT_GRID_MM}")
