"""Slot extraction from crossword grids."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from crossword.grid import Grid

Direction = Literal["across", "down"]
MIN_SLOT_LENGTH = 3


@dataclass(frozen=True)
class Slot:
    """A horizontal or vertical word slot in the grid."""

    slot_id: int
    direction: Direction
    row: int
    col: int
    length: int

    @property
    def cells(self) -> list[tuple[int, int]]:
        coords: list[tuple[int, int]] = []
        dr, dc = (0, 1) if self.direction == "across" else (1, 0)
        for i in range(self.length):
            coords.append((self.row + dr * i, self.col + dc * i))
        return coords

    def read(self, grid: Grid) -> str:
        return "".join(grid.get(r, c) for r, c in self.cells)


def extract_slots(grid: Grid) -> list[Slot]:
    """Extract all across and down slots with length >= MIN_SLOT_LENGTH."""
    slots: list[Slot] = []
    slot_id = 1
    size = grid.size

    for row in range(size):
        col = 0
        while col < size:
            if grid.is_white(row, col) and (col == 0 or grid.is_black(row, col - 1)):
                length = 0
                while col + length < size and grid.is_white(row, col + length):
                    length += 1
                if length >= MIN_SLOT_LENGTH:
                    slots.append(
                        Slot(slot_id, "across", row, col, length)
                    )
                    slot_id += 1
                col += max(length, 1)
            else:
                col += 1

    for col in range(size):
        row = 0
        while row < size:
            if grid.is_white(row, col) and (row == 0 or grid.is_black(row - 1, col)):
                length = 0
                while row + length < size and grid.is_white(row + length, col):
                    length += 1
                if length >= MIN_SLOT_LENGTH:
                    slots.append(
                        Slot(slot_id, "down", row, col, length)
                    )
                    slot_id += 1
                row += max(length, 1)
            else:
                row += 1

    return slots


def slots_by_cell(slots: list[Slot]) -> dict[tuple[int, int], list[Slot]]:
    """Map each grid cell to the slots that pass through it."""
    mapping: dict[tuple[int, int], list[Slot]] = {}
    for slot in slots:
        for cell in slot.cells:
            mapping.setdefault(cell, []).append(slot)
    return mapping
