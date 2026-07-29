from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.performance import PerformanceMonitor
from idm_eagle_bridge.ui import MainWindow


class _Root:
    def after(self, _delay: int, _callback) -> str:
        return "fixture-after"


class _NetworkProxy:
    @staticmethod
    def status() -> dict[str, object]:
        return {
            "mode": "auto",
            "active": False,
            "source": "none",
            "endpoint": "",
            "summary": "测试直连",
        }


class _Media:
    network_proxy = _NetworkProxy()

    @staticmethod
    def list_plans(limit: int) -> list[dict[str, object]]:
        return [
            {
                "created_at": float(index),
                "status": "completed_local",
                "title": f"媒体任务 {index}",
                "output_name": f"video-{index}.mp4",
                "page_url": f"https://example.test/video/{index}",
                "progress": 100,
                "downloaded_bytes": 1024,
                "total_bytes": 1024,
                "phase_detail": "完成",
                "error_code": None,
                "error_message": None,
                "job_error": None,
            }
            for index in range(min(limit, 200))
        ]


def _seed_jobs(database: Database, count: int) -> None:
    now = time.time()
    with database.transaction() as connection:
        connection.executemany(
            """
            INSERT INTO jobs(
                id, file_path, file_name, extension, status,
                attempt_count, created_at, updated_at
            ) VALUES(?, ?, ?, '.mp4', 'imported', 0, ?, ?)
            """,
            (
                (
                    f"job-{index}",
                    f"C:/fixture/video-{index}.mp4",
                    f"video-{index}.mp4",
                    now + index,
                    now + index,
                )
                for index in range(count)
            ),
        )


def _window(database: Database) -> MainWindow:
    window = object.__new__(MainWindow)
    window.database = database
    window.media = _Media()
    window.root = _Root()
    window.closing = False
    window.current_page = "diagnostics"
    window.current_ui_operation = ""
    window.performance_monitor = PerformanceMonitor(enabled=False)
    window.maintenance_events = Queue(maxsize=8)
    window.maintenance_after_id = None
    window.maintenance_generation = 0
    window.maintenance_busy = False
    window.maintenance_kind = ""
    window.media_change_events = Queue()
    window.update_events = Queue()
    window.wechat_preview_events = Queue()
    window.wechat_operation_results = Queue()
    window.api_server = SimpleNamespace(address=("127.0.0.1", 32145))
    return window


def _run_background(
    window: MainWindow,
    kind: str,
    worker,
    *args: object,
) -> dict[str, object]:
    started = time.perf_counter()
    window._start_maintenance(kind, worker, *args)
    callback_ms = (time.perf_counter() - started) * 1000
    generation, event_kind, succeeded, payload = window.maintenance_events.get(
        timeout=30
    )
    total_ms = (time.perf_counter() - started) * 1000
    if not succeeded:
        raise RuntimeError(str(payload))
    return {
        "generation": generation,
        "kind": event_kind,
        "callbackMs": round(callback_ms, 3),
        "workerCompletionMs": round(total_ms, 3),
        "result": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=10000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="idm-eagle-perf-") as temp:
        database = Database(Path(temp) / "fixture.sqlite3")
        _seed_jobs(database, max(1, args.jobs))
        diagnostics_path = Path(temp) / "diagnostics.json"

        export_window = _window(database)
        export_metrics = _run_background(
            export_window,
            "diagnostics-export",
            export_window._export_diagnostics_worker,
            str(diagnostics_path),
            PerformanceMonitor(enabled=False).snapshot(),
        )
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        export_metrics["outputBytes"] = diagnostics_path.stat().st_size
        export_metrics["exportedJobs"] = len(diagnostics["jobs"])
        export_metrics["exportedPlans"] = len(diagnostics["mediaPlans"])

        clear_window = _window(database)
        clear_metrics = _run_background(
            clear_window,
            "clear-idm",
            database.clear_terminal_history,
        )
        metrics = {
            "jobCount": max(1, args.jobs),
            "diagnosticsExport": export_metrics,
            "historyClear": clear_metrics,
        }
        output = json.dumps(metrics, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
