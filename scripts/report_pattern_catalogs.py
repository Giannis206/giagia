#!/usr/bin/env python3
"""Pattern catalog diagnostics and generation benchmarks."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.patterns import CATALOG_SIZES, get_pattern_entries
from crossword.pattern_scoring import block_density
from crossword.solver import CrosswordGenerationError, generate_crossword

_BENCH_DIAG = {"ac3_early_rejects": 0, "fillability_rejects": 0, "starting_letter_warnings": 0}


def _report_size(size: int, *, top_n: int) -> None:
    entries = get_pattern_entries(size)
    selectable = [e for e in entries if e.fillability_passed and e.tier != "archive"]
    primary = [e for e in selectable if e.tier == "primary"]
    fallback = [e for e in selectable if e.tier == "fallback"]
    print(f"\n=== {size}x{size} catalog ===")
    print(f"  total entries: {len(entries)} | selectable: {len(selectable)}")
    print(f"  primary: {len(primary)} | fallback: {len(fallback)}")
    ranked = sorted(selectable, key=lambda e: (-e.selection_score, e.id))
    print(f"  top {min(top_n, len(ranked))} by combined/fillability score:")
    for entry in ranked[:top_n]:
        density = block_density(size, entry.black_square_count)
        hist = entry.slot_histogram or {}
        print(
            f"    {entry.id} | tier={entry.tier} | combined={entry.selection_score:.2f} | "
            f"fill={entry.fillability_score:.2f} layout={entry.layout_score:.2f} | "
            f"probe={entry.probe_success_rate:.0%} | "
            f"blacks={entry.black_square_count} ({density:.1%}) | "
            f"hist={dict(sorted(hist.items()))}"
        )


def _benchmark_size(
    size: int,
    *,
    seeds: list[int],
    data_dir: Path,
) -> dict:
    pattern_ids: list[str] = []
    ok = 0
    times: list[float] = []
    length_dist: Counter[int] = Counter()
    ac3_rejects = 0
    fill_rejects = 0
    letter_warnings = 0

    for seed in seeds:
        t0 = time.perf_counter()
        try:
            result = generate_crossword(
                data_dir=data_dir,
                size=size,
                seed=seed,
                word_store=None,
            )
            elapsed = time.perf_counter() - t0
            ok += 1
            times.append(elapsed)
            if result.pattern_id:
                pattern_ids.append(result.pattern_id)
            for w in result.words:
                length_dist[len(w)] += 1
        except CrosswordGenerationError as exc:
            times.append(time.perf_counter() - t0)
            if exc.diagnostics:
                if "ac3_early_rejects=" in exc.diagnostics:
                    try:
                        part = exc.diagnostics.split("ac3_early_rejects=")[1].split(";")[0]
                        ac3_rejects += int(part)
                    except ValueError:
                        pass
                if "fillability_rejects=" in exc.diagnostics:
                    try:
                        part = exc.diagnostics.split("fillability_rejects=")[1].split(";")[0]
                        fill_rejects += int(part)
                    except ValueError:
                        pass

    unique = len(set(pattern_ids))
    row = {
        "size": size,
        "success": ok,
        "attempts": len(seeds),
        "rate": ok / len(seeds) if seeds else 0.0,
        "avg_time": sum(times) / len(times) if times else 0.0,
        "unique_patterns": unique,
        "pattern_ids": pattern_ids,
        "length_dist": dict(sorted(length_dist.items())),
        "ac3_rejects": ac3_rejects,
        "fill_rejects": fill_rejects,
    }
    print(f"\n--- benchmark {size}x{size} ({len(seeds)} seeds) ---")
    print(f"  success: {ok}/{len(seeds)} ({row['rate']:.0%})")
    print(f"  avg time: {row['avg_time']:.1f}s")
    print(f"  unique pattern ids: {unique}")
    if pattern_ids:
        print(f"  pattern usage: {dict(Counter(pattern_ids).most_common(8))}")
    if length_dist:
        print(f"  word-length dist: {row['length_dist']}")
    print(f"  ac3 early rejects (failed runs): {ac3_rejects}")
    print(f"  fillability rejects (failed runs): {fill_rejects}")
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pattern catalog diagnostics")
    parser.add_argument("--sizes", type=str, default="7,8,10,12")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args(argv)
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]

    for size in sizes:
        if size not in CATALOG_SIZES:
            print(f"\n(size {size} has no catalog — skipped)")
            continue
        _report_size(size, top_n=args.top)

    if args.benchmark:
        data_dir = ROOT / "data"
        base = 6000
        results = []
        for size in sizes:
            if size not in CATALOG_SIZES:
                continue
            seeds = [base + size * 100 + i for i in range(1, args.attempts + 1)]
            results.append(_benchmark_size(size, seeds=seeds, data_dir=data_dir))
        print("\n=== benchmark summary ===")
        for row in results:
            print(
                f"  {row['size']}x{row['size']}: {row['success']}/{row['attempts']} "
                f"({row['rate']:.0%}) avg={row['avg_time']:.1f}s "
                f"patterns={row['unique_patterns']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
