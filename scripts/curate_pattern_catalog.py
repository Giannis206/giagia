#!/usr/bin/env python3
"""Re-rank an existing catalog JSON using fillability probes."""

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
from crossword.patterns import pattern_to_grid

OUT_DIR = ROOT / "data" / "pattern_catalogs"

ACTIVE_PRIMARY: dict[int, int] = {
    10: 10,
    12: 0,  # hand primaries only; discovered are fallback
}


def curate_size(
    size: int,
    *,
    dictionary: dict[int, set[str]],
    word_scores: dict[str, int],
    probe_count: int,
    probe_time_cap: float,
    min_probe_rate: float,
) -> int:
    path = OUT_DIR / f"catalog_{size}.json"
    if not path.exists():
        print(f"Missing {path}")
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data.get("patterns", [])
    rng = random.Random(size * 31 + 7)
    probed: list[dict] = []

    print(f"Probing {size}x{size} ({len(patterns)} patterns)...")
    for rec in patterns:
        grid = pattern_to_grid(rec["grid"])
        layout_score = float(rec.get("layout_score", rec.get("score", 0)))
        result = fillability_probe(
            grid,
            dictionary,
            word_scores=word_scores,
            layout_score=layout_score,
            probe_count=probe_count,
            probe_time_cap=probe_time_cap,
            rng=rng,
        )
        passed = result.ac3_ok and not result.zero_domain_detected
        if size == 12:
            passed = passed and result.probe_verified
        elif size == 10:
            passed = passed and (
                result.probe_verified or result.min_domain_size >= 20
            )
        else:
            passed = passed and (
                result.probe_verified or result.min_domain_size >= 5
            )
        probed.append(
            {
                **rec,
                "layout_score": layout_score,
                "fillability_score": result.fillability_score,
                "combined_score": result.combined_score,
                "fillability_passed": passed,
                "probe_success_rate": result.probe_success_rate,
                "avg_probe_time": result.avg_probe_time,
                "ac3_ok": result.ac3_ok,
                "min_domain_size": result.min_domain_size,
            }
        )
        status = "PASS" if passed else "fail"
        print(
            f"  {rec['id']}: {status} combined={result.combined_score:.1f} "
            f"probe={result.probe_success_rate:.0%} ac3={result.ac3_ok}"
        )

    probed.sort(key=lambda r: -float(r.get("combined_score", 0)))
    passed_rows = [r for r in probed if r.get("fillability_passed")]
    print(f"  => {len(passed_rows)} / {len(probed)} passed")

    active_primary = ACTIVE_PRIMARY.get(size, len(passed_rows))
    for idx, row in enumerate(probed):
        if not row.get("fillability_passed"):
            row["tier"] = "archive"
        elif idx < active_primary:
            row["tier"] = "primary"
        else:
            row["tier"] = "fallback"

    payload = {"size": size, "patterns": probed}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path}")
    return len(passed_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Curate catalogs by fillability")
    parser.add_argument("--sizes", type=str, default="10,12")
    parser.add_argument("--probe-count", type=int, default=1)
    parser.add_argument("--probe-time-cap", type=float, default=5.0)
    parser.add_argument("--min-probe-rate", type=float, default=0.34)
    args = parser.parse_args(argv)

    dictionary, word_scores = load_dictionary(ROOT / "data", strict=True, use_db=True)
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    for size in sizes:
        curate_size(
            size,
            dictionary=dictionary,
            word_scores=word_scores,
            probe_count=args.probe_count,
            probe_time_cap=args.probe_time_cap,
            min_probe_rate=args.min_probe_rate,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
