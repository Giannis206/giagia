"""Pre-indexed word lists and weighted candidate sampling for the solver."""

from __future__ import annotations

import random
from collections import Counter, defaultdict

MAX_SLOT_ATTEMPTS = 150


def build_position_index(
    dictionary: dict[int, set[str]],
) -> dict[int, list[dict[str, set[str]]]]:
    index: dict[int, list[dict[str, set[str]]]] = {}
    for length, words in dictionary.items():
        buckets: list[dict[str, set[str]]] = [defaultdict(set) for _ in range(length)]
        for word in words:
            for pos, letter in enumerate(word):
                buckets[pos][letter].add(word)
        index[length] = buckets
    return index


def build_shuffled_buckets(
    dictionary: dict[int, set[str]],
    rng: random.Random,
) -> dict[int, list[str]]:
    """Shuffle each length bucket once at startup for anti-bias ordering."""
    buckets: dict[int, list[str]] = {}
    for length, words in dictionary.items():
        lst = list(words)
        rng.shuffle(lst)
        buckets[length] = lst
    return buckets


def weighted_sample_candidates(
    candidates: set[str],
    scores: dict[str, int],
    rng: random.Random,
    *,
    limit: int,
    start_letter_counts: Counter | None = None,
    assigned_word_count: int = 0,
) -> list[str]:
    """Weighted random sampling without replacement from a candidate set."""
    if not candidates:
        return []

    def _weight(word: str) -> float:
        base = float(max(1, scores.get(word, 1)))
        if start_letter_counts and assigned_word_count > 0 and word:
            letter = word[0]
            ratio = start_letter_counts.get(letter, 0) / assigned_word_count
            if ratio >= 0.40:
                base *= 0.25
            elif ratio >= 0.30:
                base *= 0.5
            elif ratio >= 0.22:
                base *= 0.75
        return base

    pool = list(candidates)
    if len(pool) <= limit:
        rng.shuffle(pool)
        return pool

    chosen: list[str] = []
    remaining = pool[:]
    for _ in range(limit):
        weights = [_weight(word) for word in remaining]
        total = sum(weights)
        pick = rng.uniform(0, total)
        acc = 0.0
        for word, weight in zip(remaining, weights):
            acc += weight
            if pick <= acc:
                chosen.append(word)
                remaining.remove(word)
                break
    return chosen


class CandidateIndex:
    """One-time pre-index for fast candidate lookup and weighted sampling."""

    def __init__(
        self,
        dictionary: dict[int, set[str]],
        scores: dict[str, int],
        rng: random.Random,
    ):
        self.dictionary = dictionary
        self.scores = scores
        self.rng = rng
        self.position_index = build_position_index(dictionary)
        self.shuffled_buckets = build_shuffled_buckets(dictionary, rng)

    def candidate_set(
        self,
        length: int,
        pattern: list[str | None],
        *,
        exclude: set[str] | None = None,
    ) -> set[str]:
        dict_words = self.dictionary.get(length)
        if not dict_words:
            return set()

        exclude = exclude or set()
        pos_index = self.position_index.get(length)
        if pos_index is None:
            return set()

        candidates: set[str] | None = None
        for pos, letter in enumerate(pattern):
            if letter is None:
                continue
            pos_words = pos_index[pos].get(letter, set())
            candidates = pos_words if candidates is None else candidates & pos_words

        if candidates is None:
            candidates = set(dict_words)
        else:
            candidates = set(candidates)

        candidates &= dict_words
        candidates -= exclude

        if any(pattern):
            return {
                w
                for w in candidates
                if all(p is None or w[i] == p for i, p in enumerate(pattern))
            }
        return candidates

    def sample_candidates(
        self,
        length: int,
        pattern: list[str | None],
        *,
        exclude: set[str] | None = None,
        limit: int = 350,
        start_letter_counts: Counter | None = None,
        assigned_word_count: int = 0,
    ) -> list[str]:
        candidates = self.candidate_set(length, pattern, exclude=exclude)
        if not candidates:
            return []
        has_constraints = any(pattern)
        cap = min(limit, len(candidates))
        return weighted_sample_candidates(
            candidates,
            self.scores,
            self.rng,
            limit=cap if has_constraints else cap,
            start_letter_counts=start_letter_counts,
            assigned_word_count=assigned_word_count,
        )
