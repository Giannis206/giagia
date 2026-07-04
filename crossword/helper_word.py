"""Post-generation helper word selection for player-facing puzzles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from crossword.slots import Direction, Slot, slots_by_cell

if TYPE_CHECKING:
    from crossword.solver import GenerationResult

DirectionLabel = Literal["across", "down"]


@dataclass(frozen=True)
class HelperWordInfo:
    helper_entry_id: int
    helper_word: str
    helper_direction: DirectionLabel
    helper_cells: tuple[tuple[int, int], ...]


def assign_clue_numbers(slots: list[Slot], grid_size: int) -> dict[tuple[int, int], int]:
    """Standard crossword numbering: top-to-bottom, left-to-right word starts."""
    starts = {(slot.row, slot.col) for slot in slots}
    numbers: dict[tuple[int, int], int] = {}
    n = 1
    for row in range(grid_size):
        for col in range(grid_size):
            if (row, col) in starts:
                numbers[(row, col)] = n
                n += 1
    return numbers


def _crossing_count(slot: Slot, cell_slots: dict[tuple[int, int], list[Slot]]) -> int:
    count = 0
    for cell in slot.cells:
        for other in cell_slots.get(cell, ()):
            if other.direction != slot.direction:
                count += 1
                break
    return count


def _select_helper_slot(slots: list[Slot], state) -> Slot:
    cell_slots = slots_by_cell(slots)
    candidates: list[tuple[tuple, Slot]] = []
    for slot in slots:
        if slot.slot_id not in state.assignments:
            continue
        crossings = _crossing_count(slot, cell_slots)
        length_tier = 0 if slot.length >= 5 else 1
        candidates.append(
            ((length_tier, -crossings, -slot.length, slot.slot_id), slot)
        )
    if not candidates:
        raise ValueError("No assigned slots available for helper word selection")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def select_helper_word(result: GenerationResult) -> HelperWordInfo:
    """Pick one solution word as the prefilled helper (deterministic ranking)."""
    slot = _select_helper_slot(result.slots, result.state)
    word = slot.read(result.grid)
    numbers = assign_clue_numbers(result.slots, result.grid.size)
    entry_id = numbers.get((slot.row, slot.col), slot.slot_id)
    return HelperWordInfo(
        helper_entry_id=entry_id,
        helper_word=word,
        helper_direction=slot.direction,
        helper_cells=tuple(slot.cells),
    )


def clue_words_for_player(words: list[str], helper: HelperWordInfo) -> list[str]:
    return sorted(word for word in words if word != helper.helper_word)


def prefilled_letters(result: GenerationResult) -> dict[tuple[int, int], str]:
    if result.helper is None:
        return {}
    letters: dict[tuple[int, int], str] = {}
    for row, col in result.helper.helper_cells:
        letters[(row, col)] = result.grid.get(row, col)
    return letters


def validate_helper_word(result: GenerationResult) -> None:
    """Ensure exactly one valid helper word and that it is omitted from clue words."""
    helper = result.helper
    if helper is None:
        raise ValueError("Puzzle is missing helper word metadata")

    if result.clue_words.count(helper.helper_word) != 0:
        raise ValueError(f"Helper word appears in clue list: {helper.helper_word}")

    solution_words = {
        slot.read(result.grid)
        for slot in result.slots
        if slot.slot_id in result.state.assignments
    }
    if helper.helper_word not in solution_words:
        raise ValueError("Helper word is not part of the solved grid")

    matching = [
        slot
        for slot in result.slots
        if tuple(slot.cells) == helper.helper_cells
        and slot.read(result.grid) == helper.helper_word
    ]
    if len(matching) != 1:
        raise ValueError("Helper word must map to exactly one slot in the solution")

    if len(prefilled_letters(result)) != len(helper.helper_cells):
        raise ValueError("Helper prefilled letter count does not match helper cells")

    if len(result.clue_words) != len(result.words) - 1:
        raise ValueError("Expected exactly one helper word removed from clue list")


def finalize_helper_word(result: GenerationResult) -> GenerationResult:
    """Attach helper metadata and player clue word list after a successful solve."""
    helper = select_helper_word(result)
    result.helper = helper
    result.clue_words = clue_words_for_player(result.words, helper)
    validate_helper_word(result)
    return result
