#!/usr/bin/env python3
"""Build data/greek_words.db from local and downloadable Greek word sources."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossword.dictionary import normalize_word, rejection_reason, word_score
from crossword.word_store import MAX_LENGTH, MIN_LENGTH, SCHEMA_SQL

DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "greek_words.db"
SOURCES_DIR = DATA_DIR / "sources"
SUBTLEX_PATH = DATA_DIR / "SUBTLEX-GR_restricted.txt"
CURATED_PATH = DATA_DIR / "curated_el.txt"
FREQ_50K_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/el/el_50k.txt"
)
FREQ_50K_PATH = SOURCES_DIR / "el_50k.txt"

SUBTLEX_LINE = re.compile(r'^\d+\s+"([^"]+)"\s+(\d+)\s+')


@dataclass
class BuildReport:
    accepted: int = 0
    rejected: int = 0
    by_length: dict[int, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    rejection_reasons: Counter[str] = field(default_factory=Counter)


def _candidate(
    raw: str,
    freq: int,
    source: str,
    bucket: dict[str, tuple[str, int, int, str]],
    report: BuildReport,
) -> None:
    original = raw.strip()
    if not original or original.startswith("#"):
        return
    word = normalize_word(original)
    if not word or not (MIN_LENGTH <= len(word) <= MAX_LENGTH):
        return
    reason = rejection_reason(word, len(word))
    if reason:
        report.rejected += 1
        report.rejection_reasons[reason] += 1
        return

    score = word_score(word, freq)
    prev = bucket.get(word)
    if prev is None or freq > prev[1] or (freq == prev[1] and score > prev[2]):
        bucket[word] = (original, freq, score, source)


def _load_subtlex(path: Path, bucket: dict, report: BuildReport) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SUBTLEX_LINE.match(line)
        if match:
            _candidate(match.group(1), int(match.group(2)), "subtlex", bucket, report)


def _load_freq_list(path: Path, bucket: dict, report: BuildReport) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        word_raw, freq_raw = parts[0], parts[1]
        try:
            freq = int(freq_raw)
        except ValueError:
            continue
        _candidate(word_raw, freq, "freq50k", bucket, report)


def _load_txt_lines(path: Path, source: str, bucket: dict, report: BuildReport) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        _candidate(line, 1, source, bucket, report)


def _load_words_files(data_dir: Path, bucket: dict, report: BuildReport) -> None:
    for path in sorted(data_dir.glob("words_*.txt")):
        _load_txt_lines(path, path.name, bucket, report)


def _load_json_words(path: Path, bucket: dict, report: BuildReport) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                _candidate(item, 1, path.name, bucket, report)
            elif isinstance(item, dict):
                raw = item.get("word") or item.get("text") or ""
                freq = int(item.get("freq") or item.get("frequency") or 1)
                _candidate(str(raw), freq, path.name, bucket, report)


def _load_csv_words(path: Path, bucket: dict, report: BuildReport) -> None:
    if not path.exists():
        return
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            word_key = next(
                (k for k in reader.fieldnames if k.lower() in ("word", "lemma", "text")),
                reader.fieldnames[0],
            )
            freq_key = next(
                (k for k in reader.fieldnames if k.lower() in ("freq", "frequency", "count")),
                None,
            )
            for row in reader:
                raw = row.get(word_key, "")
                freq = int(row.get(freq_key, 1)) if freq_key and row.get(freq_key) else 1
                _candidate(raw, freq, path.name, bucket, report)
        else:
            for row in csv.reader(fh):
                if row:
                    _candidate(row[0], 1, path.name, bucket, report)


def _load_extra_sources(sources_dir: Path, bucket: dict, report: BuildReport) -> None:
    if not sources_dir.exists():
        return
    for path in sorted(sources_dir.iterdir()):
        if path.suffix == ".txt":
            _load_txt_lines(path, f"sources/{path.name}", bucket, report)
        elif path.suffix == ".json":
            _load_json_words(path, bucket, report)
        elif path.suffix == ".csv":
            _load_csv_words(path, bucket, report)


def _download_freq_list(dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(FREQ_50K_URL, dest)
        return True
    except OSError as exc:
        print(f"Warning: could not download {FREQ_50K_URL}: {exc}")
        return False


def _write_db(db_path: Path, bucket: dict[str, tuple[str, int, int, str]], report: BuildReport) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    rows = []
    for word, (original, freq, score, source) in sorted(bucket.items()):
        rows.append((original, word, len(word), score, source, 1, 0))
        report.by_length[len(word)] = report.by_length.get(len(word), 0) + 1
        report.by_source[source] = report.by_source.get(source, 0) + 1
    conn.executemany(
        """
        INSERT INTO words (word_original, word_normalized, length, score, source, allowed, recent_penalty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    report.accepted = len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Greek word SQLite database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--download", action="store_true", help="Download el_50k frequency list")
    parser.add_argument("--no-download", action="store_true", help="Skip download even if missing")
    args = parser.parse_args(argv)

    bucket: dict[str, tuple[str, int, int, str]] = {}
    report = BuildReport()

    if args.download or (not args.no_download and not FREQ_50K_PATH.exists()):
        print("Downloading el_50k frequency list...")
        if _download_freq_list(FREQ_50K_PATH):
            print(f"Saved {FREQ_50K_PATH}")

    print("Loading sources...")
    _load_subtlex(SUBTLEX_PATH, bucket, report)
    _load_freq_list(FREQ_50K_PATH, bucket, report)
    _load_txt_lines(CURATED_PATH, "curated_el", bucket, report)
    _load_words_files(DATA_DIR, bucket, report)
    _load_extra_sources(SOURCES_DIR, bucket, report)

    print(f"Writing {args.db} ...")
    _write_db(args.db, bucket, report)

    print("\n=== Build report ===")
    print(f"Accepted: {report.accepted}")
    print(f"Rejected: {report.rejected}")
    print("\nBy length:")
    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        print(f"  {length}: {report.by_length.get(length, 0)}")
    print("\nBy source (unique normalized words attributed to best source):")
    for source, count in sorted(report.by_source.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")
    if report.rejection_reasons:
        print("\nTop rejection reasons:")
        for reason, count in report.rejection_reasons.most_common(10):
            print(f"  {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
