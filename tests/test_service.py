from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.service import ProcessingService


class ProcessingServiceTests(unittest.TestCase):
    def test_transient_processor_exception_does_not_kill_service_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            service = ProcessingService(Database(Path(temporary) / "service.db"), interval=1)
            calls = 0

            def process_once() -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("temporary database or filesystem failure")
                service.stop_event.set()
                return 0

            service.processor.process_once = Mock(side_effect=process_once)
            service.wake_signal.wait = Mock(return_value=False)
            service._run()

        self.assertEqual(calls, 2)

    def test_transient_next_action_query_failure_uses_normal_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Database(Path(temporary) / "service.db")
            service = ProcessingService(database, interval=2)
            calls = 0

            def process_once() -> int:
                nonlocal calls
                calls += 1
                if calls == 2:
                    service.stop_event.set()
                return 0

            service.processor.process_once = Mock(side_effect=process_once)
            database.seconds_until_next_action = Mock(
                side_effect=[OSError("temporary database failure"), 0.0]
            )
            service.wake_signal.wait = Mock(return_value=False)
            service._run()

        self.assertEqual(calls, 2)
        self.assertEqual(service.wake_signal.wait.call_args_list[0].args, (2.0,))


if __name__ == "__main__":
    unittest.main()
