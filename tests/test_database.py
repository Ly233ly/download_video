from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from idm_eagle_bridge.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_site_rules_default_off_and_subdomains(self) -> None:
        self.assertFalse(self.database.site_enabled("video.example.com"))
        self.database.set_site_rule("example.com", True, include_subdomains=True)
        self.assertTrue(self.database.site_enabled("example.com"))
        self.assertTrue(self.database.site_enabled("video.example.com"))

    def test_exact_rule_overrides_parent(self) -> None:
        self.database.set_site_rule("example.com", True, include_subdomains=True)
        self.database.set_site_rule("private.example.com", False)
        self.assertFalse(self.database.site_enabled("private.example.com"))
        self.assertTrue(self.database.site_enabled("public.example.com"))

    def test_site_rule_can_be_deleted(self) -> None:
        self.database.set_site_rule("example.com", True)
        self.assertTrue(self.database.delete_site_rule("example.com"))
        self.assertFalse(self.database.site_enabled("example.com"))
        self.assertFalse(self.database.delete_site_rule("example.com"))

    def test_all_site_rules_can_be_cleared_without_touching_other_records(self) -> None:
        self.database.set_site_rule("one.example", True)
        self.database.set_site_rule("two.example", False)
        job_id = self.database.add_job("C:/Downloads/keep.mp4")

        self.assertEqual(self.database.clear_site_rules(), 2)
        self.assertEqual(self.database.list_site_rules(), [])
        self.assertIsNotNone(self.database.get_job(job_id))

    def test_disabled_site_cannot_create_source_event(self) -> None:
        with self.assertRaises(PermissionError):
            self.database.add_source_event("https://example.com/video")

    def test_source_is_attached_to_next_job(self) -> None:
        self.database.set_site_rule("example.com", True)
        self.database.add_source_event(
            "https://example.com/video?utm_source=test&id=1",
            "测试视频",
            created_at=100,
        )
        job_id = self.database.add_job("C:/Downloads/test.mp4", created_at=200)

        self.assertTrue(self.database.attach_best_source(job_id))
        job = self.database.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["source_url"], "https://example.com/video?id=1")

    def test_ambiguous_sources_are_not_guessed(self) -> None:
        self.database.set_site_rule("example.com", True)
        self.database.add_source_event(
            "https://example.com/first", "完全无关页面", created_at=100
        )
        self.database.add_source_event(
            "https://example.com/second", "另一个页面", created_at=110
        )
        job_id = self.database.add_job("C:/Downloads/random-name.mp4", created_at=200)

        self.assertFalse(self.database.attach_best_source(job_id))
        self.assertEqual(self.database.get_job(job_id)["status"], "queued")

    def test_job_without_source_is_queued_immediately(self) -> None:
        job_id = self.database.add_job("C:/Downloads/no-source.mp4")
        self.assertEqual(self.database.get_job(job_id)["status"], "queued")

    def test_disabled_site_control_event_can_skip_job(self) -> None:
        self.database.add_source_event(
            "https://blocked.example/video",
            event_type="site_disabled",
            created_at=100,
        )
        job_id = self.database.add_job("C:/Downloads/blocked.mp4", created_at=101)
        self.assertTrue(self.database.attach_best_source(job_id))
        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "ignored_by_user")
        self.assertEqual(job["error_message"], "该网站已关闭自动导入")

    def test_legacy_waiting_source_is_migrated(self) -> None:
        job_id = self.database.add_job("C:/Downloads/legacy.mp4")
        self.database.update_job(job_id, status="waiting_source")
        with self.database.session() as connection:
            connection.execute("PRAGMA user_version = 1")
        reopened = Database(self.database.path)
        self.assertEqual(reopened.get_job(job_id)["status"], "queued")

    def test_same_job_duplicate_race_is_migrated_back_to_imported(self) -> None:
        job_id = self.database.add_job("C:/Downloads/already-imported.mp4")
        fingerprint = "a" * 64
        self.database.remember_fingerprint(fingerprint, job_id, 123)
        self.database.update_job(
            job_id,
            status="skipped_duplicate",
            fingerprint=fingerprint,
            eagle_item_id="eagle-item-1",
            error_code="duplicate",
            error_message="相同内容的视频已经导入过",
        )
        with self.database.session() as connection:
            connection.execute("PRAGMA user_version = 2")

        reopened = Database(self.database.path)
        repaired = reopened.get_job(job_id)
        self.assertEqual(repaired["status"], "imported")
        self.assertIsNone(repaired["error_code"])

    def test_duplicate_active_hook_event_is_coalesced(self) -> None:
        first = self.database.add_job("C:/Downloads/same.mp4")
        second = self.database.add_job("C:/Downloads/same.mp4")
        self.assertEqual(first, second)

    def test_media_filename_matches_correct_source(self) -> None:
        self.database.set_site_rule("example.com", True)
        self.database.add_source_event(
            "https://example.com/first",
            "页面一",
            media_url="https://cdn.example.com/files/cat-video.mp4",
            created_at=100,
        )
        self.database.add_source_event(
            "https://example.com/second",
            "页面二",
            media_url="https://cdn.example.com/files/dog-video.mp4",
            created_at=110,
        )
        job_id = self.database.add_job("C:/Downloads/cat-video.mp4", created_at=200)

        self.assertTrue(self.database.attach_best_source(job_id))
        self.assertEqual(
            self.database.get_job(job_id)["source_url"], "https://example.com/first"
        )

    def test_duplicate_requests_from_same_page_do_not_make_match_ambiguous(self) -> None:
        self.database.set_site_rule("videos.example.com", True)
        for created_at in (100, 114, 126):
            self.database.add_source_event(
                "https://videos.example.com/gallery/featured-product",
                "Featured Product Video",
                media_url="https://cdn.example.com/1fd240bd.mp4",
                event_type="video_request",
                created_at=created_at,
            )
        self.database.add_source_event(
            "https://videos.example.com/gallery/another-product",
            "Another Product Video",
            media_url="https://cdn.example.com/236e9de4.mp4",
            event_type="video_request",
            created_at=90,
        )
        job_id = self.database.add_job(
            "C:/Downloads/featured-product.mp4", created_at=131
        )

        self.assertTrue(self.database.attach_best_source(job_id))
        self.assertEqual(
            self.database.get_job(job_id)["source_url"],
            "https://videos.example.com/gallery/featured-product",
        )

    def test_cleanup_keeps_active_jobs_and_removes_old_history(self) -> None:
        old = time.time() - 120 * 86400
        old_job = self.database.add_job("C:/Downloads/old.txt", created_at=old)
        active_job = self.database.add_job("C:/Downloads/waiting.mp4")
        self.database.update_job(
            old_job,
            status="ignored_non_video",
            completed_at=old,
        )

        removed = self.database.cleanup_history(history_days=90)

        self.assertEqual(removed["jobs"], 1)
        self.assertIsNone(self.database.get_job(old_job))
        self.assertIsNotNone(self.database.get_job(active_job))

    def test_clear_terminal_history_keeps_active_jobs(self) -> None:
        terminal_job = self.database.add_job("C:/Downloads/finished.txt")
        active_job = self.database.add_job("C:/Downloads/active.mp4")
        self.database.update_job(terminal_job, status="ignored_non_video")

        self.assertEqual(self.database.clear_terminal_history(), 1)
        self.assertIsNone(self.database.get_job(terminal_job))
        self.assertIsNotNone(self.database.get_job(active_job))


if __name__ == "__main__":
    unittest.main()
