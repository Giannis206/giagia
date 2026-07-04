"""SQLite persistence for crossword pattern runtime statistics."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pattern_runtime_stats (
    pattern_id TEXT PRIMARY KEY,
    grid_size INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    total_fill_seconds REAL NOT NULL DEFAULT 0,
    total_probe_seconds REAL NOT NULL DEFAULT 0,
    probe_attempts INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    last_success_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pattern_runtime_grid
    ON pattern_runtime_stats(grid_size);
"""


@dataclass
class PersistedPatternStats:
    pattern_id: str
    grid_size: int = 0
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_fill_seconds: float = 0.0
    total_probe_seconds: float = 0.0
    probe_attempts: int = 0
    last_used_at: str | None = None
    last_success_at: str | None = None

    @property
    def success_ratio(self) -> float:
        if self.attempts == 0:
            return 0.5
        return self.successes / self.attempts

    @property
    def avg_fill_seconds(self) -> float:
        if self.successes > 0:
            return self.total_fill_seconds / self.successes
        if self.attempts > 0:
            return self.total_fill_seconds / self.attempts
        return 4.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PatternRuntimeStore:
    """Read/write pattern stats in greek_words.db (or dedicated path)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA_SQL)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get(self, pattern_id: str) -> PersistedPatternStats:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM pattern_runtime_stats WHERE pattern_id = ?",
            (pattern_id,),
        ).fetchone()
        if row is None:
            return PersistedPatternStats(pattern_id=pattern_id)
        return PersistedPatternStats(
            pattern_id=row["pattern_id"],
            grid_size=int(row["grid_size"] or 0),
            attempts=int(row["attempts"] or 0),
            successes=int(row["successes"] or 0),
            failures=int(row["failures"] or 0),
            total_fill_seconds=float(row["total_fill_seconds"] or 0),
            total_probe_seconds=float(row["total_probe_seconds"] or 0),
            probe_attempts=int(row["probe_attempts"] or 0),
            last_used_at=row["last_used_at"],
            last_success_at=row["last_success_at"],
        )

    def record_selection(self, pattern_id: str, *, grid_size: int = 0) -> None:
        now = _utc_now()
        with self._lock:
            conn = self.connect()
            conn.execute(
                """
                INSERT INTO pattern_runtime_stats (pattern_id, grid_size, last_used_at)
                VALUES (?, ?, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    grid_size = CASE WHEN excluded.grid_size > 0
                        THEN excluded.grid_size ELSE pattern_runtime_stats.grid_size END,
                    last_used_at = excluded.last_used_at
                """,
                (pattern_id, grid_size, now),
            )
            conn.commit()

    def record_fill(
        self,
        pattern_id: str,
        *,
        grid_size: int,
        success: bool,
        fill_seconds: float,
    ) -> None:
        now = _utc_now()
        with self._lock:
            conn = self.connect()
            conn.execute(
                """
                INSERT INTO pattern_runtime_stats (
                    pattern_id, grid_size, attempts, successes, failures,
                    total_fill_seconds, last_used_at, last_success_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    grid_size = CASE WHEN excluded.grid_size > 0
                        THEN excluded.grid_size ELSE pattern_runtime_stats.grid_size END,
                    attempts = pattern_runtime_stats.attempts + 1,
                    successes = pattern_runtime_stats.successes + excluded.successes,
                    failures = pattern_runtime_stats.failures + excluded.failures,
                    total_fill_seconds = pattern_runtime_stats.total_fill_seconds
                        + excluded.total_fill_seconds,
                    last_used_at = excluded.last_used_at,
                    last_success_at = CASE
                        WHEN excluded.last_success_at IS NOT NULL
                        THEN excluded.last_success_at
                        ELSE pattern_runtime_stats.last_success_at END
                """,
                (
                    pattern_id,
                    grid_size,
                    1 if success else 0,
                    0 if success else 1,
                    fill_seconds,
                    now,
                    now if success else None,
                ),
            )
            conn.commit()

    def record_probe(
        self,
        pattern_id: str,
        *,
        grid_size: int,
        probe_seconds: float,
    ) -> None:
        with self._lock:
            conn = self.connect()
            conn.execute(
                """
                INSERT INTO pattern_runtime_stats (
                    pattern_id, grid_size, probe_attempts, total_probe_seconds
                ) VALUES (?, ?, 1, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    grid_size = CASE WHEN excluded.grid_size > 0
                        THEN excluded.grid_size ELSE pattern_runtime_stats.grid_size END,
                    probe_attempts = pattern_runtime_stats.probe_attempts + 1,
                    total_probe_seconds = pattern_runtime_stats.total_probe_seconds
                        + excluded.total_probe_seconds
                """,
                (pattern_id, grid_size, probe_seconds),
            )
            conn.commit()

    def load_all(self) -> dict[str, PersistedPatternStats]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM pattern_runtime_stats").fetchall()
        return {
            row["pattern_id"]: PersistedPatternStats(
                pattern_id=row["pattern_id"],
                grid_size=int(row["grid_size"] or 0),
                attempts=int(row["attempts"] or 0),
                successes=int(row["successes"] or 0),
                failures=int(row["failures"] or 0),
                total_fill_seconds=float(row["total_fill_seconds"] or 0),
                total_probe_seconds=float(row["total_probe_seconds"] or 0),
                probe_attempts=int(row["probe_attempts"] or 0),
                last_used_at=row["last_used_at"],
                last_success_at=row["last_success_at"],
            )
            for row in rows
        }


_STORE: PatternRuntimeStore | None = None


def get_pattern_runtime_store(db_path: Path | None = None) -> PatternRuntimeStore:
    global _STORE
    if db_path is not None:
        return PatternRuntimeStore(db_path)
    if _STORE is None:
        root = Path(__file__).resolve().parent.parent
        _STORE = PatternRuntimeStore(root / "data" / "greek_words.db")
    return _STORE
