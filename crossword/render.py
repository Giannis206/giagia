"""HTML rendering for printable crossword output."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from crossword.grid import BLACK, Grid
from crossword.slots import Slot


def _build_grid_rows(grid: Grid, *, show_letters: bool = False) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for r in range(grid.size):
        row: list[dict] = []
        for c in range(grid.size):
            val = grid.get(r, c)
            is_black = val == BLACK
            letter = ""
            if not is_black and show_letters and val not in (".", " "):
                letter = val
            row.append({"is_black": is_black, "letter": letter})
        rows.append(row)
    return rows


def _group_words_by_length(words: list[str]) -> list[dict]:
    groups: dict[int, list[str]] = defaultdict(list)
    for word in words:
        groups[len(word)].append(word)
    return [
        {"length": length, "words": sorted(group)}
        for length, group in sorted(groups.items())
    ]


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
    cell_mm = _cell_size_mm(grid.size)

    html = template.render(
        title=title,
        css_href=css_rel,
        grid_rows=_build_grid_rows(grid, show_letters=show_letters),
        grid_size=grid.size,
        cell_mm=cell_mm,
        word_groups=_group_words_by_length(words),
        total_words=len(words),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _cell_size_mm(grid_size: int) -> float:
    """Fit grid on A4 with minimal margins (~8mm each side, ~281mm usable height)."""
    usable = 274.0
    return round(usable / grid_size, 2)
