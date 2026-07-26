"""Deterministic desktop UI fixture used by screenshot-based visual QA."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.ui import MainWindow


class _FakeNetworkProxy:
    def __init__(self) -> None:
        self.mode = "auto"
        self.manual_url = ""

    def configuration(self) -> dict[str, str]:
        return {"mode": self.mode, "manualUrl": self.manual_url}

    def configure(self, mode: str, manual_url: str = "") -> None:
        self.mode = mode
        self.manual_url = manual_url

    def status(self) -> dict[str, object]:
        return {
            "summary": "自动 · Windows 系统代理",
            "mode": self.mode,
            "manualUrl": self.manual_url,
            "detected": ["Windows 系统代理"],
        }


class _FakeMedia:
    def __init__(self, output_path: Path) -> None:
        now = time.time()
        self.network_proxy = _FakeNetworkProxy()
        self._health_cache = None
        self.plans = [
            {
                "id": "plan-active",
                "title": "东京夜景延时摄影",
                "output_name": "东京夜景延时摄影.mkv",
                "status": "downloading",
                "progress": 68,
                "downloaded_bytes": 734_003_200,
                "total_bytes": 1_073_741_824,
                "phase_detail": "正在下载视频流 2/3",
                "page_url": "https://www.bilibili.com/video/BV1example",
                "updated_at": now,
                "final_path": "",
            },
            {
                "id": "plan-complete",
                "title": "产品发布会完整回放",
                "output_name": output_path.name,
                "status": "completed_local",
                "progress": 100,
                "downloaded_bytes": 823_132_160,
                "total_bytes": 823_132_160,
                "phase_detail": "本机文件已完成，可导入 Eagle",
                "page_url": "https://example.com/product-launch",
                "updated_at": now - 420,
                "final_path": str(output_path),
            },
            {
                "id": "plan-failed",
                "title": "城市漫游纪录片",
                "output_name": "城市漫游纪录片.mp4",
                "status": "retry",
                "progress": 41,
                "downloaded_bytes": 283_115_520,
                "total_bytes": 692_060_160,
                "phase_detail": "下载中断",
                "error_message": "来源临时不可用，可稍后重试",
                "page_url": "https://video.example.net/watch/urban-walk",
                "updated_at": now - 900,
                "final_path": "",
            },
        ]

    def list_plans(self, _limit: int) -> list[dict[str, object]]:
        return self.plans

    def stop_plan(self, _plan_id: str) -> None:
        return None

    def retry_plan(self, _plan_id: str) -> None:
        return None

    def open_plan_output(self, _plan_id: str) -> None:
        return None

    def import_completed_plan(self, _plan_id: str) -> None:
        return None

    def clear_terminal_history(self) -> int:
        return 1


class _FakeWechatChannels:
    certificate = SimpleNamespace(existing=lambda: None, is_trusted=lambda _value: False)

    def __init__(self) -> None:
        now = time.time()
        self._candidates = [
            {
                "objectId": "wx-video-001",
                "title": "一座城市醒来的清晨",
                "author": "旅行手记",
                "durationMs": 182_000,
                "outputName": "一座城市醒来的清晨.mp4",
                "coverUrl": "",
                "updatedAt": now,
                "variants": [
                    {
                        "id": "1080p",
                        "quality": "1080p",
                        "fileSize": 188_743_680,
                        "encrypted": True,
                    },
                    {
                        "id": "720p",
                        "quality": "720p",
                        "fileSize": 104_857_600,
                        "encrypted": True,
                    },
                ],
            },
            {
                "objectId": "wx-video-002",
                "title": "咖啡馆里的爵士午后",
                "author": "今日放映",
                "durationMs": 96_000,
                "outputName": "咖啡馆里的爵士午后.mp4",
                "coverUrl": "",
                "updatedAt": now - 260,
                "variants": [
                    {
                        "id": "720p-b",
                        "quality": "720p",
                        "fileSize": 72_351_744,
                        "encrypted": False,
                    }
                ],
            },
        ]

    def health(self) -> dict[str, object]:
        return {
            "state": "capturing",
            "running": True,
            "candidateCount": len(self._candidates),
            "endpoint": "127.0.0.1:8899",
            "lastEvent": "已识别 2 个媒体候选组",
        }

    def candidates(self) -> list[dict[str, object]]:
        return self._candidates

    def preview_png(self, _object_id: str) -> bytes:
        return b""

    def clear_candidates(self) -> int:
        count = len(self._candidates)
        self._candidates.clear()
        return count


class _FakeProcessing:
    def wake(self) -> None:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--page",
        choices=("media", "wechat", "idm", "settings", "diagnostics"),
        default="media",
    )
    parser.add_argument("--geometry", default="1120x720")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="download-transfer-station-visual-") as folder:
        root = Path(folder)
        output_path = root / "产品发布会完整回放.mp4"
        output_path.write_bytes(b"visual fixture")
        database = Database(root / "visual.db")
        database.set_site_rule("bilibili.com", True, True)
        database.set_site_rule("example.com", False, False)

        active_job = database.add_job(str(root / "IDM-纪录片片段.mp4"))
        database.update_job(
            active_job,
            status="waiting_eagle",
            source_url="https://example.org/documentary",
            source_title="纪录片片段",
        )
        imported_job = database.add_job(str(root / "无来源本机视频.mp4"))
        database.update_job(imported_job, status="imported")
        failed_job = database.add_job(str(root / "旧下载失败.mp4"))
        database.update_job(
            failed_job,
            status="retry",
            error_code="eagle_unavailable",
            error_message="Eagle 暂未连接，稍后自动重试",
        )

        media = _FakeMedia(output_path)
        api_server = SimpleNamespace(
            address=("127.0.0.1", 32145),
            api=SimpleNamespace(media=media, wechat_channels=_FakeWechatChannels()),
        )
        window = MainWindow(database, api_server, _FakeProcessing())
        window.root.geometry(args.geometry)
        window._show_page(args.page)
        if window.auto_update_after_id:
            window.root.after_cancel(window.auto_update_after_id)
            window.auto_update_after_id = None
        window.root.mainloop()


if __name__ == "__main__":
    main()
