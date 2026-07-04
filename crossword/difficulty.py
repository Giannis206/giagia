"""Puzzle difficulty modes (post-solve presentation only)."""

from __future__ import annotations

from typing import Literal

DifficultyMode = Literal["normal", "easy"]

DEFAULT_DIFFICULTY: DifficultyMode = "normal"


def parse_difficulty(value: str | None) -> DifficultyMode:
    if value is None:
        return DEFAULT_DIFFICULTY
    normalized = value.strip().lower()
    if normalized in ("easy", "e", "γιαγια", "giagia"):
        return "easy"
    if normalized in ("normal", "n", "default"):
        return "normal"
    raise ValueError(f"Unknown difficulty mode: {value!r} (use 'easy' or 'normal')")
