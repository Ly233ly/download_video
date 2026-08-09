from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from idm_eagle_bridge.cache import ProgramCacheManager
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.media import MediaCoordinator
from idm_eagle_bridge.service import ProcessingService


class ProgramCacheManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = Database(self.root / "bridge.db")
        self.station = self.root / "留底下载器"
        self.coordinator = MediaCoordinator(self.database, workers=1)
        self.manager = ProgramCacheManager(self.database, self.station)

    def tearDown(self) -> None:
        self.coordinator.close()
        self.temporary.cleanup()

    @staticmethod
    def _payload(name: str) -> dict[str, object]:
        return {
            "pageUrl": f"https://example.com/{name}",
            "pageTitle": name,
            "outputName": f"{name}.mp4",
            "outputContainer": "mp4",
            "mergeMode": "direct",
            "route": "browser",
            "importToEagle": False,
            "streams": [
                {
                    "url": f"https://cdn.example.com/{name}.mp4",
                    "role": "video",
                    "name": f"{name}.mp4",
                    "extension": "mp4",
                    "mimeType": "video/mp4",
                }
            ],
        }

    def _plan(self, name: str, status: str, preview: Path | None = None) -> str:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self._payload(name))
        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET status = ?, preview_path = ? WHERE id = ?",
                (status, str(preview) if preview else None, plan["id"]),
            )
        return str(plan["id"])

    def test_cache_status_counts_only_temporary_preview_and_legacy_log(self) -> None:
        (self.station / "临时" / "orphan").mkdir(parents=True)
        (self.station / "临时" / "orphan" / "part.bin").write_bytes(b"t" * 11)
        (self.station / "预览").mkdir(parents=True)
        (self.station / "预览" / "frame.png").write_bytes(b"p" * 13)
        (self.station / "media-download.log").write_bytes(b"l" * 17)
        (self.station / "已完成").mkdir(parents=True)
        (self.station / "已完成" / "keep.mp4").write_bytes(b"x" * 10_000)

        status = self.manager.status()

        self.assertEqual(status["totalBytes"], 41)
        self.assertEqual(status["fileCount"], 3)
        self.assertEqual(status["categories"]["temporary"]["bytes"], 11)
        self.assertEqual(status["categories"]["previews"]["bytes"], 13)
        self.assertEqual(status["categories"]["log"]["bytes"], 17)

    def test_manual_cleanup_preserves_active_cache_and_every_completed_file(self) -> None:
        preview_root = self.station / "预览"
        preview_root.mkdir(parents=True)
        active_preview = preview_root / "active.png"
        terminal_preview = preview_root / "terminal.png"
        active_preview.write_bytes(b"active-preview")
        terminal_preview.write_bytes(b"terminal-preview")
        active_id = self._plan("active", "downloading", active_preview)
        terminal_id = self._plan("terminal", "canceled", terminal_preview)

        active_temp = self.station / "临时" / active_id
        terminal_temp = self.station / "临时" / terminal_id
        active_temp.mkdir(parents=True)
        terminal_temp.mkdir(parents=True)
        (active_temp / "part.bin").write_bytes(b"active")
        (terminal_temp / "part.bin").write_bytes(b"terminal")
        legacy_log = self.station / "media-download.log"
        legacy_log.write_text("old log", encoding="utf-8")
        completed = self.station / "已完成" / "keep.mp4"
        completed.parent.mkdir(parents=True)
        completed.write_bytes(b"never-delete")

        result = self.manager.cleanup(protected_plan_ids={active_id})

        self.assertTrue(active_temp.is_dir())
        self.assertTrue(active_preview.is_file())
        self.assertFalse(terminal_temp.exists())
        self.assertFalse(terminal_preview.exists())
        self.assertFalse(legacy_log.exists())
        self.assertTrue(completed.is_file())
        self.assertGreater(result["freedBytes"], 0)
        self.assertGreaterEqual(result["skippedActive"], 2)
        with self.database.session() as connection:
            rows = {
                row["id"]: row["preview_path"]
                for row in connection.execute(
                    "SELECT id, preview_path FROM download_plans WHERE id IN (?, ?)",
                    (active_id, terminal_id),
                )
            }
        self.assertEqual(rows[active_id], str(active_preview))
        self.assertIsNone(rows[terminal_id])

    def test_automatic_cleanup_removes_only_cache_older_than_retention(self) -> None:
        temp_root = self.station / "临时"
        old_dir = temp_root / "old-orphan"
        recent_dir = temp_root / "recent-orphan"
        old_dir.mkdir(parents=True)
        recent_dir.mkdir(parents=True)
        old_file = old_dir / "part.bin"
        recent_file = recent_dir / "part.bin"
        old_file.write_bytes(b"old")
        recent_file.write_bytes(b"recent")
        now = time.time()
        old = now - 8 * 86400
        os.utime(old_file, (old, old))
        os.utime(old_dir, (old, old))

        result = self.manager.cleanup(retention_days=7, now=now)

        self.assertFalse(old_dir.exists())
        self.assertTrue(recent_dir.is_dir())
        self.assertEqual(result["retentionDays"], 7)

    def test_zero_retention_disables_automatic_cleanup_but_keeps_cache_visible(self) -> None:
        cache_file = self.station / "临时" / "old-orphan" / "part.bin"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"keep while automatic cleanup is disabled")

        result = self.manager.cleanup(retention_days=0, now=time.time())

        self.assertTrue(cache_file.is_file())
        self.assertEqual(result["freedBytes"], 0)
        self.assertEqual(result["remainingBytes"], cache_file.stat().st_size)

    def test_manual_cleanup_does_not_block_new_plan_scheduling(self) -> None:
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        schedule_returned = threading.Event()

        class BlockingCache:
            def cleanup(self, **_kwargs: object) -> dict[str, int]:
                cleanup_entered.set()
                release_cleanup.wait(timeout=2)
                return {"freedBytes": 0}

        self.coordinator.cache = BlockingCache()
        self.coordinator.executor.submit = Mock(return_value=None)
        cleanup_thread = threading.Thread(target=self.coordinator.clear_cache)
        schedule_thread = threading.Thread(
            target=lambda: (
                self.coordinator.schedule("new-plan"),
                schedule_returned.set(),
            )
        )
        cleanup_thread.start()
        self.assertTrue(cleanup_entered.wait(timeout=1))
        schedule_thread.start()
        try:
            self.assertTrue(
                schedule_returned.wait(timeout=0.2),
                "缓存扫描期间新下载入队不应被全局协调锁阻塞",
            )
        finally:
            release_cleanup.set()
            cleanup_thread.join(timeout=2)
            schedule_thread.join(timeout=2)


class CacheMaintenanceServiceTests(unittest.TestCase):
    def test_daily_maintenance_uses_saved_cache_retention(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Database(Path(folder) / "bridge.db")
            database.set_setting("cache_retention_days", 3)
            cache = Mock()
            service = ProcessingService(database, interval=60, cache_manager=cache)

            with patch.object(database, "cleanup_history") as cleanup_history:
                service._run_daily_maintenance(now=1234.0)

            cleanup_history.assert_called_once_with()
            cache.cleanup.assert_called_once_with(retention_days=3, now=1234.0)
            self.assertEqual(service.last_cleanup, 1234.0)


if __name__ == "__main__":
    unittest.main()
