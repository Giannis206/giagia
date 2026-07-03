"""Pre-indexed word lists and weighted candidate sampling for the solver."""

from __future__ import annotations

import random
from collections import defaultdict

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
) -> list[str]:
    """Weighted random sampling without replacement from a candidate set."""
    if not candidates:
        return []
    pool = list(candidates)
    if len(pool) <= limit:
        rng.shuffle(pool)
        return pool

    chosen: list[str] = []
    remaining = pool[:]
    for _ in range(limit):
        weights = [max(1, scores.get(w, 1)) for w in remaining]
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
    ) -> list[str]:
        candidates = self.candidate_set(length, pattern, exclude=exclude)
        if not candidates:
            return []
        has_constraints = any(pattern)
        if has_constraints:
            return weighted_sample_candidates(
                candidates, self.scores, self.rng, limit=min(limit, len(candidates))
            )
        cap = min(limit, len(candidates))
        return weighted_sample_candidates(candidates, self.scores, self.rng, limit=cap)
