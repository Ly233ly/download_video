from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge import main as main_module


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


class ShutdownOrderTests(unittest.TestCase):
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
