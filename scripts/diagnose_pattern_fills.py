#!/usr/bin/env python3
"""Targeted fill diagnostics for 10x10 and 12x12 — no full benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import load_dictionary
from crossword.patterns import get_pattern_entries, pattern_to_grid
from crossword.slots import extract_slots
from crossword.pattern_classification import (
    load_profiles_from_diagnostics,
    summarize_diagnostics_10,
)
from crossword.solve_diagnostics import (
    PatternAttemptDiagnostic,
    ac3_is_uninformative,
    analyze_presearch,
)
from crossword.pattern_stats import get_pattern_stats_tracker
from crossword.solver import CrosswordGenerationError, generate_crossword


def _seeds(size: int, count: int, base: int) -> list[int]:
    return [base + size * 100 + i for i in range(1, count + 1)]


def scan_catalog_presearch(size: int, dictionary: dict) -> list[dict]:
    rows: list[dict] = []
    for entry in get_pattern_entries(size):
        if entry.tier == "archive":
            continue
        grid = pattern_to_grid(entry.grid)
        ps = analyze_presearch(
            pattern_id=entry.id,
            slots=extract_slots(grid),
            dictionary=dictionary,
            grid_size=size,
        )
        rows.append(ps.to_dict())
    return rows


def run_seeds(
    size: int,
    seeds: list[int],
    data_dir: Path,
) -> tuple[list[dict], list[PatternAttemptDiagnostic]]:
    attempts: list[PatternAttemptDiagnostic] = []
    run_rows: list[dict] = []

    for seed in seeds:
        attempt_diags: list[PatternAttemptDiagnostic] = []
        t0 = time.perf_counter()
        try:
            result = generate_crossword(
                data_dir=data_dir,
                size=size,
                seed=seed,
                word_store=None,
                attempt_diags=attempt_diags,
            )
            elapsed = time.perf_counter() - t0
            run_rows.append({
                "seed": seed,
                "success": True,
                "elapsed_s": round(elapsed, 2),
                "pattern_id": result.pattern_id,
                "attempts": len(attempt_diags),
            })
        except CrosswordGenerationError as exc:
            elapsed = time.perf_counter() - t0
            run_rows.append({
                "seed": seed,
                "success": False,
                "elapsed_s": round(elapsed, 2),
                "diagnostics": exc.diagnostics,
                "attempts": len(attempt_diags),
            })
        attempts.extend(attempt_diags)

    return run_rows, attempts


def summarize(attempts: list[PatternAttemptDiagnostic]) -> dict:
    by_pattern: dict[str, list[PatternAttemptDiagnostic]] = defaultdict(list)
    for a in attempts:
        by_pattern[a.pattern_id].append(a)

    late_fail: list[str] = []
    reliable: list[str] = []
    uninformative: list[str] = []
    presearch_cut: list[str] = []
    failure_classes: Counter[str] = Counter()
    failed_times: list[float] = []
    late_fail_times: list[float] = []
    presearch_times: list[float] = []

    for pid, group in by_pattern.items():
        successes = sum(1 for g in group if g.success)
        late = sum(1 for g in group if g.is_late_fail)
        pre = sum(1 for g in group if g.presearch_rejected)
        uni = any(g.ac3_uninformative for g in group)
        if successes > 0 and late == 0:
            reliable.append(pid)
        if late >= 1 and successes == 0:
            late_fail.append(pid)
        if pre > 0:
            presearch_cut.append(pid)
        if uni and successes == 0:
            uninformative.append(pid)

    for a in attempts:
        failure_classes[a.failure_class] += 1
        if a.presearch_rejected:
            presearch_times.append(a.elapsed_seconds)
        elif not a.success:
            failed_times.append(a.elapsed_seconds)
            if a.is_late_fail:
                late_fail_times.append(a.elapsed_seconds)

    return {
        "total_attempts": len(attempts),
        "late_fail_patterns": sorted(late_fail),
        "uninformative_ac3_patterns": sorted(set(uninformative)),
        "reliable_patterns": sorted(reliable),
        "presearch_rejected_patterns": sorted(set(presearch_cut)),
        "failure_class_counts": dict(failure_classes),
        "avg_failed_runtime_s": round(
            sum(failed_times) / len(failed_times), 2
        ) if failed_times else 0.0,
        "avg_late_fail_runtime_s": round(
            sum(late_fail_times) / len(late_fail_times), 2
        ) if late_fail_times else 0.0,
        "avg_presearch_reject_runtime_s": round(
            sum(presearch_times) / len(presearch_times), 2
        ) if presearch_times else 0.0,
        "presearch_reject_count": sum(1 for a in attempts if a.presearch_rejected),
        "quick_probe_fail_count": sum(1 for a in attempts if a.quick_probe_failed),
        "late_fail_count": sum(1 for a in attempts if a.is_late_fail),
        "ac3_uninformative_count": sum(
            1 for a in attempts if a.ac3_uninformative
        ),
        "solve_attempt_count": sum(
            1 for a in attempts
            if not a.presearch_rejected and not a.success and a.elapsed_seconds > 0
        ) + sum(1 for a in attempts if a.success),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Targeted pattern fill diagnostics")
    parser.add_argument("--sizes", default="10,12")
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--base", type=int, default=6000)
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "fill_diagnostics.json")
    args = parser.parse_args(argv)

    data_dir = ROOT / "data"
    dictionary, _ = load_dictionary(data_dir, strict=True, use_db=False)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    report: dict = {"schema_version": 1, "sizes": {}}
    if 10 in sizes:
        tier_summary = summarize_diagnostics_10(args.out.parent / "fill_diagnostics.json")
        print("\n=== prior diagnostics tier summary (10x10) ===")
        print(f"  by_tier: {tier_summary['by_tier']}")
        print(f"  with_success: {tier_summary['with_success']}")
        report["prior_tier_summary_10"] = tier_summary

    for size in sizes:
        print(f"\n=== presearch scan {size}x{size} ===")
        presearch_rows = scan_catalog_presearch(size, dictionary)
        would_reject = [r for r in presearch_rows if r.get("reject")]
        uninformed = [r for r in presearch_rows if r.get("ac3_is_uninformative")]
        print(f"  catalog patterns: {len(presearch_rows)}")
        print(f"  AC-3 uninformative: {len(uninformed)}")
        print(f"  would static presearch-reject: {len(would_reject)}")
        for row in would_reject[:5]:
            print(f"    {row['pattern_id']}: {row['reject_reason']}")

        seeds = _seeds(size, args.seeds, args.base)
        print(f"\n=== generation probe {size}x{size} seeds={seeds} ===")
        run_rows, attempts = run_seeds(size, seeds, data_dir)
        summary = summarize(attempts)
        ok = sum(1 for r in run_rows if r["success"])
        avg_run = sum(r["elapsed_s"] for r in run_rows) / len(run_rows) if run_rows else 0
        print(f"  success: {ok}/{len(seeds)}  avg_run={avg_run:.1f}s")
        print(f"  late-fail patterns: {len(summary['late_fail_patterns'])}")
        print(f"  uninformative-AC3 patterns: {len(summary['uninformative_ac3_patterns'])}")
        print(f"  reliable patterns: {summary['reliable_patterns']}")
        print(f"  presearch cuts: {summary['presearch_reject_count']} "
              f"(quick_probe={summary['quick_probe_fail_count']})")
        print(f"  solve-stage attempts: {summary.get('solve_attempt_count', 0)}")
        if size == 10:
            tiers = get_pattern_stats_tracker().summary()
            core = [p for p, s in tiers.items() if s.get("successes", 0) > 0]
            print(f"  runtime core promotions: {core}")
        print(f"  avg failed runtime: {summary['avg_failed_runtime_s']}s")
        print(f"  avg late-fail runtime: {summary['avg_late_fail_runtime_s']}s")
        print(f"  failure classes: {summary['failure_class_counts']}")

        report["sizes"][str(size)] = {
            "presearch_scan": presearch_rows,
            "runs": run_rows,
            "attempts": [a.to_dict() for a in attempts],
            "summary": summary,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
