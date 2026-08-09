from __future__ import annotations

import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.media import MediaCoordinator


class _VersionResult:
    returncode = 0
    stdout = "tool 1.0\n"


class BackendPerformanceTests(unittest.TestCase):
    def test_health_probe_is_parallel_and_singleflight_for_concurrent_pollers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            media = MediaCoordinator(
                Database(Path(temporary) / "health.db"),
                workers=1,
            )
            gate = threading.Barrier(8)
            counter_lock = threading.Lock()
            call_count = 0
            active = 0
            maximum_active = 0
            failures: list[BaseException] = []

            def version_probe(*_args: object, **_kwargs: object) -> _VersionResult:
                nonlocal call_count, active, maximum_active
                with counter_lock:
                    call_count += 1
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.03)
                with counter_lock:
                    active -= 1
                return _VersionResult()

            def poll() -> None:
                try:
                    gate.wait(timeout=3)
                    media.health()
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=poll) for _ in range(8)]
            try:
                with (
                    patch(
                        "idm_eagle_bridge.media.resolve_media_tool",
                        side_effect=lambda name: Path(str(name)),
                    ),
                    patch(
                        "idm_eagle_bridge.media.subprocess.run",
                        side_effect=version_probe,
                    ),
                ):
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=5)
            finally:
                media.close()

        self.assertFalse(failures)
        self.assertEqual(call_count, 4, "concurrent health polls must share one tool probe")
        self.assertGreaterEqual(maximum_active, 2, "independent version probes should run in parallel")

    def test_polling_order_queries_do_not_sort_the_entire_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Database(Path(temporary) / "indexes.db")
            with database.session() as connection:
                plans = connection.execute(
                    """
                    EXPLAIN QUERY PLAN
                    SELECT plan.id
                    FROM download_plans AS plan
                    JOIN media_groups AS groups ON groups.id = plan.group_id
                    LEFT JOIN jobs ON jobs.id = plan.job_id
                    ORDER BY plan.created_at DESC LIMIT 200
                    """
                ).fetchall()
                jobs = connection.execute(
                    """
                    EXPLAIN QUERY PLAN
                    SELECT * FROM jobs INDEXED BY idx_jobs_actionable_created
                    WHERE status IN ('waiting_source', 'queued', 'waiting_eagle', 'retry')
                      AND (next_retry_at IS NULL OR next_retry_at <= ?)
                    ORDER BY created_at ASC LIMIT 20
                    """,
                    (time.time(),),
                ).fetchall()
                recent_jobs = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM jobs ORDER BY created_at DESC LIMIT 500"
                ).fetchall()
                linked_job = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT id FROM download_plans WHERE job_id = ?",
                    ("job-id",),
                ).fetchall()
                linked_group = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT id FROM download_plans WHERE group_id = ?",
                    ("group-id",),
                ).fetchall()

        plan_details = " | ".join(str(row[3]) for row in plans)
        job_details = " | ".join(str(row[3]) for row in jobs)
        recent_details = " | ".join(str(row[3]) for row in recent_jobs)
        linked_job_details = " | ".join(str(row[3]) for row in linked_job)
        linked_group_details = " | ".join(str(row[3]) for row in linked_group)
        self.assertNotIn("TEMP B-TREE", plan_details)
        self.assertNotIn("TEMP B-TREE", job_details)
        self.assertNotIn("TEMP B-TREE", recent_details)
        self.assertIn("INDEX", linked_job_details)
        self.assertNotIn("SCAN download_plans", linked_job_details)
        self.assertIn("INDEX", linked_group_details)
        self.assertNotIn("SCAN download_plans", linked_group_details)

    def test_source_matching_bounds_candidate_scoring_under_capture_bursts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Database(Path(temporary) / "sources.db")
            created_at = time.time()
            media = Path(temporary) / "captured.mp4"
            media.write_bytes(b"captured")
            job_id = database.add_job(str(media), created_at=created_at)
            with database.transaction() as connection:
                connection.executemany(
                    """
                    INSERT INTO source_events(
                        id, page_url, page_title, domain, media_hint,
                        event_type, created_at
                    ) VALUES(?, ?, ?, 'example.com', ?, 'capture', ?)
                    """,
                    (
                        (
                            str(uuid.uuid4()),
                            f"https://example.com/watch/{index}",
                            f"captured {index}",
                            f"captured-{index}.mp4",
                            created_at - index * 0.001,
                        )
                        for index in range(750)
                    ),
                )

            original_choose = database._choose_source
            candidate_counts: list[int] = []

            def record_candidates(file_name: Path, candidates: list) -> object:
                candidate_counts.append(len(candidates))
                return original_choose(file_name, candidates)

            with patch.object(database, "_choose_source", side_effect=record_candidates):
                database.attach_best_source(job_id)

        self.assertEqual(len(candidate_counts), 1)
        self.assertLessEqual(candidate_counts[0], 500)

    def test_candidate_bound_never_drops_explicit_ignore_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Database(Path(temporary) / "explicit-source.db")
            created_at = time.time()
            media = Path(temporary) / "ignored.mp4"
            media.write_bytes(b"ignored")
            job_id = database.add_job(str(media), created_at=created_at)
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO source_events(
                        id, page_url, page_title, domain, media_hint,
                        event_type, created_at
                    ) VALUES(?, 'https://example.com/ignored', 'ignore',
                             'example.com', 'ignored.mp4', 'ignore', ?)
                    """,
                    (str(uuid.uuid4()), created_at - 1),
                )
                connection.executemany(
                    """
                    INSERT INTO source_events(
                        id, page_url, page_title, domain, media_hint,
                        event_type, created_at
                    ) VALUES(?, ?, ?, 'example.com', ?, 'capture', ?)
                    """,
                    (
                        (
                            str(uuid.uuid4()),
                            f"https://example.com/noise/{index}",
                            f"noise {index}",
                            f"noise-{index}.mp4",
                            created_at - index * 0.001,
                        )
                        for index in range(600)
                    ),
                )

            attached = database.attach_best_source(job_id)
            job = database.get_job(job_id)

        self.assertTrue(attached)
        self.assertEqual(job["status"], "ignored_by_user")


if __name__ == "__main__":
    unittest.main()
