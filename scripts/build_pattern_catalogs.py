#!/usr/bin/env python3
"""Discover patterns, probe fillability, and write JSON catalogs."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import load_dictionary
from crossword.fillability import fillability_probe
from crossword.pattern_discovery import discover_patterns, tier_split
from crossword.patterns import pattern_to_grid

OUT_DIR = ROOT / "data" / "pattern_catalogs"

TIER_COUNTS: dict[int, tuple[int, int]] = {
    8: (10, 8),
    10: (10, 8),
    12: (14, 12),
}

PROBE_BY_SIZE: dict[int, tuple[int, float]] = {
    8: (1, 3.0),
    10: (3, 5.0),
    12: (2, 4.0),
}


def _probe_row(
    row: dict,
    size: int,
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
    *,
    probe_count: int,
    probe_time_cap: float,
    rng: random.Random,
) -> dict:
    grid = pattern_to_grid(row["grid"])
    layout_score = float(row.get("score", 0))
    result = fillability_probe(
        grid,
        dictionary,
        word_scores=word_scores,
        layout_score=layout_score,
        probe_count=probe_count,
        probe_time_cap=probe_time_cap,
        rng=rng,
    )
    return {
        **row,
        "fillability_score": result.fillability_score,
        "combined_score": result.combined_score,
        "fillability_passed": result.passed and (
            result.probe_verified
            or size <= 8
            or (size == 10 and result.min_domain_size >= 20)
        ),
        "probe_success_rate": result.probe_success_rate,
        "avg_probe_time": result.avg_probe_time,
        "ac3_ok": result.ac3_ok,
        "min_domain_size": result.min_domain_size,
        "bottleneck_slots": result.bottleneck_slots,
        "score": result.combined_score or layout_score,
    }


def _serialize(rows: list[dict], size: int) -> dict:
    patterns = []
    for row in rows:
        pid = row.get("id") or f"p{size}_seed{row['seed']}_r{int(row['ratio']*100)}"
        patterns.append(
            {
                "id": pid,
                "source_seed": row["seed"],
                "tier": row["tier"],
                "grid": row["grid"],
                "black_count": row["black_count"],
                "block_density": row["block_density"],
                "histogram": {str(k): v for k, v in row["histogram"].items()},
                "total_slots": row["total_slots"],
                "short_slots": row["short_slots"],
                "mid_slots": row["mid_slots"],
                "long_slots": row["long_slots"],
                "max_slot_length": row["max_slot_length"],
                "score": round(float(row.get("layout_score", row.get("score", 0))), 3),
                "layout_score": round(float(row.get("layout_score", row.get("score", 0))), 3),
                "fillability_score": round(float(row.get("fillability_score", 0)), 3),
                "combined_score": round(float(row.get("combined_score", 0)), 3),
                "fillability_passed": bool(row.get("fillability_passed", False)),
                "probe_success_rate": round(float(row.get("probe_success_rate", 0)), 3),
                "avg_probe_time": round(float(row.get("avg_probe_time", 0)), 3),
                "ac3_ok": bool(row.get("ac3_ok", False)),
                "min_domain_size": int(row.get("min_domain_size", 0)),
            }
        )
    return {"size": size, "patterns": patterns}


def build_size(
    size: int,
    max_seed: int,
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
) -> int:
    print(f"Discovering {size}x{size} (seeds 0..{max_seed - 1})...")
    rows = discover_patterns(size, max_seed=max_seed, dictionary=dictionary)
    print(f"  unique valid (layout + AC-3): {len(rows)}")

    probe_count, probe_cap = PROBE_BY_SIZE.get(size, (2, 4.0))
    rng = random.Random(size * 17 + 3)
    probed: list[dict] = []
    for row in rows:
        probed.append(
            _probe_row(
                row,
                size,
                dictionary,
                word_scores,
                probe_count=probe_count,
                probe_time_cap=probe_cap,
                rng=rng,
            )
        )
    probed.sort(key=lambda r: -float(r.get("combined_score", 0)))

    passed = [r for r in probed if r.get("fillability_passed")]
    print(f"  fillability passed: {len(passed)} / {len(probed)}")
    pool = passed if passed else probed[: max(8, len(probed) // 4)]

    primary_n, fallback_n = TIER_COUNTS.get(size, (8, 6))
    if size == 10:
        primary_n = min(primary_n, max(8, len(pool)))
    tiered = tier_split(pool, primary_count=primary_n, fallback_count=fallback_n)
    payload = _serialize(tiered, size)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"catalog_{size}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path} ({len(payload['patterns'])} patterns)")
    return len(payload["patterns"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build fillability-ranked pattern catalogs")
    parser.add_argument("--sizes", type=str, default="8,10,12")
    parser.add_argument("--max-seed", type=int, default=8000)
    args = parser.parse_args(argv)
    data_dir = ROOT / "data"
    dictionary, word_scores = load_dictionary(data_dir, strict=True, use_db=True)
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    for size in sizes:
        build_size(size, args.max_seed, dictionary, word_scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
