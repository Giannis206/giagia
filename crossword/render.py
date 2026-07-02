"""HTML rendering for printable crossword output."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from crossword.grid import BLACK, Grid

# A4 portrait printable area with 5mm @page margins (210 - 10 = 200mm wide)
PRINT_GRID_MM = 200.0
CELL_UNITS = 100
LINE_WIDTH = 8


def _build_grid_svg(grid: Grid, *, show_letters: bool = False) -> str:
    """Sharp SVG grid — ideal for print/PDF (no table border-collapse artifacts)."""
    size = grid.size
    span = size * CELL_UNITS
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {span} {span}" '
        f'class="crossword-svg" '
        f'role="img" aria-label="Πλέγμα σταυρόλεξου" '
        f'shape-rendering="geometricPrecision">',
        f'<rect x="0" y="0" width="{span}" height="{span}" fill="#ffffff"/>',
    ]

    for row in range(size):
        for col in range(size):
            if grid.is_black(row, col):
                x = col * CELL_UNITS
                y = row * CELL_UNITS
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL_UNITS}" height="{CELL_UNITS}" '
                    f'fill="#000000" stroke="none"/>'
                )

    for index in range(size + 1):
        pos = index * CELL_UNITS
        parts.append(
            f'<line x1="{pos}" y1="0" x2="{pos}" y2="{span}" '
            f'stroke="#000000" stroke-width="{LINE_WIDTH}" stroke-linecap="square"/>'
        )
        parts.append(
            f'<line x1="0" y1="{pos}" x2="{span}" y2="{pos}" '
            f'stroke="#000000" stroke-width="{LINE_WIDTH}" stroke-linecap="square"/>'
        )

    if show_letters:
        font_size = CELL_UNITS * 0.58
        for row in range(size):
            for col in range(size):
                val = grid.get(row, col)
                if val in (BLACK, ".", " "):
                    continue
                cx = col * CELL_UNITS + CELL_UNITS / 2
                cy = row * CELL_UNITS + CELL_UNITS / 2
                parts.append(
                    f'<text x="{cx:.1f}" y="{cy:.1f}" '
                    f'text-anchor="middle" dominant-baseline="central" '
                    f'font-family="Segoe UI, Arial, sans-serif" '
                    f'font-size="{font_size:.1f}" font-weight="700" fill="#000000">'
                    f"{val}</text>"
                )

    parts.append("</svg>")
    return "\n".join(parts)


def _group_words_by_length(words: list[str]) -> list[dict]:
    groups: dict[int, list[str]] = defaultdict(list)
    for word in words:
        groups[len(word)].append(word)
    return [
        {"length": length, "words": sorted(group)}
        for length, group in sorted(groups.items())
    ]


def _words_layout_class(total_words: int, grid_size: int) -> str:
    if total_words > 55 or (grid_size >= 12 and total_words > 38):
        return "words-dense"
    if total_words > 30 or (grid_size >= 10 and total_words > 24):
        return "words-medium"
    return "words-sparse"


def render_printable_html(
    grid: Grid,
    words: list[str],
    output_path: Path,
    *,
    project_root: Path,
    title: str = "Σταυρόλεξο",
    show_letters: bool = False,
    css_href: str | None = None,
) -> Path:
    templates_dir = project_root / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("print.html")

    css_rel = css_href if css_href is not None else "../static/print.css"

    html = template.render(
        title=title,
        css_href=css_rel,
        grid_svg=_build_grid_svg(grid, show_letters=show_letters),
        grid_size=grid.size,
        grid_mm=PRINT_GRID_MM,
        word_groups=_group_words_by_length(words),
        total_words=len(words),
        words_layout_class=_words_layout_class(len(words), grid.size),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
