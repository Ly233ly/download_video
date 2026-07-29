from __future__ import annotations

import tempfile
import threading
import time
import unittest
import gc
import ctypes
import sys
from collections import OrderedDict
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from tkinter import BOTH, TclError, Tk
from tkinter import ttk
from tkinter import font as tkfont
from unittest.mock import patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.performance import PerformanceMonitor
from idm_eagle_bridge.service import ProcessingService
from idm_eagle_bridge.ui import (
    _AsyncProbe,
    _DynamicWrapLabel,
    _PreviewImageCache,
    _RoundedPanel,
    _RoundedProgressBar,
    _RoundedScrollbar,
    _ResponsiveTreeColumns,
    _ScrollableCardList,
    _VerticalScrolledFrame,
    _configure_styles,
    _effective_ui_scale,
    _ellipsize,
    _apply_windows_dark_title_bar,
    _bind_responsive_header_layout,
    _layout_mode_for_width,
    _load_product_image,
    _load_ui_icons,
    _media_plan_view,
    _pixel_ellipsize,
    _relative_time_label,
    _resolution_scale,
    _scale_geometry,
    _sync_tree_rows,
    _ui_scale_from_dpi,
    _windows_color_ref,
    _page_slice,
    MainWindow,
)


class _FakeTree:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, ...]] = {}
        self.order: list[str] = []
        self.inserts: list[str] = []
        self.updates: list[str] = []
        self.deletes: list[str] = []

    def get_children(self) -> tuple[str, ...]:
        return tuple(self.order)

    def exists(self, iid: str) -> bool:
        return iid in self.rows

    def insert(self, parent, index, *, iid: str, values) -> None:
        self.rows[iid] = tuple(values)
        self.order.append(iid)
        self.inserts.append(iid)

    def item(self, iid: str, option=None, **kwargs):
        if "values" in kwargs:
            self.rows[iid] = tuple(kwargs["values"])
            self.updates.append(iid)
        if option == "values":
            return self.rows[iid]
        return {"values": self.rows[iid]}

    def delete(self, *iids: str) -> None:
        for iid in iids:
            self.rows.pop(iid, None)
            if iid in self.order:
                self.order.remove(iid)
            self.deletes.append(iid)

    def move(self, iid: str, parent, index: int) -> None:
        self.order.remove(iid)
        self.order.insert(index, iid)


class _FakeSplit:
    def __init__(self) -> None:
        self.positions: list[tuple[int, int]] = []

    def sashpos(self, index: int, position: int) -> None:
        self.positions.append((index, position))


class UiPerformanceHelpersTests(unittest.TestCase):
    def test_windows_caption_color_uses_native_bgr_order(self) -> None:
        self.assertEqual(_windows_color_ref("#112233"), 0x332211)
        self.assertEqual(_windows_color_ref("#0D0F16"), 0x160F0D)
        with self.assertRaises(ValueError):
            _windows_color_ref("#123")

    def test_dark_title_bar_is_a_safe_noop_outside_windows(self) -> None:
        window = SimpleNamespace()
        with patch("idm_eagle_bridge.ui.sys.platform", "linux"):
            self.assertFalse(_apply_windows_dark_title_bar(window))

    def test_dpi_scale_keeps_logical_window_size_across_monitors(self) -> None:
        self.assertEqual(_ui_scale_from_dpi(96), 1.0)
        self.assertEqual(_ui_scale_from_dpi(144), 1.5)
        self.assertEqual(_ui_scale_from_dpi(192), 2.0)
        self.assertEqual(_scale_geometry("1120x720", 2.0), "2240x1440")

    def test_resolution_scale_handles_4k_at_one_hundred_percent(self) -> None:
        self.assertEqual(_resolution_scale(1920, 1080), 1.0)
        self.assertEqual(_resolution_scale(2560, 1440), 1.333)
        self.assertEqual(_resolution_scale(3840, 2160), 2.0)
        self.assertEqual(_resolution_scale(1366, 768), 1.0)
        self.assertEqual(_effective_ui_scale(96, 3840, 2160), 2.0)
        self.assertEqual(_effective_ui_scale(144, 1920, 1080), 1.5)
        self.assertEqual(_effective_ui_scale(192, 3840, 2160), 2.0)

    def test_page_slice_bounds_widget_projection_size(self) -> None:
        items = list(range(203))
        first, page, total_pages = _page_slice(items, 0, 12)
        last, last_page, last_total_pages = _page_slice(items, 99, 12)

        self.assertEqual(first, list(range(12)))
        self.assertEqual(page, 0)
        self.assertEqual(total_pages, 17)
        self.assertEqual(last, list(range(192, 203)))
        self.assertEqual(last_page, 16)
        self.assertEqual(last_total_pages, 17)

    def test_pixel_ellipsize_keeps_text_inside_a_tree_column(self) -> None:
        measure = lambda text: len(text) * 10

        self.assertEqual(_pixel_ellipsize("短标题", 40, measure), "短标题")
        self.assertEqual(
            _pixel_ellipsize("这是一个很长的标题", 60, measure),
            "这是一个很…",
        )
        self.assertEqual(_pixel_ellipsize("long title", 5, measure), "…")

    def test_layout_modes_follow_the_contract_breakpoints(self) -> None:
        self.assertEqual(_layout_mode_for_width(900), "compact")
        self.assertEqual(_layout_mode_for_width(1023), "compact")
        self.assertEqual(_layout_mode_for_width(1024), "normal")
        self.assertEqual(_layout_mode_for_width(1279), "normal")
        self.assertEqual(_layout_mode_for_width(1280), "wide")

    def test_responsive_layout_only_moves_the_visible_page_split(self) -> None:
        window = object.__new__(MainWindow)
        window.layout_mode = "normal"
        window.current_page = "wechat"
        window.media_split = _FakeSplit()
        window.wechat_split = _FakeSplit()
        window.idm_split = _FakeSplit()

        window._apply_mode_to_page_layouts()

        self.assertEqual(window.wechat_split.positions, [(0, 360)])
        self.assertEqual(window.media_split.positions, [])
        self.assertEqual(window.idm_split.positions, [])

    def test_ellipsize_preserves_short_text_and_marks_long_text(self) -> None:
        self.assertEqual(_ellipsize("short", 10), "short")
        self.assertEqual(_ellipsize("abcdefghij", 6), "abcde…")
        self.assertEqual(
            _ellipsize("标题第一行\n\n标题第二行\t补充", 12),
            "标题第一行 标题第二行…",
        )
        self.assertNotIn("\n", _ellipsize("第一行\n第二行", 20))

    def test_relative_time_uses_compact_today_and_yesterday_labels(self) -> None:
        now = time.mktime((2026, 7, 28, 16, 30, 0, 0, 0, -1))
        today = time.mktime((2026, 7, 28, 14, 32, 0, 0, 0, -1))
        yesterday = time.mktime((2026, 7, 27, 22, 44, 0, 0, 0, -1))

        self.assertEqual(_relative_time_label(today, now), "今天 14:32")
        self.assertEqual(_relative_time_label(yesterday, now), "昨天 22:44")

    def test_media_plan_view_keeps_incomplete_phases_below_one_hundred(self) -> None:
        validating = _media_plan_view(
            {
                "id": "plan-1",
                "status": "validating",
                "progress": 100,
                "downloaded_bytes": 2048,
                "total_bytes": 2048,
            }
        )
        completed = _media_plan_view(
            {
                "id": "plan-2",
                "status": "completed_local",
                "progress": 82,
                "final_path": r"C:\Downloads\video.mp4",
            }
        )

        self.assertEqual(validating["progress"], 99)
        self.assertEqual(completed["progress"], 100)
        self.assertTrue(completed["can_import_existing"])

    def test_tree_sync_only_mutates_changed_rows(self) -> None:
        tree = _FakeTree()
        _sync_tree_rows(
            tree,
            [
                ("a", ("A", "1")),
                ("b", ("B", "2")),
                ("c", ("C", "3")),
            ],
        )
        _sync_tree_rows(
            tree,
            [
                ("a", ("A", "1")),
                ("b", ("B", "updated")),
                ("d", ("D", "4")),
            ],
        )

        self.assertEqual(tree.order, ["a", "b", "d"])
        self.assertEqual(tree.inserts, ["a", "b", "c", "d"])
        self.assertEqual(tree.updates, ["b"])
        self.assertEqual(tree.deletes, ["c"])

    def test_async_probe_does_not_block_caller(self) -> None:
        release = threading.Event()

        def probe() -> bool:
            release.wait(2)
            return True

        async_probe = _AsyncProbe(probe, name="test-probe")
        started = time.perf_counter()
        self.assertTrue(async_probe.request())
        self.assertLess(time.perf_counter() - started, 0.1)
        self.assertFalse(async_probe.request())

        release.set()
        deadline = time.monotonic() + 2
        available = False
        value = None
        while time.monotonic() < deadline and not available:
            available, value = async_probe.poll()
            if not available:
                time.sleep(0.01)
        self.assertTrue(available)
        self.assertTrue(value)

    def test_preview_cache_reuses_unchanged_image(self) -> None:
        calls: list[str] = []

        def image_factory(*, file: str):
            calls.append(file)
            return object()

        cache = _PreviewImageCache(image_factory)
        with tempfile.TemporaryDirectory() as temp_dir:
            preview = Path(temp_dir) / "preview.png"
            preview.write_bytes(b"first")
            first = cache.resolve(preview)
            second = cache.resolve(preview)
            preview.write_bytes(b"second-image")
            third = cache.resolve(preview)

        self.assertIs(first, second)
        self.assertIsNot(second, third)
        self.assertEqual(len(calls), 2)


@unittest.skipUnless(sys.platform == "win32", "Windows title-bar integration only")
class WindowsTitleBarIntegrationTests(unittest.TestCase):
    def test_dark_caption_preserves_native_window_controls(self) -> None:
        try:
            root = Tk()
        except TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        root.withdraw()
        try:
            root.title("下载中转站")
            root.update_idletasks()
            self.assertTrue(_apply_windows_dark_title_bar(root))

            user32 = ctypes.windll.user32
            hwnd = int(root.winfo_id())
            while True:
                parent = int(user32.GetParent(hwnd) or 0)
                if not parent:
                    break
                hwnd = parent
            style = int(user32.GetWindowLongPtrW(hwnd, -16))
            native_controls = (
                0x00080000  # WS_SYSMENU
                | 0x00040000  # WS_THICKFRAME
                | 0x00020000  # WS_MINIMIZEBOX
                | 0x00010000  # WS_MAXIMIZEBOX
            )
            self.assertEqual(style & native_controls, native_controls)
        finally:
            root.destroy()


class VerticalScrolledFrameTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = Tk()
        except TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        self.root.withdraw()
        self.root.geometry("420x180")
        self.scroller = _VerticalScrolledFrame(self.root, padding=0)
        self.scroller.pack(fill=BOTH, expand=True)
        for index in range(60):
            ttk.Label(self.scroller.content, text=f"row {index}").pack()
        self.root.update_idletasks()

    def tearDown(self) -> None:
        root = getattr(self, "root", None)
        if root is not None:
            root.destroy()

    def test_content_taller_than_the_viewport_can_scroll_to_the_bottom(self) -> None:
        self.assertGreater(
            self.scroller.content.winfo_reqheight(),
            self.scroller.canvas.winfo_height(),
        )
        self.assertEqual(self.scroller.canvas.yview()[0], 0.0)

        self.scroller.scroll_to_bottom()
        self.root.update_idletasks()

        self.assertEqual(self.scroller.canvas.yview()[1], 1.0)
        self.assertGreater(self.scroller.canvas.yview()[0], 0.0)

    def test_mouse_wheel_over_an_inner_tree_keeps_the_outer_position(self) -> None:
        tree = ttk.Treeview(self.scroller.content, height=2)
        tree.pack()
        self.root.update_idletasks()
        before = self.scroller.canvas.yview()

        result = self.scroller._on_mousewheel(
            SimpleNamespace(widget=tree, delta=-120)
        )

        self.assertIsNone(result)
        self.assertEqual(self.scroller.canvas.yview(), before)

    def test_mouse_wheel_over_plain_content_scrolls_the_outer_canvas(self) -> None:
        self.assertEqual(self.scroller.canvas.yview()[0], 0.0)

        result = self.scroller._on_mousewheel(
            SimpleNamespace(widget=self.scroller.content, delta=-120)
        )
        self.root.update_idletasks()

        self.assertEqual(result, "break")
        self.assertGreater(self.scroller.canvas.yview()[0], 0.0)

    def test_high_resolution_wheel_deltas_accumulate_smoothly(self) -> None:
        before = self.scroller.canvas.yview()

        for _index in range(7):
            result = self.scroller._on_mousewheel(
                SimpleNamespace(widget=self.scroller.content, delta=-5)
            )
        self.root.update_idletasks()

        self.assertEqual(result, "break")
        self.assertEqual(self.scroller.canvas.yview(), before)
        self.scroller._on_mousewheel(
            SimpleNamespace(widget=self.scroller.content, delta=-5)
        )
        self.root.update_idletasks()
        self.assertGreater(self.scroller.canvas.yview()[0], 0.0)

    def test_layout_events_are_coalesced_and_scrollbar_tracks_overflow(self) -> None:
        first_after_id = None
        for _index in range(50):
            self.scroller._queue_layout()
            first_after_id = first_after_id or self.scroller._layout_after_id
            self.assertEqual(self.scroller._layout_after_id, first_after_id)
        self.root.update_idletasks()

        self.assertIsNone(self.scroller._layout_after_id)
        self.assertTrue(self.scroller._scrollbar_visible)
        self.assertEqual(self.scroller.scrollbar.winfo_manager(), "pack")

        self.scroller.pack_forget()
        compact = _VerticalScrolledFrame(self.root, padding=0)
        compact.pack(fill=BOTH, expand=True)
        ttk.Label(compact.content, text="one row").pack()
        self.root.update_idletasks()

        self.assertFalse(compact._scrollbar_visible)
        self.assertEqual(compact.scrollbar.winfo_manager(), "")

    def test_one_router_scrolls_card_content_from_any_descendant(self) -> None:
        self.scroller.pack_forget()
        cards = _ScrollableCardList(self.root)
        cards.pack(fill=BOTH, expand=True)
        labels = []
        for index in range(60):
            label = ttk.Label(cards.content, text=f"card {index}")
            label.pack()
            labels.append(label)
        self.root.update_idletasks()

        self.assertIs(cards._wheel_router, self.scroller._wheel_router)
        self.assertEqual(cards.canvas.yview()[0], 0.0)
        result = cards._wheel_router._dispatch(
            SimpleNamespace(widget=labels[20], delta=-120)
        )
        self.root.update_idletasks()

        self.assertEqual(result, "break")
        self.assertGreater(cards.canvas.yview()[0], 0.0)


class ResponsiveWidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = Tk()
        except TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        self.root.withdraw()
        self.root.geometry("640x300")

    def tearDown(self) -> None:
        root = getattr(self, "root", None)
        if root is not None:
            root.destroy()

    def test_dynamic_wrap_label_uses_the_rendered_width(self) -> None:
        label = _DynamicWrapLabel(
            self.root,
            text="long text",
            horizontal_padding=24,
            maximum=500,
        )
        label._update_wrap(SimpleNamespace(width=320))
        self.assertEqual(int(label.cget("wraplength")), 296)

    def test_detail_header_stacks_actions_when_space_is_tight(self) -> None:
        header = ttk.Frame(self.root)
        heading = ttk.Frame(header)
        actions = ttk.Frame(header)
        heading.grid(row=0, column=0)
        actions.grid(row=0, column=1)
        _bind_responsive_header_layout(
            header,
            heading,
            actions,
            breakpoint=700,
        )
        header.place(x=0, y=0, width=500, height=120)
        self.root.update()

        self.assertEqual(int(actions.grid_info()["row"]), 1)
        self.assertEqual(int(heading.grid_info()["columnspan"]), 2)

        header.place_configure(width=800)
        self.root.update()
        self.assertEqual(int(actions.grid_info()["row"]), 0)
        self.assertEqual(int(heading.grid_info()["columnspan"]), 1)

    def test_named_fonts_survive_style_configuration(self) -> None:
        _configure_styles(self.root, 1.0)
        gc.collect()

        self.assertGreater(tkfont.nametofont("Ui11").measure("媒体任务"), 0)
        self.assertGreater(
            int(tkfont.nametofont("Ui11").cget("size")),
            0,
            "Positive point sizes are required for Windows DPI scaling",
        )

    def test_named_fonts_use_one_readable_family_and_real_bold_weight(self) -> None:
        _configure_styles(self.root, 1.0)
        regular = tkfont.nametofont("Ui12")
        emphasized = tkfont.nametofont("Ui12Bold")
        available = set(tkfont.families(self.root))

        self.assertGreaterEqual(int(regular.cget("size")), 11)
        self.assertEqual(regular.actual("family"), emphasized.actual("family"))
        self.assertEqual(emphasized.actual("weight"), "bold")
        if "Microsoft YaHei UI" in available:
            self.assertEqual(regular.actual("family"), "Microsoft YaHei UI")

    def test_named_fonts_follow_high_dpi_tk_scaling(self) -> None:
        self.root.tk.call("tk", "scaling", 96 / 72)
        font = tkfont.Font(self.root, family="Segoe UI", size=10)
        normal = font.metrics("linespace")
        self.root.tk.call("tk", "scaling", 192 / 72)
        high_dpi = font.metrics("linespace")

        self.assertGreater(high_dpi, normal * 1.7)

    def test_wechat_capture_preflight_never_blocks_the_tk_callback(self) -> None:
        class SlowCertificate:
            def existing(self):
                time.sleep(0.25)
                return None

            def is_trusted(self, _fingerprint: str) -> bool:
                return False

        class Channels:
            certificate = SlowCertificate()

            @staticmethod
            def health() -> dict[str, bool]:
                return {"running": False}

            @staticmethod
            def start() -> None:
                return None

        class Button:
            def state(self, _value) -> None:
                return None

        class Text:
            def set(self, _value: str) -> None:
                return None

        class Root:
            def after(self, _delay: int, _callback) -> str:
                return "after-id"

        window = object.__new__(MainWindow)
        window.wechat_channels = Channels()
        window.wechat_operation_busy = False
        window.wechat_operation_results = __import__("queue").Queue()
        window.wechat_operation_generation = 0
        window.wechat_operation_after_id = None
        window.closing = False
        window.wechat_action_button = Button()
        window.wechat_status_text = Text()
        window.root = Root()

        started = time.perf_counter()
        window.toggle_wechat_capture()

        self.assertLess(time.perf_counter() - started, 0.1)

    def test_trusted_wechat_certificate_starts_without_install_permission(self) -> None:
        class Channels:
            trust_certificate = None

            def start(self, *, trust_certificate: bool) -> None:
                self.trust_certificate = trust_certificate

        channels = Channels()
        window = object.__new__(MainWindow)
        window.wechat_channels = channels
        window.wechat_operation_results = __import__("queue").Queue()

        window._run_wechat_operation(7, False, False)

        self.assertFalse(channels.trust_certificate)
        generation, event, payload = window.wechat_operation_results.get_nowait()
        self.assertEqual(generation, 7)
        self.assertEqual(event, "completed")
        self.assertEqual(payload, (True, ""))

    def test_wechat_proxy_repair_reports_the_actionable_result(self) -> None:
        class Channels:
            @staticmethod
            def repair_proxy_conflict() -> dict[str, object]:
                return {
                    "changed": True,
                    "message": "已清除失效代理，现在可以开始捕获",
                }

        window = object.__new__(MainWindow)
        window.wechat_channels = Channels()
        window.wechat_operation_results = __import__("queue").Queue()

        window._run_wechat_proxy_repair(9)

        generation, event, payload = window.wechat_operation_results.get_nowait()
        self.assertEqual(generation, 9)
        self.assertEqual(event, "proxy_repair")
        self.assertEqual(
            payload,
            (True, "已清除失效代理，现在可以开始捕获"),
        )

    def test_media_change_notifications_are_coalesced(self) -> None:
        window = object.__new__(MainWindow)
        window.media_change_events = Queue(maxsize=1)

        for _index in range(100):
            window._queue_media_change()

        self.assertEqual(window.media_change_events.qsize(), 1)

    def test_idm_text_measurement_cache_is_bounded_and_reused(self) -> None:
        window = object.__new__(MainWindow)
        window.idm_ellipsize_cache = OrderedDict()
        calls = 0

        def measure(value: str) -> int:
            nonlocal calls
            calls += 1
            return len(value) * 10

        first = window._fit_idm_column_text("一段很长的标题", 30, measure)
        first_calls = calls
        second = window._fit_idm_column_text("一段很长的标题", 30, measure)

        self.assertEqual(first, second)
        self.assertEqual(calls, first_calls)

    def test_stale_wechat_preview_result_is_discarded(self) -> None:
        window = object.__new__(MainWindow)
        window.wechat_preview_events = Queue()
        window.wechat_preview_events.put((1, "old", b"not-a-png"))
        window.wechat_preview_generation = 2
        window.wechat_preview_object_id = "current"
        window.performance_monitor = PerformanceMonitor(enabled=False)

        window._drain_wechat_preview_events()

        self.assertTrue(window.wechat_preview_events.empty())

    def test_maintenance_work_never_blocks_the_start_callback(self) -> None:
        class Root:
            def after(self, _delay: int, _callback) -> str:
                return "maintenance-poll"

        window = object.__new__(MainWindow)
        window.root = Root()
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

        def slow_worker() -> int:
            time.sleep(0.2)
            return 7

        started = time.perf_counter()
        window._start_maintenance("clear-idm", slow_worker)
        callback_duration = time.perf_counter() - started

        self.assertLess(callback_duration, 0.1)
        generation, kind, succeeded, payload = window.maintenance_events.get(
            timeout=1
        )
        self.assertEqual(generation, 1)
        self.assertEqual((kind, succeeded, payload), ("clear-idm", True, 7))

    def test_media_cards_expose_mouse_and_keyboard_context_menus(self) -> None:
        class Widget:
            def __init__(self) -> None:
                self.events: list[str] = []

            def bind(self, event: str, _callback, add: str = "") -> None:
                self.events.append(event)

        widget = Widget()
        window = object.__new__(MainWindow)
        window._bind_plan_card(widget, "plan-1")

        self.assertIn("<Button-3>", widget.events)
        self.assertIn("<Shift-F10>", widget.events)

    def test_media_context_menu_contains_single_task_cleanup(self) -> None:
        labels: list[str] = []

        class Menu:
            def __init__(self, *_args, **_kwargs) -> None:
                return None

            def add_command(self, *, label: str, command) -> None:
                labels.append(label)

            def add_separator(self) -> None:
                labels.append("---")

            def tk_popup(self, _x: int, _y: int) -> None:
                return None

            def grab_release(self) -> None:
                return None

        class Root:
            @staticmethod
            def winfo_pointerx() -> int:
                return 10

            @staticmethod
            def winfo_pointery() -> int:
                return 20

        window = object.__new__(MainWindow)
        window.root = Root()
        window.plan_rows = {
            "plan-1": {
                "final_path": "C:/Downloads/video.mp4",
                "page_url": "https://example.com/video",
            }
        }
        window._select_plan_card = lambda _plan_id: None
        with patch("idm_eagle_bridge.ui.Menu", Menu):
            result = window._show_plan_context_menu(
                SimpleNamespace(x_root=100, y_root=120),
                "plan-1",
            )

        self.assertEqual(result, "break")
        self.assertIn("打开文件位置", labels)
        self.assertIn("打开来源网页", labels)
        self.assertIn("清理任务（保留文件）", labels)

    def test_production_ui_assets_load_from_the_python_package(self) -> None:
        package_assets = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "idm_eagle_bridge"
            / "assets"
        )
        self.assertTrue((package_assets / "download-transfer-station.png").is_file())
        self.assertTrue((package_assets / "ui-icons" / "downloads-active.png").is_file())

        self.assertIsNotNone(_load_product_image(16))
        icons = _load_ui_icons()
        self.assertEqual(len(icons), 21)
        self.assertEqual(sum(value is not None for value in icons.values()), 0)
        self.assertTrue(
            {
                "downloads-active",
                "downloads-muted",
                "settings-active",
                "stop-danger",
            }.issubset(icons)
        )
        self.assertIsNotNone(icons.get("downloads-active"))
        self.assertEqual(sum(value is not None for value in icons.values()), 1)

    def test_rounded_scrollbar_uses_an_arrowless_adaptive_thumb(self) -> None:
        calls: list[tuple[object, ...]] = []
        scrollbar = _RoundedScrollbar(
            self.root,
            command=lambda *args: calls.append(args),
            background="#161820",
        )
        scrollbar.place(x=0, y=0, width=12, height=180)
        self.root.update_idletasks()
        scrollbar.set(0.2, 0.5)
        self.root.update_idletasks()

        geometry = scrollbar._thumb_geometry()
        self.assertIsNotNone(geometry)
        self.assertGreater(geometry[3] - geometry[1], 30)
        self.assertEqual(len(scrollbar.find_all()), 1)

    def test_rounded_widgets_keep_a_stable_canvas_item_count_during_resize(self) -> None:
        panel = _RoundedPanel(
            self.root,
            fill="#1A1D25",
            outer_background="#101116",
            style="TFrame",
            width=320,
            height=180,
        )
        panel.place(x=0, y=0, width=320, height=180)
        progress = _RoundedProgressBar(
            self.root,
            maximum=100,
            height=8,
            background="#1A1D25",
        )
        progress.place(x=0, y=190, width=320, height=8)
        self.root.update_idletasks()

        for width in range(320, 520, 4):
            panel.place_configure(width=width)
            progress.place_configure(width=width)
            progress.configure(value=width % 101)
        self.root.update_idletasks()

        self.assertEqual(len(panel.find_all()), 2)
        self.assertLessEqual(len(progress.find_all()), 2)
        self.assertIsNone(panel._draw_after_id)
        self.assertIsNone(progress._draw_after_id)

    def test_rounded_progress_accepts_existing_progress_style_updates(self) -> None:
        progress = _RoundedProgressBar(
            self.root,
            maximum=100,
            height=8,
            background="#1A1D25",
        )
        progress.place(x=0, y=0, width=240, height=8)
        progress.configure(
            value=100,
            style="Progress.Emerald.Horizontal.TProgressbar",
        )
        self.root.update_idletasks()

        self.assertEqual(progress._value, 100)
        self.assertEqual(progress._color, "#34D399")

    def test_tree_columns_fit_the_available_width(self) -> None:
        tree = ttk.Treeview(
            self.root,
            columns=("time", "file", "message"),
            show="headings",
        )
        tree.place(x=0, y=0, width=600, height=180)
        self.root.update_idletasks()
        manager = _ResponsiveTreeColumns(
            tree,
            [
                ("time", 90, 0),
                ("file", 150, 2),
                ("message", 160, 2),
            ],
            compact_minimums={"time": 82, "file": 130, "message": 140},
        )
        manager._resize()
        total = sum(int(tree.column(name, "width")) for name in ("time", "file", "message"))
        self.assertLessEqual(total, tree.winfo_width())
        self.assertGreaterEqual(int(tree.column("time", "width")), 82)


class ProductionUiIntegrationTests(unittest.TestCase):
    def test_real_media_plan_is_projected_into_the_production_main_window(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        database = Database(Path(temporary.name) / "bridge.db")
        processing = ProcessingService(database, interval=60)
        server = LocalApiServer(database, host="127.0.0.1", port=0)
        window = None
        server.start()
        try:
            with patch.object(server.api.media, "schedule"):
                plan = server.api.media.create_plan(
                    {
                        "pageUrl": "https://developer.apple.com/videos/play/wwdc2024/",
                        "pageTitle": "2024 年 WWDC 主题演讲 — 完整版",
                        "outputName": "WWDC 2024.mp4",
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
                                "size": 1024,
                                "duration": 12,
                                "drm": False,
                            }
                        ],
                        "runtimeHeaders": [{}],
                    }
                )

            try:
                window = MainWindow(
                    database,
                    server,
                    processing,
                    visual_capture_hidden=True,
                    visual_capture_geometry="900x600",
                )
            except TclError as exc:
                self.skipTest(f"Tk is unavailable: {exc}")

            window.refresh(force=True)
            window.root.update_idletasks()

            self.assertIs(window.media, server.api.media)
            self.assertIs(window.wechat_channels, server.api.wechat_channels)
            self.assertIs(window.processing, processing)
            self.assertIn(plan["id"], window.plan_rows)
            self.assertEqual(window.selected_plan_id(), plan["id"])
            self.assertEqual(
                window.plan_title_text.get(),
                "2024 年 WWDC 主题演讲 — 完整版",
            )
            self.assertEqual(
                window.plan_source_text.get(),
                "developer.apple.com",
            )
            self.assertEqual(
                set(window.plan_action_buttons),
                {"stop", "retry", "import", "open", "source"},
            )
            self.assertTrue(
                all(
                    button.winfo_manager() == "pack"
                    for button in window.plan_action_buttons.values()
                )
            )
            self.assertEqual(window.plan_secondary_actions.winfo_manager(), "pack")
            self.assertTrue(window.plan_action_buttons["stop"]._enabled)
            self.assertFalse(window.plan_action_buttons["retry"]._enabled)
            self.assertEqual(set(window.page_frames), {"media"})

            with patch.object(
                window.wechat_channels,
                "candidates",
                side_effect=AssertionError("hidden candidate page was refreshed"),
            ):
                window.refresh(force=True)
            window._show_page("settings")
            window.root.update_idletasks()
            self.assertIn("settings", window.page_frames)
            self.assertEqual(set(window.settings_sub_tabs), {"pairing"})
            window._show_page("media")
            window.root.update_idletasks()

            with patch.object(server.api.media, "schedule"):
                wechat_plan = server.api.media.create_plan(
                    {
                        "sourceType": "wechat_channels",
                        "pageUrl": "https://channels.weixin.qq.com/",
                        "pageTitle": "视频号统一任务",
                        "outputName": "视频号统一任务.mp4",
                        "outputContainer": "mp4",
                        "mergeMode": "direct",
                        "importToEagle": True,
                        "streams": [
                            {
                                "url": "https://finder.video.qq.com/video.mp4",
                                "role": "video",
                                "name": "video.mp4",
                                "extension": "mp4",
                                "mimeType": "video/mp4",
                            }
                        ],
                    }
                )
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and wechat_plan["id"] not in window.plan_rows:
                window.root.update()
                time.sleep(0.01)

            self.assertIn(wechat_plan["id"], window.plan_rows)
            self.assertEqual(window.selected_plan_id(), wechat_plan["id"])
        finally:
            if window is not None:
                window.quit()
            server.stop()
            processing.stop()
            temporary.cleanup()


class ProductionPackagingTests(unittest.TestCase):
    def test_idm_rows_expose_single_record_cleanup(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        ui_source = (
            project_root / "src" / "idm_eagle_bridge" / "ui.py"
        ).read_text(encoding="utf-8")

        self.assertIn('self.job_tree.bind("<Button-3>"', ui_source)
        self.assertIn('self.job_tree.bind("<Shift-F10>"', ui_source)
        self.assertIn("清理记录（保留文件）", ui_source)
        self.assertIn("self.database.remove_job", ui_source)

    def test_ui_assets_are_declared_for_wheel_and_pyinstaller_builds(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
        spec = (
            project_root / "packaging" / "DownloadTransferStation.spec"
        ).read_text(encoding="utf-8")

        self.assertIn('"assets/*.png"', pyproject)
        self.assertIn('"assets/ui-icons/*.png"', pyproject)
        self.assertIn("'src' / 'idm_eagle_bridge' / 'assets'", spec)
        self.assertIn("'idm_eagle_bridge/assets'", spec)

    def test_legacy_desktop_dialogs_and_duplicate_assets_are_removed(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        ui_source = (
            project_root / "src" / "idm_eagle_bridge" / "ui.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("class SiteRulesWindow", ui_source)
        self.assertNotIn("class ProxySettingsWindow", ui_source)
        self.assertFalse((project_root / "assets" / "ui-icons").exists())


if __name__ == "__main__":
    unittest.main()
