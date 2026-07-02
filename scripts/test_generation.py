#!/usr/bin/env python3
"""Test crossword generation for standard grid sizes."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from crossword.dictionary import dictionary_stats, load_dictionary
from crossword.solver import CrosswordGenerationError, generate_crossword

SIZES = (7, 8, 10, 12, 15)
ATTEMPTS_PER_SIZE = 2


def main() -> int:
    data_dir = ROOT / "data"
    dictionary, _ = load_dictionary(data_dir)
    print("=== Dictionary by length ===")
    for length, count in dictionary_stats(dictionary).items():
        print(f"  {length}: {count} words")
    print()

    results: list[tuple[int, bool, int, list[str]]] = []

    for size in SIZES:
        print(f"--- Size {size}x{size} ---")
        success = False
        word_count = 0
        sample: list[str] = []

        for attempt in range(1, ATTEMPTS_PER_SIZE + 1):
            t0 = time.perf_counter()
            try:
                result = generate_crossword(
                    data_dir=data_dir,
                    size=size,
                    seed=1000 + size * 10 + attempt,
                    diagnostic=True,
                    max_pattern_attempts=20,
                )
                elapsed = time.perf_counter() - t0
                success = True
                word_count = len(result.words)
                sample = result.words[:12]
                print(
                    f"  attempt {attempt}: OK in {elapsed:.1f}s — "
                    f"{word_count} words — sample: {', '.join(sample)}"
                )
                break
            except CrosswordGenerationError as exc:
                elapsed = time.perf_counter() - t0
                print(f"  attempt {attempt}: FAIL in {elapsed:.1f}s")
                if exc.diagnostics:
                    print(f"    diagnostics: {exc.diagnostics}")

        if not success:
            print(f"  => size {size} failed all {ATTEMPTS_PER_SIZE} attempts")
        results.append((size, success, word_count, sample))
        print()

    print("=== Summary ===")
    reliable: list[int] = []
    failed: list[int] = []

    for size, ok, count, sample in results:
        status = "OK" if ok else "FAIL"
        sample_txt = ", ".join(sample[:8]) if sample else "-"
        print(f"  {size}x{size}: {status} | words={count} | sample={sample_txt}")
        if ok:
            reliable.append(size)
        else:
            failed.append(size)

    if failed:
        print(f"\nSystematic failures: {failed}")
    if reliable:
        print(f"Working sizes (at least one attempt): {reliable}")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
