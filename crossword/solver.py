"""Constraint-based backtracking crossword solver."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from crossword.grid import Grid, generate_symmetric_pattern
from crossword.slots import Slot, extract_slots, slots_by_cell
from crossword.validate import validate_solution


@dataclass
class SolverState:
    assignments: dict[int, str] = field(default_factory=dict)
    used_words: set[str] = field(default_factory=set)
    letters: dict[tuple[int, int], str] = field(default_factory=dict)


def _build_position_index(
    dictionary: dict[int, set[str]],
) -> dict[int, list[dict[str, set[str]]]]:
    index: dict[int, list[dict[str, set[str]]]] = {}
    for length, words in dictionary.items():
        buckets = [defaultdict(set) for _ in range(length)]
        for word in words:
            for pos, letter in enumerate(word):
                buckets[pos][letter].add(word)
        index[length] = buckets
    return index


class CrosswordSolver:
    def __init__(
        self,
        grid: Grid,
        slots: list[Slot],
        dictionary: dict[int, set[str]],
        *,
        allow_reuse: bool = False,
        rng: random.Random | None = None,
    ):
        self.grid = grid
        self.slots = slots
        self.dictionary = dictionary
        self.allow_reuse = allow_reuse
        self.rng = rng or random.Random()
        self.cell_slots = slots_by_cell(slots)
        self.slot_map = {slot.slot_id: slot for slot in slots}
        self.position_index = _build_position_index(dictionary)
        self._neighbor_ids: dict[int, set[int]] = defaultdict(set)
        for slot in slots:
            neighbors: set[int] = set()
            for cell in slot.cells:
                for other in self.cell_slots.get(cell, []):
                    if other.slot_id != slot.slot_id:
                        neighbors.add(other.slot_id)
            self._neighbor_ids[slot.slot_id] = neighbors

    def solve(self, max_nodes: int = 120_000) -> SolverState | None:
        state = SolverState()
        nodes = 0

        def backtrack() -> bool:
            nonlocal nodes
            nodes += 1
            if nodes > max_nodes:
                return False

            next_slot = self._select_slot(state)
            if next_slot is None:
                return True

            candidates = self._candidates(next_slot, state)
            self.rng.shuffle(candidates)

            for word in candidates:
                if not self._can_place(next_slot, word, state):
                    continue

                self._place(next_slot, word, state)
                if backtrack():
                    return True
                self._unplace(next_slot, state)

            return False

        if backtrack():
            self._apply_to_grid(state)
            return state
        return None

    def _select_slot(self, state: SolverState) -> Slot | None:
        unassigned = [s for s in self.slots if s.slot_id not in state.assignments]
        if not unassigned:
            return None

        return min(
            unassigned,
            key=lambda s: (len(self._candidates(s, state)), -s.length, s.slot_id),
        )

    def _pattern_for_slot(
        self,
        slot: Slot,
        letters: dict[tuple[int, int], str],
    ) -> list[str | None]:
        return [letters.get(cell) for cell in slot.cells]

    def _candidates(
        self,
        slot: Slot,
        state: SolverState,
        letters: dict[tuple[int, int], str] | None = None,
    ) -> list[str]:
        letters = state.letters if letters is None else letters
        pattern = self._pattern_for_slot(slot, letters)
        candidates: set[str] | None = None

        for pos, letter in enumerate(pattern):
            if letter is None:
                continue
            pos_words = self.position_index[slot.length][pos].get(letter, set())
            candidates = pos_words if candidates is None else candidates & pos_words

        if candidates is None:
            candidates = set(self.dictionary.get(slot.length, set()))
        else:
            candidates = set(candidates)

        if not self.allow_reuse:
            candidates -= state.used_words

        if any(pattern):
            return [w for w in candidates if self._word_matches(w, pattern)]
        return list(candidates)

    @staticmethod
    def _word_matches(word: str, pattern: list[str | None]) -> bool:
        for w, p in zip(word, pattern):
            if p is not None and w != p:
                return False
        return True

    def _can_place(self, slot: Slot, word: str, state: SolverState) -> bool:
        tentative = dict(state.letters)
        for cell, letter in zip(slot.cells, word):
            existing = tentative.get(cell)
            if existing is not None and existing != letter:
                return False
            tentative[cell] = letter

        to_check: set[int] = set()
        for neighbor_id in self._neighbor_ids[slot.slot_id]:
            if neighbor_id in state.assignments:
                continue
            to_check.add(neighbor_id)

        for slot_id in to_check:
            other = self.slot_map[slot_id]
            if not self._candidates(other, state, tentative):
                return False
        return True

    def _place(self, slot: Slot, word: str, state: SolverState) -> None:
        state.assignments[slot.slot_id] = word
        if not self.allow_reuse:
            state.used_words.add(word)
        for cell, letter in zip(slot.cells, word):
            state.letters[cell] = letter

    def _unplace(self, slot: Slot, state: SolverState) -> None:
        word = state.assignments.pop(slot.slot_id)
        if not self.allow_reuse:
            state.used_words.discard(word)
        for cell in slot.cells:
            still_needed = any(
                cell in self.slot_map[sid].cells
                for sid in state.assignments
            )
            if not still_needed:
                state.letters.pop(cell, None)

    def _apply_to_grid(self, state: SolverState) -> None:
        self.grid.clear_letters()
        for (r, c), letter in state.letters.items():
            self.grid.set(r, c, letter)


def load_dictionary(data_dir: Path) -> dict[int, set[str]]:
    dictionary: dict[int, set[str]] = {}
    for path in sorted(data_dir.glob("words_*.txt")):
        length_str = path.stem.split("_", 1)[1]
        length = int(length_str)
        words = {
            line.strip().upper()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        dictionary[length] = {w for w in words if len(w) == length}
    return dictionary


def _pattern_score(slots: list[Slot]) -> tuple[int, int, int]:
    """Lower is better: prefer fewer/shorter slots."""
    max_len = max(slot.length for slot in slots)
    return (max_len, len(slots), sum(slot.length for slot in slots))


@dataclass
class GenerationResult:
    grid: Grid
    slots: list[Slot]
    state: SolverState
    words: list[str]


def generate_crossword(
    *,
    data_dir: Path,
    size: int = 11,
    seed: int | None = None,
    allow_reuse: bool = False,
    max_pattern_attempts: int = 60,
    max_solve_attempts: int = 12,
) -> GenerationResult:
    dictionary = load_dictionary(data_dir)
    if not dictionary:
        raise RuntimeError("No dictionary files found in data/")

    max_dict_len = max(dictionary.keys())
    base_seed = seed if seed is not None else random.randrange(1_000_000_000)
    rng = random.Random(base_seed)
    last_error: Exception | None = None

    for _ in range(max_pattern_attempts):
        pattern_seed = rng.randint(0, 2**31 - 1)
        pattern_rng = random.Random(pattern_seed)
        try:
            grid = generate_symmetric_pattern(size, rng=pattern_rng)
        except RuntimeError as exc:
            last_error = exc
            continue

        slots = extract_slots(grid)
        if any(slot.length > max_dict_len for slot in slots):
            continue
        if any(not dictionary.get(slot.length) for slot in slots):
            continue
        if _pattern_score(slots)[0] > min(9, max_dict_len):
            continue

        for solve_try in range(max_solve_attempts):
            solver_rng = random.Random(rng.randint(0, 2**31 - 1))
            solver = CrosswordSolver(
                grid.copy(),
                slots,
                dictionary,
                allow_reuse=allow_reuse,
                rng=solver_rng,
            )
            state = solver.solve()
            if state is None:
                continue

            try:
                validate_solution(
                    solver.grid,
                    slots,
                    dictionary,
                    allow_reuse=allow_reuse,
                )
            except ValueError:
                continue

            words = sorted(
                {solver.slot_map[sid].read(solver.grid) for sid in state.assignments}
            )
            return GenerationResult(
                grid=solver.grid,
                slots=slots,
                state=state,
                words=words,
            )

    raise RuntimeError(
        f"Failed to generate crossword after {max_pattern_attempts} pattern attempts"
        + (f": {last_error}" if last_error else "")
    )
