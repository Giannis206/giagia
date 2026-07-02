#!/usr/bin/env python3
"""Validate all dictionary files and print a report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import dictionary_stats, load_dictionary, load_dictionary_report


def main() -> int:
    data_dir = ROOT / "data"
    report = load_dictionary_report(data_dir)
    dictionary, scores = load_dictionary(data_dir)

    print("=== Dictionary validation report ===\n")
    print("Accepted counts by length:")
    for length, words in sorted(report.accepted.items()):
        print(f"  {length}: {len(words)} words")

    print(f"\nTotal accepted: {sum(len(w) for w in report.accepted.values())}")
    print(f"Total rejected: {len(report.rejected)}")

    if report.rejected:
        print("\nSample rejections:")
        for raw, reason in report.rejected[:20]:
            print(f"  - {raw!r}: {reason}")

    print("\nLoaded dictionary (post-validation):")
    for length, count in dictionary_stats(dictionary).items():
        sample = sorted(dictionary[length])[:5]
        print(f"  {length}: {count} — e.g. {', '.join(sample)}")

    missing_lengths = [n for n in range(3, 16) if n not in dictionary]
    if missing_lengths:
        print(f"\nMissing lengths: {missing_lengths}")

    return 0 if not report.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
