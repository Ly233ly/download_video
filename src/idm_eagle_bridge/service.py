from __future__ import annotations

import threading
import time

from .database import Database
from .processor import JobProcessor
from .wake_signal import WakeSignal


class ProcessingService:
    def __init__(self, database: Database, interval: float = 15.0) -> None:
        self.database = database
        self.processor = JobProcessor(database)
        self.interval = max(interval, 1.0)
        self.stop_event = threading.Event()
        self.wake_signal = WakeSignal()
        self.thread: threading.Thread | None = None
        self.last_cleanup = 0.0

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="job-processor", daemon=True)
        self.thread.start()

    def wake(self) -> None:
        self.wake_signal.set()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_signal.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.wake_signal.close()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            if time.time() - self.last_cleanup >= 24 * 60 * 60:
                try:
                    self.database.cleanup_history()
                except Exception:
                    # History maintenance must never stop the import queue.
                    # A locked or legacy database can be retried the next day.
                    pass
                finally:
                    self.last_cleanup = time.time()
            self.processor.process_once()
            self.wake_signal.wait(self.database.seconds_until_next_action(self.interval))
