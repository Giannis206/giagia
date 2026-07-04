"""HTML rendering for printable crossword output."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

from crossword.grid import BLACK, Grid
from crossword.slots import Slot, extract_slots

if TYPE_CHECKING:
    from crossword.helper_word import HelperWordInfo
    from crossword.puzzle_hints import PuzzleHints

# A4 portrait printable area with 5mm @page margins (210 - 10 = 200mm wide)
PRINT_GRID_MM = 186.0
CELL_UNITS = 100
LINE_WIDTH = 9

# SVG font sizes as fraction of cell (large-print: letters ≥ ~18pt when printed)
_LETTER_RATIO_BY_SIZE = {
    7: 0.64,
    8: 0.62,
    10: 0.60,
    12: 0.58,
    15: 0.55,
}
_NUMBER_RATIO_BY_SIZE = {
    7: 0.28,
    8: 0.27,
    10: 0.26,
    12: 0.25,
    15: 0.24,
}
# Compact length hints in word-start cells (smaller than main letters)
_LENGTH_LABEL_RATIO_BY_SIZE = {
    7: 0.20,
    8: 0.19,
    10: 0.18,
    12: 0.17,
    15: 0.16,
}

# High-contrast text on soft helper backgrounds (print-safe)
PRIMARY_HELPER_FILL = "#f0ebe3"
SECONDARY_HELPER_FILL = "#e8eef5"
HINT_LETTER_FILL = "#f5f0e6"
INK_COLOR = "#111111"


def _svg_font_sizes(grid_size: int) -> tuple[float, float, float]:
    """Letter font, legacy number font, and compact start-cell length label font."""
    letter_ratio = _LETTER_RATIO_BY_SIZE.get(grid_size, 0.58)
    number_ratio = _NUMBER_RATIO_BY_SIZE.get(grid_size, 0.25)
    label_ratio = _LENGTH_LABEL_RATIO_BY_SIZE.get(grid_size, 0.18)
    return (
        CELL_UNITS * letter_ratio,
        CELL_UNITS * number_ratio,
        CELL_UNITS * label_ratio,
    )


def assign_start_cell_length_labels(slots: list[Slot]) -> dict[tuple[int, int], str]:
    """Render-only labels: word length at each across/down start cell."""
    by_start: dict[tuple[int, int], dict[str, int]] = {}
    for slot in slots:
        key = (slot.row, slot.col)
        by_start.setdefault(key, {})[slot.direction] = slot.length

    labels: dict[tuple[int, int], str] = {}
    for (row, col), lengths in by_start.items():
        across = lengths.get("across")
        down = lengths.get("down")
        if across is not None and down is not None:
            labels[(row, col)] = f"{across}/{down}"
        elif across is not None:
            labels[(row, col)] = str(across)
        elif down is not None:
            labels[(row, col)] = str(down)
    return labels


def _label_font_size(base: float, label: str) -> float:
    """Shrink font slightly for wider across/down notation (e.g. 10/12)."""
    n = len(label)
    if n <= 2:
        return base
    if n <= 4:
        return base * 0.9
    return base * 0.8


def _build_grid_svg(
    grid: Grid,
    *,
    show_letters: bool = False,
    prefilled_letters: dict[tuple[int, int], str] | None = None,
    primary_helper_cells: set[tuple[int, int]] | None = None,
    secondary_helper_cells: set[tuple[int, int]] | None = None,
    hint_letter_cells: set[tuple[int, int]] | None = None,
    start_cell_labels: dict[tuple[int, int], str] | None = None,
    easy_mode: bool = False,
) -> str:
    """Sharp SVG grid — ideal for print/PDF (no table border-collapse artifacts)."""
    size = grid.size
    span = size * CELL_UNITS
    prefilled = prefilled_letters or {}
    primary = primary_helper_cells or set()
    secondary = secondary_helper_cells or set()
    hints_only = hint_letter_cells or set()
    labels = start_cell_labels or {}
    letter_font, _, label_font_base = _svg_font_sizes(size)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {span} {span}" '
        f'class="crossword-svg{" easy-mode" if easy_mode else ""}" '
        f'role="img" aria-label="Πλέγμα σταυρόλεξου" '
        f'shape-rendering="geometricPrecision">',
        f'<rect x="0" y="0" width="{span}" height="{span}" fill="#fffef8"/>',
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

    for row in range(size):
        for col in range(size):
            if not grid.is_white(row, col):
                continue
            cell = (row, col)
            fill = None
            css_class = ""
            if cell in primary:
                fill = PRIMARY_HELPER_FILL
                css_class = "helper-cell helper-primary"
            elif cell in secondary:
                fill = SECONDARY_HELPER_FILL
                css_class = "helper-cell helper-secondary"
            elif cell in hints_only:
                fill = HINT_LETTER_FILL
                css_class = "hint-letter-cell"
            if fill is None:
                continue
            x = col * CELL_UNITS
            y = row * CELL_UNITS
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL_UNITS}" height="{CELL_UNITS}" '
                f'fill="{fill}" stroke="none" class="{css_class}"/>'
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

    for (row, col), label in labels.items():
        label_font = _label_font_size(label_font_base, label)
        x = col * CELL_UNITS + CELL_UNITS * 0.10
        y = row * CELL_UNITS + CELL_UNITS * 0.18
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" '
            f'text-anchor="start" dominant-baseline="hanging" '
            f'font-family="Segoe UI, Arial, Helvetica, sans-serif" '
            f'font-size="{label_font:.1f}" font-weight="600" fill="#333333" '
            f'class="start-length-label">'
            f"{label}</text>"
        )

    for row in range(size):
        for col in range(size):
            val = grid.get(row, col)
            if val in (BLACK, ".", " "):
                continue
            show = show_letters or (row, col) in prefilled
            if not show:
                continue
            cell = (row, col)
            cx = col * CELL_UNITS + CELL_UNITS / 2
            cy = row * CELL_UNITS + CELL_UNITS / 2 + 1
            if cell in primary:
                letter_class = "helper-letter helper-primary-letter"
            elif cell in secondary:
                letter_class = "helper-letter helper-secondary-letter"
            elif cell in hints_only:
                letter_class = "hint-letter"
            else:
                letter_class = ""
            parts.append(
                f'<text x="{cx:.1f}" y="{cy:.1f}" '
                f'text-anchor="middle" dominant-baseline="central" '
                f'font-family="Segoe UI, Arial, Helvetica, sans-serif" '
                f'font-size="{letter_font:.1f}" font-weight="700" fill="{INK_COLOR}"'
                f'{" class=\"" + letter_class + "\"" if letter_class else ""}>'
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
    helper: HelperWordInfo | None = None,
    puzzle_hints: PuzzleHints | None = None,
    prefilled_letters: dict[tuple[int, int], str] | None = None,
    difficulty: str = "normal",
) -> Path:
    templates_dir = project_root / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("print.html")

    css_rel = css_href if css_href is not None else "../static/print.css"
    slots = extract_slots(grid)
    start_labels = assign_start_cell_length_labels(slots)

    easy_mode = difficulty == "easy"
    primary_cells: set[tuple[int, int]] = set()
    secondary_cells: set[tuple[int, int]] = set()
    hint_cells: set[tuple[int, int]] = set()

    if puzzle_hints is not None:
        primary_cells = set(puzzle_hints.primary_helper.helper_cells)
        if puzzle_hints.secondary_helper is not None:
            secondary_cells = set(puzzle_hints.secondary_helper.helper_cells) - primary_cells
        hint_cells = set(puzzle_hints.extra_hint_cells) - primary_cells - secondary_cells
    elif helper is not None:
        primary_cells = set(helper.helper_cells)

    html = template.render(
        title=title,
        css_href=css_rel,
        grid_svg=_build_grid_svg(
            grid,
            show_letters=show_letters,
            prefilled_letters=prefilled_letters,
            primary_helper_cells=primary_cells,
            secondary_helper_cells=secondary_cells,
            hint_letter_cells=hint_cells,
            start_cell_labels=start_labels,
            easy_mode=easy_mode,
        ),
        grid_size=grid.size,
        grid_mm=PRINT_GRID_MM,
        word_groups=_group_words_by_length(words),
        total_words=len(words),
        words_layout_class=_words_layout_class(len(words), grid.size),
        helper=helper,
        puzzle_hints=puzzle_hints,
        difficulty=difficulty,
        easy_mode=easy_mode,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
