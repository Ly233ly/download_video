from __future__ import annotations

import tempfile
import threading
import time
import unittest
import gc
import ctypes
import math
import sys
import idm_eagle_bridge.ui as ui_module
from collections import OrderedDict
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from tkinter import BOTH, StringVar, TclError, Tk
from tkinter import ttk
from tkinter import font as tkfont
from unittest.mock import Mock, patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.performance import PerformanceMonitor
from idm_eagle_bridge.service import ProcessingService
from idm_eagle_bridge.ui import (
    UI,
    _AsyncProbe,
    _DynamicWrapLabel,
    _PreviewImageCache,
    _RoundedPanel,
    _RoundedBadge,
    _RoundedCombobox,
    _RoundedProgressBar,
    _RoundedScrollbar,
    _StatusIndicator,
    _ResponsiveTreeColumns,
    _ScrollableCardList,
    _VerticalScrolledFrame,
    _configure_styles,
    _effective_ui_scale,
    _ellipsize,
    _apply_windows_dark_title_bar,
    _antialiased_circle_pixels,
    _antialiased_corner_pixels,
    _bind_responsive_header_layout,
    _layout_mode_for_width,
    _load_product_image,
    _load_ui_icons,
    _media_plan_view,
    _pixel_ellipsize,
    _relative_time_label,
    _resolution_scale,
    _set_ui_theme,
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
    def test_theme_defaults_to_light_once_and_then_persists_the_last_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "theme.db"

            first_launch = Database(database_path)
            self.assertEqual(
                first_launch.get_setting("ui_theme", ui_module.DEFAULT_UI_THEME),
                "light",
            )
            first_launch.set_setting("ui_theme", "dark")

            restarted = Database(database_path)
            self.assertEqual(
                restarted.get_setting("ui_theme", ui_module.DEFAULT_UI_THEME),
                "dark",
            )

    def test_corrupt_retention_setting_falls_back_to_safe_default(self) -> None:
        self.assertEqual(ui_module._bounded_retention_days("broken"), 7)
        self.assertEqual(ui_module._bounded_retention_days(None), 7)
        self.assertEqual(ui_module._bounded_retention_days(-4), 0)
        self.assertEqual(ui_module._bounded_retention_days(900), 365)

    def test_storage_save_failure_is_shown_without_rewriting_form(self) -> None:
        class Variable:
            def __init__(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

            def set(self, value: object) -> None:
                self.value = str(value)

        window = object.__new__(ui_module.MainWindow)
        window.storage_retention_days = Variable("7")
        window.cache_retention_days = Variable("14")
        window.storage_feedback_text = Variable("")
        window.database = Mock()
        window.database.set_settings.side_effect = OSError("database read-only")

        window._save_storage_settings()

        self.assertIn("保存失败", window.storage_feedback_text.get())
        self.assertEqual(window.storage_retention_days.get(), "7")
        self.assertEqual(window.cache_retention_days.get(), "14")

    def test_eagle_probe_falls_back_for_legacy_or_fixture_api(self) -> None:
        fallback = Mock()
        self.assertIs(
            ui_module._resolve_eagle_probe(SimpleNamespace(), fallback),
            fallback,
        )
        shared = Mock()
        self.assertIs(
            ui_module._resolve_eagle_probe(
                SimpleNamespace(eagle_available=shared),
                fallback,
            ),
            shared,
        )
    def test_periodic_network_refresh_preserves_unsaved_form_edits(self) -> None:
        class Variable:
            def __init__(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

            def set(self, value: object) -> None:
                self.value = str(value)

        window = object.__new__(ui_module.MainWindow)
        window.current_settings_tab = "network"
        window.settings_proxy_mode = Variable("manual")
        window.settings_proxy_manual = Variable("http://127.0.0.1:7890")
        window.settings_proxy_status_text = Variable("")
        window.settings_proxy_entry = Mock()
        window.media = Mock()
        window.media.network_proxy.configuration.return_value = {
            "mode": "auto",
            "manualUrl": "",
        }
        window.media.network_proxy.status.return_value = {
            "source": "manual",
            "endpoint": "127.0.0.1:7890",
            "summary": "手动代理",
        }

        window._refresh_settings()

        self.assertEqual(window.settings_proxy_mode.get(), "manual")
        self.assertEqual(
            window.settings_proxy_manual.get(),
            "http://127.0.0.1:7890",
        )

    def test_media_and_wechat_cards_support_space_activation(self) -> None:
        class Widget:
            def __init__(self) -> None:
                self.events: list[str] = []

            def bind(self, event: str, _callback, add: str = "") -> None:
                self.events.append(event)

        window = object.__new__(ui_module.MainWindow)
        media_widget = Widget()
        wechat_widget = Widget()

        window._bind_plan_card(media_widget, "plan-1")
        window._bind_wechat_card(wechat_widget, "object-1")

        self.assertIn("<space>", media_widget.events)
        self.assertIn("<space>", wechat_widget.events)

    def test_imported_idm_source_update_does_not_prompt_while_eagle_is_offline(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.maintenance_busy = False
        window.eagle_connected = False
        window.root = Mock()
        window.selected_job = lambda: {
            "id": "job-1",
            "status": "imported",
            "eagle_item_id": "eagle-1",
        }

        with (
            patch.object(ui_module.simpledialog, "askstring") as askstring,
            patch.object(ui_module.messagebox, "showinfo") as showinfo,
        ):
            window.assign_source()

        askstring.assert_not_called()
        showinfo.assert_called_once()
        self.assertEqual(showinfo.call_args.args[0], "Eagle 未连接")

    def test_imported_idm_source_button_is_disabled_while_eagle_is_offline(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.eagle_connected = False
        window.maintenance_busy = False
        window.idm_action_buttons = {
            name: Mock() for name in ("retry", "open", "source", "assign", "remove")
        }

        window._update_idm_actions(
            {
                "id": "job-1",
                "status": "imported",
                "file_path": str(Path(__file__)),
                "source_url": "https://example.com/video",
                "eagle_item_id": "eagle-1",
            }
        )

        window.idm_action_buttons["assign"].configure.assert_any_call(state="disabled")

    def test_idm_offline_button_matrix_keeps_local_actions_available(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.eagle_connected = False
        window.maintenance_busy = False
        window.idm_action_buttons = {
            name: Mock() for name in ("retry", "open", "source", "assign", "remove")
        }

        window._update_idm_actions(
            {
                "id": "job-1",
                "status": "waiting_eagle",
                "file_path": str(Path(__file__)),
                "source_url": "https://example.com/video",
            }
        )

        expected = {
            "retry": "disabled",
            "open": "normal",
            "source": "normal",
            "assign": "normal",
            "remove": "normal",
        }
        for name, state in expected.items():
            window.idm_action_buttons[name].configure.assert_any_call(state=state)

    def test_idm_retry_is_disabled_when_original_file_is_missing(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.eagle_connected = True
        window.maintenance_busy = False
        window.idm_action_buttons = {
            name: Mock() for name in ("retry", "open", "source", "assign", "remove")
        }

        window._update_idm_actions(
            {
                "id": "job-1",
                "status": "retry",
                "file_path": str(Path(__file__).with_name("missing-video.mp4")),
                "source_url": "",
            }
        )

        window.idm_action_buttons["retry"].configure.assert_any_call(state="disabled")

    def test_idm_missing_file_retry_does_not_mutate_queue(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.eagle_connected = True
        window.database = Mock()
        window.processing = Mock()
        window.selected_job = lambda: {
            "id": "job-1",
            "status": "retry",
            "file_path": str(Path(__file__).with_name("missing-video.mp4")),
        }

        with patch.object(ui_module.messagebox, "showwarning") as showwarning:
            window.retry_selected()

        window.database.retry_job.assert_not_called()
        window.processing.wake.assert_not_called()
        showwarning.assert_called_once()

    def test_media_task_offline_button_matrix_only_disables_eagle_import(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.eagle_connected = False
        final_path = str(Path(__file__))
        window.selected_plan = lambda: {"final_path": final_path}
        window.plan_action_buttons = {
            name: Mock() for name in ("stop", "retry", "import", "open", "source")
        }

        window._update_plan_actions(
            {
                "active": False,
                "can_retry": False,
                "can_import_existing": True,
                "can_open_output": True,
                "can_open_source": True,
            }
        )

        expected = {
            "stop": False,
            "retry": False,
            "import": False,
            "open": True,
            "source": True,
        }
        for name, enabled in expected.items():
            window.plan_action_buttons[name].set_enabled.assert_called_once_with(enabled)

    def test_wechat_local_delivery_does_not_require_eagle(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.eagle_connected = False
        window.wechat_import_to_eagle = Mock()
        window.wechat_import_to_eagle.get.return_value = False
        window.wechat_variant_box = Mock()
        window.wechat_variant_box.current.return_value = 0
        window.wechat_variant_ids = ["variant-1"]
        window.wechat_channels = Mock()
        window._selected_wechat_candidate = lambda: {"objectId": "object-1"}
        window._show_page = Mock()
        window.refresh = Mock()

        window.submit_selected_wechat_candidate()

        window.wechat_channels.submit.assert_called_once_with(
            "object-1",
            "variant-1",
            import_to_eagle=False,
            delete_after_import=False,
        )
        window._show_page.assert_called_once_with("media")

    def test_wechat_eagle_delivery_is_blocked_before_task_creation_when_offline(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.eagle_connected = False
        window.wechat_import_to_eagle = Mock()
        window.wechat_import_to_eagle.get.return_value = True
        window.wechat_variant_box = Mock()
        window.wechat_variant_box.current.return_value = 0
        window.wechat_variant_ids = ["variant-1"]
        window.wechat_channels = Mock()
        window._selected_wechat_candidate = lambda: {"objectId": "object-1"}

        with patch.object(ui_module.messagebox, "showinfo") as showinfo:
            window.submit_selected_wechat_candidate()

        window.wechat_channels.submit.assert_not_called()
        showinfo.assert_called_once()

    def test_idm_open_file_error_is_reported_instead_of_escaping(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.selected_job = lambda: {"file_path": str(Path(__file__))}

        with (
            patch.object(ui_module.subprocess, "Popen", side_effect=OSError("shell unavailable")),
            patch.object(ui_module.messagebox, "showerror") as showerror,
        ):
            window.open_file_location()

        showerror.assert_called_once()
        self.assertEqual(showerror.call_args.args[0], "无法打开文件位置")

    def test_plan_source_open_failure_is_reported(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.selected_plan = lambda: {"page_url": "https://example.com/video"}

        with (
            patch.object(ui_module.webbrowser, "open", return_value=False),
            patch.object(ui_module.messagebox, "showerror") as showerror,
        ):
            window.open_plan_source()

        showerror.assert_called_once()
        self.assertEqual(showerror.call_args.args[0], "无法打开来源网页")

    def test_idm_source_open_failure_is_reported(self) -> None:
        window = object.__new__(ui_module.MainWindow)
        window.root = Mock()
        window.selected_job = lambda: {"source_url": "https://example.com/video"}

        with (
            patch.object(ui_module.webbrowser, "open", side_effect=OSError("browser unavailable")),
            patch.object(ui_module.messagebox, "showerror") as showerror,
        ):
            window.open_source()

        showerror.assert_called_once()
        self.assertEqual(showerror.call_args.args[0], "无法打开来源网页")

    def test_status_circle_has_symmetric_antialiased_edges(self) -> None:
        pixels = _antialiased_circle_pixels(
            9,
            fill=(0, 255, 0),
            outer_background=(0, 0, 0),
        )
        green = list(pixels[1::3])

        self.assertEqual(green[0], 0)
        self.assertEqual(green[4 * 9 + 4], 255)
        self.assertTrue(any(0 < value < 255 for value in green))
        for y in range(9):
            for x in range(9):
                self.assertEqual(green[y * 9 + x], green[y * 9 + (8 - x)])
                self.assertEqual(green[y * 9 + x], green[(8 - y) * 9 + x])

    def test_shared_rounded_geometry_contains_antialiased_edge_pixels(self) -> None:
        pixels = _antialiased_corner_pixels(
            12,
            fill=(255, 0, 0),
            border=(255, 0, 0),
            outer_background=(0, 0, 0),
            border_width=0,
        )
        red_values = pixels[0::3]

        self.assertIn(0, red_values)
        self.assertIn(255, red_values)
        self.assertTrue(any(0 < value < 255 for value in red_values))

    def test_rounded_rect_fill_reaches_the_corner_image_edges(self) -> None:
        class RecordingCanvas:
            def __init__(self) -> None:
                self.rectangles: list[tuple[int, int, int, int]] = []

            def create_rectangle(self, x1, y1, x2, y2, **_kwargs):
                self.rectangles.append((x1, y1, x2, y2))
                return len(self.rectangles)

            def create_image(self, *_args, **_kwargs):
                return 100 + len(self.rectangles)

        canvas = RecordingCanvas()
        with patch.object(
            ui_module,
            "_corner_photo_images",
            return_value=(object(), object(), object(), object()),
        ):
            ui_module._draw_antialiased_rounded_rect(
                canvas,
                1,
                1,
                65,
                41,
                8,
                fill="#7464DF",
                border="#5B4CCB",
                border_width=1,
                outer_background="#FFFFFF",
            )

        # Tk Canvas rectangle x2/y2 coordinates are exclusive for the fill.
        # The central fills and one-pixel border strips must therefore end at
        # the exact right/bottom boundary shared by the corner images. Using
        # boundary - 1 leaves the white notch visible in the real UI.
        self.assertEqual(canvas.rectangles[0], (9, 1, 57, 41))
        self.assertEqual(canvas.rectangles[1], (1, 9, 65, 33))
        self.assertEqual(canvas.rectangles[2], (9, 1, 57, 2))
        self.assertEqual(canvas.rectangles[3], (9, 40, 57, 41))
        self.assertEqual(canvas.rectangles[4], (1, 9, 2, 33))
        self.assertEqual(canvas.rectangles[5], (64, 9, 65, 33))

    def test_antialias_geometry_is_reused_across_theme_colours(self) -> None:
        ui_module._CIRCLE_COVERAGE_CACHE.clear()
        ui_module._CORNER_COVERAGE_CACHE.clear()
        first_corner = _antialiased_corner_pixels(
            12,
            fill=(255, 0, 0),
            border=(128, 0, 0),
            outer_background=(0, 0, 0),
            border_width=1,
        )
        second_corner = _antialiased_corner_pixels(
            12,
            fill=(0, 255, 0),
            border=(0, 128, 0),
            outer_background=(255, 255, 255),
            border_width=1,
        )
        _antialiased_circle_pixels(
            9,
            fill=(0, 255, 0),
            outer_background=(0, 0, 0),
        )
        _antialiased_circle_pixels(
            9,
            fill=(255, 0, 0),
            outer_background=(255, 255, 255),
        )

        self.assertNotEqual(first_corner, second_corner)
        self.assertEqual(len(ui_module._CORNER_COVERAGE_CACHE), 1)
        self.assertEqual(len(ui_module._CIRCLE_COVERAGE_CACHE), 1)

    def test_media_task_list_scrolls_directly_without_pagination_controls(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "idm_eagle_bridge" / "ui.py").read_text(
            encoding="utf-8"
        )
        build_start = source.index("    def _build_media_tab(self) -> None:")
        build_end = source.index("    def _build_wechat_tab(self) -> None:", build_start)
        media_builder = source[build_start:build_end]
        refresh_start = source.index("    def _refresh_media_tasks(")
        refresh_end = source.index("    def selected_plan_id(", refresh_start)
        media_refresh = source[refresh_start:refresh_end]

        self.assertNotIn("media_previous_button", media_builder)
        self.assertNotIn("media_page_text", media_builder)
        self.assertNotIn("media_next_button", media_builder)
        self.assertNotIn("_page_slice", media_refresh)
        self.assertIn("self._render_plan_cards(plans)", media_refresh)

    def test_desktop_browser_connection_page_has_no_manual_pairing_code(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "idm_eagle_bridge" / "ui.py").read_text(
            encoding="utf-8"
        )
        start = source.index("    def _build_settings_pairing(self) -> None:")
        end = source.index("    def _build_settings_sites(self) -> None:", start)
        pairing_page = source[start:end]

        self.assertIn("浏览器连接", pairing_page)
        self.assertIn("无需输入配对码", pairing_page)
        self.assertNotIn("六位配对码", pairing_page)
        self.assertNotIn("copy_pairing_code", pairing_page)
        self.assertNotIn("pairing_code_text", pairing_page)

    def test_file_management_page_exposes_manual_and_automatic_cache_cleanup(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "idm_eagle_bridge" / "ui.py").read_text(
            encoding="utf-8"
        )
        start = source.index("    def _build_settings_storage(self) -> None:")
        end = source.index("    def _build_settings_updates(self) -> None:", start)
        storage_page = source[start:end]

        self.assertIn("程序缓存", storage_page)
        self.assertIn("临时下载、任务预览和旧版下载日志", storage_page)
        self.assertIn("立即清理缓存", storage_page)
        self.assertIn("cache_retention_days", storage_page)
        self.assertIn("已完成目录不会清理", storage_page)

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

    def test_eagle_offline_is_presented_as_download_available(self) -> None:
        state = ui_module._eagle_experience(False)
        self.assertEqual(state["status"], "Eagle 未连接 · 下载可用")
        self.assertFalse(state["can_import"])
        self.assertIn("不影响浏览器和视频号仅下载", state["idm_hint"])

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
            root.title("留底下载器")
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

    def test_status_indicator_uses_active_theme_and_antialiased_circle(self) -> None:
        previous_palette = dict(UI)
        try:
            _set_ui_theme("light")
            indicator = _StatusIndicator(self.root, size=9)
            indicator.pack()
            self.root.update_idletasks()

            self.assertEqual(str(indicator.cget("background")), UI["bg"])
            item_types = [indicator.type(item) for item in indicator.find_all()]
            self.assertEqual(item_types.count("image"), 1)
            self.assertNotIn("oval", item_types)

            light_palette = dict(UI)
            _set_ui_theme("dark")
            window = object.__new__(MainWindow)
            window._retheme_widget_tree(
                indicator,
                MainWindow._theme_color_map(light_palette, UI),
            )
            self.root.update_idletasks()

            self.assertEqual(str(indicator.cget("background")), UI["bg"])
            self.assertEqual(indicator._background, UI["bg"])
            self.assertEqual(
                [indicator.type(item) for item in indicator.find_all()].count("image"),
                1,
            )
        finally:
            UI.clear()
            UI.update(previous_palette)

    def test_focusable_rounded_panel_draws_a_visible_focus_border(self) -> None:
        panel = _RoundedPanel(
            self.root,
            fill=UI["surface"],
            outer_background=UI["bg"],
            style="Surface.TFrame",
            takefocus=True,
            width=180,
            height=64,
        )
        panel.pack()
        self.root.update_idletasks()

        with patch.object(panel, "focus_get", return_value=panel):
            panel._last_draw_signature = None
            panel._redraw()

        self.assertTrue(panel._last_draw_signature[-1])
        self.assertEqual(panel._last_focus_border, UI["accent"])

    def test_rounded_panel_content_clears_the_antialiased_corner(self) -> None:
        radius = 14
        panel = _RoundedPanel(
            self.root,
            fill=UI["surface"],
            outer_background=UI["bg"],
            style="Surface.TFrame",
            radius=radius,
            inset=2,
            takefocus=True,
            width=180,
            height=64,
        )

        # A rectangular child window must begin beyond the curved border.
        # Otherwise it paints square pixels over the outer rounded surface.
        required_inset = math.ceil(radius - (radius - 1) / math.sqrt(2)) + 1
        self.assertGreaterEqual(panel._inset, required_inset)

    def test_rounded_task_cards_leave_enough_height_for_their_inner_rows(self) -> None:
        _configure_styles(self.root)

        def card(
            *,
            height: int,
            lines: tuple[tuple[str, str, tuple[int, int]], ...],
            body_padding: tuple[int, int, int, int],
            thumbnail: tuple[int, int],
        ) -> tuple[_RoundedPanel, ttk.Frame]:
            panel = _RoundedPanel(
                self.root,
                fill=UI["selected"],
                outer_background=UI["surface"],
                style="TaskCardSelected.TFrame",
                radius=ui_module.RADII["card"],
                height=height,
                inset=4,
                takefocus=True,
            )
            panel.place(x=0, y=0, width=360, height=height)
            body = ttk.Frame(
                panel.inner,
                style="TaskCardSelected.TFrame",
                padding=body_padding,
            )
            body.pack(fill=BOTH, expand=True)
            body.columnconfigure(1, weight=1)
            thumbnail_host = _RoundedPanel(
                body,
                fill=UI["surface_overlay"],
                outer_background=UI["selected"],
                style="Soft.TFrame",
                width=thumbnail[0],
                height=thumbnail[1],
                radius=ui_module.RADII["thumbnail"],
                inset=2,
            )
            thumbnail_host.grid(
                row=0,
                column=0,
                rowspan=len(lines),
                sticky="nw",
                padx=(0, 8),
            )
            for index, (text, style, pady) in enumerate(lines):
                ttk.Label(
                    body,
                    text=text,
                    style=style,
                    anchor="w",
                ).grid(row=index, column=1, sticky="ew", pady=pady)
            self.root.update_idletasks()
            return panel, body

        media, media_body = card(
            height=ui_module.METRICS["task_row_height"] - 4,
            lines=(
                ("机器学习入门课程", "TaskCardTitleSelected.TLabel", (0, 0)),
                ("coursera.org", "TaskCardMetaSelected.TLabel", (2, 0)),
                ("下载失败", "TaskCardMetaSelected.TLabel", (4, 0)),
            ),
            body_padding=(8, 5, 8, 4),
            thumbnail=(48, 32),
        )
        wechat, wechat_body = card(
            height=ui_module.METRICS["wechat_row_height"] - 4,
            lines=(
                ("一座城市醒来的清晨", "TaskCardTitleSelected.TLabel", (0, 0)),
                ("旅行手记", "TaskCardMetaSelected.TLabel", (2, 0)),
                ("3:02  1080p  01:47", "TaskCardMetaSelected.TLabel", (3, 0)),
            ),
            body_padding=(12, 6, 10, 5),
            thumbnail=(64, 40),
        )

        self.assertLessEqual(media_body.winfo_reqheight(), media.inner.winfo_height())
        self.assertLessEqual(wechat_body.winfo_reqheight(), wechat.inner.winfo_height())

    def test_rounded_widgets_schedule_their_first_paint_directly(self) -> None:
        widgets = (
            _StatusIndicator(self.root),
            _RoundedPanel(
                self.root,
                fill=UI["surface"],
                outer_background=UI["bg"],
                style="Surface.TFrame",
            ),
            ui_module._RoundedButton(self.root, text="操作"),
            _RoundedCombobox(self.root, values=("一", "二")),
            ui_module._RoundedNavButton(
                self.root,
                text="设置",
                image=None,
                command=lambda: None,
            ),
            _RoundedScrollbar(
                self.root,
                command=lambda *_args: None,
                background=UI["bg"],
            ),
            _RoundedProgressBar(
                self.root,
                background=UI["surface"],
            ),
        )

        # One queued idle callback is enough. A second-level queue leaves a
        # briefly blank/square Canvas until a click or focus event repaints it.
        for widget in widgets:
            self.assertIsNotNone(widget._draw_after_id)
        for widget in widgets:
            widget.destroy()
            self.assertIsNone(widget._draw_after_id)

    def test_rounded_badge_cancels_pending_theme_paint_when_destroyed(self) -> None:
        badge = _RoundedBadge(
            self.root,
            text="本机完成",
            foreground=UI["status_completed_local"][0],
            fill=UI["status_completed_local"][1],
            outer_background=UI["surface"],
        )
        badge.set_badge(
            text="已导入",
            foreground=UI["status_imported"][0],
            fill=UI["status_imported"][1],
            outer_background=UI["surface"],
        )

        self.assertIsNotNone(badge._draw_after_id)
        badge.destroy()
        self.assertIsNone(badge._draw_after_id)

    def test_disabled_rounded_inputs_leave_keyboard_focus_traversal(self) -> None:
        button = ui_module._RoundedButton(
            self.root,
            text="不可用",
            state="disabled",
        )
        combo = _RoundedCombobox(
            self.root,
            state="disabled",
            values=("一", "二"),
        )

        self.assertIn(str(button.cget("takefocus")), {"", "0"})
        self.assertIn(str(combo.cget("takefocus")), {"", "0"})

        button.configure(state="normal")
        combo.configure(state="readonly")
        self.assertEqual(str(button.cget("takefocus")), "1")
        self.assertEqual(str(combo.cget("takefocus")), "1")

    def test_rounded_button_mouse_activation_claims_keyboard_focus(self) -> None:
        button = ui_module._RoundedButton(self.root, text="操作")
        with patch.object(button, "focus_set") as focus_set:
            button._activate(SimpleNamespace(num=1, keysym=""))

        focus_set.assert_called_once()

    def test_rounded_navigation_mouse_activation_claims_keyboard_focus(self) -> None:
        button = ui_module._RoundedNavButton(
            self.root,
            text="设置",
            image=None,
            command=lambda: None,
        )
        with patch.object(button, "focus_set") as focus_set:
            button._activate(SimpleNamespace(num=1, keysym=""))

        focus_set.assert_called_once()

    def test_combobox_escape_closes_popup_and_returns_focus(self) -> None:
        combo = _RoundedCombobox(self.root, values=("一", "二"))
        combo._popup = Mock()
        combo._listbox = Mock()
        with patch.object(combo, "focus_set") as focus_set:
            combo._close_popup(SimpleNamespace(keysym="Escape"))

        focus_set.assert_called_once()

    def test_rounded_badge_rebuilds_antialiased_surface_after_one_theme_switch(self) -> None:
        previous_palette = dict(UI)
        try:
            _set_ui_theme("light")
            badge = _RoundedBadge(
                self.root,
                text="本机完成",
                foreground=UI["status_completed_local"][0],
                fill=UI["status_completed_local"][1],
                outer_background=UI["surface"],
            )
            badge.pack()
            self.root.update_idletasks()

            light_palette = dict(UI)
            _set_ui_theme("dark")
            window = object.__new__(MainWindow)
            window._retheme_widget_tree(
                badge,
                MainWindow._theme_color_map(light_palette, UI),
            )
            self.root.update_idletasks()

            self.assertEqual(str(badge.cget("background")), UI["surface"])
            self.assertEqual(badge._last_draw_signature, badge._state)
        finally:
            UI.clear()
            UI.update(previous_palette)

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

    def test_raised_label_uses_the_active_theme_on_first_render(self) -> None:
        previous_palette = dict(UI)
        try:
            _set_ui_theme("dark")
            _configure_styles(self.root, 1.0)

            style = ttk.Style(self.root)
            self.assertEqual(
                str(style.lookup("Raised.TLabel", "background")),
                UI["surface_raised"],
            )
            self.assertEqual(
                str(style.lookup("Raised.TLabel", "foreground")),
                UI["text"],
            )
        finally:
            UI.clear()
            UI.update(previous_palette)
            _configure_styles(self.root, 1.0)

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
        self.assertTrue((package_assets / "liudi-downloader.png").is_file())
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
        self.assertEqual(len(scrollbar.find_all()), 6)

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

        self.assertEqual(panel.type(panel._surface), "rectangle")
        self.assertEqual(len(panel.find_all()), 7)
        self.assertEqual(
            [panel.type(item) for item in panel.find_all()].count("image"),
            4,
        )
        self.assertNotIn("polygon", [panel.type(item) for item in panel.find_all()])
        self.assertLessEqual(len(progress.find_all()), 12)
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
        self.assertEqual(progress._color, UI["success"])

    def test_rounded_combobox_preserves_combobox_selection_contract(self) -> None:
        value = StringVar(master=self.root, value="")
        selector = _RoundedCombobox(
            self.root,
            textvariable=value,
            values=("1080p", "720p"),
        )
        selector.pack(fill="x")
        selector.current(1)
        self.root.update_idletasks()

        self.assertEqual(selector.current(), 1)
        self.assertEqual(value.get(), "720p")
        selector.configure(values=("4K", "1080p"))
        selector.current(0)
        self.assertEqual(selector.cget("values"), ("4K", "1080p"))
        self.assertEqual(value.get(), "4K")
        self.root.update_idletasks()

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

            self.assertEqual(window.ui_theme, "light")
            self.assertEqual(window.root.title(), "留底下载器 v1.6.0 by阿毅i")
            self.assertEqual(window.theme_button_text.get(), "切换到深色主题")
            window._toggle_theme()
            window.root.update_idletasks()
            self.assertEqual(window.ui_theme, "dark")
            self.assertEqual(database.get_setting("ui_theme"), "dark")
            self.assertEqual(window.theme_button_text.get(), "切换到微亮主题")
            window._toggle_theme()
            window.root.update_idletasks()
            self.assertEqual(window.ui_theme, "light")

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
            project_root / "packaging" / "LiudiDownloader.spec"
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
