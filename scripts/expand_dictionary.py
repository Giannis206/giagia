#!/usr/bin/env python3
"""Download and merge extra Greek words (lengths 3-9) into greek_words.db."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import normalize_word, rejection_reason, word_score
from crossword.word_store import MAX_LENGTH, MIN_LENGTH, SCHEMA_SQL

DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "greek_words.db"
SOURCES_DIR = DATA_DIR / "sources"

EXPAND_MIN = 3
EXPAND_MAX = 9

# Primary URL (404 as of 2026) + fallbacks
WORDLIST_URLS = (
    "https://raw.githubusercontent.com/philoui/greek-wordlist/master/greek_wordlist.txt",
    "https://raw.githubusercontent.com/eymenefealtun/all-words-in-all-languages/main/Greek/Greek.txt",
    "https://raw.githubusercontent.com/kalpetros/greek-dictionary/master/greek.txt",
)


def _download_wordlist(dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in WORDLIST_URLS:
        try:
            urllib.request.urlretrieve(url, dest)
            return url
        except OSError as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("All download URLs failed:\n" + "\n".join(errors))


def _parse_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    words: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line and len(line) > 20:
            parts = re.split(r"[,;\s]+", line)
            words.extend(p for p in parts if p)
        else:
            words.append(line)
    return words


def _letter_distribution_report(words: list[str]) -> dict[str, float]:
    if not words:
        return {}
    counts = Counter(w[0] for w in words if w)
    total = len(words)
    return {letter: count / total for letter, count in sorted(counts.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expand Greek word DB with downloaded lists")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--download", action="store_true", help="Force re-download")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    local_path = SOURCES_DIR / "greek_wordlist_expanded.txt"
    if args.download or not local_path.exists():
        print("Downloading Greek word list...")
        try:
            used_url = _download_wordlist(local_path)
            print(f"Saved to {local_path} (from {used_url})")
        except RuntimeError as exc:
            print(exc)
            print("Place a UTF-8 word list at data/sources/greek_wordlist_expanded.txt and re-run.")
            return 1

    raw_words = _parse_lines(local_path)
    print(f"Parsed {len(raw_words)} raw tokens")

    accepted: dict[str, tuple[str, int, int, str]] = {}
    rejected = Counter()

    for raw in raw_words:
        word = normalize_word(raw)
        if not word or not (EXPAND_MIN <= len(word) <= EXPAND_MAX):
            continue
        reason = rejection_reason(word, len(word))
        if reason:
            rejected[reason] += 1
            continue
        score = word_score(word, 1)
        if word not in accepted:
            accepted[word] = (raw, 1, score, "expanded")

    print(f"New unique words to merge (length {EXPAND_MIN}-{EXPAND_MAX}): {len(accepted)}")
    print(f"Rejected: {sum(rejected.values())}")

    by_length = Counter(len(w) for w in accepted)
    print("\nBy length:")
    for length in range(EXPAND_MIN, EXPAND_MAX + 1):
        print(f"  {length}: {by_length.get(length, 0)}")

    dist = _letter_distribution_report(list(accepted.keys()))
    if dist:
        print("\nStarting-letter distribution (new words):")
        for letter, ratio in sorted(dist.items(), key=lambda x: -x[1])[:12]:
            print(f"  {letter}: {ratio:.1%}")
        max_ratio = max(dist.values())
        if max_ratio > 0.40:
            print(f"  Warning: max starting-letter ratio {max_ratio:.1%} > 40%")

    if args.dry_run:
        return 0

    if not args.db.exists():
        print(f"Database missing: {args.db}. Run scripts/build_word_db.py first.")
        return 1

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA_SQL)
    inserted = 0
    updated = 0
    with conn:
        for word, (original, freq, score, source) in accepted.items():
            row = conn.execute(
                "SELECT id, score FROM words WHERE word_normalized = ?",
                (word,),
            ).fetchone()
            if row:
                if score > int(row[1]):
                    conn.execute(
                        "UPDATE words SET score = ?, source = ? WHERE word_normalized = ?",
                        (score, source, word),
                    )
                    updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO words
                    (word_original, word_normalized, length, score, source, allowed, recent_penalty)
                    VALUES (?, ?, ?, ?, ?, 1, 0)
                    """,
                    (original, word, len(word), score, source),
                )
                inserted += 1
    conn.close()

    print(f"\nMerged into {args.db}: inserted={inserted}, updated={updated}")
    print("Reload word store cache: restart app or run generation again.")
    from crossword.word_store import clear_word_store_cache

    clear_word_store_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
