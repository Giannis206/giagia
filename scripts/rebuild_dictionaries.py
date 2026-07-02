#!/usr/bin/env python3
"""Rebuild words_N.txt from SUBTLEX-GR + curated_el.txt with strict validation."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import normalize_word, rejection_reason

SOURCE_CURATED = ROOT / "data" / "curated_el.txt"
SOURCE_SUBTLEX = ROOT / "data" / "SUBTLEX-GR_restricted.txt"
DATA_DIR = ROOT / "data"
SCORES_PATH = DATA_DIR / "word_scores.json"

SUBTLEX_LINE = re.compile(r'^\d+\s+"([^"]+)"\s+(\d+)\s+')
MIN_LENGTH = 3
MAX_LENGTH = 15


def _add_word(
    buckets: dict[int, dict[str, int]],
    raw: str,
    freq: int,
    rejected: list[tuple[str, str]],
) -> None:
    word = normalize_word(raw)
    if not word or not (MIN_LENGTH <= len(word) <= MAX_LENGTH):
        return
    reason = rejection_reason(word, len(word))
    if reason:
        rejected.append((raw, reason))
        return
    prev = buckets[len(word)].get(word, 0)
    buckets[len(word)][word] = max(prev, freq)


def load_subtlex(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SUBTLEX_LINE.match(line)
        if not match:
            continue
        rows.append((match.group(1), int(match.group(2))))
    return rows


def main() -> int:
    buckets: dict[int, dict[str, int]] = defaultdict(dict)
    rejected: list[tuple[str, str]] = []

    if SOURCE_SUBTLEX.exists():
        for raw, freq in load_subtlex(SOURCE_SUBTLEX):
            _add_word(buckets, raw, freq, rejected)
        print(f"SUBTLEX source: {sum(len(v) for v in buckets.values())} accepted so far")
    else:
        print(f"Warning: missing {SOURCE_SUBTLEX}")

    if SOURCE_CURATED.exists():
        for line in SOURCE_CURATED.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            _add_word(buckets, raw, freq=1, rejected=rejected)

    for path in sorted(DATA_DIR.glob("words_*.txt")):
        path.unlink()

    scores: dict[str, int] = {}
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        words_freq = buckets.get(length)
        if not words_freq:
            continue
        words = sorted(words_freq)
        out = DATA_DIR / f"words_{length}.txt"
        out.write_text(
            f"# Validated Greek words — length {length}\n" + "\n".join(words) + "\n",
            encoding="utf-8",
        )
        for word in words:
            freq = words_freq[word]
            scores[word] = freq
        print(f"words_{length}.txt: {len(words)} words")

    SCORES_PATH.write_text(
        json.dumps(scores, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"word_scores.json: {len(scores)} entries")
    print(f"Rejected: {len(rejected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
