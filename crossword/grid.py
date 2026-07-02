"""Grid generation with 180-degree rotational symmetry."""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Optional

BLACK = "#"
WHITE = "."
EMPTY = " "


class Grid:
    """Square crossword grid."""

    def __init__(self, size: int, cells: Optional[list[list[str]]] = None):
        if size < 5 or size % 2 == 0:
            raise ValueError("Grid size must be an odd integer >= 5")
        self.size = size
        if cells is not None:
            self.cells = deepcopy(cells)
        else:
            self.cells = [[WHITE for _ in range(size)] for _ in range(size)]

    def copy(self) -> Grid:
        return Grid(self.size, self.cells)

    def get(self, row: int, col: int) -> str:
        return self.cells[row][col]

    def set(self, row: int, col: int, value: str) -> None:
        self.cells[row][col] = value

    def is_black(self, row: int, col: int) -> bool:
        return self.cells[row][col] == BLACK

    def is_white(self, row: int, col: int) -> bool:
        return self.cells[row][col] != BLACK

    def mirror(self, row: int, col: int) -> tuple[int, int]:
        return self.size - 1 - row, self.size - 1 - col

    def set_symmetric(self, row: int, col: int, value: str) -> None:
        mr, mc = self.mirror(row, col)
        self.cells[row][col] = value
        self.cells[mr][mc] = value

    def black_count(self) -> int:
        return sum(1 for row in self.cells for cell in row if cell == BLACK)

    def white_cell_count(self) -> int:
        return sum(1 for row in self.cells for cell in row if cell != BLACK)

    def filled_letters(self) -> dict[tuple[int, int], str]:
        letters: dict[tuple[int, int], str] = {}
        for r in range(self.size):
            for c in range(self.size):
                val = self.cells[r][c]
                if val not in (BLACK, WHITE, EMPTY):
                    letters[(r, c)] = val
        return letters

    def apply_letters(self, letters: dict[tuple[int, int], str]) -> None:
        for (r, c), letter in letters.items():
            if self.is_white(r, c):
                self.cells[r][c] = letter

    def clear_letters(self) -> None:
        for r in range(self.size):
            for c in range(self.size):
                if self.is_white(r, c):
                    self.cells[r][c] = WHITE


def _symmetric_positions(size: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for r in range(size):
        for c in range(size):
            mr, mc = size - 1 - r, size - 1 - c
            if (r, c) <= (mr, mc):
                positions.append((r, c))
    return positions


def _pattern_is_valid(grid: Grid) -> bool:
    from crossword.slots import extract_slots
    from crossword.validate import validate_pattern

    slots = extract_slots(grid)
    if not slots:
        return False
    try:
        validate_pattern(grid, slots)
        return True
    except ValueError:
        return False


def generate_symmetric_pattern(
    size: int = 13,
    *,
    rng: random.Random,
    black_ratio: float = 0.17,
    max_attempts: int = 300,
) -> Grid:
    """Create a rotationally symmetric black/white pattern."""
    positions = _symmetric_positions(size)
    target_blacks = int(size * size * black_ratio)
    min_blacks = max(4, target_blacks - 4)

    for _ in range(max_attempts):
        grid = Grid(size)
        rng.shuffle(positions)

        for row, col in positions:
            if grid.black_count() >= target_blacks:
                break
            if grid.is_black(row, col):
                continue

            trial = grid.copy()
            trial.set_symmetric(row, col, BLACK)
            if _pattern_is_valid(trial):
                grid = trial

        if grid.black_count() >= min_blacks and _pattern_is_valid(grid):
            return grid

    raise RuntimeError(
        f"Failed to generate a valid symmetric pattern after {max_attempts} attempts"
    )
