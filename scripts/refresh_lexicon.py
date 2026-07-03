#!/usr/bin/env python3
"""Refresh Greek lexicon buckets (lengths 3–12) with dedup, shuffle, and bias stats.

Usage
-----
From the repo root (requires Python 3.10+):

    python scripts/refresh_lexicon.py
    python scripts/refresh_lexicon.py --seed 42          # reproducible shuffle
    python scripts/refresh_lexicon.py --db-only          # skip words_*.txt export

Dependencies
------------
Standard library only (sqlite3, pathlib). Uses the same local sources as
``scripts/build_word_db.py`` — no external downloads unless you already have
``data/sources/el_50k.txt`` or run ``build_word_db.py --download`` first.

Reads
-----
- data/SUBTLEX-GR_restricted.txt
- data/sources/el_50k.txt (if present)
- data/curated_el.txt
- data/words_*.txt
- data/sources/* (txt/json/csv)

Writes
------
- data/greek_words.db  (SQLite, length buckets stored in shuffled order)
- data/words_3.txt … data/words_12.txt  (one word per line, shuffled per file)

After running, restart the app or call ``crossword.word_store.clear_word_store_cache()``
so the solver reloads the refreshed database.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import normalize_word, rejection_reason
from crossword.word_store import MAX_LENGTH, MIN_LENGTH, SCHEMA_SQL

# Reuse source loaders from build_word_db.
from scripts.build_word_db import (  # noqa: E402
    CURATED_PATH,
    DATA_DIR,
    DEFAULT_DB,
    FREQ_50K_PATH,
    SUBTLEX_PATH,
    BuildReport,
    _load_extra_sources,
    _load_freq_list,
    _load_subtlex,
    _load_txt_lines,
    _load_words_files,
    _candidate,
)


def _collect_words() -> dict[str, tuple[str, int, int, str]]:
    bucket: dict[str, tuple[str, int, int, str]] = {}
    report = BuildReport()
    _load_subtlex(SUBTLEX_PATH, bucket, report)
    _load_freq_list(FREQ_50K_PATH, bucket, report)
    _load_txt_lines(CURATED_PATH, "curated_el", bucket, report)
    _load_words_files(DATA_DIR, bucket, report)
    _load_extra_sources(DATA_DIR / "sources", bucket, report)
    return bucket


def _bucket_by_length(
    bucket: dict[str, tuple[str, int, int, str]],
) -> dict[int, list[tuple[str, str, int, str]]]:
    """Group accepted words by length: (normalized, original, score, source)."""
    by_length: dict[int, list[tuple[str, str, int, str]]] = defaultdict(list)
    for word, (original, _freq, score, source) in bucket.items():
        if not (MIN_LENGTH <= len(word) <= MAX_LENGTH):
            continue
        if rejection_reason(word, len(word)):
            continue
        by_length[len(word)].append((word, original, score, source))
    return by_length


def _starting_letter_stats(
    words: list[str],
) -> dict[str, int]:
    return dict(sorted(Counter(w[0] for w in words if w).items()))


def _print_stats(by_length: dict[int, list[tuple[str, str, int, str]]]) -> None:
    print("\n=== Lexicon by length ===")
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        entries = by_length.get(length, [])
        words = [w for w, *_ in entries]
        print(f"  {length}: {len(words)} words")
        if not words:
            continue
        stats = _starting_letter_stats(words)
        top = sorted(stats.items(), key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{letter}={count}" for letter, count in top)
        print(f"       top starts: {top_str}")


def _write_words_files(
    by_length: dict[int, list[tuple[str, str, int, str]]],
    rng: random.Random,
) -> None:
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        entries = by_length.get(length, [])
        words = [w for w, *_ in entries]
        rng.shuffle(words)
        path = DATA_DIR / f"words_{length}.txt"
        path.write_text("\n".join(words) + ("\n" if words else ""), encoding="utf-8")
        print(f"Wrote {path.name} ({len(words)} words, shuffled)")


def _write_db(
    by_length: dict[int, list[tuple[str, str, int, str]]],
    db_path: Path,
    rng: random.Random,
) -> int:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    rows: list[tuple[str, str, int, int, str, int, int]] = []
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        entries = list(by_length.get(length, []))
        rng.shuffle(entries)
        for word, original, score, source in entries:
            rows.append((original, word, length, score, source, 1, 0))
    conn.executemany(
        """
        INSERT INTO words (word_original, word_normalized, length, score, source, allowed, recent_penalty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh shuffled Greek lexicon (3–12 letters)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite output path")
    parser.add_argument("--seed", type=int, default=None, help="Shuffle seed (default: random)")
    parser.add_argument("--db-only", action="store_true", help="Only update greek_words.db")
    parser.add_argument("--no-db", action="store_true", help="Only update words_*.txt files")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)

    print("Collecting words from local sources...")
    bucket = _collect_words()
    by_length = _bucket_by_length(bucket)
    _print_stats(by_length)

    if not args.no_db:
        total = _write_db(by_length, args.db, rng)
        print(f"\nWrote {args.db} ({total} words, shuffled per length bucket)")

    if not args.db_only:
        _write_words_files(by_length, rng)

    print("\nDone. Clear word store cache before generating:")
    print("  python -c \"from crossword.word_store import clear_word_store_cache; clear_word_store_cache()\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
