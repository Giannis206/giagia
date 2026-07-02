#!/usr/bin/env python3
"""Generation benchmark for standard grid sizes using the word database."""

from __future__ import annotations

import logging
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from crossword.solver import CrosswordGenerationError, generate_crossword
from crossword.word_store import get_word_store

SIZES = (7, 8, 10, 12)
ATTEMPTS_PER_SIZE = 3


def main() -> int:
    data_dir = ROOT / "data"
    db_path = data_dir / "greek_words.db"
    if not db_path.exists():
        print("Missing greek_words.db — run: python scripts/build_word_db.py")
        return 1

    store = get_word_store(data_dir)
    stats = store.stats()
    print("=== Word database ===")
    print(f"Total: {stats.total_allowed}")
    for length in range(3, 13):
        print(f"  {length}: {stats.by_length.get(length, 0)}")
    print()

    results: list[dict] = []

    for size in SIZES:
        print(f"--- {size}x{size} ---")
        ok_count = 0
        times: list[float] = []
        last_words: list[str] = []
        length_dist: Counter[int] = Counter()

        for attempt in range(1, ATTEMPTS_PER_SIZE + 1):
            seed = 5000 + size * 100 + attempt
            t0 = time.perf_counter()
            try:
                result = generate_crossword(
                    data_dir=data_dir,
                    size=size,
                    seed=seed,
                    diagnostic=True,
                    word_store=store,
                )
                elapsed = time.perf_counter() - t0
                ok_count += 1
                times.append(elapsed)
                last_words = result.words
                for w in result.words:
                    length_dist[len(w)] += 1
                print(
                    f"  attempt {attempt}: OK {elapsed:.1f}s | "
                    f"{len(result.words)} words | sample: {', '.join(result.words[:6])}"
                )
            except CrosswordGenerationError as exc:
                elapsed = time.perf_counter() - t0
                times.append(elapsed)
                print(f"  attempt {attempt}: FAIL {elapsed:.1f}s")
                if exc.diagnostics:
                    print(f"    {exc.diagnostics[:200]}")

        rate = ok_count / ATTEMPTS_PER_SIZE
        avg = sum(times) / len(times) if times else 0.0
        results.append(
            {
                "size": size,
                "success_rate": rate,
                "avg_seconds": avg,
                "words": len(last_words),
                "length_dist": dict(sorted(length_dist.items())),
                "sample": last_words[:8],
            }
        )
        print(f"  => success {ok_count}/{ATTEMPTS_PER_SIZE}, avg {avg:.1f}s\n")

    print("=== Summary ===")
    for row in results:
        status = "OK" if row["success_rate"] > 0 else "FAIL"
        print(
            f"  {row['size']}x{row['size']}: {status} | "
            f"rate={row['success_rate']:.0%} | avg={row['avg_seconds']:.1f}s | "
            f"lengths={row['length_dist']}"
        )
        if row["sample"]:
            print(f"    sample: {', '.join(row['sample'])}")

    failed = [r["size"] for r in results if r["success_rate"] == 0]
    if failed:
        print(f"\nUnreliable sizes: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
