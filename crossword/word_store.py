"""SQLite-backed Greek word store with in-memory candidate indexing."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from crossword.dictionary import dictionary_stats, normalize_word, rejection_reason, word_score

MIN_LENGTH = 3
MAX_LENGTH = 12

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_original TEXT NOT NULL,
    word_normalized TEXT NOT NULL UNIQUE,
    length INTEGER NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    allowed INTEGER NOT NULL DEFAULT 1,
    recent_penalty INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_words_length ON words(length);
CREATE INDEX IF NOT EXISTS idx_words_allowed_length ON words(allowed, length);
CREATE INDEX IF NOT EXISTS idx_words_score ON words(score DESC);

CREATE TABLE IF NOT EXISTS recent_usage (
    word_normalized TEXT PRIMARY KEY,
    last_used_at TEXT NOT NULL,
    use_count INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class WordStoreStats:
    total_allowed: int
    by_length: dict[int, int]
    sources: dict[str, int]


class WordStore:
    """Loads allowed words from SQLite and serves fast candidate lookups."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._dictionary: dict[int, set[str]] = {}
        self._scores: dict[str, int] = {}
        self._position_index: dict[int, list[dict[str, set[str]]]] = {}
        self._recent_penalties: dict[str, int] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA_SQL)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._loaded = False

    def ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._load_from_db()

    def _load_from_db(self) -> None:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT word_normalized, length, score, recent_penalty
            FROM words
            WHERE allowed = 1 AND length BETWEEN ? AND ?
            ORDER BY score DESC
            """,
            (MIN_LENGTH, MAX_LENGTH),
        ).fetchall()

        dictionary: dict[int, set[str]] = defaultdict(set)
        scores: dict[str, int] = {}
        recent: dict[str, int] = {}

        for row in rows:
            word = row["word_normalized"]
            length = int(row["length"])
            base = int(row["score"])
            penalty = int(row["recent_penalty"] or 0)
            dictionary[length].add(word)
            scores[word] = max(0, base - penalty)
            if penalty:
                recent[word] = penalty

        usage_rows = conn.execute(
            "SELECT word_normalized, use_count FROM recent_usage"
        ).fetchall()
        for row in usage_rows:
            word = row["word_normalized"]
            count = int(row["use_count"])
            if word in scores:
                extra = min(80, count * 8)
                scores[word] = max(0, scores[word] - extra)
                recent[word] = recent.get(word, 0) + extra

        self._dictionary = dict(dictionary)
        self._scores = scores
        self._recent_penalties = recent
        # Shuffled length buckets for anti-bias candidate access.
        import random

        shuffle_rng = random.Random(42)
        self._shuffled_buckets: dict[int, list[str]] = {}
        for length, words in self._dictionary.items():
            lst = list(words)
            shuffle_rng.shuffle(lst)
            self._shuffled_buckets[length] = lst
        self._position_index = self._build_position_index(self._dictionary)
        self._loaded = True

    @staticmethod
    def _build_position_index(
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

    @property
    def dictionary(self) -> dict[int, set[str]]:
        self.ensure_loaded()
        return self._dictionary

    @property
    def scores(self) -> dict[str, int]:
        self.ensure_loaded()
        return self._scores

    def stats(self) -> WordStoreStats:
        self.ensure_loaded()
        conn = self.connect()
        by_source = {
            row["source"]: row["cnt"]
            for row in conn.execute(
                "SELECT source, COUNT(*) AS cnt FROM words WHERE allowed=1 GROUP BY source"
            )
        }
        return WordStoreStats(
            total_allowed=sum(len(v) for v in self._dictionary.values()),
            by_length=dictionary_stats(self._dictionary),
            sources=by_source,
        )

    def has_word(self, length: int, word: str) -> bool:
        self.ensure_loaded()
        return word in self._dictionary.get(length, set())

    def effective_score(self, word: str) -> int:
        self.ensure_loaded()
        return self._scores.get(word, 0)

    def candidate_set(
        self,
        length: int,
        pattern: list[str | None],
        *,
        exclude: set[str] | None = None,
    ) -> set[str]:
        self.ensure_loaded()
        dict_words = self._dictionary.get(length)
        if not dict_words:
            return set()

        exclude = exclude or set()
        pos_index = self._position_index.get(length)
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

    def record_puzzle_words(self, words: Iterable[str]) -> None:
        """Persist recent usage and refresh in-memory penalties."""
        from datetime import datetime, timezone

        conn = self.connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            for word in words:
                conn.execute(
                    """
                    INSERT INTO recent_usage (word_normalized, last_used_at, use_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(word_normalized) DO UPDATE SET
                        last_used_at = excluded.last_used_at,
                        use_count = recent_usage.use_count + 1
                    """,
                    (word, now),
                )
                conn.execute(
                    "UPDATE words SET recent_penalty = MIN(80, recent_penalty + 8) WHERE word_normalized = ?",
                    (word,),
                )
        self._loaded = False
        self.ensure_loaded()

    def as_solver_dicts(self) -> tuple[dict[int, set[str]], dict[str, int]]:
        self.ensure_loaded()
        return self._dictionary, dict(self._scores)


_STORE_CACHE: dict[str, WordStore] = {}
_CACHE_LOCK = threading.Lock()


def get_word_store(data_dir: Path, *, db_name: str = "greek_words.db") -> WordStore:
    """Return a cached WordStore for the given data directory."""
    db_path = data_dir / db_name
    key = str(db_path.resolve())
    with _CACHE_LOCK:
        store = _STORE_CACHE.get(key)
        if store is None:
            if not db_path.exists():
                raise FileNotFoundError(
                    f"Word database not found: {db_path}. Run scripts/build_word_db.py first."
                )
            store = WordStore(db_path)
            _STORE_CACHE[key] = store
        return store


def clear_word_store_cache() -> None:
    with _CACHE_LOCK:
        for store in _STORE_CACHE.values():
            store.close()
        _STORE_CACHE.clear()
