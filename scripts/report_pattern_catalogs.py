#!/usr/bin/env python3
"""Report discovered pattern catalogs and optional benchmark diversity stats."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.patterns import (
    CATALOG_SIZES,
    get_pattern_entries,
)
from crossword.pattern_scoring import block_density
from crossword.solver import CrosswordGenerationError, generate_crossword
from crossword.word_store import get_word_store


def _report_size(size: int, *, top_n: int) -> None:
    entries = get_pattern_entries(size)
    primary = [e for e in entries if e.tier == "primary"]
    fallback = [e for e in entries if e.tier == "fallback"]
    print(f"\n=== {size}x{size} catalog ===")
    print(f"  total unique patterns: {len(entries)}")
    print(f"  primary: {len(primary)} | fallback: {len(fallback)}")
    ranked = sorted(entries, key=lambda e: (-e.layout_score, e.id))
    print(f"  top {min(top_n, len(ranked))} by score:")
    for entry in ranked[:top_n]:
        cells = size * size
        density = block_density(size, entry.black_square_count)
        hist = entry.slot_histogram or {}
        print(
            f"    {entry.id} | tier={entry.tier} | score={entry.layout_score:.2f} | "
            f"blacks={entry.black_square_count} ({density:.1%}) | "
            f"slots={entry.total_slot_count} | max={entry.max_slot_length} | "
            f"hist={dict(sorted(hist.items()))}"
        )


def _benchmark_size(
    size: int,
    *,
    seeds: list[int],
    data_dir: Path,
    store,
) -> None:
    pattern_ids: list[str] = []
    ok = 0
    times: list[float] = []
    length_dist: Counter[int] = Counter()
    for seed in seeds:
        t0 = time.perf_counter()
        try:
            result = generate_crossword(
                data_dir=data_dir,
                size=size,
                seed=seed,
                word_store=store,
            )
            elapsed = time.perf_counter() - t0
            ok += 1
            times.append(elapsed)
            if result.pattern_id:
                pattern_ids.append(result.pattern_id)
            for w in result.words:
                length_dist[len(w)] += 1
        except CrosswordGenerationError:
            times.append(time.perf_counter() - t0)
    unique = len(set(pattern_ids))
    print(f"\n--- benchmark {size}x{size} ({len(seeds)} seeds) ---")
    print(f"  success: {ok}/{len(seeds)} ({ok / len(seeds):.0%})")
    if times:
        print(f"  avg time: {sum(times) / len(times):.1f}s")
    print(f"  unique pattern ids used: {unique}")
    if pattern_ids:
        counts = Counter(pattern_ids)
        print(f"  pattern usage: {dict(counts.most_common(8))}")
    if length_dist:
        print(f"  word-length dist: {dict(sorted(length_dist.items()))}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pattern catalog diagnostics")
    parser.add_argument(
        "--sizes",
        type=str,
        default="7,8,10,12",
        help="Comma-separated grid sizes",
    )
    parser.add_argument("--top", type=int, default=8, help="Top patterns to show")
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run generation benchmark and report pattern-id diversity",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=12,
        help="Benchmark attempts per size",
    )
    args = parser.parse_args(argv)
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]

    for size in sizes:
        if size not in CATALOG_SIZES:
            print(f"\n(size {size} has no catalog — skipped)")
            continue
        _report_size(size, top_n=args.top)

    if args.benchmark:
        data_dir = ROOT / "data"
        store = get_word_store(data_dir)
        base = 6000
        for size in sizes:
            if size not in CATALOG_SIZES:
                continue
            seeds = [base + size * 100 + i for i in range(1, args.attempts + 1)]
            _benchmark_size(size, seeds=seeds, data_dir=data_dir, store=store)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
