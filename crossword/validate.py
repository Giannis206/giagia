"""Validation rules for crossword patterns and solutions."""

from __future__ import annotations

from collections import Counter, deque

from crossword.grid import BLACK, WHITE, Grid
from crossword.slots import MIN_SLOT_LENGTH, Slot, extract_slots, slots_by_cell


def validate_pattern(grid: Grid, slots: list[Slot] | None = None) -> None:
    """Validate black/white pattern before filling."""
    if slots is None:
        slots = extract_slots(grid)

    _validate_slot_lengths(slots)
    _validate_intersections(slots)
    _validate_connected_white_cells(grid)
    _validate_checked_cells(grid, slots)
    _validate_no_orphan_letters(grid, slots)


def validate_solution(
    grid: Grid,
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    *,
    allow_reuse: bool = False,
) -> None:
    """Validate a fully filled crossword."""
    validate_pattern(grid, slots)

    used_words: list[str] = []
    for slot in slots:
        word = slot.read(grid)
        if len(word) != slot.length:
            raise ValueError(
                f"Slot {slot.slot_id} ({slot.direction}) has wrong length: "
                f"{len(word)} != {slot.length}"
            )
        if any(ch in (WHITE, BLACK) for ch in word):
            raise ValueError(
                f"Slot {slot.slot_id} ({slot.direction}) contains unfilled cells"
            )
        if word not in dictionary.get(slot.length, set()):
            raise ValueError(
                f"Slot {slot.slot_id} ({slot.direction}) is not a dictionary word: {word}"
            )
        used_words.append(word)

    if not allow_reuse:
        counts = Counter(used_words)
        duplicates = [w for w, n in counts.items() if n > 1]
        if duplicates:
            raise ValueError(f"Duplicate words used: {', '.join(sorted(duplicates))}")

    validate_starting_letter_distribution(used_words)


MAX_STARTING_LETTER_RATIO = 0.40
BIAS_DEBUG_RATIO = 0.35


def starting_letter_stats(words: list[str]) -> dict[str, int]:
    """Count how many words start with each Greek letter."""
    return dict(Counter(w[0] for w in words if w))


def starting_letter_bias_report(
    words: list[str],
    *,
    max_ratio: float = MAX_STARTING_LETTER_RATIO,
    debug_ratio: float = BIAS_DEBUG_RATIO,
) -> dict:
    """Summarize starting-letter distribution for debug / rejection."""
    if not words:
        return {
            "biased": False,
            "debug_flag": False,
            "dominant_letter": "",
            "dominant_ratio": 0.0,
            "distribution": {},
        }
    counts = Counter(w[0] for w in words if w)
    letter, count = counts.most_common(1)[0]
    ratio = count / len(words)
    dist = dict(sorted(counts.items()))
    return {
        "biased": ratio > max_ratio,
        "debug_flag": ratio > debug_ratio,
        "dominant_letter": letter,
        "dominant_ratio": ratio,
        "distribution": dist,
    }


def validate_starting_letter_distribution(
    words: list[str],
    *,
    max_ratio: float = MAX_STARTING_LETTER_RATIO,
) -> None:
    """Reject puzzles where one starting letter dominates (>40% by default)."""
    if not words:
        return
    counts = Counter(w[0] for w in words if w)
    if not counts:
        return
    letter, count = counts.most_common(1)[0]
    ratio = count / len(words)
    if ratio > max_ratio:
        raise ValueError(
            f"Starting letter bias: '{letter}' starts {count}/{len(words)} words ({ratio:.0%})"
        )


def _validate_slot_lengths(slots: list[Slot]) -> None:
    for slot in slots:
        if slot.length < MIN_SLOT_LENGTH:
            raise ValueError(
                f"Slot {slot.slot_id} ({slot.direction}) is too short: {slot.length}"
            )


def _validate_intersections(slots: list[Slot]) -> None:
    cell_slots = slots_by_cell(slots)
    for cell, crossing in cell_slots.items():
        directions = [slot.direction for slot in crossing]
        if directions.count("across") > 1 or directions.count("down") > 1:
            raise ValueError(f"Cell {cell} belongs to multiple slots in same direction")


def _validate_connected_white_cells(grid: Grid) -> None:
    white_cells = [(r, c) for r in range(grid.size) for c in range(grid.size) if grid.is_white(r, c)]
    if not white_cells:
        raise ValueError("Grid has no white cells")

    start = white_cells[0]
    seen = {start}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        r, c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < grid.size and 0 <= nc < grid.size and grid.is_white(nr, nc):
                if (nr, nc) not in seen:
                    seen.add((nr, nc))
                    queue.append((nr, nc))

    if len(seen) != len(white_cells):
        raise ValueError("White cells are not all connected")


def _validate_checked_cells(grid: Grid, slots: list[Slot]) -> None:
    """Every white cell must belong to at least one across and one down slot."""
    cell_slots = slots_by_cell(slots)
    for r in range(grid.size):
        for c in range(grid.size):
            if not grid.is_white(r, c):
                continue
            crossing = cell_slots.get((r, c), [])
            has_across = any(s.direction == "across" for s in crossing)
            has_down = any(s.direction == "down" for s in crossing)
            if not has_across or not has_down:
                raise ValueError(
                    f"White cell ({r}, {c}) is not checked (across={has_across}, down={has_down})"
                )


def _validate_no_orphan_letters(grid: Grid, slots: list[Slot]) -> None:
    """No stray letters outside slots; unfilled cells must be WHITE/EMPTY only."""
    slot_cells = {cell for slot in slots for cell in slot.cells}
    for r in range(grid.size):
        for c in range(grid.size):
            val = grid.get(r, c)
            if val in (BLACK, WHITE):
                continue
            if (r, c) not in slot_cells:
                raise ValueError(f"Orphan letter '{val}' at ({r}, {c}) outside any slot")
