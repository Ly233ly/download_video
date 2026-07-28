from __future__ import annotations

import tempfile
import threading
import time
import unittest
import gc
from pathlib import Path
from types import SimpleNamespace
from tkinter import BOTH, TclError, Tk
from tkinter import ttk
from tkinter import font as tkfont
from unittest.mock import patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.service import ProcessingService
from idm_eagle_bridge.ui import (
    _AsyncProbe,
    _DynamicWrapLabel,
    _PreviewImageCache,
    _RoundedProgressBar,
    _RoundedScrollbar,
    _ResponsiveTreeColumns,
    _VerticalScrolledFrame,
    _configure_styles,
    _ellipsize,
    _layout_mode_for_width,
    _load_product_image,
    _load_ui_icons,
    _media_plan_view,
    _relative_time_label,
    _sync_tree_rows,
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

    def test_named_fonts_survive_style_configuration(self) -> None:
        _configure_styles(self.root)
        gc.collect()

        self.assertGreater(tkfont.nametofont("Ui11").measure("媒体任务"), 0)

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
        self.assertTrue(
            {
                "downloads-active",
                "downloads-muted",
                "settings-active",
                "stop-danger",
            }.issubset(icons)
        )

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

        geometry = scrollbar._thumb_geometry()
        self.assertIsNotNone(geometry)
        self.assertGreater(geometry[3] - geometry[1], 30)
        self.assertEqual(len(scrollbar.find_all()), 1)

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
        finally:
            if window is not None:
                window.quit()
            server.stop()
            processing.stop()
            temporary.cleanup()


class ProductionPackagingTests(unittest.TestCase):
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
