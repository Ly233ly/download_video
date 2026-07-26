from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import BOTH, TclError, Tk
from tkinter import ttk

from idm_eagle_bridge.ui import (
    _AsyncProbe,
    _PreviewImageCache,
    _VerticalScrolledFrame,
    _media_plan_view,
    _sync_tree_rows,
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


class UiPerformanceHelpersTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
