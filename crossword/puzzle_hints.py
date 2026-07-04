"""Post-solve puzzle hints: helper words and easy-mode extras."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from crossword.difficulty import DifficultyMode
from crossword.helper_word import (
    EntryScore,
    HelperWordInfo,
    _entry_sort_key,
    assign_clue_numbers,
    clue_words_for_player,
    score_all_entries,
    select_helper_word,
    validate_helper_word,
)
from crossword.slots import slots_by_cell

if TYPE_CHECKING:
    from crossword.solver import GenerationResult

DirectionLabel = Literal["across", "down"]

_EXTRA_LETTERS_BY_SIZE: dict[int, int] = {
    7: 2,
    8: 2,
    10: 3,
    12: 3,
}


@dataclass(frozen=True)
class PuzzleHints:
    """Player-facing hints derived from the solved grid."""

    difficulty: DifficultyMode
    primary_helper: HelperWordInfo
    secondary_helper: HelperWordInfo | None = None
    extra_hint_cells: tuple[tuple[int, int], ...] = ()

    @property
    def helper_word_count(self) -> int:
        return 1 + (1 if self.secondary_helper is not None else 0)

    @property
    def extra_letter_count(self) -> int:
        return len(self.extra_hint_cells)


def _entry_to_helper(entry: EntryScore) -> HelperWordInfo:
    slot = entry.slot
    return HelperWordInfo(
        helper_entry_id=entry.clue_number,
        helper_word=entry.word,
        helper_direction=slot.direction,
        helper_cells=tuple(slot.cells),
    )


def _cells_overlap(a: tuple[tuple[int, int], ...], b: tuple[tuple[int, int], ...]) -> bool:
    return bool(set(a) & set(b))


def select_secondary_helper(
    result: GenerationResult,
    primary: HelperWordInfo,
    *,
    word_scores: dict[str, int] | None = None,
) -> EntryScore | None:
    """Second-best helper, preferably opposite direction and non-overlapping."""
    scored = score_all_entries(result, word_scores=word_scores)
    primary_cells = set(primary.helper_cells)
    candidates = [
        entry
        for entry in scored
        if entry.word != primary.helper_word
        and not _cells_overlap(tuple(entry.slot.cells), primary.helper_cells)
    ]
    if not candidates:
        return None

    opposite = [
        entry for entry in candidates
        if entry.slot.direction != primary.helper_direction
    ]
    pool = opposite if opposite else candidates
    return min(pool, key=_entry_sort_key)


def select_extra_hint_cells(
    result: GenerationResult,
    occupied: set[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """A few high-degree cells (many crossings) with correct solution letters."""
    count = _EXTRA_LETTERS_BY_SIZE.get(result.grid.size, 2)
    cell_slots = slots_by_cell(result.slots)
    ranked: list[tuple[tuple, tuple[int, int]]] = []

    for slot in result.slots:
        if slot.slot_id not in result.state.assignments:
            continue
        for row, col in slot.cells:
            if (row, col) in occupied:
                continue
            if not result.grid.is_white(row, col):
                continue
            degree = len(cell_slots.get((row, col), ()))
            ranked.append(((-degree, row, col), (row, col)))

    ranked.sort(key=lambda item: item[0])
    chosen: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for _, cell in ranked:
        if cell in seen:
            continue
        seen.add(cell)
        chosen.append(cell)
        if len(chosen) >= count:
            break
    return tuple(chosen)


def prefilled_letters_from_hints(result: GenerationResult) -> dict[tuple[int, int], str]:
    letters: dict[tuple[int, int], str] = {}
    hints = result.puzzle_hints
    if hints is None:
        if result.helper is not None:
            for row, col in result.helper.helper_cells:
                letters[(row, col)] = result.grid.get(row, col)
        return letters

    for row, col in hints.primary_helper.helper_cells:
        letters[(row, col)] = result.grid.get(row, col)
    if hints.secondary_helper is not None:
        for row, col in hints.secondary_helper.helper_cells:
            letters[(row, col)] = result.grid.get(row, col)
    for row, col in hints.extra_hint_cells:
        letters[(row, col)] = result.grid.get(row, col)
    return letters


def clue_words_for_hints(result: GenerationResult) -> list[str]:
    hints = result.puzzle_hints
    if hints is None:
        return result.clue_words or result.words

    exclude = {hints.primary_helper.helper_word}
    if hints.secondary_helper is not None:
        exclude.add(hints.secondary_helper.helper_word)
    return sorted(word for word in result.words if word not in exclude)


def validate_puzzle_hints(result: GenerationResult) -> None:
    hints = result.puzzle_hints
    if hints is None:
        validate_helper_word(result)
        return

    primary = hints.primary_helper
    result.helper = primary

    clue_words = clue_words_for_hints(result)
    if primary.helper_word in clue_words:
        raise ValueError("Primary helper word appears in clue list")
    if hints.secondary_helper is not None:
        if hints.secondary_helper.helper_word in clue_words:
            raise ValueError("Secondary helper word appears in clue list")
        if hints.secondary_helper.helper_word == primary.helper_word:
            raise ValueError("Secondary helper must differ from primary")

    expected_clues = len(result.words) - hints.helper_word_count
    if len(clue_words) != expected_clues:
        raise ValueError(
            f"Expected {expected_clues} clue words, got {len(clue_words)}"
        )

    solution_words = {
        slot.read(result.grid)
        for slot in result.slots
        if slot.slot_id in result.state.assignments
    }
    for helper in (primary, hints.secondary_helper):
        if helper is None:
            continue
        if helper.helper_word not in solution_words:
            raise ValueError(f"Helper {helper.helper_word!r} not in solution")

    letters = prefilled_letters_from_hints(result)
    for (row, col), letter in letters.items():
        if result.grid.get(row, col) != letter:
            raise ValueError(f"Prefilled letter mismatch at ({row}, {col})")

    if hints.difficulty == "easy" and hints.secondary_helper is None:
        if len(score_all_entries(result, word_scores=result.word_scores)) < 2:
            pass  # tiny grids may only have one eligible entry
        # secondary is optional when no second slot qualifies


def finalize_puzzle_hints(
    result: GenerationResult,
    *,
    difficulty: DifficultyMode = "normal",
) -> GenerationResult:
    """Attach helper metadata after solve (does not affect solver)."""
    primary = select_helper_word(result, word_scores=result.word_scores)
    secondary: HelperWordInfo | None = None
    extra_cells: tuple[tuple[int, int], ...] = ()

    if difficulty == "easy":
        second = select_secondary_helper(
            result, primary, word_scores=result.word_scores,
        )
        if second is not None:
            secondary = _entry_to_helper(second)
        occupied = set(primary.helper_cells)
        if secondary is not None:
            occupied.update(secondary.helper_cells)
        extra_cells = select_extra_hint_cells(result, occupied)

    result.puzzle_hints = PuzzleHints(
        difficulty=difficulty,
        primary_helper=primary,
        secondary_helper=secondary,
        extra_hint_cells=extra_cells,
    )
    result.helper = primary
    result.difficulty = difficulty
    result.clue_words = clue_words_for_hints(result)
    validate_puzzle_hints(result)
    return result
