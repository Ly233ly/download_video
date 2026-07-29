from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any


def _environment_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _environment_float(name: str, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


class PerformanceMonitor:
    """Keep only slow-operation evidence in a small in-memory ring buffer."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        threshold_ms: float = 50.0,
        max_events: int = 256,
    ) -> None:
        self.enabled = bool(enabled)
        self.threshold_ms = max(1.0, float(threshold_ms))
        self.max_events = max(16, min(4096, int(max_events)))
        self._events: deque[dict[str, Any]] = deque(maxlen=self.max_events)
        self._counts = {"over50": 0, "over100": 0, "over500": 0}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "PerformanceMonitor":
        return cls(
            enabled=_environment_flag("IDM_EAGLE_PERFORMANCE_MONITOR", True),
            threshold_ms=_environment_float(
                "IDM_EAGLE_PERFORMANCE_THRESHOLD_MS",
                50.0,
                1.0,
            ),
            max_events=int(
                _environment_float(
                    "IDM_EAGLE_PERFORMANCE_MAX_EVENTS",
                    256.0,
                    16.0,
                )
            ),
        )

    @staticmethod
    def _severity(duration_ms: float) -> str:
        if duration_ms >= 500:
            return "severe"
        if duration_ms >= 100:
            return "slow"
        return "notice"

    def record(
        self,
        name: str,
        duration_ms: float,
        context: dict[str, Any] | None = None,
    ) -> bool:
        duration_ms = max(0.0, float(duration_ms))
        if not self.enabled or duration_ms < self.threshold_ms:
            return False
        event = {
            "time": time.time(),
            "name": str(name),
            "durationMs": round(duration_ms, 3),
            "severity": self._severity(duration_ms),
            **dict(context or {}),
        }
        with self._lock:
            self._events.append(event)
            if duration_ms >= 50:
                self._counts["over50"] += 1
            if duration_ms >= 100:
                self._counts["over100"] += 1
            if duration_ms >= 500:
                self._counts["over500"] += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = [dict(event) for event in self._events]
            counts = dict(self._counts)
        return {
            "enabled": self.enabled,
            "thresholdMs": self.threshold_ms,
            "capacity": self.max_events,
            "eventCount": len(events),
            "counts": counts,
            "events": events,
        }
