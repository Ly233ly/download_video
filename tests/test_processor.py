from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.eagle import EagleUnavailable
from idm_eagle_bridge.processor import JobProcessor


class FakeEagle:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.imports: list[tuple[str, str | None]] = []

    def is_available(self) -> bool:
        return self.available

    def add_from_path(self, file_path: str, website: str | None = None) -> str:
        if not self.available:
            raise EagleUnavailable("Eagle 当前不可用")
        self.imports.append((file_path, website))
        return f"item-{len(self.imports)}"


class ProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = Database(root / "test.db")
        self.database.set_site_rule("example.com", True)
        self.video = root / "中文 视频 (1).mp4"
        self.video.write_bytes(b"fake-video-content")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _add_job(self, path: Path, offset: float = 0) -> str:
        now = time.time() + offset
        self.database.add_source_event(
            f"https://example.com/watch?id={now}",
            "来源网页",
            created_at=now,
        )
        return self.database.add_job(str(path), created_at=now + 1)

    def _link_download_plan(
        self,
        job_id: str,
        output: Path,
        *,
        delete_after_import: bool,
    ) -> str:
        plan_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = time.time()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO capture_sessions(
                    id, page_url, page_title, created_at, updated_at
                ) VALUES(?, '', '测试计划', ?, ?)
                """,
                (session_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO media_groups(
                    id, session_id, group_key, title, media_kind,
                    created_at, updated_at
                ) VALUES(?, ?, ?, '测试计划', 'direct', ?, ?)
                """,
                (group_id, session_id, group_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO download_plans(
                    id, group_id, output_name, output_container, merge_mode,
                    route, import_to_eagle, delete_after_import,
                    status, progress, phase_detail, final_path, job_id,
                    created_at, updated_at
                ) VALUES(
                    ?, ?, ?, 'mp4', 'direct', 'desktop', 1, ?,
                    'ready_to_import', 90, '等待 Eagle 导入', ?, ?, ?, ?
                )
                """,
                (
                    plan_id,
                    group_id,
                    output.name,
                    1 if delete_after_import else 0,
                    str(output),
                    job_id,
                    now,
                    now,
                ),
            )
        return plan_id

    def test_video_is_imported_with_source_page(self) -> None:
        job_id = self._add_job(self.video)
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database, eagle=eagle, minimum_file_age=0, source_grace_period=0
        )

        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "imported")
        self.assertEqual(len(eagle.imports), 1)
        self.assertTrue(eagle.imports[0][1].startswith("https://example.com/watch?id="))

    def test_video_without_source_is_imported_directly(self) -> None:
        job_id = self.database.add_job(str(self.video))
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database, eagle=eagle, minimum_file_age=0, source_grace_period=0
        )

        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "imported")
        self.assertIsNone(job["source_url"])
        self.assertEqual(eagle.imports, [(str(self.video), None)])
        self.assertTrue(self.video.is_file(), "ordinary IDM/user files must be preserved")

    def test_owned_desktop_output_is_deleted_only_after_successful_eagle_import(
        self,
    ) -> None:
        download_root = Path(self.temp_dir.name) / "owned-downloads"
        output = download_root / "下载中转站" / "已完成" / "owned.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"owned-desktop-video")
        job_id = self.database.add_job(str(output))
        plan_id = self._link_download_plan(
            job_id,
            output,
            delete_after_import=True,
        )
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        with patch.dict(
            os.environ,
            {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)},
        ):
            processor.process_job(job_id)

        self.assertFalse(output.exists())
        self.assertEqual(self.database.get_job(job_id)["status"], "imported")
        with self.database.session() as connection:
            plan = connection.execute(
                "SELECT final_path, phase_detail, error_code FROM download_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        self.assertIsNone(plan["final_path"])
        self.assertEqual(plan["phase_detail"], "已导入 Eagle，本机下载文件已自动删除")
        self.assertIsNone(plan["error_code"])

    def test_unchecked_or_failed_import_keeps_owned_desktop_output(self) -> None:
        download_root = Path(self.temp_dir.name) / "kept-downloads"
        output = download_root / "下载中转站" / "已完成" / "kept.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"kept-desktop-video")
        job_id = self.database.add_job(str(output))
        self._link_download_plan(
            job_id,
            output,
            delete_after_import=False,
        )
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        with patch.dict(
            os.environ,
            {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)},
        ):
            processor.process_job(job_id)

        self.assertTrue(output.is_file())

        failed_output = output.with_name("waiting-eagle.mp4")
        failed_output.write_bytes(b"waiting-eagle-video")
        failed_job = self.database.add_job(str(failed_output))
        self._link_download_plan(
            failed_job,
            failed_output,
            delete_after_import=True,
        )
        unavailable = JobProcessor(
            self.database,
            eagle=FakeEagle(available=False),
            minimum_file_age=0,
            source_grace_period=0,
        )
        with patch.dict(
            os.environ,
            {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)},
        ):
            unavailable.process_job(failed_job)
        self.assertTrue(failed_output.is_file())
        self.assertEqual(self.database.get_job(failed_job)["status"], "waiting_eagle")

    def test_linked_output_outside_owned_directory_is_never_deleted(self) -> None:
        job_id = self.database.add_job(str(self.video))
        plan_id = self._link_download_plan(
            job_id,
            self.video,
            delete_after_import=True,
        )
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        with patch.dict(
            os.environ,
            {"IDM_EAGLE_DOWNLOAD_ROOT": str(Path(self.temp_dir.name) / "other-root")},
        ):
            processor.process_job(job_id)

        self.assertTrue(self.video.is_file())
        self.assertEqual(self.database.get_job(job_id)["status"], "imported")
        with self.database.session() as connection:
            plan = connection.execute(
                "SELECT final_path, phase_detail, error_code FROM download_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        self.assertEqual(plan["final_path"], str(self.video))
        self.assertEqual(plan["phase_detail"], "已导入 Eagle，本机文件未删除")
        self.assertEqual(plan["error_code"], "local_file_delete_not_owned")

    def test_delete_failure_does_not_turn_successful_eagle_import_into_failure(
        self,
    ) -> None:
        download_root = Path(self.temp_dir.name) / "locked-downloads"
        output = download_root / "下载中转站" / "已完成" / "locked.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"locked-desktop-video")
        job_id = self.database.add_job(str(output))
        plan_id = self._link_download_plan(
            job_id,
            output,
            delete_after_import=True,
        )
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        with (
            patch.dict(
                os.environ,
                {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)},
            ),
            patch.object(Path, "unlink", side_effect=PermissionError("locked")),
            patch("idm_eagle_bridge.processor.time.sleep"),
        ):
            processor.process_job(job_id)

        self.assertTrue(output.is_file())
        self.assertEqual(self.database.get_job(job_id)["status"], "imported")
        with self.database.session() as connection:
            plan = connection.execute(
                "SELECT final_path, phase_detail, error_code FROM download_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        self.assertEqual(plan["final_path"], str(output))
        self.assertEqual(plan["phase_detail"], "已导入 Eagle，本机文件未删除")
        self.assertEqual(plan["error_code"], "local_file_delete_failed")

    def test_pending_cleanup_recovers_after_import_process_interruption(self) -> None:
        download_root = Path(self.temp_dir.name) / "recovery-downloads"
        output = download_root / "下载中转站" / "已完成" / "recover.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"recover-desktop-video")
        job_id = self.database.add_job(str(output))
        plan_id = self._link_download_plan(
            job_id,
            output,
            delete_after_import=True,
        )
        self.database.update_job(
            job_id,
            status="imported",
            eagle_item_id="already-imported-item",
            completed_at=time.time(),
        )
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        with patch.dict(
            os.environ,
            {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)},
        ):
            processed = processor.process_once()

        self.assertEqual(processed, 1)
        self.assertFalse(output.exists())
        with self.database.session() as connection:
            plan = connection.execute(
                "SELECT final_path, phase_detail FROM download_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        self.assertIsNone(plan["final_path"])
        self.assertEqual(plan["phase_detail"], "已导入 Eagle，本机下载文件已自动删除")

    def test_same_content_is_skipped_even_with_different_name(self) -> None:
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database, eagle=eagle, minimum_file_age=0, source_grace_period=0
        )

        first_job = self._add_job(self.video)
        processor.process_job(first_job)

        copy = Path(self.temp_dir.name) / "another-name.mkv"
        copy.write_bytes(self.video.read_bytes())
        second_job = self._add_job(copy, offset=10)
        processor.process_job(second_job)

        self.assertEqual(self.database.get_job(second_job)["status"], "skipped_duplicate")
        self.assertEqual(len(eagle.imports), 1)

    def test_eagle_offline_keeps_waiting_job(self) -> None:
        job_id = self._add_job(self.video)
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(available=False),
            minimum_file_age=0,
            source_grace_period=0,
        )

        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "waiting_eagle")
        self.assertEqual(job["attempt_count"], 1)
        self.assertIsNotNone(job["next_retry_at"])
        self.assertIn("自动重试", job["error_message"])

    def test_non_video_is_ignored(self) -> None:
        text_file = Path(self.temp_dir.name) / "notes.txt"
        text_file.write_text("not a video", encoding="utf-8")
        job_id = self._add_job(text_file)
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=0,
            source_grace_period=0,
        )

        processor.process_job(job_id)

        self.assertEqual(self.database.get_job(job_id)["status"], "ignored_non_video")

    def test_user_ignore_event_does_not_import(self) -> None:
        now = time.time()
        self.database.add_source_event(
            "https://example.com/watch?id=ignore",
            "忽略这次",
            event_type="ignore",
            created_at=now,
        )
        job_id = self.database.add_job(str(self.video), created_at=now + 1)
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database, eagle=eagle, minimum_file_age=0, source_grace_period=0
        )

        processor.process_job(job_id)

        self.assertEqual(self.database.get_job(job_id)["status"], "ignored_by_user")
        self.assertEqual(eagle.imports, [])

    def test_short_grace_allows_late_browser_source_to_attach(self) -> None:
        job_id = self.database.add_job(str(self.video))
        job = self.database.get_job(job_id)
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database,
            eagle=eagle,
            minimum_file_age=0,
            source_grace_period=30,
        )

        processor.process_job(job_id)

        waiting = self.database.get_job(job_id)
        self.assertEqual(waiting["status"], "queued")
        self.assertEqual(waiting["error_code"], "source_grace")
        self.assertEqual(eagle.imports, [])

        self.database.add_source_event(
            "https://example.com/late-source",
            "稍晚到达的浏览器来源",
            created_at=float(job["created_at"]) - 0.1,
        )
        processor.process_job(job_id)

        imported = self.database.get_job(job_id)
        self.assertEqual(imported["status"], "imported")
        self.assertEqual(eagle.imports[0][1], "https://example.com/late-source")

    def test_newly_finished_file_retries_automatically_with_short_delay(self) -> None:
        job_id = self.database.add_job(str(self.video))
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=10,
            source_grace_period=0,
        )

        before = time.time()
        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "retry")
        self.assertEqual(job["error_code"], "file_not_stable")
        self.assertIn("自动重试", job["error_message"])
        self.assertGreater(job["next_retry_at"], before)
        self.assertLessEqual(job["next_retry_at"] - before, 3.5)

    def test_unstable_file_stops_after_twenty_attempts(self) -> None:
        job_id = self.database.add_job(str(self.video))
        self.database.update_job(job_id, attempt_count=19)
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(),
            minimum_file_age=10,
            source_grace_period=0,
        )

        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "failed_permanent")
        self.assertEqual(job["attempt_count"], 20)
        self.assertIsNone(job["next_retry_at"])
        self.assertIn("停止自动重试", job["error_message"])

    def test_waiting_for_eagle_stops_after_one_hundred_twenty_checks(self) -> None:
        job_id = self._add_job(self.video)
        self.database.update_job(job_id, attempt_count=119)
        processor = JobProcessor(
            self.database,
            eagle=FakeEagle(available=False),
            minimum_file_age=0,
            source_grace_period=0,
        )

        processor.process_job(job_id)

        job = self.database.get_job(job_id)
        self.assertEqual(job["status"], "failed_permanent")
        self.assertEqual(job["attempt_count"], 120)
        self.assertIsNone(job["next_retry_at"])
        self.assertIn("1 小时", job["error_message"])

    def test_completed_same_job_cannot_turn_into_duplicate_on_retry_race(self) -> None:
        job_id = self._add_job(self.video)
        eagle = FakeEagle()
        processor = JobProcessor(
            self.database,
            eagle=eagle,
            minimum_file_age=0,
            source_grace_period=0,
        )
        processor.process_job(job_id)

        self.assertEqual(self.database.get_job(job_id)["status"], "imported")
        self.assertFalse(self.database.retry_job(job_id))

        # 模拟旧界面在导入完成边界上把同一任务再次标记为重试。
        self.database.update_job(
            job_id,
            status="retry",
            next_retry_at=None,
            error_code="file_not_stable",
            error_message="模拟竞态",
            completed_at=None,
        )
        processor.process_job(job_id)

        restored = self.database.get_job(job_id)
        self.assertEqual(restored["status"], "imported")
        self.assertIsNone(restored["error_code"])
        self.assertEqual(len(eagle.imports), 1)


if __name__ == "__main__":
    unittest.main()
