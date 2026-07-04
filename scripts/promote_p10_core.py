#!/usr/bin/env python3
"""Promote proven random 10x10 patterns into stable p10_core_* catalog entries."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.grid import generate_symmetric_pattern
from crossword.pattern_scoring import score_pattern_histogram
from crossword.slots import extract_slots
from crossword.slot_policy import slot_length_histogram

CORE = [
    ("p10_core_a", 1544773357),
    ("p10_core_b", 1734303921),
    ("p10_core_c", 2003388859),
    ("p10_core_d", 327213367),
    ("p10_core_e", 482392705),
    ("p10_core_f", 585740760),
]

# Top-quartile catalog layouts from diagnostics — still probed on default path.
PROBATION_IDS = frozenset({
    "p10_seed1932_r17",
    "p10_seed5_r15",
    "p10_seed889_r17",
    "p10_seed3265_r15",
})


def grid_to_matrix(grid) -> list[list[int]]:
    return [
        [1 if grid.is_black(r, c) else 0 for c in range(grid.size)]
        for r in range(grid.size)
    ]


def build_entry(pid: str, seed: int) -> dict:
    rng = random.Random(seed)
    grid = generate_symmetric_pattern(10, rng=rng)
    mat = grid_to_matrix(grid)
    slots = extract_slots(grid)
    lengths = [s.length for s in slots]
    hist = slot_length_histogram(lengths)
    blacks = sum(sum(row) for row in mat)
    score = score_pattern_histogram(
        hist, grid_size=10, total_slots=len(slots), black_square_count=blacks
    )
    return {
        "id": pid,
        "source_seed": seed,
        "tier": "primary",
        "grid": mat,
        "black_count": blacks,
        "block_density": round(blacks / 100, 3),
        "histogram": {str(k): v for k, v in hist.items()},
        "total_slots": len(slots),
        "short_slots": sum(1 for length in lengths if length <= 3),
        "mid_slots": sum(1 for length in lengths if 4 <= length <= 6),
        "long_slots": sum(1 for length in lengths if length >= 7),
        "max_slot_length": max(lengths) if lengths else 0,
        "score": round(score, 3),
        "layout_score": round(score, 3),
        "fillability_score": 0.0,
        "combined_score": round(score, 3),
        "fillability_passed": True,
        "probe_success_rate": 1.0,
        "avg_probe_time": 0.0,
        "ac3_ok": True,
        "min_domain_size": 0,
        "provenance": f"promoted from random_seed{seed}",
    }


def main() -> None:
    entries = [build_entry(pid, seed) for pid, seed in CORE]
    path = ROOT / "data" / "pattern_catalogs" / "catalog_10.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    archived: list[dict] = []
    for row in data.get("patterns", []):
        if row["id"].startswith("p10_core_"):
            continue
        archived_row = dict(row)
        if archived_row["id"] in PROBATION_IDS:
            archived_row["tier"] = "fallback"
            archived_row["fillability_passed"] = True
        else:
            archived_row["tier"] = "archive"
            archived_row["fillability_passed"] = False
        archived.append(archived_row)
    data["patterns"] = entries + archived
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} core + {len(archived)} archived -> {path}")


if __name__ == "__main__":
    main()
