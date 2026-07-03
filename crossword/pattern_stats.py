"""In-memory runtime stats and recent-use diversity for pattern selection."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass
class PatternRuntimeStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_fill_seconds: float = 0.0

    @property
    def success_ratio(self) -> float:
        if self.attempts == 0:
            return 0.5
        return self.successes / self.attempts

    @property
    def avg_fill_seconds(self) -> float:
        if self.successes == 0:
            if self.attempts == 0:
                return 4.0
            return self.total_fill_seconds / self.attempts
        return self.total_fill_seconds / self.successes


class PatternStatsTracker:
    """Process-wide in-memory tracker (no persistence)."""

    def __init__(self) -> None:
        self._stats: dict[str, PatternRuntimeStats] = {}
        self._recent_ids: deque[str] = deque(maxlen=24)
        self._lock = threading.Lock()

    def record_selection(self, pattern_id: str) -> None:
        """Track pattern chosen for a fill attempt (diversity protection)."""
        with self._lock:
            self._recent_ids.append(pattern_id)

    def diversity_weight(self, pattern_id: str) -> float:
        """Penalize patterns used very recently when alternatives exist."""
        with self._lock:
            if not self._recent_ids:
                return 1.0
            count = sum(1 for pid in self._recent_ids if pid == pattern_id)
            if count >= 3:
                return 0.35
            if count == 2:
                return 0.55
            if count == 1 and len(self._recent_ids) >= 6:
                return 0.8
            return 1.0

    def get(self, pattern_id: str) -> PatternRuntimeStats:
        with self._lock:
            if pattern_id not in self._stats:
                self._stats[pattern_id] = PatternRuntimeStats()
            return self._stats[pattern_id]

    def record(self, pattern_id: str, *, success: bool, fill_seconds: float) -> None:
        with self._lock:
            stats = self._stats.setdefault(pattern_id, PatternRuntimeStats())
            stats.attempts += 1
            stats.total_fill_seconds += fill_seconds
            if success:
                stats.successes += 1
            else:
                stats.failures += 1

    def runtime_weight(self, pattern_id: str) -> float:
        """Higher weight for patterns that succeed quickly and often."""
        stats = self.get(pattern_id)
        if stats.attempts == 0:
            return 1.0
        ratio = (stats.successes + 1) / (stats.attempts + 2)
        weight = 0.55 + ratio * 1.6
        if stats.attempts >= 8 and stats.successes == 0:
            weight *= 0.45
        elif stats.attempts >= 5 and stats.success_ratio < 0.15:
            weight *= 0.65
        if stats.successes > 0:
            avg = stats.avg_fill_seconds
            if avg <= 3.0:
                weight *= 1.3
            elif avg <= 6.0:
                weight *= 1.1
            elif avg >= 7.5:
                weight *= 0.85
        return max(0.25, weight)

    def summary(self) -> dict[str, dict]:
        with self._lock:
            out: dict[str, dict] = {}
            for pid, s in self._stats.items():
                out[pid] = {
                    "attempts": s.attempts,
                    "successes": s.successes,
                    "failures": s.failures,
                    "avg_fill_s": round(s.avg_fill_seconds, 2),
                    "success_ratio": round(s.success_ratio, 2),
                }
            return out


_TRACKER = PatternStatsTracker()


def get_pattern_stats_tracker() -> PatternStatsTracker:
    return _TRACKER
