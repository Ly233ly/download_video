from __future__ import annotations

import unittest

from idm_eagle_bridge.performance import PerformanceMonitor


class PerformanceMonitorTests(unittest.TestCase):
    def test_ignores_fast_operations_and_classifies_slow_ones(self) -> None:
        monitor = PerformanceMonitor(threshold_ms=50, max_events=16)

        self.assertFalse(monitor.record("fast", 49.9))
        self.assertTrue(monitor.record("notice", 50, {"page": "media"}))
        self.assertTrue(monitor.record("slow", 100))
        self.assertTrue(monitor.record("severe", 500))

        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["eventCount"], 3)
        self.assertEqual(
            [event["severity"] for event in snapshot["events"]],
            ["notice", "slow", "severe"],
        )
        self.assertEqual(
            snapshot["counts"],
            {"over50": 3, "over100": 2, "over500": 1},
        )

    def test_ring_buffer_is_bounded_without_losing_total_counts(self) -> None:
        monitor = PerformanceMonitor(threshold_ms=1, max_events=16)

        for index in range(30):
            monitor.record(f"event-{index}", 60)

        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["eventCount"], 16)
        self.assertEqual(snapshot["events"][0]["name"], "event-14")
        self.assertEqual(snapshot["counts"]["over50"], 30)

    def test_disabled_monitor_keeps_no_events(self) -> None:
        monitor = PerformanceMonitor(enabled=False)

        self.assertFalse(monitor.record("blocked", 1000))
        self.assertEqual(monitor.snapshot()["eventCount"], 0)


if __name__ == "__main__":
    unittest.main()
