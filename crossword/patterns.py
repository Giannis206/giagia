"""Pre-defined symmetric crossword block patterns (180° rotational symmetry)."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from crossword.pattern_stats import PatternStatsTracker

from crossword.grid import BLACK, Grid, WHITE
from crossword.pattern_classification import (
    load_profiles_from_diagnostics,
    partition_catalog_entries_10,
    partition_catalog_entries_12,
)
from crossword.slots import extract_slots
from crossword.slot_policy import slot_length_histogram
from crossword.validate import validate_pattern

CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "pattern_catalogs"
CATALOG_SIZES = frozenset({7, 8, 10, 12})

CATALOG_TIME_FRACTION: dict[int, float] = {
    7: 1.0,
    8: 0.9,
    10: 0.42,
    12: 0.40,
}

# Legacy 12x12 fallback ids used when include_legacy=False
_P12_FALLBACK_IDS = frozenset({
    "p12_fb_seed487",
    "p12_fb_seed1708",
    "p12_fb_seed1883",
    "p12_fb_seed1968",
})

# Hand-tuned 12x12 primaries — always tried before discovered layouts
_P12_HAND_PRIMARY_IDS = frozenset({
    "p12_i_seed89",
    "p12_j_seed292",
    "p12_k_seed983",
})

_P12_HAND_PRIMARY_ORDER = (
    "p12_i_seed89",
    "p12_j_seed292",
    "p12_k_seed983",
)

# Proven 10x10 layouts promoted from successful random_seed diagnostics runs.
_P10_CORE_IDS = frozenset({
    "p10_core_a",
    "p10_core_b",
    "p10_core_c",
    "p10_core_d",
    "p10_core_e",
    "p10_core_f",
})

_P10_CORE_ORDER = (
    "p10_core_a",
    "p10_core_b",
    "p10_core_c",
    "p10_core_d",
    "p10_core_e",
    "p10_core_f",
)

P10_CORE_COUNT = len(_P10_CORE_ORDER)

# Hand-tuned 12x12 catalog attempts before any discovered late fallback.
P12_PRIMARY_COUNT = len(_P12_HAND_PRIMARY_ORDER)
P12_HAND_CATALOG_LIMIT = P12_PRIMARY_COUNT + len(_P12_FALLBACK_IDS)

MAX_CATALOG_PATTERNS: dict[int, int] = {
    10: P10_CORE_COUNT + 4,
    12: P12_PRIMARY_COUNT + 2,
}


def entry_is_hand_primary(entry: PatternEntry) -> bool:
    return entry.id in _P12_HAND_PRIMARY_IDS


def entry_is_core_10(entry: PatternEntry) -> bool:
    return entry.id in _P10_CORE_IDS


def entry_is_core_12(entry: PatternEntry) -> bool:
    from crossword.pattern_classification import classify_pattern_12

    return classify_pattern_12(
        entry.id,
        max_slot_length=entry.max_slot_length,
    ) == "core_catalog"


def is_core_10_pattern_id(pattern_id: str) -> bool:
    return pattern_id in _P10_CORE_IDS


def entry_is_discovered_12(entry: PatternEntry) -> bool:
    return (
        len(entry.grid) == 12
        and entry.id not in _P12_HAND_PRIMARY_IDS
        and entry.id not in _P12_FALLBACK_IDS
    )


# 0 = white (letter cell), 1 = black block

PatternTier = Literal["primary", "fallback", "archive"]


@dataclass(frozen=True)
class PatternEntry:
    """Metadata for a pre-validated crossword block pattern."""

    id: str
    source_seed: int | None
    grid: list[list[int]]
    max_slot_length: int
    total_slot_count: int
    tier: PatternTier
    slot_histogram: dict[int, int] | None = None
    black_square_count: int = 0
    layout_score: float = 0.0
    fillability_score: float = 0.0
    combined_score: float = 0.0
    fillability_passed: bool = True
    probe_success_rate: float = 0.0

    @property
    def selection_score(self) -> float:
        if self.combined_score > 0:
            return self.combined_score
        if self.fillability_score > 0:
            return self.fillability_score * 0.65 + self.layout_score * 0.35
        return self.layout_score

    @property
    def name(self) -> str:
        return self.id


def pattern_to_grid(pattern: list[list[int]]) -> Grid:
    n = len(pattern)
    cells = [
        [BLACK if pattern[r][c] else WHITE for c in range(n)]
        for r in range(n)
    ]
    return Grid(n, cells)


def pattern_to_rows(pattern: list[list[int]]) -> list[str]:
    return ["".join("#" if cell else "." for cell in row) for row in pattern]


def _validate_stored_pattern(pattern: list[list[int]], size: int) -> None:
    if len(pattern) != size or any(len(row) != size for row in pattern):
        raise ValueError(f"Pattern must be {size}x{size}")
    grid = pattern_to_grid(pattern)
    slots = extract_slots(grid)
    validate_pattern(grid, slots)


# Generated with generate_symmetric_pattern(12) seeds 0–7; validated at import.
_P12_A = [
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
]

_P12_B = [
    [0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0],
]

_P12_C = [
    [1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1],
]

_P12_D = [
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
]

_P12_E = [
    [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1],
    [1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1],
]

_P12_F = [
    [0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1],
    [1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1],
    [1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0],
]

_P12_G = [
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
]

_P12_H = [
    [1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1],
]

# Shorter max-slot patterns (seeds 89, 292, 983) — easier 12x12 fills.
_P12_I = [
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1],
    [1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1],
    [1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
]

_P12_J = [
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
]

_P12_K = [
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
]

# Fallback tier — shorter max slots than legacy A–H patterns (seeds 487, 1708, 1883, 1968).
_P12_FALLBACK_487 = [
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
]

_P12_FALLBACK_1708 = [
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
]

_P12_FALLBACK_1883 = [
    [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0],
]

_P12_FALLBACK_1968 = [
    [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
]


def _slot_stats(pattern: list[list[int]]) -> tuple[int, int]:
    grid = pattern_to_grid(pattern)
    slots = extract_slots(grid)
    lengths = [s.length for s in slots]
    return max(lengths), len(slots)


def _entry(
    pattern_id: str,
    source_seed: int | None,
    pattern: list[list[int]],
    tier: PatternTier,
) -> PatternEntry:
    max_len, total = _slot_stats(pattern)
    return PatternEntry(
        id=pattern_id,
        source_seed=source_seed,
        grid=pattern,
        max_slot_length=max_len,
        total_slot_count=total,
        tier=tier,
    )


def pattern_selection_weight(
    entry: PatternEntry,
    tracker: PatternStatsTracker | None = None,
) -> float:
    """Higher weight for lower max slot length, richer slot counts, and runtime success."""
    grid_size = len(entry.grid)
    runtime = tracker.runtime_weight(entry.id) if tracker is not None else 1.0
    diversity = tracker.diversity_weight(entry.id) if tracker is not None else 1.0

    if grid_size == 7 and entry.layout_score > 0:
        from crossword.pattern7 import pattern7_selection_weight

        return pattern7_selection_weight(
            layout_score=entry.layout_score,
            slot_histogram=entry.slot_histogram,
            total_slot_count=entry.total_slot_count,
            tier=entry.tier,
            tracker_weight=runtime * diversity,
        )

    if entry.layout_score > 0 or entry.fillability_score > 0:
        if grid_size == 12 and entry_is_discovered_12(entry):
            if tracker is None or not tracker.has_runtime_success(entry.id):
                return 0.05
            ratio = tracker.runtime_success_ratio(entry.id)
            weight = 0.35 + ratio * 2.4
            weight *= tracker.runtime_weight(entry.id) * diversity
            return max(0.2, weight)

        weight = max(0.5, entry.selection_score) * runtime * diversity
        if entry.tier == "primary":
            weight *= 1.12
        if grid_size == 12 and entry.max_slot_length <= 9:
            weight *= 1.08
        if entry.id in _P12_HAND_PRIMARY_IDS:
            weight *= 2.5
        if entry.id == "p12_i_seed89":
            weight *= 1.35
        if entry.probe_success_rate > 0:
            weight *= 1.18
        if tracker is not None:
            weight *= tracker.late_fail_penalty(entry.id)
            weight *= tracker.uninformative_penalty(entry.id)
        return max(0.2, weight)

    weight = 1.0
    weight += (13 - entry.max_slot_length) * 3.0
    weight += min(entry.total_slot_count, 60) * 0.08
    if entry.max_slot_length >= 11:
        weight -= 3.0
    if entry.tier == "primary":
        weight += 1.5
    weight *= runtime * diversity
    if tracker is not None:
        weight *= tracker.late_fail_penalty(entry.id)
        weight *= tracker.uninformative_penalty(entry.id)
    return max(0.2, weight)


def weighted_pattern_order(
    entries: list[PatternEntry],
    rng: random.Random,
    tracker: PatternStatsTracker | None = None,
) -> list[PatternEntry]:
    """Weighted random permutation without replacement."""
    remaining = entries[:]
    order: list[PatternEntry] = []
    while remaining:
        weights = [pattern_selection_weight(entry, tracker) for entry in remaining]
        total = sum(weights)
        pick = rng.uniform(0, total)
        acc = 0.0
        for idx, weight in enumerate(weights):
            acc += weight
            if pick <= acc:
                order.append(remaining.pop(idx))
                break
    return order


PATTERN_ENTRIES_12: list[PatternEntry] = [
    _entry("p12_i_seed89", 89, _P12_I, "primary"),
    _entry("p12_j_seed292", 292, _P12_J, "primary"),
    _entry("p12_k_seed983", 983, _P12_K, "primary"),
    _entry("p12_fb_seed487", 487, _P12_FALLBACK_487, "fallback"),
    _entry("p12_fb_seed1708", 1708, _P12_FALLBACK_1708, "fallback"),
    _entry("p12_fb_seed1883", 1883, _P12_FALLBACK_1883, "fallback"),
    _entry("p12_fb_seed1968", 1968, _P12_FALLBACK_1968, "fallback"),
    # Legacy patterns kept for reference; not used in tiered selection.
    _entry("p12_a_seed0", 0, _P12_A, "fallback"),
    _entry("p12_b_seed1", 1, _P12_B, "fallback"),
    _entry("p12_c_seed2", 2, _P12_C, "fallback"),
    _entry("p12_d_seed3", 3, _P12_D, "fallback"),
    _entry("p12_e_seed4", 4, _P12_E, "fallback"),
    _entry("p12_f_seed5", 5, _P12_F, "fallback"),
    _entry("p12_g_seed6", 6, _P12_G, "fallback"),
    _entry("p12_h_seed7", 7, _P12_H, "fallback"),
]

PATTERNS_12: list[list[list[int]]] = [entry.grid for entry in PATTERN_ENTRIES_12]

PATTERN_CATALOG_12: list[tuple[str, list[list[int]]]] = [
    (entry.id, entry.grid) for entry in PATTERN_ENTRIES_12
]

def _entry_7(
    pattern_id: str,
    source_seed: int | None,
    pattern: list[list[int]],
    tier: PatternTier,
) -> PatternEntry:
    from crossword.pattern_scoring import score_pattern_histogram

    grid = pattern_to_grid(pattern)
    slots = extract_slots(grid)
    lengths = [slot.length for slot in slots]
    hist = slot_length_histogram(lengths)
    blacks = sum(sum(row) for row in pattern)
    score = score_pattern_histogram(
        hist, grid_size=7, total_slots=len(slots), black_square_count=blacks
    )
    return PatternEntry(
        id=pattern_id,
        source_seed=source_seed,
        grid=pattern,
        max_slot_length=max(lengths) if lengths else 0,
        total_slot_count=len(slots),
        tier=tier,
        slot_histogram=hist,
        black_square_count=blacks,
        layout_score=score,
    )


# 7x7 catalog — rotationally symmetric layouts from discovery search.
_P7_A = [
    [0, 0, 0, 0, 0, 1, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0, 0, 0],
]

_P7_B = [
    [0, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 0],
]

_P7_C = [
    [1, 0, 0, 0, 0, 1, 1],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0, 0, 1],
]

_P7_D = [
    [1, 1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 1, 1],
]

_P7_E = [
    [1, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 1],
]

_P7_FB_F = [
    [1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1],
]

_P7_FB_G = [
    [1, 0, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 1],
]

_P7_FB_H = [
    [1, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1],
]

PATTERN_ENTRIES_7: list[PatternEntry] = [
    _entry_7("p7_a_seed12", 12, _P7_A, "primary"),
    _entry_7("p7_b_seed42", 42, _P7_B, "primary"),
    _entry_7("p7_c_seed5", 5, _P7_C, "primary"),
    _entry_7("p7_d_seed1", 1, _P7_D, "primary"),
    _entry_7("p7_e_seed177", 177, _P7_E, "primary"),
    _entry_7("p7_fb_seed4", 4, _P7_FB_F, "fallback"),
    _entry_7("p7_fb_seed95", 95, _P7_FB_G, "fallback"),
    _entry_7("p7_fb_seed23", 23, _P7_FB_H, "fallback"),
]

PATTERNS_7: list[list[list[int]]] = [entry.grid for entry in PATTERN_ENTRIES_7]

PATTERN_CATALOG_7: list[tuple[str, list[list[int]]]] = [
    (entry.id, entry.grid) for entry in PATTERN_ENTRIES_7
]

PATTERNS_BY_SIZE: dict[int, list[list[list[int]]]] = {
    7: PATTERNS_7,
    12: PATTERNS_12,
}

CATALOG_BY_SIZE: dict[int, list[tuple[str, list[list[int]]]]] = {
    7: PATTERN_CATALOG_7,
    12: PATTERN_CATALOG_12,
}

ENTRIES_BY_SIZE: dict[int, list[PatternEntry]] = {
    7: PATTERN_ENTRIES_7,
    12: PATTERN_ENTRIES_12,
}


def _grid_fingerprint(pattern: list[list[int]]) -> tuple:
    return tuple(tuple(row) for row in pattern)


def _entry_from_json(record: dict, grid_size: int) -> PatternEntry:
    from crossword.pattern_scoring import score_pattern_histogram

    grid = record["grid"]
    hist_raw = record.get("histogram", {})
    hist = {int(k): int(v) for k, v in hist_raw.items()}
    blacks = int(record.get("black_count", sum(sum(row) for row in grid)))
    slots = extract_slots(pattern_to_grid(grid))
    total = int(record.get("total_slots", len(slots)))
    if not hist:
        hist = slot_length_histogram([s.length for s in slots])
    score = float(record.get("score", 0))
    if score <= 0:
        score = score_pattern_histogram(
            hist, grid_size=grid_size, total_slots=total, black_square_count=blacks
        )
    fill_score = float(record.get("fillability_score", 0))
    combined = float(record.get("combined_score", 0))
    if combined <= 0 and fill_score > 0:
        combined = fill_score * 0.65 + score * 0.35
    passed = record.get("fillability_passed")
    pid = str(record["id"])
    hand_12 = pid in _P12_HAND_PRIMARY_IDS or pid in _P12_FALLBACK_IDS
    if passed is None:
        if grid_size == 12 and not hand_12:
            fillability_passed = float(record.get("probe_success_rate", 0)) > 0
        else:
            fillability_passed = fill_score > 0 or grid_size not in (10, 12)
    else:
        if grid_size == 12 and not hand_12:
            fillability_passed = bool(passed) and float(record.get("probe_success_rate", 0)) > 0
        else:
            fillability_passed = bool(passed)
    return PatternEntry(
        id=str(record["id"]),
        source_seed=record.get("source_seed"),
        grid=grid,
        max_slot_length=int(record.get("max_slot_length", max(hist) if hist else 0)),
        total_slot_count=total,
        tier=record.get("tier", "fallback"),
        slot_histogram=hist,
        black_square_count=blacks,
        layout_score=score,
        fillability_score=fill_score,
        combined_score=combined,
        fillability_passed=fillability_passed,
        probe_success_rate=float(record.get("probe_success_rate", 0)),
    )


def _load_json_catalog(size: int) -> list[PatternEntry]:
    path = CATALOG_DIR / f"catalog_{size}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_entry_from_json(rec, size) for rec in data.get("patterns", [])]


def _merge_pattern_entries(*groups: list[PatternEntry]) -> list[PatternEntry]:
    out: list[PatternEntry] = []
    seen_ids: set[str] = set()
    seen_grids: set[tuple] = set()
    for group in groups:
        for entry in group:
            fp = _grid_fingerprint(entry.grid)
            if entry.id in seen_ids or fp in seen_grids:
                continue
            seen_ids.add(entry.id)
            seen_grids.add(fp)
            out.append(entry)
    return out


def _enrich_entry_12(entry: PatternEntry) -> PatternEntry:
    """Add histogram/score metadata to legacy 12x12 entries if missing."""
    if entry.layout_score > 0 and entry.slot_histogram:
        return entry
    from crossword.pattern_scoring import score_pattern_histogram

    grid = pattern_to_grid(entry.grid)
    slots = extract_slots(grid)
    lengths = [s.length for s in slots]
    hist = slot_length_histogram(lengths)
    blacks = sum(sum(row) for row in entry.grid)
    score = score_pattern_histogram(
        hist, grid_size=12, total_slots=len(slots), black_square_count=blacks
    )
    return PatternEntry(
        id=entry.id,
        source_seed=entry.source_seed,
        grid=entry.grid,
        max_slot_length=entry.max_slot_length,
        total_slot_count=entry.total_slot_count,
        tier=entry.tier,
        slot_histogram=hist,
        black_square_count=blacks,
        layout_score=score,
    )


def _finalize_multi_size_catalogs() -> None:
    """Merge hand-tuned and discovered catalogs for 8/10/12."""
    global PATTERNS_BY_SIZE, CATALOG_BY_SIZE, ENTRIES_BY_SIZE

    base_12 = [_enrich_entry_12(e) for e in PATTERN_ENTRIES_12]
    hand_12_primary = [e for e in base_12 if e.id in _P12_HAND_PRIMARY_IDS]
    hand_12_fb = [e for e in base_12 if e.id in _P12_FALLBACK_IDS]
    discovered_12 = [
        e
        for e in _load_json_catalog(12)
        if e.id not in _P12_HAND_PRIMARY_IDS and e.id not in _P12_FALLBACK_IDS
    ]
    discovered_12 = [
        PatternEntry(
            id=e.id,
            source_seed=e.source_seed,
            grid=e.grid,
            max_slot_length=e.max_slot_length,
            total_slot_count=e.total_slot_count,
            tier="archive",
            slot_histogram=e.slot_histogram,
            black_square_count=e.black_square_count,
            layout_score=e.layout_score,
            fillability_score=e.fillability_score,
            combined_score=e.combined_score,
            fillability_passed=False,
            probe_success_rate=e.probe_success_rate,
        )
        for e in discovered_12
    ]
    merged_12 = _merge_pattern_entries(hand_12_primary, hand_12_fb, discovered_12)

    entries_8 = _load_json_catalog(8)
    raw_10 = _load_json_catalog(10)
    core_10 = [e for e in raw_10 if e.id in _P10_CORE_IDS]
    by_core_id = {e.id: e for e in core_10}
    core_10_ordered = [by_core_id[pid] for pid in _P10_CORE_ORDER if pid in by_core_id]
    probation_10 = [
        e for e in raw_10
        if e.id not in _P10_CORE_IDS and e.tier != "archive"
    ]
    entries_10 = _merge_pattern_entries(core_10_ordered, probation_10)

    ENTRIES_BY_SIZE[12] = merged_12
    if entries_8:
        ENTRIES_BY_SIZE[8] = entries_8
        PATTERNS_BY_SIZE[8] = [e.grid for e in entries_8]
        CATALOG_BY_SIZE[8] = [(e.id, e.grid) for e in entries_8]
    if entries_10:
        ENTRIES_BY_SIZE[10] = entries_10
        PATTERNS_BY_SIZE[10] = [e.grid for e in entries_10]
        CATALOG_BY_SIZE[10] = [(e.id, e.grid) for e in entries_10]

    PATTERNS_BY_SIZE[12] = [e.grid for e in merged_12]
    CATALOG_BY_SIZE[12] = [(e.id, e.grid) for e in merged_12]


def get_patterns(size: int) -> list[list[list[int]]]:
    return PATTERNS_BY_SIZE.get(size, [])


def get_pattern_catalog(size: int) -> list[tuple[str, list[list[int]]]]:
    """Named patterns for a grid size: (pattern_id, 0/1 matrix)."""
    return [entry for entry in CATALOG_BY_SIZE.get(size, [])]


def _selectable_entries(entries: list[PatternEntry]) -> list[PatternEntry]:
    """Patterns allowed in weighted selection (fillability-gated)."""
    return [
        entry
        for entry in entries
        if entry.fillability_passed and entry.tier != "archive"
    ]


def _discovered_12_runtime_fallback(
    tracker: PatternStatsTracker | None,
) -> list[PatternEntry]:
    """Discovered 12x12 layouts only when runtime stats prove they fill."""
    if tracker is None:
        return []
    return [
        entry
        for entry in get_pattern_entries(12)
        if entry_is_discovered_12(entry) and tracker.has_runtime_success(entry.id)
    ]


def get_pattern_entries(size: int, *, tier: PatternTier | None = None) -> list[PatternEntry]:
    entries = ENTRIES_BY_SIZE.get(size, [])
    if tier is None:
        return list(entries)
    return [entry for entry in entries if entry.tier == tier]


def _partition_by_runtime_tier(
    entries: list[PatternEntry],
    tracker: PatternStatsTracker | None,
) -> tuple[list[PatternEntry], list[PatternEntry]]:
    """Early catalog vs late fallback based on runtime diagnostics memory."""
    if tracker is None:
        return entries, []
    early: list[PatternEntry] = []
    late: list[PatternEntry] = []
    for entry in entries:
        if tracker.is_late_fail_pattern(entry.id) or tracker.is_uninformative_penalized(entry.id):
            late.append(entry)
        else:
            early.append(entry)
    return early, late


def select_pattern_order(
    size: int,
    rng: random.Random,
    *,
    tracker: PatternStatsTracker | None = None,
    include_legacy_12: bool = False,
) -> list[PatternEntry]:
    """Weighted primary-then-fallback order for catalog-backed sizes."""
    if size == 12 and not include_legacy_12:
        load_profiles_from_diagnostics(grid_size=12)
        selectable = [
            e for e in get_pattern_entries(12)
            if e.tier != "archive"
        ]
        core, probation, _reject = partition_catalog_entries_12(
            selectable, tracker=tracker,
        )
        by_id = {e.id: e for e in core}
        core_ordered = [by_id[pid] for pid in _P12_HAND_PRIMARY_ORDER if pid in by_id]
        for entry in core:
            if entry.id not in _P12_HAND_PRIMARY_ORDER:
                core_ordered.append(entry)
        return (
            core_ordered
            + weighted_pattern_order(probation, rng, tracker)
        )
    if size == 10:
        load_profiles_from_diagnostics()
        by_id = {e.id: e for e in get_pattern_entries(10)}
        core = [by_id[pid] for pid in _P10_CORE_ORDER if pid in by_id]
        primary = _selectable_entries(get_pattern_entries(10, tier="primary"))
        fallback = _selectable_entries(get_pattern_entries(10, tier="fallback"))
        _core_ids = set(_P10_CORE_IDS)
        _, probation, _reject = partition_catalog_entries_10(
            [e for e in primary + fallback if e.id not in _core_ids],
            tracker=tracker,
        )
        return (
            core
            + weighted_pattern_order(probation, rng, tracker)
        )

    primary = _selectable_entries(get_pattern_entries(size, tier="primary"))
    fallback = _selectable_entries(get_pattern_entries(size, tier="fallback"))
    if size >= 10:
        early_p, late_p = _partition_by_runtime_tier(primary, tracker)
        early_f, late_f = _partition_by_runtime_tier(fallback, tracker)
        return (
            weighted_pattern_order(early_p, rng, tracker)
            + weighted_pattern_order(early_f, rng, tracker)
            + weighted_pattern_order(late_p, rng, tracker)
            + weighted_pattern_order(late_f, rng, tracker)
        )

    return (
        weighted_pattern_order(primary, rng, tracker)
        + weighted_pattern_order(fallback, rng, tracker)
    )


def select_7_pattern_order(
    rng: random.Random,
    *,
    tracker: PatternStatsTracker | None = None,
) -> list[PatternEntry]:
    return select_pattern_order(7, rng, tracker=tracker)


def select_12_pattern_order(
    rng: random.Random,
    *,
    include_legacy: bool = False,
    tracker: PatternStatsTracker | None = None,
) -> list[PatternEntry]:
    return select_pattern_order(
        12, rng, tracker=tracker, include_legacy_12=include_legacy
    )


def random_pattern_grid(size: int, rng: random.Random | None = None) -> Grid | None:
    """Return a random validated pre-defined pattern grid, or None if none exist."""
    patterns = get_patterns(size)
    if not patterns:
        return None
    rng = rng or random.Random()
    order = patterns[:]
    rng.shuffle(order)
    for pattern in order:
        return pattern_to_grid(pattern)
    return None


_finalize_multi_size_catalogs()

for _size, _plist in PATTERNS_BY_SIZE.items():
    for _p in _plist:
        _validate_stored_pattern(_p, _size)

for _size, _entries in ENTRIES_BY_SIZE.items():
    for _entry in _entries:
        _validate_stored_pattern(_entry.grid, _size)
