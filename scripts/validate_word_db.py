#!/usr/bin/env python3
"""Validate Greek word SQLite database and print a report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import rejection_reason
from crossword.word_store import MAX_LENGTH, MIN_LENGTH, WordStore

DEFAULT_DB = ROOT / "data" / "greek_words.db"


def main() -> int:
    db_path = DEFAULT_DB
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"Missing database: {db_path}")
        print("Run: python scripts/build_word_db.py")
        return 1

    store = WordStore(db_path)
    store.ensure_loaded()
    stats = store.stats()

    print("=== Word DB validation ===\n")
    print(f"Database: {db_path}")
    print(f"Total allowed words (length {MIN_LENGTH}-{MAX_LENGTH}): {stats.total_allowed}")
    print("\nBy length:")
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        print(f"  {length}: {stats.by_length.get(length, 0)}")

    print("\nBy source:")
    for source, count in sorted(stats.sources.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")

    conn = store.connect()
    invalid = 0
    samples: list[tuple[str, str]] = []
    for row in conn.execute(
        "SELECT word_normalized, length FROM words WHERE allowed=1"
    ):
        word = row["word_normalized"]
        length = int(row["length"])
        reason = rejection_reason(word, length)
        if reason:
            invalid += 1
            if len(samples) < 10:
                samples.append((word, reason))

    print(f"\nRe-validation failures in DB: {invalid}")
    if samples:
        print("Samples:")
        for word, reason in samples:
            print(f"  {word}: {reason}")

    d = store.dictionary
    print("\nSample words per length:")
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        words = sorted(d.get(length, set()))[:5]
        if words:
            print(f"  {length}: {', '.join(words)}")

    store.close()
    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
