"""Post-generation helper word selection for player-facing puzzles.

Scoring formula (per entry):
    total = α·length + β·crossings + γ·position + δ·frequency

    α = 1   — longer words give a bit more context, but not the main signal.
    β = 2   — crossings matter most: each crossed letter helps lock neighbours.
    γ = 0.5 — slight preference for centrally placed words (visible anchor).
    δ = 0.3 — optional tie-break toward common / high-frequency dictionary words.

The entry with the highest total score becomes the prefilled helper word.
Ties break deterministically: Across before Down, then lower clue number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from crossword.slots import Direction, Slot, slots_by_cell

if TYPE_CHECKING:
    from crossword.solver import GenerationResult

DirectionLabel = Literal["across", "down"]

# α, β, γ, δ — see module docstring
_LENGTH_WEIGHT = 1.0
_CROSSING_WEIGHT = 2.0
_POSITION_WEIGHT = 0.5
_FREQUENCY_WEIGHT = 0.3

_DIRECTION_ORDER = {"across": 0, "down": 1}


@dataclass(frozen=True)
class HelperScoreConfig:
    """Per-grid-size tuning for helper selection."""

    min_length: int
    preferred_min_length: int
    length_bonus: float = 2.0


_SIZE_CONFIGS: dict[int, HelperScoreConfig] = {
    7: HelperScoreConfig(min_length=3, preferred_min_length=4),
    8: HelperScoreConfig(min_length=3, preferred_min_length=5),
    10: HelperScoreConfig(min_length=3, preferred_min_length=5),
    12: HelperScoreConfig(min_length=3, preferred_min_length=6),
}


@dataclass(frozen=True)
class HelperWordInfo:
    helper_entry_id: int
    helper_word: str
    helper_direction: DirectionLabel
    helper_cells: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class EntryScore:
    """Debuggable breakdown for one candidate helper entry."""

    slot: Slot
    word: str
    total_score: float
    length_score: float
    crossings: int
    crossing_score: float
    position_score: float
    frequency_score: float
    clue_number: int


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


def _length_component(length: int, config: HelperScoreConfig) -> float:
    base = float(length)
    if length >= config.preferred_min_length:
        base += config.length_bonus
    return base


def _position_component(slot: Slot, grid_size: int) -> float:
    """1.0 at grid centre, tapering toward edges/corners."""
    if grid_size <= 1:
        return 1.0
    center = (grid_size - 1) / 2.0
    avg_row = sum(row for row, _col in slot.cells) / len(slot.cells)
    avg_col = sum(col for _row, col in slot.cells) / len(slot.cells)
    dist = ((avg_row - center) ** 2 + (avg_col - center) ** 2) ** 0.5
    max_dist = center * (2**0.5) if center > 0 else 1.0
    return max(0.0, 1.0 - dist / max_dist)


def _frequency_component(word: str, word_scores: dict[str, int] | None) -> float:
    if not word_scores:
        return 0.0
    raw = float(word_scores.get(word, 0))
    peak = float(max(word_scores.values())) if word_scores else 0.0
    if peak <= 0:
        return 0.0
    return raw / peak


def score_entry(
    slot: Slot,
    word: str,
    *,
    grid_size: int,
    cell_slots: dict[tuple[int, int], list[Slot]],
    clue_number: int,
    config: HelperScoreConfig,
    word_scores: dict[str, int] | None = None,
) -> EntryScore:
    crossings = _crossing_count(slot, cell_slots)
    length_score = _length_component(slot.length, config)
    crossing_score = float(crossings)
    position_score = _position_component(slot, grid_size)
    frequency_score = _frequency_component(word, word_scores)

    total = (
        _LENGTH_WEIGHT * length_score
        + _CROSSING_WEIGHT * crossing_score
        + _POSITION_WEIGHT * position_score
        + _FREQUENCY_WEIGHT * frequency_score
    )
    return EntryScore(
        slot=slot,
        word=word,
        total_score=total,
        length_score=length_score,
        crossings=crossings,
        crossing_score=crossing_score,
        position_score=position_score,
        frequency_score=frequency_score,
        clue_number=clue_number,
    )


def score_all_entries(
    result: GenerationResult,
    *,
    word_scores: dict[str, int] | None = None,
) -> list[EntryScore]:
    grid_size = result.grid.size
    config = _SIZE_CONFIGS.get(grid_size, HelperScoreConfig(min_length=3, preferred_min_length=5))
    cell_slots = slots_by_cell(result.slots)
    clue_numbers = assign_clue_numbers(result.slots, grid_size)

    scored: list[EntryScore] = []
    for slot in result.slots:
        if slot.slot_id not in result.state.assignments:
            continue
        if slot.length < config.min_length:
            continue
        word = slot.read(result.grid)
        clue_number = clue_numbers.get((slot.row, slot.col), slot.slot_id)
        scored.append(
            score_entry(
                slot,
                word,
                grid_size=grid_size,
                cell_slots=cell_slots,
                clue_number=clue_number,
                config=config,
                word_scores=word_scores,
            )
        )
    return scored


def _entry_sort_key(entry: EntryScore) -> tuple:
    """Highest score first; deterministic tie-break."""
    direction_rank = _DIRECTION_ORDER.get(entry.slot.direction, 9)
    return (
        -entry.total_score,
        direction_rank,
        entry.clue_number,
        entry.slot.slot_id,
    )


def select_helper_entry(
    result: GenerationResult,
    *,
    word_scores: dict[str, int] | None = None,
) -> EntryScore:
    scored = score_all_entries(result, word_scores=word_scores)
    if not scored:
        raise ValueError("No eligible entries for helper word selection")
    return min(scored, key=_entry_sort_key)


def select_helper_word(
    result: GenerationResult,
    *,
    word_scores: dict[str, int] | None = None,
) -> HelperWordInfo:
    """Pick the highest-scoring solution word as the prefilled helper."""
    best = select_helper_entry(result, word_scores=word_scores)
    slot = best.slot
    return HelperWordInfo(
        helper_entry_id=best.clue_number,
        helper_word=best.word,
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
    from crossword.puzzle_hints import finalize_puzzle_hints

    return finalize_puzzle_hints(result, difficulty="normal")
