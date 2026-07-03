#!/usr/bin/env python3
"""Discover patterns and write JSON catalogs under data/pattern_catalogs/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.pattern_discovery import discover_patterns, tier_split

OUT_DIR = ROOT / "data" / "pattern_catalogs"

TIER_COUNTS: dict[int, tuple[int, int]] = {
    8: (10, 8),
    10: (12, 10),
    12: (14, 12),
}


def _serialize(rows: list[dict], size: int) -> dict:
    patterns = []
    for idx, row in enumerate(rows):
        pid = f"p{size}_seed{row['seed']}_r{int(row['ratio']*100)}"
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
                "score": round(row["score"], 3),
            }
        )
    return {"size": size, "patterns": patterns}


def build_size(size: int, max_seed: int) -> int:
    print(f"Discovering {size}x{size} (seeds 0..{max_seed - 1})...")
    rows = discover_patterns(size, max_seed=max_seed)
    print(f"  unique valid: {len(rows)}")
    primary_n, fallback_n = TIER_COUNTS.get(size, (8, 6))
    tiered = tier_split(rows, primary_count=primary_n, fallback_count=fallback_n)
    payload = _serialize(tiered, size)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"catalog_{size}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path} ({len(payload['patterns'])} patterns)")
    return len(payload["patterns"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build pattern JSON catalogs")
    parser.add_argument(
        "--sizes",
        type=str,
        default="8,10,12",
        help="Comma-separated grid sizes",
    )
    parser.add_argument("--max-seed", type=int, default=8000)
    args = parser.parse_args(argv)
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    for size in sizes:
        build_size(size, args.max_seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
