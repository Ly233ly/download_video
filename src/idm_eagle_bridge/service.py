from __future__ import annotations

import threading
import time

from .database import Database
from .cache import ProgramCacheManager
from .processor import JobProcessor
from .wake_signal import WakeSignal


class ProcessingService:
    def __init__(
        self,
        database: Database,
        interval: float = 15.0,
        cache_manager: ProgramCacheManager | None = None,
    ) -> None:
        self.database = database
        self.processor = JobProcessor(database)
        self.interval = max(interval, 1.0)
        self.stop_event = threading.Event()
        self.wake_signal = WakeSignal()
        self.thread: threading.Thread | None = None
        self.last_cleanup = 0.0
        self.cache_manager = cache_manager or ProgramCacheManager(database)

    def _run_daily_maintenance(self, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        try:
            self.database.cleanup_history()
        except Exception:
            # A locked or legacy database can be retried the next day.
            pass
        try:
            days = max(
                0,
                min(365, int(self.database.get_setting("cache_retention_days", 7))),
            )
            self.cache_manager.cleanup(retention_days=days, now=current)
        except Exception:
            # Cache maintenance must never stop the import queue.
            pass
        self.last_cleanup = current

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
                self._run_daily_maintenance()
            try:
                self.processor.process_once()
            except Exception:
                # A transient database, filesystem or local API failure must
                # not permanently kill the only import/retention worker.
                pass
            try:
                delay = self.database.seconds_until_next_action(self.interval)
            except Exception:
                delay = self.interval
            self.wake_signal.wait(delay)
