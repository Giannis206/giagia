"""Constraint-based backtracking crossword solver."""

from __future__ import annotations

import logging
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from crossword.dictionary import dictionary_stats, load_dictionary
from crossword.grid import BLACK, Grid, WHITE, generate_symmetric_pattern
from crossword.slots import Slot, extract_slots, slots_by_cell
from crossword.validate import validate_solution
from crossword.word_store import WordStore, get_word_store

logger = logging.getLogger(__name__)

USER_FAILURE_MESSAGE = (
    "Δεν βρέθηκε έγκυρο σταυρόλεξο με πραγματικές λέξεις για αυτό το μέγεθος. "
    "Δοκίμασε ξανά."
)


class CrosswordGenerationError(RuntimeError):
    """Raised when no valid crossword can be produced."""

    def __init__(self, message: str, *, diagnostics: str | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass
class SolverState:
    assignments: dict[int, str] = field(default_factory=dict)
    used_words: set[str] = field(default_factory=set)
    letters: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass
class GenerationBudget:
    total_seconds: float
    max_pattern_attempts: int
    restarts: int
    max_nodes: int
    pattern_time_cap: float


def _budget_for_size(size: int) -> GenerationBudget:
    if size <= 7:
        return GenerationBudget(35.0, 20, 6, 18_000, 12.0)
    if size <= 8:
        return GenerationBudget(50.0, 15, 5, 15_000, 18.0)
    if size <= 10:
        return GenerationBudget(90.0, 12, 4, 12_000, 25.0)
    if size <= 12:
        return GenerationBudget(150.0, 14, 4, 12_000, 40.0)
    return GenerationBudget(90.0, 6, 2, 8_000, 40.0)


def _pattern_is_acceptable(slot_lengths: list[int]) -> bool:
    if not slot_lengths:
        return False
    counts = Counter(slot_lengths)
    total = len(slot_lengths)
    if counts.get(3, 0) / total > 0.38:
        return False
    if sum(v for k, v in counts.items() if k >= 11) / total > 0.25:
        return False
    if len(counts) < 3:
        return False
    return True


def _pattern_balance_score(slot_lengths: list[int]) -> float:
    """Prefer mixed slot lengths; penalize extreme 3-letter dominance."""
    if not slot_lengths:
        return 0.0
    counts = Counter(slot_lengths)
    total = len(slot_lengths)
    three_ratio = counts.get(3, 0) / total
    long_ratio = sum(v for k, v in counts.items() if k >= 9) / total
    variety = len(counts) / max(1, min(8, total))
    mid_ratio = sum(v for k, v in counts.items() if 5 <= k <= 8) / total
    score = variety * 4.0 + mid_ratio * 3.0
    score -= max(0.0, three_ratio - 0.45) * 8.0
    score -= long_ratio * 4.0
    return score


@dataclass
class GenerationDiagnostics:
    size: int
    dictionary_counts: dict[int, int] = field(default_factory=dict)
    pattern_attempts: int = 0
    solve_attempts: int = 0
    skipped_missing_lengths: int = 0
    skipped_empty_slots: int = 0
    solve_failures: int = 0
    validation_failures: int = 0
    elapsed_seconds: float = 0.0
    zero_candidate_slots: list[tuple[int, int, str]] = field(default_factory=list)
    last_slot_lengths: list[int] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"size={self.size}",
            f"dictionary_by_length={self.dictionary_counts}",
            f"pattern_attempts={self.pattern_attempts}",
            f"solve_attempts={self.solve_attempts}",
            f"elapsed_s={self.elapsed_seconds:.1f}",
            f"skipped_missing_lengths={self.skipped_missing_lengths}",
            f"skipped_empty_slots={self.skipped_empty_slots}",
            f"solve_failures={self.solve_failures}",
            f"validation_failures={self.validation_failures}",
        ]
        if self.last_slot_lengths:
            need = Counter(self.last_slot_lengths)
            lines.append(f"slot_lengths_needed={dict(sorted(need.items()))}")
        if self.zero_candidate_slots:
            lines.append(
                "zero_candidate_examples="
                + ", ".join(f"{d}#{sid}({length})" for sid, length, d in self.zero_candidate_slots[:8])
            )
        return "; ".join(lines)


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


MAX_CANDIDATES_PER_SLOT = 350


class CrosswordSolver:
    def __init__(
        self,
        grid: Grid,
        slots: list[Slot],
        dictionary: dict[int, set[str]],
        *,
        word_scores: dict[str, int] | None = None,
        rng: random.Random | None = None,
        deadline: float | None = None,
    ):
        self.grid = grid
        self.slots = slots
        self.dictionary = dictionary
        self.word_scores = word_scores or {}
        self.rng = rng or random.Random()
        self.deadline = deadline
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
            if self.deadline is not None and time.monotonic() > self.deadline:
                return False
            nodes += 1
            if nodes > max_nodes:
                return False

            next_slot = self._select_slot(state)
            if next_slot is None:
                return True

            candidates = self._candidates(next_slot, state)
            self._shuffle_scored(candidates)

            for word in candidates:
                if word not in self.dictionary.get(next_slot.length, set()):
                    continue
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

    def solve_with_restarts(
        self,
        *,
        restarts: int = 80,
        max_nodes: int = 80_000,
        deadline: float | None = None,
    ) -> SolverState | None:
        effective_deadline = deadline if deadline is not None else self.deadline
        for _ in range(restarts):
            if effective_deadline is not None and time.monotonic() > effective_deadline:
                break
            trial = CrosswordSolver(
                self.grid.copy(),
                self.slots,
                self.dictionary,
                word_scores=self.word_scores,
                rng=self.rng,
                deadline=effective_deadline,
            )
            state = trial.solve(max_nodes=max_nodes)
            if state is not None:
                self.grid = trial.grid
                return state
        return None

    def count_zero_candidate_slots(self, state: SolverState | None = None) -> list[tuple[int, int, str]]:
        state = state or SolverState()
        empty: list[tuple[int, int, str]] = []
        for slot in self.slots:
            if slot.slot_id in state.assignments:
                continue
            if not self._candidate_set(slot, state):
                empty.append((slot.slot_id, slot.length, slot.direction))
        return empty

    def _shuffle_scored(self, candidates: list[str]) -> None:
        self.rng.shuffle(candidates)
        candidates.sort(
            key=lambda w: (
                self.word_scores.get(w, 0),
                sum(ch in "ΑΕΗΙΟΥΩ" for ch in w),
            ),
            reverse=True,
        )

    def _select_slot(self, state: SolverState) -> Slot | None:
        unassigned = [s for s in self.slots if s.slot_id not in state.assignments]
        if not unassigned:
            return None

        # MRV with degree tie-breaker (more intersections first).
        return min(
            unassigned,
            key=lambda s: (
                len(self._candidate_set(s, state)),
                -sum(len(self._neighbor_ids[s.slot_id]) for _ in [0]),
                -s.length,
                s.slot_id,
            ),
        )

    def _pattern_for_slot(
        self,
        slot: Slot,
        letters: dict[tuple[int, int], str],
    ) -> list[str | None]:
        return [letters.get(cell) for cell in slot.cells]

    def _candidate_set(
        self,
        slot: Slot,
        state: SolverState,
        letters: dict[tuple[int, int], str] | None = None,
    ) -> set[str]:
        letters = state.letters if letters is None else letters
        pattern = self._pattern_for_slot(slot, letters)
        dict_words = self.dictionary.get(slot.length)
        if not dict_words:
            return set()

        candidates: set[str] | None = None

        for pos, letter in enumerate(pattern):
            if letter is None:
                continue
            pos_words = self.position_index[slot.length][pos].get(letter, set())
            candidates = pos_words if candidates is None else candidates & pos_words

        if candidates is None:
            candidates = set(dict_words)
        else:
            candidates = set(candidates)

        candidates &= dict_words
        candidates -= state.used_words

        if any(pattern):
            return {w for w in candidates if self._word_matches(w, pattern)}
        return candidates

    def _candidates(
        self,
        slot: Slot,
        state: SolverState,
        letters: dict[tuple[int, int], str] | None = None,
        *,
        limit: int | None = MAX_CANDIDATES_PER_SLOT,
    ) -> list[str]:
        resolved_letters = state.letters if letters is None else letters
        candidates = list(self._candidate_set(slot, state, letters))
        if not candidates:
            return []
        has_constraints = any(self._pattern_for_slot(slot, resolved_letters))
        self._shuffle_scored(candidates)
        if (
            limit is not None
            and not has_constraints
            and len(candidates) > limit
        ):
            return candidates[:limit]
        return candidates

    @staticmethod
    def _word_matches(word: str, pattern: list[str | None]) -> bool:
        for w, p in zip(word, pattern):
            if p is not None and w != p:
                return False
        return True

    def _can_place(self, slot: Slot, word: str, state: SolverState) -> bool:
        if word not in self.dictionary.get(slot.length, set()):
            return False

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
            if not self._candidate_set(other, state, tentative):
                return False
        return True

    def _place(self, slot: Slot, word: str, state: SolverState) -> None:
        state.assignments[slot.slot_id] = word
        state.used_words.add(word)
        for cell, letter in zip(slot.cells, word):
            state.letters[cell] = letter

    def _unplace(self, slot: Slot, state: SolverState) -> None:
        word = state.assignments.pop(slot.slot_id)
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


@dataclass
class GenerationResult:
    grid: Grid
    slots: list[Slot]
    state: SolverState
    words: list[str]


def _grid_from_pattern_rows(size: int, rows: list[str]) -> Grid:
    cells = [
        [BLACK if ch == "#" else WHITE for ch in row]
        for row in rows
    ]
    return Grid(size, cells)


def _load_pattern_bank(data_dir: Path) -> list[dict]:
    path = data_dir / "pattern_bank.json"
    if not path.exists():
        return []
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _attempt_fill(
    grid: Grid,
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
    rng: random.Random,
    diag: GenerationDiagnostics,
    *,
    restarts: int,
    max_nodes: int,
    deadline: float | None = None,
) -> GenerationResult | None:
    if any(slot.length > max(dictionary) for slot in slots):
        diag.skipped_missing_lengths += 1
        return None

    missing = sorted({slot.length for slot in slots if not dictionary.get(slot.length)})
    if missing:
        diag.skipped_missing_lengths += 1
        return None

    if deadline is not None and time.monotonic() > deadline:
        return None

    diag.solve_attempts += 1
    solver_rng = random.Random(rng.randint(0, 2**31 - 1))
    solver = CrosswordSolver(
        grid.copy(),
        slots,
        dictionary,
        word_scores=word_scores,
        rng=solver_rng,
        deadline=deadline,
    )
    state = solver.solve_with_restarts(
        restarts=restarts,
        max_nodes=max_nodes,
        deadline=deadline,
    )
    if state is None:
        diag.solve_failures += 1
        zeros = solver.count_zero_candidate_slots()
        if zeros:
            diag.zero_candidate_slots.extend(zeros[:3])
        return None

    try:
        validate_solution(grid=solver.grid, slots=slots, dictionary=dictionary)
    except ValueError as exc:
        diag.validation_failures += 1
        if diag.validation_failures <= 3:
            logger.warning("Validation failed: %s", exc)
        return None

    words = sorted({solver.slot_map[sid].read(solver.grid) for sid in state.assignments})
    return GenerationResult(grid=solver.grid, slots=slots, state=state, words=words)


def generate_crossword(
    *,
    data_dir: Path,
    size: int = 7,
    seed: int | None = None,
    max_pattern_attempts: int | None = None,
    diagnostic: bool = False,
    word_store: WordStore | None = None,
) -> GenerationResult:
    t0 = time.monotonic()
    store: WordStore | None = word_store
    if store is None and (data_dir / "greek_words.db").exists():
        store = get_word_store(data_dir)
        dictionary, word_scores = store.as_solver_dicts()
    else:
        dictionary, word_scores = load_dictionary(
            data_dir, strict=True, use_db=store is not None
        )

    if not dictionary:
        raise CrosswordGenerationError(
            "Δεν βρέθηκαν έγκυρα λεξικά στο data/.",
            diagnostics="dictionary empty after validation",
        )

    budget = _budget_for_size(size)
    if max_pattern_attempts is None:
        max_pattern_attempts = budget.max_pattern_attempts
    else:
        max_pattern_attempts = min(max_pattern_attempts, budget.max_pattern_attempts)

    deadline = t0 + budget.total_seconds

    diag = GenerationDiagnostics(
        size=size,
        dictionary_counts=dictionary_stats(dictionary),
    )
    if diagnostic:
        logger.info("Dictionary stats: %s", diag.dictionary_counts)

    base_seed = seed if seed is not None else random.randrange(1_000_000_000)
    rng = random.Random(base_seed)
    last_error: Exception | None = None

    bank_patterns = [
        entry
        for entry in _load_pattern_bank(data_dir)
        if entry.get("size") == size and entry.get("pattern")
    ]
    rng.shuffle(bank_patterns)

    for entry in bank_patterns[:3]:
        if time.monotonic() > deadline:
            break
        diag.pattern_attempts += 1
        grid = _grid_from_pattern_rows(size, entry["pattern"])
        slots = extract_slots(grid)
        diag.last_slot_lengths = [slot.length for slot in slots]
        pattern_deadline = min(deadline, time.monotonic() + budget.pattern_time_cap)
        result = _attempt_fill(
            grid,
            slots,
            dictionary,
            word_scores,
            rng,
            diag,
            restarts=budget.restarts,
            max_nodes=budget.max_nodes,
            deadline=pattern_deadline,
        )
        if result is not None:
            diag.elapsed_seconds = time.monotonic() - t0
            if store is not None:
                store.record_puzzle_words(result.words)
            if diagnostic:
                logger.info(
                    "Generation succeeded (bank pattern): %d words in %.1fs",
                    len(result.words),
                    diag.elapsed_seconds,
                )
            return result

    pattern_candidates: list[tuple[float, int, Grid, list[Slot]]] = []
    for _ in range(max_pattern_attempts * 2):
        if time.monotonic() > deadline:
            break
        pattern_seed = rng.randint(0, 2**31 - 1)
        pattern_rng = random.Random(pattern_seed)
        try:
            grid = generate_symmetric_pattern(size, rng=pattern_rng)
        except RuntimeError as exc:
            last_error = exc
            continue
        slots = extract_slots(grid)
        lengths = [s.length for s in slots]
        if any(l > max(dictionary) for l in lengths):
            continue
        if any(not dictionary.get(s.length) for s in slots):
            continue
        if not _pattern_is_acceptable(lengths):
            continue
        balance = _pattern_balance_score(lengths)
        pattern_candidates.append((balance, pattern_seed, grid, slots))

    pattern_candidates.sort(key=lambda item: (-item[0], item[1]))
    pattern_candidates = pattern_candidates[:max_pattern_attempts]

    for _, pattern_seed, grid, slots in pattern_candidates:
        if time.monotonic() > deadline:
            break
        diag.pattern_attempts += 1
        diag.last_slot_lengths = [slot.length for slot in slots]
        pattern_deadline = min(deadline, time.monotonic() + budget.pattern_time_cap)
        result = _attempt_fill(
            grid,
            slots,
            dictionary,
            word_scores,
            random.Random(pattern_seed + 17),
            diag,
            restarts=budget.restarts,
            max_nodes=budget.max_nodes,
            deadline=pattern_deadline,
        )
        if result is not None:
            diag.elapsed_seconds = time.monotonic() - t0
            if store is not None:
                store.record_puzzle_words(result.words)
            if diagnostic:
                logger.info(
                    "Generation succeeded: %d words in %.1fs",
                    len(result.words),
                    diag.elapsed_seconds,
                )
            return result

    diag.elapsed_seconds = time.monotonic() - t0
    logger.error("Crossword generation failed: %s", diag.summary())
    raise CrosswordGenerationError(
        USER_FAILURE_MESSAGE,
        diagnostics=diag.summary()
        + (f"; last_error={last_error}" if last_error else ""),
    )


def generate_crossword_with_fallback(
    *,
    data_dir: Path,
    size: int = 7,
    seed: int | None = None,
    allow_reuse: bool = False,
    diagnostic: bool = False,
) -> GenerationResult:
    """Backward-compatible alias — no bank/greedy fallbacks."""
    if allow_reuse:
        logger.warning("allow_reuse is ignored; only unique dictionary words are used")
    return generate_crossword(
        data_dir=data_dir,
        size=size,
        seed=seed,
        diagnostic=diagnostic,
    )
