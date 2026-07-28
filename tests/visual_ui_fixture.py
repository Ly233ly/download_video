"""Deterministic desktop UI fixture used by screenshot-based visual QA."""

from __future__ import annotations

import argparse
import ctypes
import struct
import tempfile
import time
import zlib
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.ui import MainWindow


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def _write_rgb_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    stride = width * 3
    scanlines = b"".join(
        b"\0" + pixels[row * stride : (row + 1) * stride]
        for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _top_level_hwnd(hwnd: int) -> int:
    user32 = ctypes.windll.user32
    current = hwnd
    while True:
        parent = user32.GetParent(current)
        if not parent:
            return current
        current = parent


def _show_fixture_without_activation(window: MainWindow) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    client_hwnd = int(window.root.winfo_id())
    top_hwnd = _top_level_hwnd(client_hwnd)
    sw_shownoactivate = 4
    hwnd_bottom = 1
    swp_nosize = 0x0001
    swp_nomove = 0x0002
    swp_noactivate = 0x0010
    user32.ShowWindow(top_hwnd, sw_shownoactivate)
    user32.SetWindowPos(
        top_hwnd,
        hwnd_bottom,
        0,
        0,
        0,
        0,
        swp_nosize | swp_nomove | swp_noactivate,
    )
    window.root.update()
    window._apply_responsive_layout()
    window._apply_mode_to_page_layouts()
    window.root.update()
    if getattr(window, "_visual_scroll_detail_bottom", False):
        scroller = {
            "media": getattr(window, "media_detail_scroller", None),
            "wechat": getattr(window, "wechat_detail_scroller", None),
            "idm": getattr(window, "idm_detail_scroller", None),
        }.get(window.current_page)
        if scroller is not None:
            scroller.scroll_to_bottom()
            window.root.update()
    return client_hwnd, top_hwnd


def _capture_fixture_window(window: MainWindow, destination: Path) -> None:
    """Capture only this fixture's client area without input hooks or activation."""

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    client_hwnd, top_hwnd = _show_fixture_without_activation(window)
    rdw_invalidate = 0x0001
    rdw_allchildren = 0x0080
    rdw_updatenow = 0x0100
    user32.RedrawWindow(
        top_hwnd,
        None,
        None,
        rdw_invalidate | rdw_allchildren | rdw_updatenow,
    )
    window.root.update()

    window_bounds = wintypes.RECT()
    if not user32.GetClientRect(client_hwnd, ctypes.byref(window_bounds)):
        raise ctypes.WinError()
    width = window_bounds.right - window_bounds.left
    height = window_bounds.bottom - window_bounds.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid fixture window size: {width}x{height}")

    window_dc = user32.GetDC(client_hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        pw_renderfullcontent = 0x00000002
        if not user32.PrintWindow(
            client_hwnd,
            memory_dc,
            pw_renderfullcontent,
        ):
            raise RuntimeError("PrintWindow failed for the visual fixture")

        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        raw = (ctypes.c_ubyte * (width * height * 4))()
        if not gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            ctypes.byref(raw),
            ctypes.byref(info),
            0,
        ):
            raise RuntimeError("GetDIBits failed for the visual fixture")
        bgra = bytes(raw)
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(client_hwnd, window_dc)
        user32.ShowWindow(top_hwnd, 0)

    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    _write_rgb_png(destination, width, height, bytes(rgb))


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
    def __init__(
        self,
        output_path: Path,
        scenario: str = "standard",
        preview_path: Path | None = None,
    ) -> None:
        now = time.time()
        self.network_proxy = _FakeNetworkProxy()
        self._health_cache = None
        self.plans = [
            {
                "id": "plan-active",
                "title": "2024 年 WWDC 主题演讲 — 完整版",
                "output_name": "2024 年 WWDC 主题演讲 — 完整版.mkv",
                "status": "downloading",
                "progress": 68,
                "downloaded_bytes": 734_003_200,
                "total_bytes": 1_073_741_824,
                "phase_detail": "正在下载视频流…",
                "page_url": "https://developer.apple.com/videos/play/wwdc2024/",
                "updated_at": now,
                "final_path": "",
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-complete",
                "title": "城市延时摄影合集 4K",
                "output_name": output_path.name,
                "status": "completed_local",
                "progress": 100,
                "downloaded_bytes": 823_132_160,
                "total_bytes": 823_132_160,
                "phase_detail": "本机文件已完成，可导入 Eagle",
                "page_url": "https://vimeo.com/example",
                "updated_at": now - 420,
                "final_path": str(output_path),
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-failed",
                "title": "机器学习入门课程 第三讲",
                "output_name": "机器学习入门课程 第三讲.mp4",
                "status": "retry",
                "progress": 41,
                "downloaded_bytes": 283_115_520,
                "total_bytes": 692_060_160,
                "phase_detail": "下载中断",
                "error_message": "来源临时不可用，可稍后重试",
                "page_url": "https://coursera.org/learn/example",
                "updated_at": now - 900,
                "final_path": "",
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-validating",
                "title": "摄影技巧大全：构图与光线",
                "output_name": "摄影技巧大全：构图与光线.mp4",
                "status": "validating",
                "progress": 91,
                "downloaded_bytes": 874_512_384,
                "total_bytes": 874_512_384,
                "phase_detail": "正在校验文件完整性",
                "page_url": "https://youtube.com/watch/example",
                "updated_at": now - 240,
                "final_path": "",
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-imported",
                "title": "React 19 新特性深度解析",
                "output_name": "React 19 新特性深度解析.mp4",
                "status": "imported",
                "progress": 100,
                "downloaded_bytes": 441_450_496,
                "total_bytes": 441_450_496,
                "phase_detail": "已导入 Eagle",
                "page_url": "https://bilibili.com/video/example",
                "updated_at": now - 620,
                "final_path": str(output_path),
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-waiting",
                "title": "爵士钢琴现场演出实录",
                "output_name": "爵士钢琴现场演出实录.mp4",
                "status": "ready_to_import",
                "job_status": "waiting_eagle",
                "progress": 99,
                "downloaded_bytes": 1_181_116_006,
                "total_bytes": 1_181_116_006,
                "phase_detail": "等待 Eagle 恢复连接",
                "page_url": "https://youtube.com/watch/jazz",
                "updated_at": now - 1220,
                "final_path": str(output_path),
                "preview_path": str(preview_path or ""),
            },
            {
                "id": "plan-queued",
                "title": "Kubernetes 生产环境最佳实践",
                "output_name": "Kubernetes 生产环境最佳实践.mp4",
                "status": "queued",
                "progress": 0,
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "phase_detail": "等待本机下载",
                "page_url": "https://youtube.com/watch/kubernetes",
                "updated_at": now - 1540,
                "final_path": "",
                "preview_path": str(preview_path or ""),
            },
        ]
        if scenario == "empty":
            self.plans = []
        elif scenario == "stress":
            self.plans[0]["title"] = (
                "无尽夏 · 花的节拍\n"
                "音乐被转译成花开的次序。\n"
                "单次绽放与连续涌现交替出现，节拍不断回到同一处。"
            )
            self.plans[0]["page_url"] = (
                "https://www.bilibili.com/video/" + "very-long-source-segment-" * 18
            )
            self.plans[0]["output_name"] = "超长输出文件名" * 28 + ".mkv"
            self.plans[0]["phase_detail"] = "正在处理复杂分片；" * 24
            self.plans[2]["error_message"] = "来源暂不可用，请检查网络后重试；" * 30
            template = dict(self.plans[1])
            for index in range(3, 200):
                row = dict(template)
                row.update(
                    {
                        "id": f"plan-{index:03d}",
                        "title": f"压力任务 {index:03d} · 中英文 Mixed Content",
                        "output_name": f"pressure-{index:03d}.mp4",
                        "updated_at": now - index * 12,
                    }
                )
                self.plans.append(row)

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

    def __init__(self, scenario: str = "standard") -> None:
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
        if scenario == "empty":
            self._candidates = []
        elif scenario == "stress":
            self._candidates[0]["title"] = "视频号超长中文标题" * 24
            self._candidates[0]["author"] = "中英文作者 Mixed Author " * 8
            self._candidates[0]["outputName"] = "超长预计输出文件名" * 22 + ".mp4"
            self._candidates[0]["sourceUrl"] = (
                "https://channels.weixin.qq.com/" + "long-source-" * 42
            )
            self._candidates[0]["variants"] = [
                {
                    "id": f"quality-{index}",
                    "quality": f"{2160 - index * 72}p",
                    "fileSize": 220_000_000 - index * 4_000_000,
                    "encrypted": index % 2 == 0,
                }
                for index in range(20)
            ]
            self._candidates.reverse()

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
    parser.add_argument(
        "--scenario",
        choices=("standard", "empty", "stress"),
        default="standard",
    )
    parser.add_argument(
        "--settings-tab",
        choices=("pairing", "sites", "network", "updates"),
        default="pairing",
    )
    parser.add_argument("--selected-id", default="")
    parser.add_argument("--scroll-detail-bottom", action="store_true")
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Capture only the fixture window to PNG without activating it.",
    )
    parser.add_argument("--screenshot-delay-ms", type=int, default=250)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="download-transfer-station-visual-") as folder:
        root = Path(folder)
        output_path = root / "产品发布会完整回放.mp4"
        output_path.write_bytes(b"visual fixture")
        database = Database(root / "visual.db")
        database.set_setting("pairing_code", "482731")
        database.set_site_rule("bilibili.com", True, True)
        database.set_site_rule("example.com", False, False)

        if args.scenario != "empty":
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
        if args.scenario == "stress" and args.page == "idm":
            long_name = "超长文件名" * 36 + ".mp4"
            for index in range(997):
                job_id = database.add_job(str(root / f"{index:04d}-{long_name}"))
                database.update_job(
                    job_id,
                    status="retry",
                    source_url="https://example.org/" + "source-segment-" * 30,
                    error_message="可操作错误说明" * 38,
                )

        preview_path = (
            Path(__file__).resolve().parent
            / "visual-assets"
            / "download-preview-reference.png"
        )
        media = _FakeMedia(output_path, args.scenario, preview_path)
        api_server = SimpleNamespace(
            address=("127.0.0.1", 32145),
            api=SimpleNamespace(
                media=media,
                wechat_channels=_FakeWechatChannels(args.scenario),
            ),
        )
        window = MainWindow(
            database,
            api_server,
            _FakeProcessing(),
            visual_capture_hidden=bool(args.screenshot),
            visual_capture_geometry=args.geometry if args.screenshot else None,
        )
        window.root.geometry(args.geometry)
        window._show_page(args.page)
        if args.page == "settings":
            window._settings_show_tab(args.settings_tab)
        elif args.page == "media" and args.selected_id:
            window._select_plan_card(args.selected_id)
        elif args.page == "wechat" and args.selected_id:
            window._select_wechat_card(args.selected_id)
        window._visual_scroll_detail_bottom = args.scroll_detail_bottom
        if window.auto_update_after_id:
            window.root.after_cancel(window.auto_update_after_id)
            window.auto_update_after_id = None
        if args.screenshot:
            def finish_capture() -> None:
                try:
                    _capture_fixture_window(window, args.screenshot)
                finally:
                    window.root.destroy()

            def prepare_capture() -> None:
                _show_fixture_without_activation(window)
                window.root.after(120, finish_capture)

            window.root.after(max(0, args.screenshot_delay_ms), prepare_capture)
        window.root.mainloop()


if __name__ == "__main__":
    main()
