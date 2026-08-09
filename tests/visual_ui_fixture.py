"""Deterministic desktop UI fixture used by screenshot-based visual QA."""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import struct
import tempfile
import time
import tracemalloc
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


def _capture_fixture_window(
    window: MainWindow,
    destination: Path,
    *,
    include_window_frame: bool = False,
) -> None:
    """Capture this fixture without input hooks or activation."""

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

    target_hwnd = top_hwnd if include_window_frame else client_hwnd
    window_bounds = wintypes.RECT()
    bounds_reader = user32.GetWindowRect if include_window_frame else user32.GetClientRect
    if not bounds_reader(target_hwnd, ctypes.byref(window_bounds)):
        raise ctypes.WinError()
    width = window_bounds.right - window_bounds.left
    height = window_bounds.bottom - window_bounds.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid fixture window size: {width}x{height}")

    window_dc = (
        user32.GetWindowDC(target_hwnd)
        if include_window_frame
        else user32.GetDC(target_hwnd)
    )
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        pw_renderfullcontent = 0x00000002
        if not user32.PrintWindow(
            target_hwnd,
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
        user32.ReleaseDC(target_hwnd, window_dc)
        user32.ShowWindow(top_hwnd, 0)

    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    _write_rgb_png(destination, width, height, bytes(rgb))


def _widget_count(widget: object) -> int:
    children = list(widget.winfo_children())
    return 1 + sum(_widget_count(child) for child in children)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * percentile)),
    )
    return ordered[index]


def _measure_ui_performance(
    window: MainWindow,
    *,
    startup_ms: float,
    build_timings: dict[str, list[float]],
    iterations: int,
) -> dict[str, object]:
    root = window.root
    root.update()
    if window.performance_after_id:
        root.after_cancel(window.performance_after_id)
        window.performance_after_id = None
    if window.prewarm_after_id:
        root.after_cancel(window.prewarm_after_id)
        window.prewarm_after_id = None
    if window.window_settle_after_id:
        root.after_cancel(window.window_settle_after_id)
        window.window_settle_after_id = None
    window.window_interaction_active = False
    initial_widget_count = _widget_count(root)
    initial_memory, _initial_peak = tracemalloc.get_traced_memory()

    def cancel_refresh() -> None:
        if window.refresh_after_id:
            root.after_cancel(window.refresh_after_id)
            window.refresh_after_id = None

    def sample(callback, count: int) -> list[float]:
        durations = []
        for _index in range(max(1, count)):
            started = time.perf_counter()
            callback()
            root.update_idletasks()
            durations.append((time.perf_counter() - started) * 1000)
            cancel_refresh()
        return durations

    refresh_warm = sample(lambda: window.refresh(force=False), iterations)
    refresh_forced = sample(
        lambda: window.refresh(force=True),
        max(3, iterations // 4),
    )

    first_page_switch: dict[str, float] = {}
    warm_page_switch: dict[str, float] = {}
    pages = ("media", "wechat", "idm", "settings", "diagnostics")
    for page in pages:
        first_page_switch[page] = sample(
            lambda value=page: window._show_page(value),
            1,
        )[0]
    for page in pages:
        warm_page_switch[page] = statistics.mean(
            sample(lambda value=page: window._show_page(value), 3)
        )
    window._show_page("media")
    root.update_idletasks()

    wheel_dispatch_ms = 0.0
    wheel_router = getattr(root, "_mousewheel_router", None)
    if wheel_router is not None and window.plan_card_widgets:
        first_card = next(iter(window.plan_card_widgets.values()))
        wheel_target = first_card.get("title", window.plan_card_list.content)
        wheel_started = time.perf_counter()
        for index in range(120):
            wheel_router._dispatch(
                SimpleNamespace(
                    widget=wheel_target,
                    delta=-120 if index % 2 == 0 else 120,
                )
            )
        root.update_idletasks()
        wheel_dispatch_ms = (time.perf_counter() - wheel_started) * 1000

    base_width = max(900, root.winfo_width())
    base_height = max(600, root.winfo_height())
    resize_sizes = [
        (
            base_width + ((index % 9) - 4) * 18,
            base_height + ((index % 7) - 3) * 12,
        )
        for index in range(60)
    ]
    resize_started = time.perf_counter()
    for width, height in resize_sizes:
        root.geometry(f"{width}x{height}")
        root.update_idletasks()
    root.geometry(f"{base_width}x{base_height}")
    root.update()
    resize_ms = (time.perf_counter() - resize_started) * 1000
    cancel_refresh()

    current_memory, peak_memory = tracemalloc.get_traced_memory()
    return {
        "startup_ms": round(startup_ms, 3),
        "initial_widget_count": initial_widget_count,
        "final_widget_count": _widget_count(root),
        "python_memory_initial_mb": round(initial_memory / 1024 / 1024, 3),
        "python_memory_current_mb": round(current_memory / 1024 / 1024, 3),
        "python_memory_peak_mb": round(peak_memory / 1024 / 1024, 3),
        "build_ms": {
            name: round(sum(values), 3)
            for name, values in build_timings.items()
        },
        "refresh_warm": {
            "mean_ms": round(statistics.mean(refresh_warm), 3),
            "p50_ms": round(_percentile(refresh_warm, 0.50), 3),
            "p95_ms": round(_percentile(refresh_warm, 0.95), 3),
            "max_ms": round(max(refresh_warm), 3),
        },
        "refresh_forced": {
            "mean_ms": round(statistics.mean(refresh_forced), 3),
            "p50_ms": round(_percentile(refresh_forced, 0.50), 3),
            "p95_ms": round(_percentile(refresh_forced, 0.95), 3),
            "max_ms": round(max(refresh_forced), 3),
        },
        "first_page_switch_ms": {
            key: round(value, 3)
            for key, value in first_page_switch.items()
        },
        "warm_page_switch_mean_ms": {
            key: round(value, 3)
            for key, value in warm_page_switch.items()
        },
        "rapid_resize_60_steps_ms": round(resize_ms, 3),
        "wheel_dispatch_120_events_ms": round(wheel_dispatch_ms, 3),
        "wheel_router_scrollers": (
            len(wheel_router.scrollers)
            if wheel_router is not None
            else 0
        ),
        "pending_tk_callbacks": len(root.tk.call("after", "info")),
    }


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

    def ui_summary(self) -> dict[str, int | float]:
        active_statuses = {
            "queued",
            "downloading",
            "merging",
            "validating",
            "ready_to_import",
        }
        return {
            "total": len(self.plans),
            "active": sum(
                1
                for plan in self.plans
                if str(plan.get("status") or "") in active_statuses
            ),
            "revision": max(
                (
                    float(plan.get("updated_at") or 0)
                    for plan in self.plans
                ),
                default=0.0,
            ),
        }

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

    def cache_status(self) -> dict[str, object]:
        return {
            "totalBytes": 754_974_720,
            "fileCount": 38,
            "categories": {
                "temporary": {"bytes": 734_003_200, "files": 12},
                "previews": {"bytes": 20_971_520, "files": 25},
                "log": {"bytes": 24_000, "files": 1},
            },
        }

    def clear_cache(self) -> dict[str, object]:
        return {
            "freedBytes": 754_974_720,
            "remainingBytes": 0,
            "removedFiles": 38,
            "removedDirectories": 7,
            "skippedActive": 2,
            "skippedUnsafe": 0,
            "errorCount": 0,
        }


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
        if self._candidates:
            self._candidates = self._candidates[:1]

    def health(self) -> dict[str, object]:
        return {
            "state": "capturing",
            "running": True,
            "candidateCount": len(self._candidates),
            "endpoint": "127.0.0.1:8899",
            "lastEvent": "当前视频已识别",
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
        "--theme",
        choices=("light", "dark"),
        default="light",
    )
    parser.add_argument("--toggle-theme", action="store_true")
    parser.add_argument(
        "--scenario",
        choices=("standard", "empty", "stress"),
        default="standard",
    )
    parser.add_argument(
        "--settings-tab",
        choices=("pairing", "sites", "network", "storage", "updates"),
        default="pairing",
    )
    parser.add_argument("--selected-id", default="")
    parser.add_argument("--scroll-detail-bottom", action="store_true")
    parser.add_argument(
        "--resize-stress",
        action="store_true",
        help="Resize the visible fixture repeatedly before capture.",
    )
    parser.add_argument(
        "--navigate-after-show",
        action="store_true",
        help="Show the media page first, then navigate to the requested page.",
    )
    parser.add_argument(
        "--metrics-json",
        type=Path,
        help="Write repeatable desktop UI timing and resource metrics.",
    )
    parser.add_argument("--metrics-iterations", type=int, default=20)
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Capture only the fixture window to PNG without activating it.",
    )
    parser.add_argument("--screenshot-delay-ms", type=int, default=250)
    parser.add_argument(
        "--include-window-frame",
        action="store_true",
        help="Include the Windows title bar and frame in the screenshot.",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="liudi-downloader-visual-") as folder:
        root = Path(folder)
        output_path = root / "产品发布会完整回放.mp4"
        output_path.write_bytes(b"visual fixture")
        database = Database(root / "visual.db")
        database.set_setting("ui_theme", args.theme)
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
                eagle_available=lambda: False,
            ),
        )
        build_timings: dict[str, list[float]] = {}
        original_builders: dict[str, object] = {}
        builder_names = (
            "_build_media_tab",
            "_build_wechat_tab",
            "_build_idm_tab",
            "_build_settings_tab",
            "_build_diagnostics_tab",
        )
        if args.metrics_json:
            tracemalloc.start()
            for builder_name in builder_names:
                original = getattr(MainWindow, builder_name)
                original_builders[builder_name] = original

                def timed_builder(
                    instance: MainWindow,
                    *builder_args: object,
                    _name: str = builder_name,
                    _original=original,
                    **builder_kwargs: object,
                ):
                    started = time.perf_counter()
                    try:
                        return _original(
                            instance,
                            *builder_args,
                            **builder_kwargs,
                        )
                    finally:
                        build_timings.setdefault(_name, []).append(
                            (time.perf_counter() - started) * 1000
                        )

                setattr(MainWindow, builder_name, timed_builder)
        startup_started = time.perf_counter()
        try:
            window = MainWindow(
                database,
                api_server,
                _FakeProcessing(),
                visual_capture_hidden=bool(args.screenshot or args.metrics_json),
                visual_capture_geometry=(
                    args.geometry
                    if args.screenshot or args.metrics_json
                    else None
                ),
            )
        except Exception:
            for builder_name, original in original_builders.items():
                setattr(MainWindow, builder_name, original)
            if args.metrics_json:
                tracemalloc.stop()
            raise
        startup_ms = (time.perf_counter() - startup_started) * 1000
        window.root.geometry(args.geometry)
        deferred_navigation = bool(
            args.screenshot
            and args.navigate_after_show
            and args.page != "media"
        )

        def apply_requested_state() -> None:
            window._show_page(args.page)
            if args.page == "settings":
                window._settings_show_tab(args.settings_tab)
            elif args.page == "media" and args.selected_id:
                window._select_plan_card(args.selected_id)
            elif args.page == "wechat" and args.selected_id:
                window._select_wechat_card(args.selected_id)

        if not deferred_navigation:
            apply_requested_state()
        if args.toggle_theme:
            window._toggle_theme()
        window._visual_scroll_detail_bottom = args.scroll_detail_bottom
        if window.auto_update_after_id:
            window.root.after_cancel(window.auto_update_after_id)
            window.auto_update_after_id = None
        if args.metrics_json:
            try:
                metrics = _measure_ui_performance(
                    window,
                    startup_ms=startup_ms,
                    build_timings=build_timings,
                    iterations=max(1, args.metrics_iterations),
                )
                args.metrics_json.parent.mkdir(parents=True, exist_ok=True)
                args.metrics_json.write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            finally:
                for builder_name, original in original_builders.items():
                    setattr(MainWindow, builder_name, original)
                tracemalloc.stop()
            if not args.screenshot:
                window.quit()
                return
        if args.screenshot:
            def finish_capture() -> None:
                try:
                    _capture_fixture_window(
                        window,
                        args.screenshot,
                        include_window_frame=args.include_window_frame,
                    )
                finally:
                    window.root.destroy()

            def prepare_capture() -> None:
                _show_fixture_without_activation(window)
                if deferred_navigation:
                    apply_requested_state()
                    window.root.update()
                if not args.resize_stress:
                    window.root.after(
                        240 if deferred_navigation else 120,
                        finish_capture,
                    )
                    return

                target_width, target_height = (
                    int(value)
                    for value in args.geometry.lower().split("x", 1)
                )
                sizes = [
                    (max(900, target_width - 130), max(600, target_height - 90)),
                    (target_width + 120, target_height + 70),
                    (max(900, target_width - 60), target_height + 35),
                    (target_width, target_height),
                ]

                def resize_step(index: int = 0) -> None:
                    if index >= len(sizes):
                        window.root.after(260, finish_capture)
                        return
                    width, height = sizes[index]
                    window.root.geometry(f"{width}x{height}")
                    window.root.after(35, lambda: resize_step(index + 1))

                resize_step()

            window.root.after(max(0, args.screenshot_delay_ms), prepare_capture)
        window.root.mainloop()


if __name__ == "__main__":
    main()
