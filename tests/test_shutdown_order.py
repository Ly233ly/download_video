from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge import main as main_module
from idm_eagle_bridge.wechat_channels_proxy import WechatLoopbackProxy


class _Recorder:
    def __init__(self, events: list[str], name: str) -> None:
        self.events = events
        self.name = name

    def close(self) -> None:
        self.events.append(f"{self.name}.close")


class _HttpServer:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def shutdown(self) -> None:
        self.events.append("http.shutdown")

    def server_close(self) -> None:
        self.events.append("http.close")


class _Thread:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def join(self, timeout: float | None = None) -> None:
        self.events.append(f"http.join:{timeout}")


class _UnstartedHttpServer(_HttpServer):
    def shutdown(self) -> None:
        raise AssertionError("shutdown() would block when serve_forever() never started")


class ShutdownOrderTests(unittest.TestCase):
    def test_api_start_failure_keeps_server_on_non_started_close_path(self) -> None:
        server = object.__new__(LocalApiServer)
        server.server = SimpleNamespace(serve_forever=Mock())
        server.thread = None
        failed_thread = Mock()
        failed_thread.is_alive.return_value = False
        failed_thread.start.side_effect = OSError("thread unavailable")

        with patch("idm_eagle_bridge.api_server.threading.Thread", return_value=failed_thread):
            with self.assertRaises(OSError):
                server.start()

        self.assertIsNone(server.thread)

    def test_capture_proxy_start_failure_keeps_non_started_close_path(self) -> None:
        proxy = object.__new__(WechatLoopbackProxy)
        proxy.server = SimpleNamespace(serve_forever=Mock())
        proxy.thread = None
        failed_thread = Mock()
        failed_thread.is_alive.return_value = False
        failed_thread.start.side_effect = OSError("thread unavailable")

        with patch(
            "idm_eagle_bridge.wechat_channels_proxy.threading.Thread",
            return_value=failed_thread,
        ):
            with self.assertRaises(OSError):
                proxy.start()

        self.assertIsNone(proxy.thread)

    def test_unstarted_api_server_can_be_closed_without_shutdown_deadlock(self) -> None:
        events: list[str] = []
        server = object.__new__(LocalApiServer)
        server.server = _UnstartedHttpServer(events)
        server.thread = None
        server.api = SimpleNamespace(
            wechat_channels=_Recorder(events, "wechat"),
            media=_Recorder(events, "media"),
        )

        server.stop()

        self.assertEqual(events, ["wechat.close", "http.close", "media.close"])

    def test_unstarted_capture_proxy_can_be_closed_without_shutdown_deadlock(self) -> None:
        events: list[str] = []
        proxy = object.__new__(WechatLoopbackProxy)
        proxy.server = _UnstartedHttpServer(events)
        proxy.thread = None
        proxy.replace_upstream = lambda *_args: events.append("upstream.close")

        proxy.stop()

        self.assertEqual(events, ["http.close", "upstream.close"])

    def test_api_restores_wechat_proxy_before_waiting_for_workers(self) -> None:
        events: list[str] = []
        server = object.__new__(LocalApiServer)
        server.server = _HttpServer(events)
        server.thread = _Thread(events)
        server.api = SimpleNamespace(
            wechat_channels=_Recorder(events, "wechat"),
            media=_Recorder(events, "media"),
        )

        server.stop()

        self.assertEqual(
            events,
            [
                "wechat.close",
                "http.shutdown",
                "http.close",
                "http.join:3",
                "media.close",
            ],
        )

    def test_main_stops_api_before_legacy_processor(self) -> None:
        events: list[str] = []

        class FakeInstance:
            already_running = False

            def close(self) -> None:
                events.append("instance.close")

        class FakeProcessing:
            def __init__(self, database: object, interval: float) -> None:
                self.database = database

            def start(self) -> None:
                events.append("processing.start")

            def stop(self) -> None:
                events.append("processing.stop")

            def wake(self) -> None:
                pass

        class FakeApiServer:
            def __init__(self, database: object, media_ready_callback: object) -> None:
                self.database = database

            def start(self) -> None:
                events.append("api.start")

            def stop(self) -> None:
                events.append("api.stop")

        with (
            patch.object(main_module, "Database", return_value=object()),
            patch.object(main_module, "SingleInstance", return_value=FakeInstance()),
            patch.object(main_module, "ProcessingService", FakeProcessing),
            patch.object(main_module, "LocalApiServer", FakeApiServer),
            patch.object(main_module.time, "sleep", side_effect=KeyboardInterrupt),
        ):
            result = main_module.main(["--headless"])

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            [
                "api.start",
                "processing.start",
                "api.stop",
                "processing.stop",
                "instance.close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
