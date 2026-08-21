from __future__ import annotations

import functools
import http.server
import io
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.media import (
    MediaCoordinator,
    MediaPlanError,
    canonical_page_resolver_url,
    redact_media_url,
    resolve_media_tool,
    safe_output_name,
)
from idm_eagle_bridge.network_proxy import ProxyRoute


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        return


class MediaCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = Database(self.root / "bridge.db")
        self.ready = Mock()
        self.coordinator = MediaCoordinator(
            self.database, workers=1, ready_callback=self.ready
        )

    def tearDown(self) -> None:
        self.coordinator.close()
        self.temporary.cleanup()

    @staticmethod
    def payload(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "pageUrl": "https://www.bilibili.com/video/BV1test?spm_id_from=secret",
            "pageTitle": "测试视频",
            "outputName": "测试：视频.mp4",
            "outputContainer": "mp4",
            "mergeMode": "direct",
            "route": "browser",
            "importToEagle": True,
            "tabId": 7,
            "streams": [
                {
                    "clientIndex": 0,
                    "url": "https://cdn.example/video.mp4?token=private",
                    "role": "video",
                    "name": "video.mp4",
                    "extension": "mp4",
                    "mimeType": "video/mp4",
                    "size": 123,
                    "duration": 12,
                    "drm": False,
                }
            ],
            "runtimeHeaders": [{}],
        }
        payload.update(overrides)
        return payload

    def _media_tools(self) -> tuple[Path, Path]:
        try:
            return resolve_media_tool("ffmpeg"), resolve_media_tool("ffprobe")
        except MediaPlanError:
            self.skipTest("FFmpeg build asset is not available")

    def test_ui_summary_is_lightweight_and_list_projection_is_read_only(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())
        job_id = self.database.add_job(str(self.root / "projected.mp4"))
        fixed_revision = time.time() - 120
        with self.database.session() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'imported' WHERE id = ?",
                (job_id,),
            )
            connection.execute(
                """
                UPDATE download_plans SET status = 'ready_to_import',
                    progress = 90, job_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (job_id, fixed_revision, plan["id"]),
            )

        summary = self.coordinator.ui_summary()
        listed = self.coordinator.list_plans()
        with self.database.session() as connection:
            stored = connection.execute(
                "SELECT status, updated_at FROM download_plans WHERE id = ?",
                (plan["id"],),
            ).fetchone()

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["active"], 0)
        self.assertEqual(listed[0]["status"], "imported")
        self.assertEqual(listed[0]["progress"], 100)
        self.assertEqual(stored["status"], "ready_to_import")
        self.assertEqual(stored["updated_at"], fixed_revision)

    def _make_video(self, target: Path, color: str = "blue", seconds: int = 1) -> None:
        ffmpeg, _ffprobe = self._media_tools()
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=25",
                "-t",
                str(seconds),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )

    def test_manifest_quality_selection_uses_the_requested_program(self) -> None:
        probe = {
            "programs": [
                {"program_id": 0, "streams": [
                    {"index": 0, "codec_type": "video", "width": 1280, "height": 720, "bit_rate": "3200000"},
                    {"index": 1, "codec_type": "audio", "bit_rate": "128000"},
                ]},
                {"program_id": 1, "streams": [
                    {"index": 2, "codec_type": "video", "width": 1920, "height": 1080, "bit_rate": "6300000"},
                    {"index": 3, "codec_type": "audio", "bit_rate": "128000"},
                ]},
                {"program_id": 2, "streams": [
                    {"index": 4, "codec_type": "video", "width": 640, "height": 360, "bit_rate": "900000"},
                    {"index": 5, "codec_type": "audio", "bit_rate": "96000"},
                ]},
                {"program_id": 3, "streams": [
                    {"index": 6, "codec_type": "video", "width": 3840, "height": 2160, "bit_rate": "18000000"},
                    {"index": 7, "codec_type": "audio", "bit_rate": "192000"},
                ]},
                {"program_id": 4, "streams": [
                    {"index": 8, "codec_type": "video", "width": 2560, "height": 1440, "bit_rate": "9000000"},
                    {"index": 9, "codec_type": "audio", "bit_rate": "160000"},
                ]},
                {"program_id": 5, "streams": [
                    {"index": 10, "codec_type": "video", "width": 854, "height": 480, "bit_rate": "1300000"},
                    {"index": 11, "codec_type": "audio", "bit_rate": "96000"},
                ]},
                {"program_id": 6, "streams": [
                    {"index": 12, "codec_type": "video", "width": 426, "height": 240, "bit_rate": "480000"},
                    {"index": 13, "codec_type": "audio", "bit_rate": "64000"},
                ]},
                {"program_id": 7, "streams": [
                    {"index": 14, "codec_type": "video", "width": 256, "height": 144, "bit_rate": "180000"},
                    {"index": 15, "codec_type": "audio", "bit_rate": "64000"},
                ]},
            ]
        }
        self.assertEqual(
            MediaCoordinator._select_manifest_stream_indexes(probe, 1080),
            (2, 3),
        )
        self.assertEqual(
            MediaCoordinator._select_manifest_stream_indexes(probe, 720),
            (0, 1),
        )
        self.assertEqual(
            MediaCoordinator._select_manifest_stream_indexes(probe, 1440),
            (8, 9),
        )
        self.assertEqual(
            MediaCoordinator._select_manifest_stream_indexes(probe, 480),
            (10, 11),
        )
        self.assertEqual(
            MediaCoordinator._select_manifest_stream_indexes(probe, None),
            (6, 7),
        )

    @staticmethod
    def _start_server(directory: Path, handler_type: type[http.server.SimpleHTTPRequestHandler] = QuietHandler):
        handler = functools.partial(handler_type, directory=str(directory))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _wait(self, plan_id: str, timeout: float = 40) -> dict:
        deadline = time.monotonic() + timeout
        result = self.coordinator.get_plan(plan_id)
        while result["status"] not in {
            "ready_to_import",
            "completed_local",
            "retry",
            "canceled",
        } and time.monotonic() < deadline:
            time.sleep(0.1)
            result = self.coordinator.get_plan(plan_id)
        return result

    def test_schema_six_has_safe_post_import_cleanup_state(self) -> None:
        with self.database.session() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(download_plans)")
            }
        self.assertEqual(version, 6)
        self.assertNotIn("component_files", names)
        self.assertTrue(
            {
                "import_to_eagle",
                "downloaded_bytes",
                "total_bytes",
                "phase_detail",
                "preview_path",
                "delete_after_import",
            }.issubset(columns)
        )

    def test_post_import_cleanup_requires_an_explicit_request(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(
                self.payload(deleteAfterImport=True)
            )
        stored = self.coordinator.get_plan(plan["id"])
        self.assertEqual(stored["import_to_eagle"], 1)
        self.assertEqual(stored["delete_after_import"], 1)

        with patch.object(self.coordinator, "schedule"):
            legacy_extension = self.coordinator.create_plan(self.payload())
        self.assertEqual(
            self.coordinator.get_plan(legacy_extension["id"])["delete_after_import"],
            0,
        )

        with patch.object(self.coordinator, "schedule"):
            non_boolean = self.coordinator.create_plan(
                self.payload(deleteAfterImport="true")
            )
        self.assertEqual(
            self.coordinator.get_plan(non_boolean["id"])["delete_after_import"],
            0,
        )

        with patch.object(self.coordinator, "schedule"):
            download_only = self.coordinator.create_plan(
                self.payload(importToEagle=False)
            )
        self.assertEqual(
            self.coordinator.get_plan(download_only["id"])["delete_after_import"],
            0,
        )

    def test_schema_six_migration_keeps_existing_plans_by_default(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(
                self.payload(deleteAfterImport=True)
            )
        with self.database.session() as connection:
            connection.execute(
                "ALTER TABLE download_plans DROP COLUMN delete_after_import"
            )
            connection.execute("PRAGMA user_version = 5")

        reopened = Database(self.database.path)

        with reopened.session() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            migrated = connection.execute(
                "SELECT delete_after_import FROM download_plans WHERE id = ?",
                (plan["id"],),
            ).fetchone()
        self.assertEqual(version, 6)
        self.assertEqual(migrated["delete_after_import"], 0)

    def test_schema_five_migrates_old_browser_tasks_without_guessing_urls(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())
        with self.database.session() as connection:
            connection.execute(
                """
                CREATE TABLE component_files (
                    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, stream_id TEXT NOT NULL,
                    role TEXT NOT NULL, expected_relative_path TEXT NOT NULL,
                    status TEXT NOT NULL, owned INTEGER NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "UPDATE download_plans SET route = 'browser', status = 'downloading_components' WHERE id = ?",
                (plan["id"],),
            )
            connection.execute("PRAGMA user_version = 4")
        reopened = Database(self.database.path)
        with reopened.session() as connection:
            migrated = connection.execute(
                "SELECT route, status, error_code FROM download_plans WHERE id = ?",
                (plan["id"],),
            ).fetchone()
            component_table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'component_files'"
            ).fetchone()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 6)
        self.assertIsNone(component_table)
        self.assertEqual(dict(migrated), {
            "route": "desktop",
            "status": "retry",
            "error_code": "download_context_expired",
        })

    def test_every_plan_is_desktop_and_sensitive_context_is_memory_only(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(
                self.payload(
                    route="browser",
                    runtimeHeaders=[
                        {
                            "referer": "https://www.bilibili.com/",
                            "authorization": "Bearer private",
                            "cookie": "SESSDATA=private",
                            "origin": "https://www.bilibili.com\r\nX-Injected: yes",
                        }
                    ],
                )
            )
        self.assertEqual(plan["route"], "desktop")
        runtime = self.coordinator._remote_inputs[plan["id"]]["streams"][0]
        self.assertEqual(runtime["headers"]["authorization"], "Bearer private")
        self.assertEqual(runtime["headers"]["cookie"], "SESSDATA=private")
        self.assertNotIn("origin", runtime["headers"])
        with self.database.session() as connection:
            stored = connection.execute(
                "SELECT route FROM download_plans WHERE id = ?", (plan["id"],)
            ).fetchone()
            dump = " ".join(
                str(value)
                for row in connection.execute("SELECT * FROM media_streams")
                for value in row
                if value is not None
            )
        self.assertEqual(stored["route"], "desktop")
        self.assertNotIn("private", dump)

    def test_youtube_resolver_plan_keeps_quality_and_auth_context_out_of_database(self) -> None:
        stream = {
            **self.payload()["streams"][0],
            "url": "https://www.youtube.com/watch?v=pIzs1qe-aBc",
            "resolver": "youtube",
            "preferredQuality": "1440p",
            "size": None,
        }
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload(
                pageUrl=stream["url"],
                streams=[stream],
                runtimeHeaders=[{"cookie": "SAPISID=top-secret", "user-agent": "Chrome/Test"}],
            ))
        runtime = self.coordinator._remote_inputs[plan["id"]]["streams"][0]
        self.assertEqual(runtime["resolver"], "youtube")
        self.assertEqual(runtime["preferred_quality"], "1440p")
        self.assertEqual(runtime["headers"]["cookie"], "SAPISID=top-secret")
        with self.database.session() as connection:
            dump = " ".join(
                str(value)
                for table in ("media_streams", "media_groups", "download_plans")
                for row in connection.execute(f"SELECT * FROM {table}")
                for value in row
                if value is not None
            )
        self.assertNotIn("top-secret", dump)

    def test_page_resolver_plan_keeps_permalink_and_auth_context_out_of_database(self) -> None:
        long_session_cookie = "sessionid=" + "s" * 6000 + "; csrftoken=top-secret"
        stream = {
            **self.payload()["streams"][0],
            "url": "https://www.instagram.com/p/Da9rBuVjAGK/",
            "resolver": "page",
            "preferredQuality": "",
            "size": None,
        }
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload(
                pageUrl="https://www.instagram.com/",
                streams=[stream],
                runtimeHeaders=[{"cookie": long_session_cookie, "user-agent": "Chrome/Test"}],
            ))
        runtime = self.coordinator._remote_inputs[plan["id"]]["streams"][0]
        self.assertEqual(runtime["resolver"], "page")
        self.assertEqual(runtime["url"], "https://www.instagram.com/p/Da9rBuVjAGK/")
        self.assertEqual(runtime["headers"]["cookie"], long_session_cookie)
        with self.database.session() as connection:
            dump = " ".join(
                str(value)
                for table in ("media_streams", "media_groups", "download_plans")
                for row in connection.execute(f"SELECT * FROM {table}")
                for value in row
                if value is not None
            )
        self.assertNotIn("top-secret", dump)

    def test_page_resolver_rejects_private_network_urls(self) -> None:
        stream = {
            **self.payload()["streams"][0],
            "url": "http://127.0.0.1/private-video",
            "resolver": "page",
            "size": None,
        }
        with self.assertRaises(MediaPlanError) as raised:
            self.coordinator.create_plan(self.payload(streams=[stream]))
        self.assertEqual(raised.exception.code, "invalid_page_resolver_url")

    def test_douyin_modal_page_is_canonicalized_to_supported_video_permalink(self) -> None:
        self.assertEqual(
            canonical_page_resolver_url(
                "https://www.douyin.com/jingxuan?modal_id=7662692425235828009&from_page=feed"
            ),
            "https://www.douyin.com/video/7662692425235828009",
        )

    def test_youtube_resolver_uses_exact_quality_and_ephemeral_cookie_file(self) -> None:
        class FakeProcess:
            returncode = 0

            def communicate(self):
                return (
                    "https://rr.example.googlevideo.com/videoplayback?itag=271\n"
                    "https://rr.example.googlevideo.com/videoplayback?itag=251\n",
                    "",
                )

            def terminate(self):
                self.returncode = 1

        process = FakeProcess()
        with patch("idm_eagle_bridge.media.resolve_media_tool", side_effect=lambda name: self.root / f"{name}.exe"), patch(
            "idm_eagle_bridge.media.subprocess.Popen", return_value=process
        ) as popen:
            streams = self.coordinator._resolve_youtube_streams(
                "plan-youtube",
                {
                    "url": "https://www.youtube.com/watch?v=pIzs1qe-aBc",
                    "resolver": "youtube",
                    "preferred_quality": "1440p",
                    "duration": 3207,
                    "headers": {
                        "cookie": "SAPISID=top-secret==; SIDCC=other-secret",
                        "user-agent": "Chrome/Test",
                        "referer": "https://www.youtube.com/watch?v=pIzs1qe-aBc",
                    },
                },
                self.root / "resolver-work",
                "http://127.0.0.1:7890",
            )
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--proxy") + 1], "http://127.0.0.1:7890")
        self.assertIn("bestvideo[height=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height=1440]+bestaudio/best[height=1440]", command)
        self.assertNotIn("top-secret", " ".join(str(value) for value in command))
        cookie_path = Path(command[command.index("--cookies") + 1])
        self.assertFalse(cookie_path.exists(), "the resolver cookie file must be removed immediately")
        self.assertEqual([stream["role"] for stream in streams], ["video", "audio"])
        self.assertTrue(all(stream["headers"]["cookie"] == "SAPISID=top-secret==; SIDCC=other-secret" for stream in streams))

    def test_blob_url_is_rejected_instead_of_falling_back_to_browser_download(self) -> None:
        stream = {**self.payload()["streams"][0], "url": "blob:https://example.com/id"}
        with self.assertRaisesRegex(MediaPlanError, "blob"):
            self.coordinator.create_plan(self.payload(streams=[stream]))
        self.assertEqual(self.coordinator.list_plans(), [])

    def test_fixed_byte_range_mp4_is_rejected_before_ffmpeg(self) -> None:
        stream = {
            **self.payload()["streams"][0],
            "url": (
                "https://media.example/v2/range/prot/"
                "cmFuZ2U9OTIwNzAwOS0xMzQ4NDE3Ng/avf/video-id.mp4"
            ),
            "size": 4_277_168,
        }
        with self.assertRaises(MediaPlanError) as raised:
            self.coordinator.create_plan(self.payload(streams=[stream]))
        self.assertEqual(raised.exception.code, "fixed_range_fragment")
        self.assertIn("分片", str(raised.exception))
        self.assertEqual(self.coordinator.list_plans(), [])

    def test_instagram_bytestart_byteend_fragment_is_rejected_before_ffmpeg(self) -> None:
        stream = {
            **self.payload()["streams"][0],
            "url": (
                "https://scontent.example.cdninstagram.com/o1/video.mp4?token=signed"
                "&bytestart=886&byteend=173864"
            ),
            "size": 172_979,
        }
        with self.assertRaises(MediaPlanError) as raised:
            self.coordinator.create_plan(self.payload(streams=[stream]))
        self.assertEqual(raised.exception.code, "fixed_range_fragment")
        self.assertEqual(self.coordinator.list_plans(), [])

    def test_explicit_range_query_is_rejected_even_when_size_reports_whole_file(self) -> None:
        stream = {
            **self.payload()["streams"][0],
            "url": "https://cdn.example/video.mp4?range=0-1023",
            "size": 50_000_000,
        }
        with self.assertRaises(MediaPlanError) as raised:
            self.coordinator.create_plan(self.payload(streams=[stream]))
        self.assertEqual(raised.exception.code, "fixed_range_fragment")

    def test_generic_page_resolver_uses_permalink_and_ephemeral_cookie_file(self) -> None:
        class FakeProcess:
            returncode = 0

            def communicate(self):
                return ("https://cdn.example/video.mp4\nhttps://cdn.example/audio.m4a\n", "")

            def terminate(self):
                self.returncode = 1

        context = {
            "url": "https://www.instagram.com/p/Da9rBuVjAGK/",
            "resolver": "page",
            "preferred_quality": "",
            "duration": 10.4,
            "headers": {
                "cookie": "sessionid=top-secret; csrftoken=other-secret",
                "user-agent": "Chrome/Test",
                "referer": "https://www.instagram.com/",
            },
        }
        process = FakeProcess()
        with patch("idm_eagle_bridge.media.resolve_media_tool", side_effect=lambda name: self.root / f"{name}.exe"), patch(
            "idm_eagle_bridge.media.subprocess.Popen", return_value=process
        ) as popen:
            streams = self.coordinator._resolve_page_streams(
                "plan-page",
                context,
                self.root / "page-resolver-work",
                "http://127.0.0.1:7890",
            )
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--proxy") + 1], "http://127.0.0.1:7890")
        selector = command[command.index("--format") + 1]
        self.assertTrue(selector.startswith("bestvideo[ext=mp4]+bestaudio[ext=m4a]/"))
        self.assertIn("bestvideo[ext=mp4]+bestaudio[ext=mp4]", selector)
        self.assertIn("bestvideo[ext=mp4]+bestaudio", selector)
        self.assertTrue(selector.endswith("/best"))
        self.assertNotIn("top-secret", " ".join(str(value) for value in command))
        cookie_path = Path(command[command.index("--cookies") + 1])
        self.assertFalse(cookie_path.exists(), "generic resolver cookies must be deleted immediately")
        self.assertEqual([stream["role"] for stream in streams], ["video", "audio"])
        self.assertTrue(all(stream["resolver"] == "" for stream in streams))

    def test_page_resolver_does_not_forward_oversized_page_credentials_to_cdn(self) -> None:
        class FakeProcess:
            returncode = 0

            def communicate(self):
                return ("https://cdn.example/video.mp4\n", "")

            def terminate(self):
                self.returncode = 1

        context = {
            "url": "https://www.douyin.com/video/7662692425235828009",
            "resolver": "page",
            "headers": {
                "cookie": "sessionid=" + "s" * 9000,
                "authorization": "Bearer page-only-secret",
                "user-agent": "Chrome/Test",
                "referer": "https://www.douyin.com/jingxuan",
                "origin": "https://www.douyin.com",
            },
        }
        with patch(
            "idm_eagle_bridge.media.resolve_media_tool",
            side_effect=lambda name: self.root / f"{name}.exe",
        ), patch(
            "idm_eagle_bridge.media.subprocess.Popen", return_value=FakeProcess()
        ):
            streams = self.coordinator._resolve_page_streams(
                "plan-douyin-cdn",
                context,
                self.root / "douyin-cdn-work",
            )

        self.assertEqual(len(streams), 1)
        resolved_headers = streams[0]["headers"]
        self.assertEqual(resolved_headers["user-agent"], "Chrome/Test")
        self.assertEqual(resolved_headers["referer"], "https://www.douyin.com/jingxuan")
        self.assertEqual(resolved_headers["origin"], "https://www.douyin.com")
        self.assertNotIn("cookie", resolved_headers)
        self.assertNotIn("authorization", resolved_headers)
        ffmpeg_arguments = self.coordinator._ffmpeg_input_arguments(streams[0], None)
        self.assertNotIn("Cookie:", " ".join(ffmpeg_arguments))
        self.assertNotIn("Authorization:", " ".join(ffmpeg_arguments))

    def test_page_resolver_keeps_small_credentials_for_the_same_host(self) -> None:
        headers = self.coordinator._page_resolved_headers(
            "https://media.example/watch/1",
            "https://media.example/files/1.mp4",
            {
                "cookie": "sessionid=needed",
                "authorization": "Bearer needed",
                "user-agent": "Chrome/Test",
            },
        )
        self.assertEqual(headers["cookie"], "sessionid=needed")
        self.assertEqual(headers["authorization"], "Bearer needed")
        self.assertEqual(headers["user-agent"], "Chrome/Test")

    def test_douyin_page_resolver_canonicalizes_modal_url_before_process_start(self) -> None:
        class FakeProcess:
            returncode = 1

            def communicate(self):
                return ("", "ERROR: Unsupported URL: https://www.douyin.com/jingxuan")

            def terminate(self):
                self.returncode = 1

        context = {
            "url": "https://www.douyin.com/jingxuan?modal_id=7662692425235828009",
            "resolver": "page",
            "headers": {"user-agent": "Chrome/Test"},
        }
        with patch("idm_eagle_bridge.media.resolve_media_tool", side_effect=lambda name: self.root / f"{name}.exe"), patch(
            "idm_eagle_bridge.media.subprocess.Popen", return_value=FakeProcess()
        ) as popen, self.assertRaises(MediaPlanError) as raised:
            self.coordinator._resolve_page_streams(
                "plan-douyin-modal", context, self.root / "douyin-resolver-work"
            )
        self.assertEqual(popen.call_args.args[0][-1], "https://www.douyin.com/video/7662692425235828009")
        self.assertEqual(raised.exception.code, "douyin_page_unsupported")
        self.assertNotIn("https://", str(raised.exception))

    def test_douyin_page_resolver_reports_expired_browser_session_separately(self) -> None:
        class FakeProcess:
            returncode = 1

            def communicate(self):
                return ("", "Fresh cookies (not necessarily logged in) are needed")

            def terminate(self):
                self.returncode = 1

        with patch("idm_eagle_bridge.media.resolve_media_tool", side_effect=lambda name: self.root / f"{name}.exe"), patch(
            "idm_eagle_bridge.media.subprocess.Popen", return_value=FakeProcess()
        ), self.assertRaises(MediaPlanError) as raised:
            self.coordinator._resolve_page_streams(
                "plan-douyin-cookie",
                {
                    "url": "https://www.douyin.com/video/7662692425235828009",
                    "resolver": "page",
                    "headers": {"cookie": "sessionid=top-secret"},
                },
                self.root / "douyin-cookie-work",
            )
        self.assertEqual(raised.exception.code, "douyin_session_expired")
        self.assertNotIn("top-secret", str(raised.exception))

    def test_desktop_downloads_direct_media_preserves_subtitle_and_queues_eagle(self) -> None:
        media_root = self.root / "direct"
        media_root.mkdir()
        video = media_root / "video.mp4"
        subtitle = media_root / "subtitle.vtt"
        self._make_video(video)
        subtitle.write_text("WEBVTT\n\n00:00.000 --> 00:00.500\n测试\n", encoding="utf-8")
        server, thread = self._start_server(media_root)
        port = server.server_address[1]
        try:
            streams = [
                {
                    "url": f"http://127.0.0.1:{port}/video.mp4?token=ephemeral",
                    "role": "video",
                    "name": "video.mp4",
                    "extension": "mp4",
                    "mimeType": "video/mp4",
                    "size": video.stat().st_size,
                    "duration": 1,
                    "drm": False,
                },
                {
                    "url": f"http://127.0.0.1:{port}/subtitle.vtt?token=ephemeral",
                    "role": "subtitle",
                    "name": "简体中文.vtt",
                    "extension": "vtt",
                    "mimeType": "text/vtt",
                    "language": "zh-CN",
                    "drm": False,
                },
            ]
            download_root = self.root / "desktop-downloads"
            with patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)}):
                plan = self.coordinator.create_plan(
                    self.payload(
                        outputName="本机直链.mp4",
                        streams=streams,
                        runtimeHeaders=[{}, {}],
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "ready_to_import", result.get("error_message"))
            self.assertEqual(result["route"], "desktop")
            self.assertEqual(result["progress"], 90)
            self.assertTrue(Path(result["final_path"]).is_file())
            self.assertTrue(Path(result["preview_path"]).is_file())
            self.assertTrue(list(Path(result["final_path"]).parent.glob("本机直链.zh-CN.vtt")))
            self.assertIsNotNone(result["job_id"])
            self.assertEqual(
                self.database.get_job(result["job_id"])["source_url"],
                "https://www.bilibili.com/video/BV1test",
            )
            self.assertTrue(self.ready.called)
            self.database.update_job(
                result["job_id"], status="imported", completed_at=time.time()
            )
            imported = self.coordinator.get_plan(plan["id"])
            self.assertEqual(imported["status"], "imported")
            self.assertEqual(imported["progress"], 100)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_ffmpeg_reports_overlong_headers_without_hiding_the_cause(self) -> None:
        media_root = self.root / "overlong-headers"
        media_root.mkdir()
        video = media_root / "video.mp4"
        self._make_video(video)
        server, thread = self._start_server(media_root)
        try:
            stream = {
                "url": f"http://127.0.0.1:{server.server_address[1]}/video.mp4",
                "role": "video",
                "name": "video.mp4",
                "extension": "mp4",
                "mimeType": "video/mp4",
                "size": video.stat().st_size,
                "duration": 1,
                "drm": False,
            }
            with patch.dict(
                os.environ,
                {"IDM_EAGLE_DOWNLOAD_ROOT": str(self.root / "overlong-downloads")},
            ):
                plan = self.coordinator.create_plan(
                    self.payload(
                        streams=[stream],
                        runtimeHeaders=[{"cookie": "sessionid=" + "s" * 9000}],
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "retry")
            self.assertEqual(result["error_code"], "desktop_headers_too_large")
            self.assertIn("下载请求头超过", result["error_message"])
            self.assertNotIn("sessionid", result["error_message"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_direct_subtitle_download_explicitly_bypasses_system_proxy(self) -> None:
        target = self.root / "direct-subtitle.vtt"
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"WEBVTT\n")

        with patch("idm_eagle_bridge.media.ProxyHandler") as proxy_handler, patch(
            "idm_eagle_bridge.media.build_opener", return_value=opener
        ):
            self.coordinator._download_direct_subtitle(
                "plan-direct-subtitle",
                {"url": "https://cdn.example/subtitle.vtt", "headers": {}},
                target,
            )

        proxy_handler.assert_called_once_with({})
        opener.open.assert_called_once()
        self.assertEqual(target.read_bytes(), b"WEBVTT\n")

    def test_wechat_download_retries_http_400_with_range_header(self) -> None:
        class Response(io.BytesIO):
            def __init__(self, content: bytes) -> None:
                super().__init__(content)
                self.headers = {"Content-Length": str(len(content))}

        target = self.root / "wechat-range-retry.mp4"
        content = b"wechat-media"
        url = "https://finder.video.qq.com/251/20302/stodownload?token=redacted"
        opener = Mock()
        opener.open.side_effect = [
            HTTPError(url, 400, "Bad Request", {}, io.BytesIO()),
            Response(content),
        ]

        with patch("idm_eagle_bridge.media.build_opener", return_value=opener):
            prepared = self.coordinator._download_and_decrypt_wechat_stream(
                "missing-plan",
                {
                    "url": url,
                    "headers": {"User-Agent": "Mozilla/5.0"},
                    "size": len(content),
                    "wechat_decode_key": 1,
                    "wechat_encrypted_bytes": 0,
                },
                target,
            )

        self.assertEqual(opener.open.call_count, 2)
        first_request = opener.open.call_args_list[0].args[0]
        second_request = opener.open.call_args_list[1].args[0]
        self.assertIsNone(first_request.get_header("Range"))
        self.assertEqual(second_request.get_header("Range"), "bytes=0-")
        self.assertEqual(first_request.get_header("Accept-encoding"), "identity")
        self.assertEqual(target.read_bytes(), content)
        self.assertTrue(prepared["local_input"])

    def test_wechat_download_reports_expired_address_after_range_retry(self) -> None:
        target = self.root / "wechat-expired.mp4"
        url = "https://finder.video.qq.com/251/20302/stodownload?token=redacted"
        opener = Mock()
        opener.open.side_effect = [
            HTTPError(url, 400, "Bad Request", {}, io.BytesIO()),
            HTTPError(url, 400, "Bad Request", {}, io.BytesIO()),
        ]

        with patch("idm_eagle_bridge.media.build_opener", return_value=opener):
            with self.assertRaisesRegex(MediaPlanError, "重新播放后选择当前画质") as caught:
                self.coordinator._download_and_decrypt_wechat_stream(
                    "missing-plan",
                    {
                        "url": url,
                        "headers": {},
                        "size": 0,
                        "wechat_decode_key": 1,
                        "wechat_encrypted_bytes": 0,
                    },
                    target,
                )

        self.assertEqual(caught.exception.code, "wechat_download_failed")
        self.assertEqual(opener.open.call_count, 2)
        self.assertFalse(target.exists())

    def test_wechat_download_uses_size_verified_captured_url_after_400(self) -> None:
        class Response(io.BytesIO):
            def __init__(self, content: bytes) -> None:
                super().__init__(content)
                self.headers = {"Content-Length": str(len(content))}

        target = self.root / "wechat-captured-fallback.mp4"
        content = b"verified-original-media"
        minimal = (
            "https://finder.video.qq.com/251/20302/stodownload?"
            "encfilekey=file-key&token=access-token"
        )
        captured = minimal + "&hy=SZ&idx=1&sign=current-signature"
        opener = Mock()
        opener.open.side_effect = [
            HTTPError(minimal, 400, "Bad Request", {}, io.BytesIO()),
            HTTPError(minimal, 400, "Bad Request", {}, io.BytesIO()),
            Response(content),
        ]

        with patch("idm_eagle_bridge.media.build_opener", return_value=opener):
            prepared = self.coordinator._download_and_decrypt_wechat_stream(
                "missing-plan",
                {
                    "url": minimal,
                    "wechat_captured_url": captured,
                    "headers": {},
                    "size": len(content),
                    "wechat_decode_key": 1,
                    "wechat_encrypted_bytes": 0,
                },
                target,
            )

        self.assertEqual(opener.open.call_count, 3)
        fallback_request = opener.open.call_args_list[2].args[0]
        self.assertEqual(fallback_request.full_url, captured)
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(prepared["wechat_captured_url"], "")

    def test_wechat_captured_url_must_match_declared_original_size(self) -> None:
        class Response(io.BytesIO):
            def __init__(self, content: bytes) -> None:
                super().__init__(content)
                self.headers = {"Content-Length": str(len(content))}

        target = self.root / "wechat-captured-size-mismatch.mp4"
        minimal = (
            "https://finder.video.qq.com/251/20302/stodownload?"
            "encfilekey=file-key&token=access-token"
        )
        captured = minimal + "&sign=current-signature"
        opener = Mock()
        opener.open.side_effect = [
            HTTPError(minimal, 400, "Bad Request", {}, io.BytesIO()),
            HTTPError(minimal, 400, "Bad Request", {}, io.BytesIO()),
            Response(b"lower-quality"),
        ]

        with patch("idm_eagle_bridge.media.build_opener", return_value=opener):
            with self.assertRaises(MediaPlanError) as caught:
                self.coordinator._download_and_decrypt_wechat_stream(
                    "missing-plan",
                    {
                        "url": minimal,
                        "wechat_captured_url": captured,
                        "headers": {},
                        "size": 99,
                        "wechat_decode_key": 1,
                        "wechat_encrypted_bytes": 0,
                    },
                    target,
                )

        self.assertEqual(caught.exception.code, "wechat_original_size_mismatch")
        self.assertIn("响应 13 字节，原画声明 99 字节", str(caught.exception))
        self.assertIn("精简地址 HTTP 400", str(caught.exception))
        self.assertIn("改选非“原始视频”的明确画质", str(caught.exception))
        self.assertFalse(target.exists())

    def test_wechat_captured_url_cannot_change_signed_asset(self) -> None:
        payload = self.payload(
            sourceType="wechat_channels",
            streams=[{
                "url": (
                    "https://finder.video.qq.com/251/20302/stodownload?"
                    "encfilekey=file-key&token=access-token"
                ),
                "role": "video",
                "extension": "mp4",
                "size": 10,
                "wechatDecodeKey": "1",
                "wechatEncryptedBytes": 131_072,
                "wechatCapturedUrl": (
                    "https://evil.example/stodownload?"
                    "encfilekey=file-key&token=access-token"
                ),
            }],
            runtimeHeaders=[{}],
        )
        with self.assertRaises(MediaPlanError) as caught:
            self.coordinator.create_plan(payload)
        self.assertEqual(caught.exception.code, "wechat_captured_url_invalid")

    def test_download_only_uses_desktop_and_does_not_create_eagle_job(self) -> None:
        media_root = self.root / "download-only"
        media_root.mkdir()
        video = media_root / "video.mp4"
        self._make_video(video, "orange")
        server, thread = self._start_server(media_root)
        port = server.server_address[1]
        try:
            stream = {
                **self.payload()["streams"][0],
                "url": f"http://127.0.0.1:{port}/video.mp4",
                "size": video.stat().st_size,
                "duration": 1,
            }
            with patch.dict(
                os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(self.root / "only-root")}
            ):
                plan = self.coordinator.create_plan(
                    self.payload(
                        streams=[stream],
                        runtimeHeaders=[{}],
                        importToEagle=False,
                        outputName="仅下载.mp4",
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "completed_local", result.get("error_message"))
            self.assertEqual(result["progress"], 100)
            self.assertIsNone(result["job_id"])
            self.assertTrue(Path(result["final_path"]).is_file())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_direct_download_rejects_duration_identity_mismatch(self) -> None:
        media_root = self.root / "duration-mismatch"
        media_root.mkdir()
        video = media_root / "video.mp4"
        self._make_video(video, "purple", seconds=1)
        server, thread = self._start_server(media_root)
        port = server.server_address[1]
        try:
            stream = {
                **self.payload()["streams"][0],
                "url": f"http://127.0.0.1:{port}/video.mp4",
                "size": video.stat().st_size,
                "duration": 12,
            }
            with patch.dict(
                os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(self.root / "mismatch-root")}
            ):
                plan = self.coordinator.create_plan(
                    self.payload(
                        streams=[stream],
                        runtimeHeaders=[{}],
                        importToEagle=False,
                        outputName="不应交付的错配视频.mp4",
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "retry")
            self.assertEqual(result["error_code"], "output_duration_mismatch")
            self.assertIsNone(result["final_path"])
            self.assertFalse(
                list((self.root / "mismatch-root" / "已完成").glob("不应交付的错配视频*.mp4"))
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_desktop_downloads_protected_separate_video_and_audio(self) -> None:
        ffmpeg, ffprobe = self._media_tools()
        media_root = self.root / "protected"
        media_root.mkdir()
        video_path = media_root / "video.m4s"
        audio_path = media_root / "audio.m4s"
        common = {"capture_output": True, "text": True, "timeout": 60, "check": True}
        subprocess.run(
            [
                str(ffmpeg), "-hide_banner", "-y", "-f", "lavfi", "-i",
                "color=c=purple:s=320x180:r=25", "-t", "1", "-an", "-c:v",
                "libx264", "-pix_fmt", "yuv420p", "-f", "mp4", str(video_path),
            ],
            **common,
        )
        subprocess.run(
            [
                str(ffmpeg), "-hide_banner", "-y", "-f", "lavfi", "-i",
                "sine=frequency=660:sample_rate=48000", "-t", "1", "-vn", "-c:a",
                "aac", "-f", "mp4", str(audio_path),
            ],
            **common,
        )
        required_referer = "https://www.bilibili.com/video/BV1protected"
        required_user_agent = "Mozilla/5.0 Protected-Media-Test"

        class ProtectedHandler(QuietHandler):
            def do_GET(self) -> None:
                if (
                    self.headers.get("Referer") != required_referer
                    or self.headers.get("User-Agent") != required_user_agent
                ):
                    self.send_error(403)
                    return
                super().do_GET()

        server, thread = self._start_server(media_root, ProtectedHandler)
        port = server.server_address[1]
        try:
            streams = [
                {
                    "url": f"http://127.0.0.1:{port}/video.m4s?token=ephemeral",
                    "role": "video", "name": "video.m4s", "extension": "m4s",
                    "mimeType": "video/mp4", "size": video_path.stat().st_size,
                    "duration": 1, "drm": False,
                },
                {
                    "url": f"http://127.0.0.1:{port}/audio.m4s?token=ephemeral",
                    "role": "audio", "name": "audio.m4s", "extension": "m4s",
                    "mimeType": "audio/mp4", "size": audio_path.stat().st_size,
                    "duration": 1, "drm": False,
                },
            ]
            headers = {"referer": required_referer, "user-agent": required_user_agent}
            with patch.dict(
                os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(self.root / "protected-root")}
            ):
                plan = self.coordinator.create_plan(
                    self.payload(
                        pageUrl=required_referer,
                        outputName="受保护分轨.mp4",
                        mergeMode="local_streamcopy",
                        streams=streams,
                        runtimeHeaders=[headers, headers],
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "ready_to_import", result.get("error_message"))
            probe = subprocess.run(
                [
                    str(ffprobe), "-v", "error", "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0", str(result["final_path"]),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(set(probe.stdout.split()), {"video", "audio"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_desktop_downloads_aes128_hls_manifest(self) -> None:
        ffmpeg, ffprobe = self._media_tools()
        hls_root = self.root / "hls"
        hls_root.mkdir()
        server, thread = self._start_server(hls_root)
        port = server.server_address[1]
        try:
            key_path = hls_root / "enc.key"
            key_path.write_bytes(b"0123456789abcdef")
            key_info = hls_root / "enc.keyinfo"
            key_info.write_text(
                f"http://127.0.0.1:{port}/enc.key\n{key_path}\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    str(ffmpeg), "-hide_banner", "-y", "-f", "lavfi", "-i",
                    "color=c=green:s=320x180:r=25", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000", "-t", "2", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "hls",
                    "-hls_time", "0.5", "-hls_list_size", "0", "-hls_key_info_file",
                    str(key_info), str(hls_root / "index.m3u8"),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            stream = {
                "url": f"http://127.0.0.1:{port}/index.m3u8?token=ephemeral",
                "role": "media",
                "name": "index.m3u8",
                "extension": "m3u8",
                "mimeType": "application/vnd.apple.mpegurl",
                "duration": 2,
                "drm": False,
            }
            with patch.dict(
                os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(self.root / "hls-root")}
            ):
                plan = self.coordinator.create_plan(
                    self.payload(
                        outputName="AES-128 HLS.mkv",
                        outputContainer="mkv",
                        mergeMode="local_streamcopy",
                        streams=[stream],
                        runtimeHeaders=[{"referer": f"http://127.0.0.1:{port}/page"}],
                    )
                )
                result = self._wait(plan["id"])
            self.assertEqual(result["status"], "ready_to_import", result.get("error_message"))
            probe = subprocess.run(
                [
                    str(ffprobe), "-v", "error", "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0", str(result["final_path"]),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(set(probe.stdout.split()), {"video", "audio"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_failed_plan_can_retry_only_while_memory_context_exists(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET status = 'retry' WHERE id = ?",
                    (plan["id"],),
                )
            retried = self.coordinator.retry_plan(plan["id"])
        self.assertEqual(retried["status"], "queued")

        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET status = 'downloading' WHERE id = ?",
                (plan["id"],),
            )
        reopened = MediaCoordinator(self.database, workers=1)
        try:
            recovered = reopened.get_plan(plan["id"])
            self.assertEqual(recovered["status"], "retry")
            self.assertEqual(recovered["error_code"], "download_context_expired")
            with self.assertRaisesRegex(MediaPlanError, "来源网页"):
                reopened.retry_plan(plan["id"])
        finally:
            reopened.close()

    def test_queued_plan_can_be_canceled_without_browser_download(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())
        stopped = self.coordinator.stop_plan(plan["id"])
        self.assertEqual(stopped["status"], "canceled")

    def test_stop_on_terminal_plan_does_not_leave_stale_stop_request(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload(importToEagle=False))
        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET status = 'completed_local', progress = 100 WHERE id = ?",
                (plan["id"],),
            )

        result = self.coordinator.stop_plan(plan["id"])

        self.assertEqual(result["status"], "completed_local")
        self.assertNotIn(plan["id"], self.coordinator._stop_requested)

    def test_stop_during_validation_cannot_be_overwritten_by_completion(self) -> None:
        class FinishedProcess:
            def __init__(self, command: list[str]) -> None:
                Path(command[-1]).write_bytes(b"downloaded-media")
                self.stdout = io.StringIO("progress=end\n")
                self.stdin = None
                self.returncode = 0

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

            def poll(self) -> int:
                return self.returncode

            def terminate(self) -> None:
                self.returncode = 1

        entered_validation = threading.Event()
        release_validation = threading.Event()

        def paused_probe(*_args: object, **_kwargs: object) -> dict:
            entered_validation.set()
            self.assertTrue(release_validation.wait(timeout=3))
            return {"streams": [{"codec_type": "video"}], "format": {"duration": "1"}}

        download_root = self.root / "stop-during-validation"
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)}),
            patch.object(self.coordinator, "schedule"),
        ):
            plan = self.coordinator.create_plan(self.payload(importToEagle=False))

        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(download_root)}),
            patch.object(
                self.coordinator.network_proxy,
                "routes_for",
                return_value=[ProxyRoute(None, "direct", "direct", "直连")],
            ),
            patch("idm_eagle_bridge.media.resolve_media_tool", return_value=self.root / "ffmpeg.exe"),
            patch(
                "idm_eagle_bridge.media.subprocess.Popen",
                side_effect=lambda command, **_kwargs: FinishedProcess(command),
            ),
            patch.object(self.coordinator, "_probe", side_effect=paused_probe),
            patch.object(self.coordinator, "_validate_output_duration"),
            patch.object(self.coordinator, "_create_preview", return_value=None),
        ):
            worker = threading.Thread(
                target=self.coordinator._process_guarded,
                args=(plan["id"],),
            )
            worker.start()
            self.assertTrue(entered_validation.wait(timeout=3))
            stopped = self.coordinator.stop_plan(plan["id"])
            self.assertEqual(stopped["status"], "canceled")
            release_validation.set()
            worker.join(timeout=5)

        result = self.coordinator.get_plan(plan["id"])
        self.assertEqual(result["status"], "canceled")
        self.assertFalse((download_root / "留底下载器" / "已完成" / result["output_name"]).exists())

    def test_clear_terminal_history_removes_records_but_not_files_or_active_plans(self) -> None:
        output = self.root / "finished.mp4"
        output.write_bytes(b"user-visible-download")
        with patch.object(self.coordinator, "schedule"):
            finished = self.coordinator.create_plan(self.payload(outputName="finished.mp4"))
            active = self.coordinator.create_plan(self.payload(outputName="active.mp4", tabId=8))
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'completed_local',
                    progress = 100, final_path = ? WHERE id = ?
                """,
                (str(output), finished["id"]),
            )

        self.assertEqual(self.coordinator.clear_terminal_history(), 1)
        self.assertTrue(output.is_file())
        self.assertEqual([plan["id"] for plan in self.coordinator.list_plans()], [active["id"]])
        self.assertNotIn(finished["id"], self.coordinator._remote_inputs)
        self.assertIn(active["id"], self.coordinator._remote_inputs)

    def test_single_plan_cleanup_removes_waiting_import_but_preserves_file(self) -> None:
        output = self.root / "waiting-import.mp4"
        output.write_bytes(b"keep-this-local-file")
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(
                self.payload(outputName="waiting-import.mp4")
            )
        job_id = self.database.add_job(str(output))
        self.database.update_job(job_id, status="waiting_eagle")
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'ready_to_import',
                    progress = 90, final_path = ?, job_id = ?
                WHERE id = ?
                """,
                (str(output), job_id, plan["id"]),
            )

        result = self.coordinator.remove_plan(plan["id"])

        self.assertTrue(result["removed"])
        self.assertTrue(result["filePreserved"])
        self.assertTrue(output.is_file())
        self.assertEqual(self.coordinator.list_plans(), [])
        self.assertIsNone(self.database.get_job(job_id))
        self.assertNotIn(plan["id"], self.coordinator._remote_inputs)

    def test_single_idm_cleanup_detaches_waiting_media_plan_and_preserves_file(self) -> None:
        output = self.root / "waiting-idm-cleanup.mp4"
        output.write_bytes(b"keep-this-local-file")
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(
                self.payload(outputName="waiting-idm-cleanup.mp4")
            )
        job_id = self.database.add_job(str(output))
        self.database.update_job(job_id, status="waiting_eagle")
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'ready_to_import',
                    progress = 90, final_path = ?, job_id = ?
                WHERE id = ?
                """,
                (str(output), job_id, plan["id"]),
            )

        self.assertTrue(self.database.remove_job(job_id))

        detached = self.coordinator.get_plan(plan["id"])
        self.assertEqual(detached["status"], "completed_local")
        self.assertEqual(detached["progress"], 100)
        self.assertEqual(detached["import_to_eagle"], 0)
        self.assertIsNone(detached["job_id"])
        self.assertTrue(output.is_file())
        self.assertIsNone(self.database.get_job(job_id))

    def test_automatic_history_cleanup_unlinks_terminal_plan_without_fk_failure(self) -> None:
        old = time.time() - 120 * 86400
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload(outputName="old-import.mp4"))
        job_id = self.database.add_job(str(self.root / "old-import.mp4"), created_at=old)
        self.database.update_job(
            job_id,
            status="imported",
            eagle_item_id="old-item",
            completed_at=old,
        )
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'imported',
                    job_id = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (job_id, old, old, plan["id"]),
            )

        removed = self.database.cleanup_history(history_days=90)

        self.assertEqual(removed["jobs"], 1)
        self.assertIsNone(self.database.get_job(job_id))
        self.assertIsNone(self.coordinator.get_plan(plan["id"])["job_id"])

    def test_plan_cleanup_removes_orphaned_capture_metadata(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())

        self.coordinator.remove_plan(plan["id"])

        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM download_plans").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_streams").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_groups").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM capture_sessions").fetchone()[0], 0)

    def test_bulk_plan_cleanup_handles_more_than_sqlite_parameter_limit(self) -> None:
        now = time.time()
        count = 1_005
        with self.database.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO capture_sessions(
                    id, page_url, page_title, created_at, updated_at
                ) VALUES(?, '', '', ?, ?)
                """,
                ((f"session-{index}", now, now) for index in range(count)),
            )
            connection.executemany(
                """
                INSERT INTO media_groups(
                    id, session_id, group_key, title, created_at, updated_at
                ) VALUES(?, ?, ?, '', ?, ?)
                """,
                (
                    (
                        f"group-{index}",
                        f"session-{index}",
                        f"group-key-{index}",
                        now,
                        now,
                    )
                    for index in range(count)
                ),
            )
            connection.executemany(
                """
                INSERT INTO download_plans(
                    id, group_id, output_name, output_container, merge_mode,
                    route, status, created_at, updated_at
                ) VALUES(?, ?, 'finished.mp4', 'mp4', 'direct',
                    'desktop', 'completed_local', ?, ?)
                """,
                (
                    (f"plan-{index}", f"group-{index}", now, now)
                    for index in range(count)
                ),
            )

        self.assertEqual(self.coordinator.clear_terminal_history(), count)
        self.assertEqual(self.coordinator.list_plans(), [])
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_groups").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM capture_sessions").fetchone()[0], 0)

    def test_clearing_idm_history_unlinks_terminal_media_plan_only(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            terminal_plan = self.coordinator.create_plan(self.payload(outputName="imported.mp4"))
            active_plan = self.coordinator.create_plan(self.payload(outputName="waiting.mp4", tabId=8))
        terminal_job = self.database.add_job(str(self.root / "imported.mp4"))
        active_job = self.database.add_job(str(self.root / "waiting.mp4"))
        self.database.update_job(terminal_job, status="imported", eagle_item_id="item-1")
        self.database.update_job(active_job, status="failed_permanent")
        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET status = 'imported', job_id = ? WHERE id = ?",
                (terminal_job, terminal_plan["id"]),
            )
            connection.execute(
                "UPDATE download_plans SET status = 'ready_to_import', job_id = ? WHERE id = ?",
                (active_job, active_plan["id"]),
            )

        self.assertEqual(self.database.clear_terminal_history(), 1)
        self.assertIsNone(self.database.get_job(terminal_job))
        self.assertIsNotNone(self.database.get_job(active_job))
        with self.database.session() as connection:
            terminal_link = connection.execute(
                "SELECT job_id FROM download_plans WHERE id = ?", (terminal_plan["id"],)
            ).fetchone()
            active_link = connection.execute(
                "SELECT job_id FROM download_plans WHERE id = ?", (active_plan["id"],)
            ).fetchone()
        self.assertIsNone(terminal_link["job_id"])
        self.assertEqual(active_link["job_id"], active_job)

    def test_completed_plan_preview_is_bounded_to_program_preview_directory(self) -> None:
        station_root = self.root / "preview-root"
        preview = station_root / "留底下载器" / "预览" / "frame.png"
        preview.parent.mkdir(parents=True)
        preview.write_bytes(b"\x89PNG\r\n\x1a\n" + b"preview-frame")
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            patch.object(self.coordinator, "schedule"),
        ):
            plan = self.coordinator.create_plan(self.payload())
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET preview_path = ? WHERE id = ?",
                    (str(preview), plan["id"]),
                )
            result = self.coordinator.get_plan_preview(plan["id"])

        self.assertEqual(result["mimeType"], "image/png")
        self.assertTrue(result["dataUrl"].startswith("data:image/png;base64,"))

        outside = self.root / "outside.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\nnot-owned")
        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET preview_path = ? WHERE id = ?",
                (str(outside), plan["id"]),
            )
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            self.assertRaisesRegex(MediaPlanError, "预览"),
        ):
            self.coordinator.get_plan_preview(plan["id"])

    def test_open_output_uses_only_program_owned_completed_directory(self) -> None:
        station_root = self.root / "open-root"
        completed = station_root / "留底下载器" / "已完成"
        completed.mkdir(parents=True)
        output = completed / "finished.mp4"
        output.write_bytes(b"media")
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            patch.object(self.coordinator, "schedule"),
        ):
            plan = self.coordinator.create_plan(self.payload())
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET status = 'completed_local', progress = 100, final_path = ? WHERE id = ?",
                    (str(output), plan["id"]),
                )
            with patch.object(os, "startfile", create=True) as startfile:
                result = self.coordinator.open_plan_output(plan["id"])

        self.assertTrue(result["opened"])
        self.assertEqual(result["fileName"], "finished.mp4")
        startfile.assert_called_once_with(str(completed.resolve()))

        outside = self.root / "outside.mp4"
        outside.write_bytes(b"media")
        with self.database.session() as connection:
            connection.execute(
                "UPDATE download_plans SET final_path = ? WHERE id = ?",
                (str(outside), plan["id"]),
            )
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            self.assertRaisesRegex(MediaPlanError, "下载目录"),
        ):
            self.coordinator.open_plan_output(plan["id"])

    def test_completed_local_plan_can_be_queued_for_eagle_without_redownload(self) -> None:
        station_root = self.root / "import-existing-root"
        completed = station_root / "留底下载器" / "已完成"
        completed.mkdir(parents=True)
        output = completed / "already-downloaded.mp4"
        output.write_bytes(b"already-downloaded-media")
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            patch.object(self.coordinator, "schedule"),
        ):
            plan = self.coordinator.create_plan(self.payload(importToEagle=False))
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET status = 'completed_local', progress = 100, final_path = ? WHERE id = ?",
                    (str(output), plan["id"]),
                )
            result = self.coordinator.import_completed_plan(plan["id"])

        self.assertEqual(result["status"], "ready_to_import")
        self.assertEqual(result["progress"], 90)
        self.assertEqual(result["import_to_eagle"], 1)
        self.assertEqual(result["delete_after_import"], 0)
        self.assertIsNotNone(result["job_id"])
        job = self.database.get_job(result["job_id"])
        self.assertEqual(job["file_path"], str(output.resolve()))
        self.assertEqual(job["source_url"], "https://www.bilibili.com/video/BV1test")

        repeated = self.coordinator.import_completed_plan(plan["id"])
        self.assertEqual(repeated["job_id"], result["job_id"], "repeated clicks must not create duplicate Eagle jobs")

    def test_concurrent_completed_local_import_claim_creates_only_one_job(self) -> None:
        station_root = self.root / "concurrent-import-root"
        completed = station_root / "留底下载器" / "已完成"
        completed.mkdir(parents=True)
        output = completed / "concurrent.mp4"
        output.write_bytes(b"concurrent-media")
        with (
            patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_root)}),
            patch.object(self.coordinator, "schedule"),
        ):
            plan = self.coordinator.create_plan(self.payload(importToEagle=False))
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET status = 'completed_local', progress = 100, final_path = ? WHERE id = ?",
                    (str(output), plan["id"]),
                )

            owned_barrier = threading.Barrier(2)
            original_owned = self.coordinator._owned_plan_file
            original_add_job = self.database.add_job
            add_lock = threading.Lock()
            first_created = threading.Event()
            second_created = threading.Event()
            add_calls = 0

            def synchronized_owned(plan_id: str, field: str, directory: str) -> Path:
                result = original_owned(plan_id, field, directory)
                owned_barrier.wait(timeout=3)
                return result

            def force_distinct_legacy_jobs(file_path: str, created_at: float | None = None) -> str:
                nonlocal add_calls
                with add_lock:
                    call_index = add_calls
                    add_calls += 1
                if call_index == 0:
                    job_id = original_add_job(file_path, created_at)
                    self.database.update_job(
                        job_id,
                        status="imported",
                        eagle_item_id="race-item",
                        completed_at=time.time(),
                    )
                    first_created.set()
                    self.assertTrue(second_created.wait(timeout=3))
                    return job_id
                self.assertTrue(first_created.wait(timeout=3))
                job_id = original_add_job(file_path, created_at)
                second_created.set()
                return job_id

            results: list[dict] = []
            failures: list[BaseException] = []

            def import_plan() -> None:
                try:
                    results.append(self.coordinator.import_completed_plan(plan["id"]))
                except BaseException as exc:  # captured so thread failures fail the test
                    failures.append(exc)

            with (
                patch.object(self.coordinator, "_owned_plan_file", side_effect=synchronized_owned),
                patch.object(self.database, "add_job", side_effect=force_distinct_legacy_jobs),
            ):
                threads = [threading.Thread(target=import_plan) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)

        self.assertFalse(failures)
        self.assertEqual(len(results), 2)
        with self.database.session() as connection:
            jobs = connection.execute(
                "SELECT id FROM jobs WHERE file_path = ?",
                (str(output.resolve()),),
            ).fetchall()
            linked = connection.execute(
                "SELECT job_id FROM download_plans WHERE id = ?",
                (plan["id"],),
            ).fetchone()
        self.assertEqual(len(jobs), 1, "concurrent import clicks must not leave an orphan job")
        self.assertEqual(linked["job_id"], jobs[0]["id"])

    def test_drm_plan_is_blocked_before_rows_are_created(self) -> None:
        streams = list(self.payload()["streams"])
        streams[0] = {**streams[0], "drm": True}
        with self.assertRaisesRegex(MediaPlanError, "DRM"):
            self.coordinator.create_plan(self.payload(streams=streams))
        self.assertEqual(self.coordinator.list_plans(), [])

    def test_output_name_and_url_are_sanitized(self) -> None:
        self.assertEqual(safe_output_name("CON?.mp4", "mp4"), "CON_.mp4")
        self.assertEqual(
            redact_media_url("https://cdn.example/a.mp4?token=secret#part"),
            "https://cdn.example/a.mp4",
        )

    def test_ffmpeg_inputs_receive_the_selected_http_proxy(self) -> None:
        arguments = self.coordinator._ffmpeg_input_arguments(
            {
                "url": "https://cdn.example/video.mp4",
                "headers": {"referer": "https://www.behance.net/"},
            },
            "http://127.0.0.1:7890",
        )
        self.assertEqual(
            arguments[:2], ["-http_proxy", "http://127.0.0.1:7890"]
        )
        self.assertIn("Referer: https://www.behance.net/\r\n", arguments)

    def test_auto_proxy_route_fallback_runs_at_most_once(self) -> None:
        with patch.object(self.coordinator, "schedule"):
            plan = self.coordinator.create_plan(self.payload())
        routes = [
            ProxyRoute(
                "http://127.0.0.1:7890", "windows", "auto", "系统代理 127.0.0.1:7890"
            ),
            ProxyRoute(None, "direct", "auto", "直连"),
        ]
        calls: list[str] = []

        def process(_plan_id: str, route: ProxyRoute) -> None:
            calls.append(route.source)
            with self.database.session() as connection:
                connection.execute(
                    "UPDATE download_plans SET status = ? WHERE id = ?",
                    ("downloading" if len(calls) == 1 else "completed_local", plan["id"]),
                )
            if len(calls) == 1:
                raise MediaPlanError(
                    "本机 FFmpeg 下载失败：Server returned 403 Forbidden",
                    "desktop_download_failed",
                )

        with (
            patch.object(self.coordinator.network_proxy, "routes_for", return_value=routes),
            patch.object(self.coordinator, "_process_remote", side_effect=process),
            patch.object(self.coordinator, "schedule"),
        ):
            self.coordinator._process_guarded(plan["id"])
        self.assertEqual(calls, ["windows", "direct"])
        self.assertEqual(self.coordinator.get_plan(plan["id"])["status"], "completed_local")


if __name__ == "__main__":
    unittest.main()
