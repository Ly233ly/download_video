from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
import json
import math
import re
import threading
import ctypes
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path
from queue import Empty, Full, Queue
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    BooleanVar,
    Canvas,
    Listbox,
    Menu,
    PhotoImage,
    StringVar,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
    simpledialog,
)
from tkinter import ttk
from tkinter import font as tkfont
from urllib.parse import urlsplit

from .api_server import LocalApiServer
from .constants import APP_AUTHOR, APP_NAME, APP_VERSION
from .control_signal import ControlSignals
from .database import Database
from .eagle import EagleClient
from .network_proxy import ProxyConfigurationError
from .performance import PerformanceMonitor
from .security import PairingManager
from .service import ProcessingService
from .updater import (
    UpdateError,
    UpdateInfo,
    automatic_check_due,
    check_for_update,
    launch_installer,
    prepare_update,
    record_successful_check,
)
from .url_utils import InvalidPageUrl, clean_page_url, normalize_domain


STATUS_TEXT = {
    "waiting_source": "等待处理",
    "queued": "等待处理",
    "waiting_eagle": "等待 Eagle",
    "retry": "等待自动重试",
    "imported": "导入成功",
    "skipped_duplicate": "重复跳过",
    "ignored_non_video": "非视频忽略",
    "ignored_by_user": "本次忽略",
    "failed_permanent": "导入失败",
}

MEDIA_STATUS_TEXT = {
    "queued": "等待本机下载",
    "downloading": "本机正在下载",
    "merging": "本机正在合并",
    "validating": "正在校验",
    "ready_to_import": "等待导入 Eagle",
    "waiting_eagle": "等待 Eagle",
    "imported": "已导入 Eagle",
    "completed_local": "已下载到本机",
    "retry": "下载失败",
    "import_failed": "Eagle 导入失败",
    "failed_permanent": "无法继续",
    "canceled": "已停止",
    "needs_rebuild": "需要回到来源重建",
}

MEDIA_CARD_STATUS_TEXT = {
    "queued": "排队中",
    "downloading": "下载中",
    "merging": "合并中",
    "validating": "校验中",
    "ready_to_import": "待导入",
    "waiting_eagle": "等待 Eagle",
    "imported": "已导入",
    "completed_local": "本机完成",
    "retry": "下载失败",
    "import_failed": "导入失败",
    "failed_permanent": "永久失败",
    "canceled": "已停止",
    "needs_rebuild": "待重建",
}

MEDIA_ACTIVE_STATUSES = {"queued", "downloading", "merging", "validating", "ready_to_import"}
MEDIA_RETRYABLE_STATUSES = {"retry"}

DARK_UI = {
    "bg": "#0D0F16",
    "sidebar_bg": "#111318",
    "surface": "#161820",
    "surface_raised": "#1A1D25",
    "surface_overlay": "#1F222B",
    "border": "#2A2D35",
    "divider": "#1E2029",
    "text": "#E2E8F0",
    "text_secondary": "#B3B8C3",
    "text_muted": "#858B9C",
    "text_disabled": "#73798A",
    "accent": "#6366F1",
    "accent_button": "#6265F1",
    "accent_hover": "#5558E6",
    "accent_subtle": "#1E1F3A",
    "accent_text": "#A5B4FC",
    "success": "#34D399",
    "success_subtle": "#0F2F24",
    "warning": "#FBBF24",
    "warning_subtle": "#2F2508",
    "danger": "#F87171",
    "danger_subtle": "#2F1515",
    "info": "#60A5FA",
    "selected": "#1E2440",
    "progress_track": "#1A1D25",

    # ── state badge colors (fg, bg) ──
    "status_queued": ("#9CA3AF", "#17191E"),
    "status_downloading": ("#60A5FA", "#0F1F2F"),
    "status_merging": ("#60A5FA", "#0F1F2F"),
    "status_validating": ("#A78BFA", "#1A1430"),
    "status_ready_to_import": ("#FBBF24", "#2F2508"),
    "status_waiting_eagle": ("#FB923C", "#2F1A08"),
    "status_imported": ("#34D399", "#0F2F24"),
    "status_completed_local": ("#2DD4BF", "#0A2F2A"),
    "status_retry": ("#FACC15", "#2F2A00"),
    "status_failed_permanent": ("#F87171", "#2F1515"),
    "status_import_failed": ("#FB7185", "#2F151A"),
    "status_canceled": ("#6B7280", "#15171A"),
    "status_needs_rebuild": ("#E879F9", "#2F1530"),

    # ── idm job status colors ──
    "job_imported": ("#34D399", "#0F2F24"),
    "job_waiting": ("#FBBF24", "#2F2508"),
    "job_active": ("#60A5FA", "#0F1F2F"),
    "job_failed": ("#F87171", "#2F1515"),
    "job_ignored": ("#9CA3AF", "#17191E"),
}

LIGHT_UI = {
    "bg": "#F0F1F6",
    "sidebar_bg": "#F7F7FB",
    "surface": "#F5F6FA",
    "surface_raised": "#FFFFFF",
    "surface_overlay": "#ECEEF5",
    "border": "#D8DBE6",
    "divider": "#E1E3EB",
    "text": "#252936",
    "text_secondary": "#535A6D",
    "text_muted": "#777F92",
    "text_disabled": "#A3A8B6",
    "accent": "#6C63D9",
    "accent_button": "#7168DE",
    "accent_hover": "#5F57C8",
    "accent_subtle": "#EAE8FB",
    "accent_text": "#554FC1",
    "success": "#23815F",
    "success_subtle": "#E4F4EC",
    "warning": "#A66B05",
    "warning_subtle": "#FFF2D1",
    "danger": "#C14D5B",
    "danger_subtle": "#FAE7EA",
    "info": "#3476BF",
    "selected": "#E7E6F8",
    "progress_track": "#E4E6EE",

    "status_queued": ("#697083", "#EEF0F4"),
    "status_downloading": ("#2D70B7", "#E5F0FA"),
    "status_merging": ("#2D70B7", "#E5F0FA"),
    "status_validating": ("#7655B8", "#EEE8FA"),
    "status_ready_to_import": ("#946100", "#FFF0C7"),
    "status_waiting_eagle": ("#AA5B18", "#FDEBD9"),
    "status_imported": ("#247B5D", "#E4F4EC"),
    "status_completed_local": ("#187B72", "#DFF3F1"),
    "status_retry": ("#8D6800", "#FFF4CC"),
    "status_failed_permanent": ("#B84553", "#FAE7EA"),
    "status_import_failed": ("#B44160", "#F9E7ED"),
    "status_canceled": ("#737987", "#ECEEF2"),
    "status_needs_rebuild": ("#9952A5", "#F5E6F7"),

    "job_imported": ("#247B5D", "#E4F4EC"),
    "job_waiting": ("#946100", "#FFF0C7"),
    "job_active": ("#2D70B7", "#E5F0FA"),
    "job_failed": ("#B84553", "#FAE7EA"),
    "job_ignored": ("#697083", "#EEF0F4"),
}

THEMES = {
    "light": LIGHT_UI,
    "dark": DARK_UI,
}
DEFAULT_UI_THEME = "light"
UI = dict(THEMES[DEFAULT_UI_THEME])


def _set_ui_theme(theme: object) -> str:
    """Apply one complete palette in place so existing widgets can redraw."""

    normalized = str(theme or "").strip().lower()
    if normalized not in THEMES:
        normalized = DEFAULT_UI_THEME
    UI.clear()
    UI.update(THEMES[normalized])
    return normalized

METRICS = {
    "topbar_height": 44,
    "topbar_compact_height": 60,
    "sidebar_width": 208,
    "sidebar_compact_width": 176,
    "secondary_nav_width": 160,
    "secondary_nav_compact_width": 136,
    "master_width": 360,
    "master_compact_width": 300,
    "preview_max_width": 448,
    "button_height": 38,
    "task_row_height": 106,
    "wechat_row_height": 106,
    "table_row_height": 46,
}

RADII = {
    "thumbnail": 10,
    "badge": 12,
    "control": 14,
    "card": 18,
    "panel": 22,
}

FONT_FAMILIES = {
    "ui": "Microsoft YaHei UI",
    "medium": "Microsoft YaHei UI",
    "bold": "Microsoft YaHei UI",
    "latin": "Microsoft YaHei UI",
    "mono": "Microsoft YaHei UI",
}

LAYOUT_COMPACT = "compact"
LAYOUT_NORMAL = "normal"
LAYOUT_WIDE = "wide"
BASE_WINDOWS_DPI = 96
BASE_SCREEN_WIDTH = 1920
BASE_SCREEN_HEIGHT = 1080
CARD_PAGE_SIZE = 12
TREE_PAGE_SIZE = 80
UI_QUEUE_DRAIN_LIMIT = 64
PERFORMANCE_HEARTBEAT_MS = 100


def _ui_scale_from_dpi(dpi: object) -> float:
    """Convert a Windows monitor DPI to a bounded UI scale."""

    try:
        value = float(dpi)
    except (TypeError, ValueError):
        value = BASE_WINDOWS_DPI
    if not 48 <= value <= 480:
        value = BASE_WINDOWS_DPI
    return round(max(0.75, min(5.0, value / BASE_WINDOWS_DPI)), 3)


def _window_dpi(root: Tk) -> int:
    if sys.platform == "win32":
        try:
            dpi = int(ctypes.windll.user32.GetDpiForWindow(root.winfo_id()))
            if dpi > 0:
                return dpi
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    try:
        return max(1, round(float(root.winfo_fpixels("1i"))))
    except Exception:
        return BASE_WINDOWS_DPI


def _resolution_scale(width: object, height: object) -> float:
    """Keep the same physical UI footprint when Windows reports 96 DPI on 4K."""

    try:
        screen_width = int(width)
        screen_height = int(height)
    except (TypeError, ValueError):
        return 1.0
    if screen_width <= 0 or screen_height <= 0:
        return 1.0
    scale = min(
        screen_width / BASE_SCREEN_WIDTH,
        screen_height / BASE_SCREEN_HEIGHT,
    )
    return round(max(1.0, min(3.0, scale)), 3)


def _effective_ui_scale(dpi: object, width: object, height: object) -> float:
    """Combine the user's Windows scale with a resolution-density fallback."""

    return max(
        _ui_scale_from_dpi(dpi),
        _resolution_scale(width, height),
    )


def _scale_geometry(geometry: str, scale: float) -> str:
    """Scale only the size portion of a Tk geometry string."""

    match = re.fullmatch(
        r"\s*(\d+)x(\d+)(?:(?P<x>[+-]\d+)(?P<y>[+-]\d+))?\s*",
        str(geometry or ""),
    )
    if not match:
        return geometry
    width = max(1, round(int(match.group(1)) * scale))
    height = max(1, round(int(match.group(2)) * scale))
    position = f"{match.group('x')}{match.group('y')}" if match.group("x") else ""
    return f"{width}x{height}{position}"


def _scaled_metrics(scale: float) -> dict[str, int]:
    return {
        name: max(1, round(value * scale))
        for name, value in METRICS.items()
    }


def _widget_ui_scale(widget: object) -> float:
    try:
        scaling = float(widget.tk.call("tk", "scaling"))
    except Exception:
        return 1.0
    return max(0.75, min(5.0, scaling / (BASE_WINDOWS_DPI / 72)))


def _page_slice(
    items: list[object],
    page: int,
    page_size: int,
) -> tuple[list[object], int, int]:
    """Return one bounded projection page and its clamped page metadata."""

    size = max(1, int(page_size))
    total_pages = max(1, (len(items) + size - 1) // size)
    current = max(0, min(int(page), total_pages - 1))
    start = current * size
    return items[start : start + size], current, total_pages


def _enable_windows_dpi_awareness() -> bool:
    """Prevent Windows from bitmap-scaling Tk text on high-DPI displays."""

    if sys.platform != "win32":
        return False
    try:
        per_monitor_v2 = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            return True
    except (AttributeError, OSError):
        pass
    try:
        return ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except (AttributeError, OSError):
        try:
            return bool(ctypes.windll.user32.SetProcessDPIAware())
        except (AttributeError, OSError):
            return False


def _layout_mode_for_width(width: int) -> str:
    if width < 1024:
        return LAYOUT_COMPACT
    if width < 1280:
        return LAYOUT_NORMAL
    return LAYOUT_WIDE


def _ellipsize(value: object, max_characters: int) -> str:
    # Titles coming from page metadata may contain paragraphs and tabs. Every
    # call site for this helper is a compact, single-line projection, so fold
    # whitespace before applying the visible ellipsis.
    text = " ".join(str(value or "").split())
    if max_characters <= 1 or len(text) <= max_characters:
        return text
    return text[: max_characters - 1].rstrip() + "…"


def _pixel_ellipsize(value: object, maximum_width: int, measure) -> str:
    """Fit one-line text to a rendered pixel width and keep an explicit ellipsis."""

    text = " ".join(str(value or "").split())
    width = max(1, int(maximum_width))
    if not text or measure(text) <= width:
        return text
    ellipsis = "…"
    if measure(ellipsis) >= width:
        return ellipsis
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = text[:middle].rstrip() + ellipsis
        if measure(candidate) <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ellipsis


def _display_bytes(value: object) -> str:
    try:
        size = max(0.0, float(value or 0))
    except (TypeError, ValueError):
        size = 0.0
    if size <= 0:
        return "未知"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "未知"


def _relative_time_label(timestamp: float, now: float | None = None) -> str:
    if not timestamp:
        return "—"
    current = time.time() if now is None else now
    value = time.localtime(timestamp)
    today = time.localtime(current)
    value_day = (value.tm_year, value.tm_yday)
    today_day = (today.tm_year, today.tm_yday)
    clock = time.strftime("%H:%M", value)
    if value_day == today_day:
        return f"今天 {clock}"
    yesterday = time.localtime(current - 86400)
    if value_day == (yesterday.tm_year, yesterday.tm_yday):
        return f"昨天 {clock}"
    return time.strftime("%m-%d %H:%M", value)


def _fit_photo_image(
    image: PhotoImage,
    maximum_width: int,
    maximum_height: int,
) -> PhotoImage:
    """Scale a Tk image down with a small rational ratio instead of coarse halving."""

    width = max(1, int(image.width()))
    height = max(1, int(image.height()))
    scale = min(1.0, maximum_width / width, maximum_height / height)
    if scale >= 0.995:
        return image
    ratio = max(
        (
            Fraction(numerator, denominator)
            for denominator in range(1, 13)
            for numerator in range(1, denominator + 1)
            if numerator / denominator <= scale
        ),
        default=Fraction(1, 12),
    )
    return image.zoom(ratio.numerator, ratio.numerator).subsample(
        ratio.denominator,
        ratio.denominator,
    )


def _scale_photo_image(image: PhotoImage, scale: float) -> PhotoImage:
    if abs(scale - 1.0) < 0.01:
        return image
    ratio = Fraction(scale).limit_denominator(4)
    return image.zoom(ratio.numerator, ratio.numerator).subsample(
        ratio.denominator,
        ratio.denominator,
    )


def _eagle_experience(connected: bool) -> dict[str, object]:
    if connected:
        return {
            "status": "Eagle 已连接",
            "summary": "Eagle 已连接",
            "can_import": True,
            "import_button": "导入 Eagle",
            "idm_hint": "IDM 原文件始终保留；没有可靠来源时仍会导入，Eagle 网站字段保持为空。",
        }
    return {
        "status": "Eagle 未连接 · 下载可用",
        "summary": "Eagle 未连接（下载可用）",
        "can_import": False,
        "import_button": "Eagle 未连接",
        "idm_hint": "Eagle 未安装或未启动：IDM 原文件已经下载完成并会保留；启动 Eagle 后可重试导入，不影响浏览器和视频号仅下载。",
    }


def _bounded_retention_days(value: object, default: int = 7) -> int:
    try:
        return max(0, min(365, int(value)))
    except (TypeError, ValueError):
        return max(0, min(365, int(default)))


def _media_plan_view(plan: dict) -> dict:
    status = str(plan.get("status") or "")
    job_status = str(plan.get("job_status") or "")
    display_status = status
    if status == "ready_to_import" and job_status == "waiting_eagle":
        display_status = "waiting_eagle"
    elif status == "ready_to_import" and job_status == "failed_permanent":
        display_status = "import_failed"
    try:
        progress = max(0.0, min(100.0, float(plan.get("progress") or 0)))
    except (TypeError, ValueError):
        progress = 0.0
    if status in {"completed_local", "imported"}:
        progress = 100.0
    else:
        progress = min(progress, 99.0)
    final_path = str(plan.get("final_path") or "")
    page_url = str(plan.get("page_url") or "")
    return {
        "status": status,
        "status_label": MEDIA_STATUS_TEXT.get(display_status, display_status),
        "progress": progress,
        "processed": _display_bytes(plan.get("downloaded_bytes")),
        "total": _display_bytes(plan.get("total_bytes")),
        "active": status in MEDIA_ACTIVE_STATUSES,
        "can_retry": status in MEDIA_RETRYABLE_STATUSES,
        "can_open_output": bool(final_path),
        "can_open_source": bool(page_url),
        "can_import_existing": status == "completed_local"
        and bool(final_path),
    }


def _configure_styles(root: Tk, scale: float | None = None) -> None:
    ui_scale = (
        _effective_ui_scale(
            _window_dpi(root),
            root.winfo_screenwidth(),
            root.winfo_screenheight(),
        )
        if scale is None
        else scale
    )
    try:
        root.tk.call("tk", "scaling", ui_scale * BASE_WINDOWS_DPI / 72)
    except Exception:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    available_families = set(tkfont.families(root))
    ui_family = next(
        (
            family
            for family in (
                "Microsoft YaHei UI",
                "Microsoft YaHei",
                "Segoe UI",
                FONT_FAMILIES["ui"],
            )
            if family in available_families
        ),
        "TkDefaultFont",
    )
    medium_family = ui_family
    bold_family = ui_family
    FONT_FAMILIES["ui"] = ui_family
    FONT_FAMILIES["medium"] = medium_family
    FONT_FAMILIES["bold"] = bold_family
    FONT_FAMILIES["latin"] = ui_family
    FONT_FAMILIES["mono"] = ui_family
    # Positive sizes are typographic points. Negative Tk font sizes are fixed
    # device pixels and stay physically tiny on a 4K/200% monitor.
    root.option_add("*Font", (ui_family, 11))
    named_fonts = {
        "Ui10": (ui_family, 9, "normal"),
        "Ui11": (ui_family, 10, "normal"),
        "Ui11Bold": (medium_family, 10, "bold"),
        "Ui12": (ui_family, 11, "normal"),
        "Ui12Bold": (medium_family, 11, "bold"),
        "Ui13": (medium_family, 12, "normal"),
        "Ui13Bold": (bold_family, 12, "bold"),
        "Ui14Bold": (bold_family, 14, "bold"),
        "Mono10": (ui_family, 9, "normal"),
        "Mono11": (ui_family, 10, "normal"),
        "Mono24Bold": (bold_family, 22, "bold"),
    }
    persistent_fonts: dict[str, tkfont.Font] = {}
    for name, definition in named_fonts.items():
        try:
            font = tkfont.nametofont(name)
            font.configure(
                family=definition[0],
                size=definition[1],
                weight=definition[2] if len(definition) > 2 else "normal",
            )
        except Exception:
            font = tkfont.Font(
                root=root,
                name=name,
                family=definition[0],
                size=definition[1],
                weight=definition[2] if len(definition) > 2 else "normal",
            )
        persistent_fonts[name] = font
    root._ui_named_fonts = persistent_fonts  # type: ignore[attr-defined]
    default_font = "Ui12"
    style.configure(".", font=default_font, foreground=UI["text"])
    style.configure("App.TFrame", background=UI["bg"])
    style.configure("Topbar.TFrame", background=UI["bg"])
    style.configure("Sidebar.TFrame", background=UI["sidebar_bg"])
    style.configure("Surface.TFrame", background=UI["surface"])
    style.configure("SurfaceRaised.TFrame", background=UI["surface_raised"])
    style.configure("Soft.TFrame", background=UI["surface_raised"])
    style.configure("TaskCard.TFrame", background=UI["surface"])
    style.configure("TaskCardSelected.TFrame", background=UI["selected"])
    style.configure(
        "TaskCardTitle.TLabel",
        background=UI["surface"],
        foreground=UI["text_secondary"],
        font="Ui11Bold",
    )
    style.configure(
        "TaskCardTitleSelected.TLabel",
        background=UI["selected"],
        foreground=UI["text"],
        font="Ui11Bold",
    )
    style.configure(
        "TaskCardMeta.TLabel",
        background=UI["surface"],
        foreground=UI["text_muted"],
        font="Mono10",
    )
    style.configure(
        "TaskCardMetaSelected.TLabel",
        background=UI["selected"],
        foreground=UI["text_muted"],
        font="Mono10",
    )
    for state_name, (foreground, background) in (
        (name, colors)
        for name, colors in UI.items()
        if name.startswith("status_") and isinstance(colors, tuple)
    ):
        style.configure(
            f"{state_name}.TLabel",
            background=background,
            foreground=foreground,
            font="Mono10",
            padding=(6, 2),
        )
    style.configure("App.TLabel", background=UI["bg"], foreground=UI["text"])
    style.configure("Topbar.TLabel", background=UI["bg"], foreground=UI["text"])
    style.configure(
        "TopbarBrand.TLabel",
        background=UI["bg"],
        foreground=UI["text"],
        font="Ui13Bold",
    )
    style.configure(
        "TopbarVersion.TLabel",
        background=UI["bg"],
        foreground=UI["text_muted"],
        font="Mono10",
    )
    style.configure(
        "TopbarStatus.TLabel",
        background=UI["bg"],
        foreground=UI["text_secondary"],
        font="Ui11",
    )
    style.configure("Sidebar.TLabel", background=UI["sidebar_bg"], foreground=UI["text"])
    style.configure("SidebarMuted.TLabel", background=UI["sidebar_bg"], foreground=UI["text_muted"])
    style.configure("Surface.TLabel", background=UI["surface"], foreground=UI["text"])
    style.configure("SurfaceRaised.TLabel", background=UI["surface_raised"], foreground=UI["text"])
    style.configure("Raised.TLabel", background=UI["surface_raised"], foreground=UI["text"])
    style.configure("Soft.TLabel", background=UI["surface_overlay"], foreground=UI["text_muted"])
    style.configure("Muted.TLabel", background=UI["surface"], foreground=UI["text_muted"])
    style.configure(
        "Title.TLabel",
        background=UI["surface"],
        foreground=UI["text"],
        font="Ui14Bold",
    )
    style.configure(
        "Section.TLabel",
        background=UI["surface_raised"],
        foreground=UI["text"],
        font="Ui13Bold",
    )
    style.configure(
        "SectionOnSurface.TLabel",
        background=UI["surface"],
        foreground=UI["text"],
        font="Ui13Bold",
    )
    style.configure(
        "MediaToolbarTitle.TLabel",
        background=UI["surface"],
        foreground=UI["text"],
        font="Ui11Bold",
    )
    style.configure(
        "Body.TLabel",
        background=UI["surface"],
        foreground=UI["text_secondary"],
        font="Ui12",
    )
    style.configure(
        "MonoMuted.TLabel",
        background=UI["surface"],
        foreground=UI["text_muted"],
        font="Mono11",
    )
    style.configure(
        "RaisedMuted.TLabel",
        background=UI["surface_raised"],
        foreground=UI["text_muted"],
        font="Ui10",
    )
    style.configure(
        "DetailValue.TLabel",
        background=UI["surface_raised"],
        foreground=UI["text_secondary"],
        font="Ui11Bold",
    )
    style.configure(
        "DetailPrimaryValue.TLabel",
        background=UI["surface_raised"],
        foreground=UI["text"],
        font="Ui12Bold",
    )
    style.configure(
        "Success.TLabel",
        background=UI["surface"],
        foreground=UI["success"],
        font="Ui11",
    )
    style.configure(
        "Warning.TLabel",
        background=UI["warning_subtle"],
        foreground=UI["warning"],
        font="Ui11",
    )
    style.configure(
        "Error.TLabel",
        background=UI["danger_subtle"],
        foreground=UI["danger"],
        font="Ui11",
    )
    style.configure(
        "Nav.TButton",
        anchor="w",
        padding=(12, 8),
        background=UI["sidebar_bg"],
        foreground=UI["text_secondary"],
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["accent"],
        font="Ui13",
    )
    style.map(
        "Nav.TButton",
        background=[("active", UI["surface_overlay"]), ("pressed", UI["surface_overlay"])],
        foreground=[("disabled", UI["text_disabled"])],
    )
    style.configure(
        "NavSelected.TButton",
        anchor="w",
        padding=(12, 8),
        background=UI["selected"],
        foreground=UI["accent_text"],
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["accent"],
        font="Ui13Bold",
    )
    style.map(
        "NavSelected.TButton",
        background=[("active", UI["selected"]), ("pressed", UI["selected"])],
    )
    style.configure(
        "Accent.TButton",
        padding=(14, 7),
        background=UI["accent_button"],
        foreground="#FFFFFF",
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["accent_text"],
        relief="flat",
        font="Ui12",
    )
    style.map(
        "Accent.TButton",
        foreground=[("disabled", UI["text_disabled"])],
        background=[
            ("disabled", UI["border"]),
            ("active", UI["accent_hover"]),
            ("pressed", UI["accent_hover"]),
        ],
    )
    style.configure(
        "Danger.TButton",
        padding=(14, 7),
        background=UI["danger_subtle"],
        foreground=UI["danger"],
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["danger"],
        relief="flat",
        font="Ui12",
    )
    style.map(
        "Danger.TButton",
        foreground=[("disabled", UI["text_disabled"])],
        background=[("active", "#3F1A1A"), ("pressed", "#3F1A1A")],
    )
    style.configure(
        "Quiet.TButton",
        padding=(12, 7),
        background=UI["surface_overlay"],
        foreground=UI["text_secondary"],
        bordercolor=UI["border"],
        borderwidth=1,
        focusthickness=1,
        focuscolor=UI["accent"],
        relief="flat",
        font="Ui12",
    )
    style.map(
        "Quiet.TButton",
        background=[("active", UI["surface_raised"]), ("pressed", UI["surface_raised"])],
        foreground=[("disabled", UI["text_disabled"])],
    )
    style.configure(
        "Secondary.TButton",
        padding=(12, 7),
        background=UI["surface_raised"],
        foreground=UI["text_secondary"],
        bordercolor=UI["border"],
        borderwidth=1,
        focusthickness=1,
        focuscolor=UI["accent"],
        relief="flat",
        font="Ui12",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", UI["surface_overlay"]), ("pressed", UI["surface_overlay"])],
        foreground=[("disabled", UI["text_disabled"])],
    )
    style.configure(
        "Link.TButton",
        padding=(4, 4),
        background=UI["surface"],
        foreground=UI["text_muted"],
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["accent"],
        font="Ui11",
    )
    style.configure(
        "MediaToolbar.TButton",
        padding=(5, 3),
        background=UI["surface"],
        foreground=UI["text_muted"],
        borderwidth=0,
        focusthickness=1,
        focuscolor=UI["accent"],
        font="Ui10",
    )
    style.map(
        "MediaToolbar.TButton",
        background=[("active", UI["surface_overlay"])],
        foreground=[("active", UI["text_secondary"]), ("disabled", UI["text_disabled"])],
    )
    style.map(
        "Link.TButton",
        background=[("active", UI["surface_overlay"])],
        foreground=[("active", UI["text"]), ("disabled", UI["text_disabled"])],
    )
    style.configure(
        "Card.TLabelframe",
        background=UI["surface_raised"],
        bordercolor=UI["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=UI["surface_raised"],
        foreground=UI["text"],
        font="Ui11Bold",
    )
    style.configure(
        "Treeview",
        background=UI["surface"],
        fieldbackground=UI["surface"],
        foreground=UI["text"],
        bordercolor=UI["border"],
        borderwidth=1,
        relief="flat",
        rowheight=max(1, round(METRICS["table_row_height"] * ui_scale)),
        font="Ui12",
    )
    style.map(
        "Treeview",
        background=[("selected", UI["selected"])],
        foreground=[("selected", UI["text"])],
    )
    style.configure(
        "Treeview.Heading",
        background=UI["sidebar_bg"],
        foreground=UI["text_muted"],
        padding=(8, 7),
        borderwidth=0,
        relief="flat",
        font="Ui11",
    )
    # ── multi-colour progress bars ──
    for name, color in (
        ("Progress.Indigo", UI["accent"]),
        ("Progress.Emerald", UI["success"]),
        ("Progress.Orange", UI["status_waiting_eagle"][0]),
    ):
        style.configure(
            f"{name}.Horizontal.TProgressbar",
            troughcolor=UI["progress_track"],
            background=color,
            bordercolor=UI["progress_track"],
            lightcolor=color,
            darkcolor=color,
        )
    # ── Radiobutton ──
    style.configure("TRadiobutton", background=UI["surface"], foreground=UI["text"])
    style.map("TRadiobutton", foreground=[("disabled", UI["text_disabled"])])
    # ── Entry ──
    style.configure("TEntry", fieldbackground=UI["surface_raised"], foreground=UI["text"])
    style.map("TEntry", fieldbackground=[("disabled", UI["surface"])], foreground=[("disabled", UI["text_disabled"])])
    # ── Spinbox ──
    # The Windows-native fallback is bright white under the dark theme. Keep
    # number fields visually aligned with the rest of the settings controls.
    style.configure(
        "Settings.TSpinbox",
        padding=(8, 5),
        fieldbackground=UI["surface_overlay"],
        background=UI["surface_overlay"],
        foreground=UI["text"],
        arrowcolor=UI["text_secondary"],
        bordercolor=UI["border"],
        lightcolor=UI["surface_overlay"],
        darkcolor=UI["surface_overlay"],
        borderwidth=1,
        relief="flat",
        arrowsize=max(10, round(11 * ui_scale)),
    )
    style.map(
        "Settings.TSpinbox",
        fieldbackground=[
            ("disabled", UI["surface"]),
            ("focus", UI["surface_overlay"]),
        ],
        background=[
            ("active", UI["selected"]),
            ("pressed", UI["selected"]),
        ],
        foreground=[("disabled", UI["text_disabled"])],
        arrowcolor=[
            ("active", UI["accent_text"]),
            ("disabled", UI["text_disabled"]),
        ],
        bordercolor=[("focus", UI["accent"])],
    )
    # ── Combobox ──
    style.configure("TCombobox", fieldbackground=UI["surface_raised"], foreground=UI["text"], arrowcolor=UI["text_secondary"])
    style.map("TCombobox", fieldbackground=[("readonly", UI["surface_raised"])], foreground=[("disabled", UI["text_disabled"])])
    # ── Scrollbar ──
    style.configure(
        "TScrollbar",
        background=UI["surface_overlay"],
        troughcolor=UI["bg"],
        bordercolor=UI["bg"],
        arrowcolor=UI["text_muted"],
        lightcolor=UI["surface_overlay"],
        darkcolor=UI["surface_overlay"],
        relief="flat",
        borderwidth=0,
        arrowsize=10,
        width=11,
    )
    style.map(
        "TScrollbar",
        background=[
            ("active", UI["border"]),
            ("pressed", UI["border"]),
        ],
        arrowcolor=[("active", UI["text_secondary"])],
    )
    for orientation in ("Vertical", "Horizontal"):
        style.configure(
            f"{orientation}.TScrollbar",
            background=UI["surface_overlay"],
            troughcolor=UI["bg"],
            bordercolor=UI["bg"],
            arrowcolor=UI["text_muted"],
            lightcolor=UI["surface_overlay"],
            darkcolor=UI["surface_overlay"],
            relief="flat",
            borderwidth=0,
            arrowsize=10,
            width=11,
        )
    style.configure(
        "TPanedwindow",
        background=UI["divider"],
        sashwidth=4,
        sashrelief="flat",
    )
    style.configure(
        "Sash",
        background=UI["divider"],
        sashthickness=4,
        sashrelief="flat",
    )
    # ── TLabelframe ──
    style.configure("TLabelframe", background=UI["surface_raised"], bordercolor=UI["border"])
    style.configure("TLabelframe.Label", background=UI["surface_raised"], foreground=UI["text"])
    # ── Combobox dropdown overrides ──
    root.option_add("*TCombobox*Listbox.background", UI["surface_raised"])
    root.option_add("*TCombobox*Listbox.foreground", UI["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", UI["selected"])
    root.option_add("*TCombobox*Listbox.selectForeground", UI["accent_text"])


class _AsyncProbe:
    """Run a slow health probe without blocking Tk's event loop."""

    def __init__(self, probe, *, name: str) -> None:
        self._probe = probe
        self._name = name
        self._results: Queue[object] = Queue()
        self._lock = threading.Lock()
        self._running = False

    def request(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(
            target=self._run,
            name=self._name,
            daemon=True,
        ).start()
        return True

    def _run(self) -> None:
        try:
            result = self._probe()
        except Exception:
            result = False
        self._results.put(result)
        with self._lock:
            self._running = False

    def poll(self) -> tuple[bool, object | None]:
        available = False
        latest = None
        while True:
            try:
                latest = self._results.get_nowait()
                available = True
            except Empty:
                return available, latest


def _resolve_eagle_probe(api: object, fallback) -> object:
    """Use the shared capability when present, with old/fake API compatibility."""

    probe = getattr(api, "eagle_available", None)
    return probe if callable(probe) else fallback


class _PreviewImageCache:
    """Decode a preview only when its path or file identity changes."""

    def __init__(self, image_factory=PhotoImage) -> None:
        self._image_factory = image_factory
        self._signature: tuple[str, int, int] | None = None
        self._image: object | None = None

    def clear(self) -> None:
        self._signature = None
        self._image = None

    def resolve(self, path: Path) -> object | None:
        try:
            stat = path.stat()
            if not path.is_file():
                raise FileNotFoundError(path)
            signature = (str(path), int(stat.st_size), int(stat.st_mtime_ns))
        except OSError:
            self.clear()
            return None
        if signature == self._signature:
            return self._image
        try:
            image = self._image_factory(file=str(path))
        except Exception:
            image = None
        self._signature = signature
        self._image = image
        return image


def _sync_tree_rows(tree: object, rows: list[tuple[str, tuple[object, ...]]]) -> None:
    """Incrementally project rows into a Treeview-like interface."""
    desired_ids = [iid for iid, _values in rows]
    desired_set = set(desired_ids)
    existing_ids = list(tree.get_children())
    stale_ids = [iid for iid in existing_ids if iid not in desired_set]
    if stale_ids:
        tree.delete(*stale_ids)

    for iid, values in rows:
        values = tuple(values)
        if not tree.exists(iid):
            tree.insert("", END, iid=iid, values=values)
        elif tuple(tree.item(iid, "values")) != values:
            tree.item(iid, values=values)

    current_order = list(tree.get_children())
    for index, iid in enumerate(desired_ids):
        if current_order[index] == iid:
            continue
        tree.move(iid, "", index)
        current_order.remove(iid)
        current_order.insert(index, iid)


def _set_var_if_changed(variable: object, value: object) -> bool:
    """Avoid triggering Tk traces and relayout when text did not change."""

    text = str(value)
    try:
        if str(variable.get()) == text:
            return False
    except Exception:
        pass
    variable.set(text)
    return True


def _configure_if_changed(widget: object, **options: object) -> bool:
    """Configure only options whose rendered value actually changed."""

    changed: dict[str, object] = {}
    for name, value in options.items():
        try:
            current = widget.cget(name)
        except Exception:
            changed[name] = value
            continue
        if str(current) != str(value):
            changed[name] = value
    if not changed:
        return False
    widget.configure(**changed)
    return True


def _path_render_revision(value: object) -> tuple[str, int, int]:
    path = Path(str(value or ""))
    if not str(value or ""):
        return "", 0, 0
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return str(path), 0, 0


class _DynamicWrapLabel(ttk.Label):
    """A label whose wrap length follows its actual rendered width."""

    def __init__(
        self,
        parent: object,
        *,
        horizontal_padding: int = 0,
        maximum: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._horizontal_padding = max(0, horizontal_padding)
        self._maximum = maximum
        self._wrap_after_id: str | None = None
        self._last_wrap = -1
        self.bind("<Configure>", self._queue_wrap_update, add="+")

    def _queue_wrap_update(self, _event: object | None = None) -> None:
        if self._wrap_after_id is not None:
            return
        self._wrap_after_id = self.after_idle(self._update_wrap)

    def _update_wrap(self, event: object | None = None) -> None:
        self._wrap_after_id = None
        width = int(getattr(event, "width", 0) or self.winfo_width() or 1)
        wrap = max(80, width - self._horizontal_padding)
        if self._maximum is not None:
            wrap = min(wrap, self._maximum)
        if wrap == self._last_wrap:
            return
        self._last_wrap = wrap
        self.configure(wraplength=wrap)


class _ResponsiveActionGroup(ttk.Frame):
    """Reflow important actions without hiding or recreating them."""

    def __init__(
        self,
        parent: object,
        *,
        compact_breakpoint: int = 430,
        vertical_breakpoint: int = 300,
        wide_breakpoint: int = 680,
        style: str = "SurfaceRaised.TFrame",
    ) -> None:
        super().__init__(parent, style=style)
        self._buttons: list[ttk.Button] = []
        self._compact_breakpoint = compact_breakpoint
        self._vertical_breakpoint = vertical_breakpoint
        self._wide_breakpoint = max(compact_breakpoint, wide_breakpoint)
        self._pending_after: str | None = None
        self._last_columns = 0
        self.bind("<Configure>", self._queue_layout, add="+")

    def add(self, button: ttk.Button) -> ttk.Button:
        self._buttons.append(button)
        self._queue_layout()
        return button

    def _queue_layout(self, _event: object | None = None) -> None:
        if self._pending_after is not None:
            return
        self._pending_after = self.after_idle(self._apply_layout)

    def _apply_layout(self) -> None:
        self._pending_after = None
        width = max(1, self.winfo_width())
        if width < self._vertical_breakpoint:
            columns = 1
        elif width < self._compact_breakpoint:
            columns = 2
        elif width < self._wide_breakpoint and len(self._buttons) > 3:
            columns = 3
        else:
            columns = max(1, len(self._buttons))
        if columns == self._last_columns:
            return
        for button in self._buttons:
            button.grid_forget()
        for column in range(max(self._last_columns, len(self._buttons), columns)):
            self.columnconfigure(column, weight=0, uniform="")
        for column in range(max(1, columns)):
            self.columnconfigure(column, weight=1, uniform="actions")
        for index, button in enumerate(self._buttons):
            row, column = divmod(index, columns)
            button.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 4, 4 if column < columns - 1 else 0),
                pady=(0 if row == 0 else 4, 0),
            )
        self._last_columns = columns


class _ResponsiveTreeColumns:
    """Allocate Treeview columns from available width and stable minimums."""

    def __init__(
        self,
        tree: ttk.Treeview,
        specifications: list[tuple[str, int, int]],
        *,
        compact_minimums: dict[str, int] | None = None,
        reserved_width: int = 18,
    ) -> None:
        self.tree = tree
        self.specifications = specifications
        self.compact_minimums = compact_minimums or {}
        self.reserved_width = reserved_width
        self._pending_after: str | None = None
        self._last_available = -1
        self._last_widths: dict[str, int] = {}
        tree.bind("<Configure>", self._queue_resize, add="+")
        self._queue_resize()

    def _queue_resize(self, _event: object | None = None) -> None:
        if self._pending_after is not None:
            return
        self._pending_after = self.tree.after_idle(self._resize)

    def _resize(self) -> None:
        self._pending_after = None
        available = max(1, self.tree.winfo_width() - self.reserved_width)
        if available == self._last_available:
            return
        self._last_available = available
        preferred_minimums = {
            name: max(24, minimum)
            for name, minimum, _weight in self.specifications
        }
        minimum_total = sum(preferred_minimums.values())
        if available < minimum_total:
            preferred_minimums.update(
                {
                    name: max(24, self.compact_minimums.get(name, minimum))
                    for name, minimum, _weight in self.specifications
                }
            )
        minimum_total = sum(preferred_minimums.values())
        extra = max(0, available - minimum_total)
        total_weight = max(
            1,
            sum(max(0, weight) for _name, _minimum, weight in self.specifications),
        )
        allocated = 0
        for index, (name, _minimum, weight) in enumerate(self.specifications):
            if index == len(self.specifications) - 1:
                width = max(24, available - allocated)
            else:
                width = preferred_minimums[name] + int(extra * max(0, weight) / total_weight)
                allocated += width
            if self._last_widths.get(name) != width:
                self.tree.column(name, width=width, minwidth=24, stretch=False)
                self._last_widths[name] = width


class _Tooltip:
    """Keyboard- and pointer-accessible complete text viewer."""

    def __init__(self, widget: object, text_getter) -> None:
        self.widget = widget
        self.text_getter = text_getter
        self.window: Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._queue_show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<FocusIn>", self._queue_show, add="+")
        widget.bind("<FocusOut>", self.hide, add="+")

    def _queue_show(self, _event: object | None = None) -> None:
        self.hide()
        self._after_id = self.widget.after(450, self.show)

    def show(self) -> None:
        self._after_id = None
        text = str(self.text_getter() or "")
        if not text:
            return
        window = Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(background=UI["border"])
        label = ttk.Label(
            window,
            text=text,
            style="SurfaceRaised.TLabel",
            justify=LEFT,
            wraplength=420,
            padding=(10, 8),
        )
        label.pack()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        self.window = window

    def hide(self, _event: object | None = None) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None


class _StatusIndicator(Canvas):
    """A compact antialiased status circle with live theme colours."""

    def __init__(
        self,
        parent: object,
        *,
        color: str | None = None,
        background: str | None = None,
        size: int = 8,
    ) -> None:
        resolved_color = color or UI["text_muted"]
        resolved_background = background or UI["bg"]
        super().__init__(
            parent,
            width=size,
            height=size,
            background=resolved_background,
            highlightthickness=0,
            borderwidth=0,
        )
        self._size = size
        self._color = resolved_color
        self._background = resolved_background
        self._dot = 0
        self._dot_image: PhotoImage | None = None
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    def set_color(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self._last_draw_signature = None
        self._queue_draw()

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is None:
            self._draw_after_id = self.after_idle(self._draw)

    def _draw(self) -> None:
        self._draw_after_id = None
        signature = (self._size, self._color, self._background)
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        self._dot_image = _circle_photo_image(
            self,
            diameter=self._size,
            fill=self._color,
            outer_background=self._background,
        )
        self._dot = self.create_image(0, 0, image=self._dot_image, anchor="nw")

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


def _rgb8(widget: object, color: str) -> tuple[int, int, int]:
    red, green, blue = widget.winfo_rgb(color)
    return red // 257, green // 257, blue // 257


_CIRCLE_COVERAGE_CACHE: dict[tuple[int, int], tuple[int, ...]] = {}
_CORNER_COVERAGE_CACHE: dict[
    tuple[int, int, int],
    tuple[tuple[int, int, int], ...],
] = {}


def _circle_coverage(diameter: int, samples: int) -> tuple[int, ...]:
    key = (diameter, samples)
    cached = _CIRCLE_COVERAGE_CACHE.get(key)
    if cached is not None:
        return cached
    radius = diameter / 2
    limit = radius * radius
    coverage: list[int] = []
    for y in range(diameter):
        for x in range(diameter):
            fill_samples = 0
            for sample_y in range(samples):
                delta_y = y + (sample_y + 0.5) / samples - radius
                for sample_x in range(samples):
                    delta_x = x + (sample_x + 0.5) / samples - radius
                    if delta_x * delta_x + delta_y * delta_y <= limit:
                        fill_samples += 1
            coverage.append(fill_samples)
    result = tuple(coverage)
    _CIRCLE_COVERAGE_CACHE[key] = result
    return result


def _antialiased_circle_pixels(
    diameter: int,
    *,
    fill: tuple[int, int, int],
    outer_background: tuple[int, int, int],
    samples: int = 8,
) -> bytes:
    """Render one exact circle with sub-pixel edge coverage."""

    diameter = max(1, int(diameter))
    samples = max(2, int(samples))
    sample_count = samples * samples
    pixels = bytearray()
    for fill_samples in _circle_coverage(diameter, samples):
        for fill_channel, background_channel in zip(fill, outer_background):
            blended = (
                fill_channel * fill_samples
                + background_channel * (sample_count - fill_samples)
            ) / sample_count
            pixels.append(round(blended))
    return bytes(pixels)


def _circle_photo_image(
    canvas: Canvas,
    *,
    diameter: int,
    fill: str,
    outer_background: str,
) -> PhotoImage:
    """Return one cached antialiased circle for the active Tk interpreter."""

    fill_rgb = _rgb8(canvas, fill)
    background_rgb = _rgb8(canvas, outer_background)
    key = (int(diameter), fill_rgb, background_rgb)
    owner = canvas.winfo_toplevel()
    cache = getattr(owner, "_antialiased_circle_cache", None)
    if cache is None:
        cache = {}
        setattr(owner, "_antialiased_circle_cache", cache)
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = _antialiased_circle_pixels(
        diameter,
        fill=fill_rgb,
        outer_background=background_rgb,
    )
    header = f"P6\n{diameter} {diameter}\n255\n".encode("ascii")
    image = PhotoImage(
        master=canvas,
        data=header + payload,
        format="PPM",
    )
    cache[key] = image
    return image


def _antialiased_corner_pixels(
    radius: int,
    *,
    fill: tuple[int, int, int],
    border: tuple[int, int, int],
    outer_background: tuple[int, int, int],
    border_width: int,
    samples: int = 8,
) -> bytes:
    """Render one top-left rounded corner with real sub-pixel coverage.

    Tk 8.6 Canvas curves are flattened to non-antialiased line segments on
    Windows.  Sampling each output pixel on a fine grid and averaging the
    colours gives the edge coverage Tk's legacy renderer does not provide.
    """

    radius = max(1, int(radius))
    samples = max(2, int(samples))
    border_width = max(0, min(int(border_width), radius))
    sample_count = samples * samples
    pixels = bytearray()
    coverage_key = (radius, border_width, samples)
    coverage = _CORNER_COVERAGE_CACHE.get(coverage_key)
    if coverage is None:
        inner_radius = max(0, radius - border_width)
        outer_limit = radius * radius
        inner_limit = inner_radius * inner_radius
        coverage_rows: list[tuple[int, int, int]] = []
        for y in range(radius):
            for x in range(radius):
                fill_samples = 0
                border_samples = 0
                outer_samples = 0
                for sample_y in range(samples):
                    point_y = y + (sample_y + 0.5) / samples
                    delta_y = radius - point_y
                    for sample_x in range(samples):
                        point_x = x + (sample_x + 0.5) / samples
                        delta_x = radius - point_x
                        distance_squared = delta_x * delta_x + delta_y * delta_y
                        if distance_squared > outer_limit:
                            outer_samples += 1
                        elif border_width and distance_squared > inner_limit:
                            border_samples += 1
                        else:
                            fill_samples += 1
                coverage_rows.append(
                    (fill_samples, border_samples, outer_samples)
                )
        coverage = tuple(coverage_rows)
        _CORNER_COVERAGE_CACHE[coverage_key] = coverage
    for fill_samples, border_samples, outer_samples in coverage:
        for fill_channel, border_channel, outer_channel in zip(
            fill,
            border,
            outer_background,
        ):
            total = (
                fill_channel * fill_samples
                + border_channel * border_samples
                + outer_channel * outer_samples
            )
            pixels.append(round(total / sample_count))
    return bytes(pixels)


def _corner_photo_images(
    canvas: Canvas,
    *,
    radius: int,
    fill: str,
    border: str,
    border_width: int,
    outer_background: str,
) -> tuple[PhotoImage, PhotoImage, PhotoImage, PhotoImage]:
    """Return cached antialiased corner images for one Tk interpreter."""

    fill_rgb = _rgb8(canvas, fill)
    background_rgb = _rgb8(canvas, outer_background)
    effective_border_width = border_width if border else 0
    border_rgb = _rgb8(canvas, border) if border else fill_rgb
    key = (
        int(radius),
        fill_rgb,
        border_rgb,
        int(effective_border_width),
        background_rgb,
    )
    owner = canvas.winfo_toplevel()
    cache = getattr(owner, "_antialiased_corner_cache", None)
    if cache is None:
        cache = {}
        setattr(owner, "_antialiased_corner_cache", cache)
    cached = cache.get(key)
    if cached is not None:
        return cached

    top_left = _antialiased_corner_pixels(
        radius,
        fill=fill_rgb,
        border=border_rgb,
        outer_background=background_rgb,
        border_width=effective_border_width,
    )
    row_stride = radius * 3
    rows = tuple(
        top_left[offset : offset + row_stride]
        for offset in range(0, len(top_left), row_stride)
    )

    def reverse_row(row: bytes) -> bytes:
        return b"".join(
            row[offset : offset + 3]
            for offset in range(row_stride - 3, -1, -3)
        )

    horizontal_rows = tuple(reverse_row(row) for row in rows)
    payloads = (
        b"".join(rows),
        b"".join(horizontal_rows),
        b"".join(reversed(horizontal_rows)),
        b"".join(reversed(rows)),
    )
    header = f"P6\n{radius} {radius}\n255\n".encode("ascii")
    images: list[PhotoImage] = []
    for payload in payloads:
        images.append(
            PhotoImage(
                master=canvas,
                data=header + payload,
                format="PPM",
            )
        )
    result = tuple(images)
    cache[key] = result
    return result


def _draw_antialiased_rounded_rect(
    canvas: Canvas,
    left: int,
    top: int,
    right: int,
    bottom: int,
    radius: int,
    *,
    fill: str,
    border: str = "",
    border_width: int = 0,
    outer_background: str,
    tags: tuple[str, ...] | str = (),
) -> tuple[int, ...]:
    """Draw a rounded rectangle whose four curved edges are antialiased."""

    width = right - left
    height = bottom - top
    if width < 2 or height < 2:
        return (
            canvas.create_rectangle(
                left,
                top,
                max(left + 1, right),
                max(top + 1, bottom),
                fill=fill,
                outline=border,
                width=border_width if border else 0,
                tags=tags,
            ),
        )
    radius = max(1, min(int(radius), width // 2, height // 2))
    effective_border_width = max(0, min(border_width if border else 0, radius))
    items: list[int] = []
    items.append(
        canvas.create_rectangle(
            left + radius,
            top,
            right - radius,
            bottom,
            fill=fill,
            outline="",
            tags=tags,
        )
    )
    items.append(
        canvas.create_rectangle(
            left,
            top + radius,
            right,
            bottom - radius,
            fill=fill,
            outline="",
            tags=tags,
        )
    )
    if effective_border_width:
        edge_rectangles = (
            (left + radius, top, right - radius, top + effective_border_width),
            (
                left + radius,
                bottom - effective_border_width,
                right - radius,
                bottom,
            ),
            (left, top + radius, left + effective_border_width, bottom - radius),
            (
                right - effective_border_width,
                top + radius,
                right,
                bottom - radius,
            ),
        )
        for x1, y1, x2, y2 in edge_rectangles:
            items.append(
                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=border,
                    outline="",
                    tags=tags,
                )
            )
    corner_images = _corner_photo_images(
        canvas,
        radius=radius,
        fill=fill,
        border=border,
        border_width=effective_border_width,
        outer_background=outer_background,
    )
    positions = (
        (left, top),
        (right - radius, top),
        (right - radius, bottom - radius),
        (left, bottom - radius),
    )
    for image, (x, y) in zip(corner_images, positions):
        items.append(
            canvas.create_image(x, y, image=image, anchor="nw", tags=tags)
        )
    return tuple(items)


def _rounded_content_inset(radius: int, requested: int, border_width: int) -> int:
    """Keep a rectangular child window clear of an antialiased round corner."""

    radius = max(1, int(radius))
    edge_width = max(1, int(border_width))
    inner_radius = max(0, radius - edge_width)
    geometric_inset = math.ceil(radius - inner_radius / math.sqrt(2)) + 1
    return max(2, int(requested), geometric_inset)


class _RoundedPanel(Canvas):
    """Canvas-backed rounded surface with a regular Tk content frame."""

    def __init__(
        self,
        parent: object,
        *,
        fill: str,
        outer_background: str,
        style: str,
        radius: int = RADII["control"],
        border: str = "",
        border_width: int = 0,
        width: int = 1,
        height: int = 1,
        inset: int = 4,
        takefocus: bool = False,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
            takefocus=takefocus,
        )
        self._fill = fill
        self._border = border
        self._border_width = border_width
        self._focusable = bool(takefocus)
        self._last_focus_border = ""
        self._radius = radius
        self._inset = _rounded_content_inset(radius, inset, border_width)
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self.inner = ttk.Frame(self, style=style)
        self._inner_window = self.create_window(
            (self._inset, self._inset),
            window=self.inner,
            anchor="nw",
        )
        self._surface = 0
        self.bind("<Configure>", self._queue_redraw, add="+")
        if self._focusable:
            self.bind("<FocusIn>", self._queue_redraw, add="+")
            self.bind("<FocusOut>", self._queue_redraw, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_redraw()

    def set_surface(
        self,
        *,
        fill: str,
        style: str,
        border: str | None = None,
    ) -> None:
        changed = (
            fill != self._fill
            or (border is not None and border != self._border)
            or str(self.inner.cget("style")) != style
        )
        self._fill = fill
        if border is not None:
            self._border = border
        if str(self.inner.cget("style")) != style:
            self.inner.configure(style=style)
        if changed:
            self._last_draw_signature = None
            self._queue_redraw()

    def _queue_redraw(self, _event: object | None = None) -> None:
        if self._draw_after_id is not None:
            return
        self._draw_after_id = self.after_idle(self._redraw)

    def _redraw(self, _event: object | None = None) -> None:
        self._draw_after_id = None
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        focused = self._focusable and self.focus_get() is self
        focus_border = UI["accent"] if focused else self._border
        focus_border_width = max(1, self._border_width) if focused else self._border_width
        self._last_focus_border = focus_border
        signature = (
            width,
            height,
            self._fill,
            self._border,
            self._border_width,
            self._radius,
            self._inset,
            focused,
        )
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("surface")
        surface_items = _draw_antialiased_rounded_rect(
            self,
            1,
            1,
            width - 1,
            height - 1,
            self._radius,
            fill=self._fill,
            border=focus_border,
            border_width=focus_border_width,
            outer_background=str(self.cget("background")),
            tags=("surface",),
        )
        self._surface = surface_items[0]
        self.tag_lower("surface")
        self.coords(self._inner_window, self._inset, self._inset)
        self.itemconfigure(
            self._inner_window,
            width=max(1, width - self._inset * 2),
            height=max(1, height - self._inset * 2),
        )

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


class _RoundedButton(Canvas):
    """Accessible rounded action button with the subset of ttk.Button we use."""

    def __init__(
        self,
        parent: object,
        *,
        text: str = "",
        command=None,
        image: PhotoImage | None = None,
        compound: object = LEFT,
        style: str = "Quiet.TButton",
        state: str = "normal",
        textvariable: object | None = None,
        kind: str | None = None,
        width: int = 88,
    ) -> None:
        ui_scale = _widget_ui_scale(parent)
        resolved_kind = kind or self._kind_from_style(style)
        self._font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=10,
            weight="bold" if resolved_kind in {"accent", "danger", "nav_selected"} else "normal",
        )
        resolved_text = str(textvariable.get()) if textvariable is not None else text
        content_width = self._font.measure(resolved_text)
        if image is not None:
            content_width += image.width() + round(6 * ui_scale)
        requested_width = (
            round(max(32, width * 14) * ui_scale)
            if width <= 4
            else round(width * ui_scale)
        )
        super().__init__(
            parent,
            width=max(
                requested_width,
                content_width + round(24 * ui_scale),
            ),
            height=max(1, round(METRICS["button_height"] * ui_scale)),
            background=self._parent_background(parent),
            borderwidth=0,
            highlightthickness=0,
            takefocus=str(state) != "disabled",
            cursor="hand2" if str(state) != "disabled" else "arrow",
        )
        self._text = resolved_text
        self._command = command or (lambda: None)
        self._image = image
        self._compound = compound
        self._style_name = style
        self._kind = resolved_kind
        self._enabled = str(state) != "disabled"
        self._textvariable = textvariable
        self._text_trace_id: str | None = None
        self._hovered = False
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        if textvariable is not None:
            try:
                self._text_trace_id = textvariable.trace_add(
                    "write",
                    self._sync_textvariable,
                )
            except Exception:
                self._text_trace_id = None
        self.bind("<Configure>", self._queue_draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._activate, add="+")
        self.bind("<Return>", self._activate, add="+")
        self.bind("<space>", self._activate, add="+")
        self.bind("<FocusIn>", self._queue_draw, add="+")
        self.bind("<FocusOut>", self._queue_draw, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    @staticmethod
    def _kind_from_style(style: object) -> str:
        name = str(style or "")
        if "Accent" in name:
            return "accent"
        if "Danger" in name:
            return "danger"
        if "NavSelected" in name:
            return "nav_selected"
        if "Nav" in name:
            return "nav"
        if "Link" in name or "Toolbar" in name:
            return "link"
        if "Secondary" in name:
            return "secondary"
        return "quiet"

    @staticmethod
    def _parent_background(parent: object) -> str:
        try:
            style_name = str(parent.cget("style") or "")
            if style_name:
                background = ttk.Style(parent).lookup(style_name, "background")
                if background:
                    return str(background)
        except Exception:
            pass
        try:
            return str(parent.cget("background"))
        except Exception:
            return UI["surface"]

    def _sync_textvariable(self, *_args: object) -> None:
        try:
            text = str(self._textvariable.get())
        except Exception:
            return
        if text != self._text:
            self._text = text
            self._resize_to_content()
            self._last_draw_signature = None
            self._queue_draw()

    def _resize_to_content(self) -> None:
        image_width = self._image.width() if self._image is not None else 0
        required = self._font.measure(self._text) + (image_width + 6 if image_width else 0) + 24
        try:
            if self.winfo_reqwidth() < required:
                super().configure(width=required)
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        super().configure(
            cursor="hand2" if self._enabled else "arrow",
            takefocus=self._enabled,
        )
        self._last_draw_signature = None
        self._queue_draw()

    def state(self, spec: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
        if spec is not None:
            if "disabled" in spec:
                self.set_enabled(False)
            elif "!disabled" in spec:
                self.set_enabled(True)
        return () if self._enabled else ("disabled",)

    def configure(self, cnf: object | None = None, **kwargs: object):
        if cnf is not None:
            if isinstance(cnf, dict):
                kwargs = {**cnf, **kwargs}
            else:
                return super().configure(cnf, **kwargs)
        if not hasattr(self, "_kind"):
            return super().configure(**kwargs)
        if "state" in kwargs:
            self.set_enabled(str(kwargs.pop("state")) != "disabled")
        if "style" in kwargs:
            self._style_name = str(kwargs.pop("style"))
            self._kind = self._kind_from_style(self._style_name)
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
        if "image" in kwargs:
            self._image = kwargs.pop("image")  # type: ignore[assignment]
        if "command" in kwargs:
            self._command = kwargs.pop("command") or (lambda: None)
        if "textvariable" in kwargs:
            self._textvariable = kwargs.pop("textvariable")
            self._sync_textvariable()
        if kwargs:
            result = super().configure(**kwargs)
        else:
            result = None
        self._resize_to_content()
        self._last_draw_signature = None
        self._queue_draw()
        return result

    config = configure

    def cget(self, key: str):
        if hasattr(self, "_kind"):
            values = {
                "state": "normal" if self._enabled else "disabled",
                "style": self._style_name,
                "text": self._text,
                "image": self._image,
                "command": self._command,
                "textvariable": self._textvariable,
            }
            if key in values:
                return values[key]
        return super().cget(key)

    def invoke(self):
        if self._enabled:
            return self._command()
        return None

    def _palette(self) -> tuple[str, str, str]:
        if not self._enabled:
            return UI["surface_overlay"], UI["text_disabled"], UI["border"]
        if self._kind == "danger":
            return (
                UI["danger"] if self._hovered else UI["danger_subtle"],
                "#FFFFFF" if self._hovered else UI["danger"],
                UI["danger"],
            )
        if self._kind == "accent":
            return (
                UI["accent_hover"] if self._hovered else UI["accent_button"],
                "#FFFFFF",
                "",
            )
        if self._kind == "nav_selected":
            return UI["selected"], UI["accent_text"], ""
        if self._kind == "nav":
            return (
                UI["surface_overlay"] if self._hovered else self.cget("background"),
                UI["text_secondary"],
                "",
            )
        if self._kind == "link":
            return (
                UI["surface_overlay"] if self._hovered else self.cget("background"),
                UI["text_secondary"] if self._hovered else UI["text_muted"],
                "",
            )
        if self._kind == "secondary":
            return (
                UI["surface_overlay"] if self._hovered else UI["surface_raised"],
                UI["text_secondary"],
                UI["border"],
            )
        return (
            UI["surface_raised"] if self._hovered else UI["surface_overlay"],
            UI["text_secondary"],
            UI["border"],
        )

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is not None:
            return
        self._draw_after_id = self.after_idle(self._draw)

    def _draw(self, _event: object | None = None) -> None:
        self._draw_after_id = None
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        fill, foreground, border = self._palette()
        signature = (
            width,
            height,
            fill,
            foreground,
            border,
            self._text,
            str(self._image),
            self.focus_get() is self,
        )
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        _draw_antialiased_rounded_rect(
            self,
            1,
            1,
            width - 1,
            height - 1,
            RADII["control"],
            fill=fill,
            border=UI["accent"] if self.focus_get() is self else border,
            border_width=1,
            outer_background=str(self.cget("background")),
        )
        image_width = self._image.width() if self._image is not None else 0
        text_width = self._font.measure(self._text)
        total_width = image_width + (6 if image_width else 0) + text_width
        start_x = max(8, (width - total_width) // 2)
        if self._image is not None:
            self.create_image(
                start_x + image_width // 2,
                height // 2,
                image=self._image,
            )
            start_x += image_width + 6
        self.create_text(
            start_x,
            height // 2,
            text=self._text,
            fill=foreground,
            font=self._font,
            anchor="w",
        )

    def _enter(self, _event: object | None = None) -> None:
        if self._hovered:
            return
        self._hovered = True
        self._queue_draw()

    def _leave(self, _event: object | None = None) -> None:
        if not self._hovered:
            return
        self._hovered = False
        self._queue_draw()

    def _activate(self, _event: object | None = None) -> str:
        if getattr(_event, "num", None) == 1:
            self.focus_set()
        if self._enabled:
            self._command()
        return "break"

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None
        if self._textvariable is not None and self._text_trace_id is not None:
            try:
                self._textvariable.trace_remove("write", self._text_trace_id)
            except Exception:
                pass
            self._text_trace_id = None


class _RoundedCombobox(Canvas):
    """Rounded selector with a themed popup list."""

    def __init__(
        self,
        parent: object,
        *,
        state: str = "readonly",
        textvariable: object | None = None,
        values: tuple[object, ...] | list[object] = (),
    ) -> None:
        ui_scale = _widget_ui_scale(parent)
        super().__init__(
            parent,
            height=max(44, round(44 * ui_scale)),
            background=_RoundedButton._parent_background(parent),
            borderwidth=0,
            highlightthickness=0,
            takefocus=state != "disabled",
            cursor="hand2" if state != "disabled" else "arrow",
        )
        self._font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=10,
        )
        self._values = tuple(str(value) for value in values)
        self._textvariable = textvariable
        self._state = state
        self._hovered = False
        self._popup: Toplevel | None = None
        self._listbox: Listbox | None = None
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self._trace_id: str | None = None
        if textvariable is not None:
            try:
                self._trace_id = textvariable.trace_add(
                    "write",
                    self._variable_changed,
                )
            except Exception:
                self._trace_id = None
        self.bind("<Configure>", self._queue_draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._open_popup, add="+")
        self.bind("<Return>", self._open_popup, add="+")
        self.bind("<space>", self._open_popup, add="+")
        self.bind("<Escape>", self._close_popup, add="+")
        self.bind("<FocusIn>", self._queue_draw, add="+")
        self.bind("<FocusOut>", self._queue_draw, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    def _display_text(self) -> str:
        try:
            value = str(self._textvariable.get())
        except Exception:
            value = ""
        return value or "请选择下载质量"

    def _variable_changed(self, *_args: object) -> None:
        self._last_draw_signature = None
        self._queue_draw()

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is None:
            self._draw_after_id = self.after_idle(self._draw)

    def _draw(self) -> None:
        self._draw_after_id = None
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        text = self._display_text()
        enabled = self._state != "disabled"
        signature = (
            width,
            height,
            text,
            enabled,
            self._hovered,
            self.focus_get() is self,
        )
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        fill = UI["surface_overlay"] if self._hovered and enabled else UI["surface_raised"]
        border = UI["accent"] if self.focus_get() is self else UI["border"]
        _draw_antialiased_rounded_rect(
            self,
            1,
            1,
            width - 1,
            height - 1,
            RADII["control"],
            fill=fill,
            border=border,
            border_width=1,
            outer_background=str(self.cget("background")),
        )
        self.create_text(
            14,
            height // 2,
            text=text,
            fill=UI["text"] if enabled else UI["text_disabled"],
            font=self._font,
            anchor="w",
            width=max(60, width - 94),
        )
        pill_width = max(52, self._font.measure("选择") + 22)
        _draw_antialiased_rounded_rect(
            self,
            width - pill_width - 7,
            7,
            width - 7,
            height - 7,
            RADII["badge"],
            fill=UI["accent_subtle"] if enabled else UI["surface_overlay"],
            outer_background=fill,
        )
        self.create_text(
            width - pill_width // 2 - 7,
            height // 2,
            text="选择",
            fill=UI["accent_text"] if enabled else UI["text_disabled"],
            font=self._font,
        )

    def _enter(self, _event: object | None = None) -> None:
        self._hovered = True
        self._queue_draw()

    def _leave(self, _event: object | None = None) -> None:
        self._hovered = False
        self._queue_draw()

    def _open_popup(self, _event: object | None = None) -> str:
        if self._state == "disabled" or not self._values:
            return "break"
        if self._popup is not None and self._popup.winfo_exists():
            self._close_popup()
            return "break"
        popup = Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.winfo_toplevel())
        popup.configure(background=UI["border"])
        popup.attributes("-topmost", True)
        width = max(self.winfo_width(), 220)
        row_height = max(30, round(32 * _widget_ui_scale(self)))
        visible_rows = min(8, len(self._values))
        height = visible_rows * row_height + 12
        panel = _RoundedPanel(
            popup,
            fill=UI["surface_raised"],
            outer_background=UI["border"],
            style="SurfaceRaised.TFrame",
            radius=RADII["control"],
            border=UI["border"],
            border_width=1,
            inset=6,
        )
        panel.pack(fill=BOTH, expand=True)
        listbox = Listbox(
            panel.inner,
            activestyle="none",
            background=UI["surface_raised"],
            foreground=UI["text"],
            selectbackground=UI["selected"],
            selectforeground=UI["text"],
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            font=self._font,
            exportselection=False,
        )
        for value in self._values:
            listbox.insert(END, value)
        selected = self.current()
        if selected >= 0:
            listbox.selection_set(selected)
            listbox.see(selected)
        listbox.pack(fill=BOTH, expand=True)
        listbox.bind("<ButtonRelease-1>", self._choose_popup_value, add="+")
        listbox.bind("<Return>", self._choose_popup_value, add="+")
        listbox.bind("<Escape>", self._close_popup, add="+")
        popup.bind("<FocusOut>", self._popup_focus_out, add="+")
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        screen_height = self.winfo_screenheight()
        if y + height > screen_height:
            y = max(0, self.winfo_rooty() - height - 4)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        self._popup = popup
        self._listbox = listbox
        popup.deiconify()
        popup.lift()
        listbox.focus_set()
        return "break"

    def _popup_focus_out(self, _event: object | None = None) -> None:
        if self._popup is not None:
            self.after_idle(self._close_popup_if_unfocused)

    def _close_popup_if_unfocused(self) -> None:
        popup = self._popup
        if popup is None:
            return
        try:
            focused = popup.focus_get()
        except Exception:
            focused = None
        if focused is None:
            self._close_popup()

    def _choose_popup_value(self, _event: object | None = None) -> str:
        if self._listbox is not None:
            selection = self._listbox.curselection()
            if selection:
                self.current(int(selection[0]))
        self._close_popup()
        self.focus_set()
        return "break"

    def _close_popup(self, _event: object | None = None) -> str:
        popup = self._popup
        self._popup = None
        self._listbox = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass
        if str(getattr(_event, "keysym", "")) == "Escape":
            self.focus_set()
        return "break"

    def current(self, index: int | None = None) -> int:
        if index is not None:
            if 0 <= int(index) < len(self._values):
                value = self._values[int(index)]
                try:
                    self._textvariable.set(value)
                except Exception:
                    pass
                return int(index)
            return -1
        try:
            return self._values.index(str(self._textvariable.get()))
        except (AttributeError, ValueError):
            return -1

    def configure(self, cnf: object | None = None, **kwargs: object):
        if cnf is not None:
            if isinstance(cnf, dict):
                kwargs = {**cnf, **kwargs}
            else:
                return super().configure(cnf, **kwargs)
        if not hasattr(self, "_values"):
            return super().configure(**kwargs)
        if "values" in kwargs:
            self._values = tuple(str(value) for value in kwargs.pop("values"))
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            enabled = self._state != "disabled"
            super().configure(
                cursor="hand2" if enabled else "arrow",
                takefocus=enabled,
            )
        if kwargs:
            result = super().configure(**kwargs)
        else:
            result = None
        self._last_draw_signature = None
        self._queue_draw()
        return result

    config = configure

    def cget(self, key: str):
        if hasattr(self, "_values"):
            if key == "values":
                return self._values
            if key == "state":
                return self._state
            if key == "textvariable":
                return self._textvariable
        return super().cget(key)

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None
        self._close_popup()
        if self._textvariable is not None and self._trace_id is not None:
            try:
                self._textvariable.trace_remove("write", self._trace_id)
            except Exception:
                pass
            self._trace_id = None


class _RoundedBadge(Canvas):
    def __init__(
        self,
        parent: object,
        *,
        text: str,
        foreground: str,
        fill: str,
        outer_background: str,
    ) -> None:
        ui_scale = _widget_ui_scale(parent)
        self._font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=9,
            weight="bold",
        )
        self._ui_scale = ui_scale
        self._height = max(
            round(22 * ui_scale),
            self._font.metrics("linespace") + round(4 * ui_scale),
        )
        width = self._font.measure(text) + round(14 * ui_scale)
        super().__init__(
            parent,
            width=width,
            height=self._height,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
        )
        self._state = (text, foreground, fill, outer_background)
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self._surface = 0
        self._label = self.create_text(
            width // 2,
            self._height // 2,
            text=text,
            fill=foreground,
            font=self._font,
        )
        self.bind("<Destroy>", self._destroy, add="+")
        self._draw()

    def set_badge(
        self,
        *,
        text: str,
        foreground: str,
        fill: str,
        outer_background: str,
    ) -> None:
        state = (text, foreground, fill, outer_background)
        if state == self._state:
            return
        self._state = state
        self._last_draw_signature = None
        self._queue_draw()

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is None:
            self._draw_after_id = self.after_idle(self._draw)

    def _draw(self) -> None:
        self._draw_after_id = None
        if self._state == self._last_draw_signature:
            return
        self._last_draw_signature = self._state
        text, foreground, fill, outer_background = self._state
        width = self._font.measure(text) + round(14 * self._ui_scale)
        self.configure(width=width, background=outer_background)
        self.delete("surface")
        surface_items = _draw_antialiased_rounded_rect(
            self,
            0,
            1,
            width,
            self._height - 1,
            RADII["badge"],
            fill=fill,
            outer_background=outer_background,
            tags=("surface",),
        )
        self._surface = surface_items[0]
        self.tag_lower("surface")
        self.coords(self._label, width // 2, self._height // 2)
        self.itemconfigure(self._label, text=text, fill=foreground)

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


class _RoundedNavButton(Canvas):
    def __init__(
        self,
        parent: object,
        *,
        text: str,
        image: PhotoImage | None,
        command,
    ) -> None:
        ui_scale = _widget_ui_scale(parent)
        super().__init__(
            parent,
            height=max(36, round(36 * ui_scale)),
            background=UI["sidebar_bg"],
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self._text = text
        self._image = image
        self._command = command
        self._selected = False
        self._hovered = False
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self._font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=11,
        )
        self._selected_font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=11,
            weight="bold",
        )
        self.bind("<Configure>", self._queue_draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._activate, add="+")
        self.bind("<Return>", self._activate, add="+")
        self.bind("<space>", self._activate, add="+")
        self.bind("<FocusIn>", self._queue_draw, add="+")
        self.bind("<FocusOut>", self._queue_draw, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    def set_selected(
        self,
        selected: bool,
        *,
        image: PhotoImage | None = None,
    ) -> None:
        selected = bool(selected)
        changed = selected != self._selected
        self._selected = selected
        if image is not None:
            changed = changed or image is not self._image
            self._image = image
        if changed:
            self._last_draw_signature = None
            self._queue_draw()

    def set_text(self, text: object) -> None:
        value = str(text)
        if value == self._text:
            return
        self._text = value
        self._last_draw_signature = None
        self._queue_draw()

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is not None:
            return
        self._draw_after_id = self.after_idle(self._draw)

    def _draw(self, _event: object | None = None) -> None:
        self._draw_after_id = None
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        signature = (
            width,
            height,
            self._selected,
            self._hovered,
            str(self._image),
            self.focus_get() is self,
        )
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        if self._selected or self._hovered:
            fill = UI["selected"] if self._selected else UI["surface_overlay"]
            _draw_antialiased_rounded_rect(
                self,
                1,
                2,
                width - 1,
                height - 2,
                RADII["control"],
                fill=fill,
                border=UI["accent"] if self.focus_get() is self else "",
                border_width=1,
                outer_background=str(self.cget("background")),
            )
        x = 12
        if self._image is not None:
            self.create_image(x + 8, height // 2, image=self._image)
            x += 28
        self.create_text(
            x,
            height // 2,
            text=self._text,
            fill=UI["accent_text"] if self._selected else UI["text_secondary"],
            font=self._selected_font if self._selected else self._font,
            anchor="w",
        )

    def _enter(self, _event: object | None = None) -> None:
        if self._hovered:
            return
        self._hovered = True
        self._queue_draw()

    def _leave(self, _event: object | None = None) -> None:
        if not self._hovered:
            return
        self._hovered = False
        self._queue_draw()

    def _activate(self, _event: object | None = None) -> str:
        if getattr(_event, "num", None) == 1:
            self.focus_set()
        self._command()
        return "break"

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


class _RoundedScrollbar(Canvas):
    """Arrowless vertical scrollbar with a rounded adaptive thumb."""

    def __init__(
        self,
        parent: object,
        *,
        command,
        background: str,
        width: int = 12,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            cursor="arrow",
        )
        self._command = command
        self._first = 0.0
        self._last = 1.0
        self._hovered = False
        self._drag_origin_y: int | None = None
        self._drag_origin_first = 0.0
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self.bind("<Configure>", self._queue_draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._press, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    def set(self, first: object, last: object) -> None:
        previous = (self._first, self._last)
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        if (self._first, self._last) != previous:
            self._queue_draw()

    def _thumb_geometry(self) -> tuple[int, int, int, int] | None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        if self._last - self._first >= 0.999:
            return None
        margin_y = 4
        track_height = max(1, height - margin_y * 2)
        visible = max(0.0, self._last - self._first)
        thumb_height = max(30, int(track_height * visible))
        thumb_height = min(track_height, thumb_height)
        movable = max(1, track_height - thumb_height)
        denominator = max(0.0001, 1.0 - visible)
        top = margin_y + int(movable * self._first / denominator)
        thumb_width = min(8, max(6, width - 4))
        left = (width - thumb_width) // 2
        return left, top, left + thumb_width, top + thumb_height

    def _queue_draw(self, _event: object | None = None) -> None:
        if self._draw_after_id is not None:
            return
        self._draw_after_id = self.after_idle(self._draw)

    def _draw(self, _event: object | None = None) -> None:
        self._draw_after_id = None
        signature = (
            self.winfo_width(),
            self.winfo_height(),
            round(self._first, 6),
            round(self._last, 6),
            self._hovered,
        )
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        geometry = self._thumb_geometry()
        if geometry is None:
            return
        left, top, right, bottom = geometry
        fill = UI["text_secondary"] if self._hovered else UI["text_muted"]
        _draw_antialiased_rounded_rect(
            self,
            left,
            top,
            right,
            bottom,
            max(2, (right - left) // 2),
            fill=fill,
            outer_background=str(self.cget("background")),
            tags=("thumb",),
        )

    def _enter(self, _event: object | None = None) -> None:
        if self._hovered:
            return
        self._hovered = True
        self._queue_draw()

    def _leave(self, _event: object | None = None) -> None:
        if not self._hovered:
            return
        self._hovered = False
        self._queue_draw()

    def _press(self, event: object) -> str:
        geometry = self._thumb_geometry()
        if geometry is None:
            return "break"
        _left, top, _right, bottom = geometry
        y = int(getattr(event, "y", 0))
        if top <= y <= bottom:
            self._drag_origin_y = y
            self._drag_origin_first = self._first
        else:
            self._command("scroll", -1 if y < top else 1, "pages")
        return "break"

    def _drag(self, event: object) -> str:
        if self._drag_origin_y is None:
            return "break"
        geometry = self._thumb_geometry()
        if geometry is None:
            return "break"
        _left, top, _right, bottom = geometry
        movable = max(1, self.winfo_height() - 8 - (bottom - top))
        delta = int(getattr(event, "y", 0)) - self._drag_origin_y
        self._command("moveto", max(0.0, min(1.0, self._drag_origin_first + delta / movable)))
        return "break"

    def _release(self, _event: object | None = None) -> str:
        self._drag_origin_y = None
        return "break"

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


class _RoundedProgressBar(Canvas):
    def __init__(
        self,
        parent: object,
        *,
        maximum: float = 100,
        height: int = 8,
        background: str,
    ) -> None:
        super().__init__(
            parent,
            height=height,
            background=background,
            borderwidth=0,
            highlightthickness=0,
        )
        self._maximum = max(1.0, float(maximum))
        self._value = 0.0
        self._color = UI["accent"]
        self._draw_after_id: str | None = None
        self._last_draw_signature: tuple[object, ...] | None = None
        self.bind("<Configure>", self._queue_draw, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._queue_draw()

    def configure(self, cnf: object | None = None, **kwargs: object) -> object:
        changed = False
        if "value" in kwargs:
            try:
                value = max(0.0, min(self._maximum, float(kwargs.pop("value"))))
            except (TypeError, ValueError):
                value = 0.0
            changed = changed or value != self._value
            self._value = value
        style_name = str(kwargs.pop("style", "") or "")
        if style_name:
            if "Emerald" in style_name:
                color = UI["success"]
            elif "Orange" in style_name:
                color = UI["status_waiting_eagle"][0]
            else:
                color = UI["accent"]
            changed = changed or color != self._color
            self._color = color
        if "background" in kwargs:
            changed = changed or str(kwargs["background"]) != str(self.cget("background"))
        result = super().configure(cnf, **kwargs)
        if hasattr(self, "_value") and (changed or cnf is not None):
            self._last_draw_signature = None
            self._queue_draw()
        return result

    config = configure

    def _queue_draw(self, _event: object | None = None) -> None:
        if not hasattr(self, "_value") or self._draw_after_id is not None:
            return
        self._draw_after_id = self.after_idle(self._draw)

    def _draw(self, _event: object | None = None) -> None:
        if not hasattr(self, "_value"):
            return
        self._draw_after_id = None
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        signature = (width, height, self._value, self._maximum, self._color)
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        radius = max(2, height // 2)
        _draw_antialiased_rounded_rect(
            self,
            0,
            0,
            width,
            height,
            radius,
            fill=UI["progress_track"],
            outer_background=str(self.cget("background")),
        )
        fill_width = int(width * self._value / self._maximum)
        if fill_width <= 0:
            return
        _draw_antialiased_rounded_rect(
            self,
            0,
            0,
            max(height, fill_width),
            height,
            min(radius, max(2, fill_width // 2)),
            fill=self._color,
            outer_background=UI["progress_track"],
        )

    def _destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self:
            return
        if self._draw_after_id is not None:
            try:
                self.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None


class _MouseWheelRouter:
    """Route one top-level wheel binding to the nearest owning scroller."""

    def __init__(self, toplevel: object) -> None:
        self.toplevel = toplevel
        self.scrollers: set[object] = set()
        self.binding = toplevel.bind(
            "<MouseWheel>",
            self._dispatch,
            add="+",
        )

    def register(self, scroller: object) -> None:
        self.scrollers.add(scroller)

    def unregister(self, scroller: object) -> None:
        self.scrollers.discard(scroller)
        if self.scrollers or not self.binding:
            return
        try:
            self.toplevel.unbind("<MouseWheel>", self.binding)
        except Exception:
            pass
        self.binding = ""

    def _dispatch(self, event: object) -> str | None:
        current = getattr(event, "widget", None)
        while current is not None:
            if isinstance(current, (ttk.Treeview, ttk.Combobox, _RoundedCombobox)):
                return None
            if current in self.scrollers:
                return current._on_mousewheel(event)
            current = getattr(current, "master", None)
        return None


def _register_mousewheel_scroller(scroller: object) -> _MouseWheelRouter:
    toplevel = scroller.winfo_toplevel()
    router = getattr(toplevel, "_mousewheel_router", None)
    if not isinstance(router, _MouseWheelRouter):
        router = _MouseWheelRouter(toplevel)
        setattr(toplevel, "_mousewheel_router", router)
    router.register(scroller)
    return router


class _ScrollableCardList(ttk.Frame):
    """A vertically scrolling host for task and candidate card rows."""

    def __init__(
        self,
        parent: object,
        *,
        background: str | None = None,
        initial_width: int | None = None,
    ) -> None:
        background = background or UI["bg"]
        super().__init__(parent, style="App.TFrame")
        self.canvas = Canvas(
            self,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            yscrollincrement=24,
            width=initial_width or 1,
        )
        self.scrollbar = _RoundedScrollbar(
            self,
            command=self.canvas.yview,
            background=background,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self._sync_after_id: str | None = None
        self._last_layout: tuple[int, int, int, bool] | None = None
        self._scrollbar_visible = False
        self._wheel_remainder = 0.0
        self.canvas.bind("<Configure>", self._queue_sync, add="+")
        self.content.bind("<Configure>", self._queue_sync, add="+")
        self._wheel_router = _register_mousewheel_scroller(self)
        self.bind("<Destroy>", self._release_wheel_router, add="+")

    def _queue_sync(self, _event: object | None = None) -> None:
        if self._sync_after_id is not None:
            return
        self._sync_after_id = self.after_idle(self._sync)

    def _sync(self, _event: object | None = None, *, force: bool = False) -> None:
        self._sync_after_id = None
        width = max(1, self.canvas.winfo_width())
        viewport_height = max(1, self.canvas.winfo_height())
        height = max(1, self.content.winfo_reqheight())
        overflow = height > viewport_height + 1
        if overflow != self._scrollbar_visible:
            self._scrollbar_visible = overflow
            if overflow:
                self.scrollbar.pack(side=RIGHT, fill=Y, before=self.canvas)
            else:
                self.scrollbar.pack_forget()
            self._queue_sync()
        signature = (width, viewport_height, height, overflow)
        if not force and signature == self._last_layout:
            return
        self._last_layout = signature
        self.canvas.itemconfigure(self._window, width=width)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _on_mousewheel(self, event: object) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0 or self.canvas.yview() == (0.0, 1.0):
            return None
        self._wheel_remainder += delta * 3 / 120
        units = int(self._wheel_remainder)
        if units == 0:
            return "break"
        self._wheel_remainder -= units
        self.canvas.yview_scroll(-units, "units")
        return "break"

    _wheel = _on_mousewheel

    def _release_wheel_router(self, event: object) -> None:
        if getattr(event, "widget", None) is self:
            self._wheel_router.unregister(self)

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self._last_layout = None
        self._queue_sync()


def _set_window_icon(window: Tk | Toplevel) -> None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "assets" / "liudi-downloader.ico")
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "assets"
        / "liudi-downloader.ico"
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            window.iconbitmap(default=str(candidate))
            return
        except Exception:
            continue


def _windows_color_ref(color: str) -> int:
    """Convert #RRGGBB to the BGR COLORREF expected by Windows."""

    value = str(color).strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"invalid Windows caption color: {color}")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red | (green << 8) | (blue << 16)


def _apply_windows_dark_title_bar(
    window: Tk | Toplevel,
    dark: bool = True,
) -> bool:
    """Keep native window behavior while matching the active application theme."""

    if sys.platform != "win32":
        return False
    try:
        # Never call update_idletasks here: it synchronously drains idle
        # callbacks and livelocks against _DynamicWrapLabel's <Configure>
        # re-wrap, which freezes the UI thread.
        user32 = ctypes.windll.user32
        hwnd = int(window.winfo_id())
        while True:
            parent = int(user32.GetParent(hwnd) or 0)
            if not parent:
                break
            hwnd = parent

        dwmapi = ctypes.windll.dwmapi
        enabled = ctypes.c_int(1 if dark else 0)
        dark_result = int(
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                20,  # DWMWA_USE_IMMERSIVE_DARK_MODE
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
        )
        if dark_result != 0:
            dark_result = int(
                dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    19,  # Older Windows 10 builds
                    ctypes.byref(enabled),
                    ctypes.sizeof(enabled),
                )
            )

        color_results: list[int] = []
        for attribute, color in (
            (35, UI["bg"]),  # DWMWA_CAPTION_COLOR
            (36, UI["text"]),  # DWMWA_TEXT_COLOR
            (34, UI["border"]),  # DWMWA_BORDER_COLOR
        ):
            value = ctypes.c_uint(_windows_color_ref(color))
            color_results.append(
                int(
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        attribute,
                        ctypes.byref(value),
                        ctypes.sizeof(value),
                    )
                )
            )
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)
        return dark_result == 0 or any(result == 0 for result in color_results)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _redraw_windows_client_area(window: Tk | Toplevel) -> bool:
    """Invalidate the full Tk window once an interactive move or resize settles."""

    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = int(window.winfo_id())
        while True:
            parent = int(user32.GetParent(hwnd) or 0)
            if not parent:
                break
            hwnd = parent
        flags = (
            0x0001  # RDW_INVALIDATE
            | 0x0004  # RDW_ERASE
            | 0x0080  # RDW_ALLCHILDREN
            | 0x0100  # RDW_UPDATENOW
        )
        return bool(user32.RedrawWindow(hwnd, None, None, flags))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _load_product_image(maximum_size: int = 30) -> PhotoImage | None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(
            Path(bundle_root)
            / "idm_eagle_bridge"
            / "assets"
            / "liudi-downloader.png"
        )
        candidates.append(
            Path(bundle_root) / "assets" / "liudi-downloader.png"
        )
    candidates.append(
        Path(__file__).resolve().parent
        / "assets"
        / "liudi-downloader.png"
    )
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "assets"
        / "liudi-downloader.png"
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            source = PhotoImage(file=str(candidate))
            factor = max(
                1,
                (max(source.width(), source.height()) + maximum_size - 1)
                // maximum_size,
            )
            return source.subsample(factor, factor)
        except Exception:
            continue
    return None


class _LazyIconMap(dict[str, PhotoImage | None]):
    """Discover icon keys up front and decode pixels only on first use."""

    def __init__(self, paths: dict[str, Path], scale: float) -> None:
        super().__init__((name, None) for name in paths)
        self._paths = paths
        self._scale = scale
        self._failed: set[str] = set()

    def __getitem__(self, key: str) -> PhotoImage | None:
        value = super().__getitem__(key)
        if value is not None or key in self._failed:
            return value
        try:
            value = _scale_photo_image(
                PhotoImage(file=str(self._paths[key])),
                self._scale,
            )
        except Exception:
            self._failed.add(key)
            return None
        super().__setitem__(key, value)
        return value

    def get(
        self,
        key: str,
        default: PhotoImage | None = None,
    ) -> PhotoImage | None:
        if key not in self:
            return default
        value = self[key]
        return default if value is None else value


def _load_ui_icons(scale: float = 1.0) -> dict[str, PhotoImage | None]:
    bundle_value = str(getattr(sys, "_MEIPASS", "") or "")
    roots = []
    if bundle_value:
        roots.append(
            Path(bundle_value)
            / "idm_eagle_bridge"
            / "assets"
            / "ui-icons"
        )
        roots.append(Path(bundle_value) / "assets" / "ui-icons")
    roots.append(Path(__file__).resolve().parent / "assets" / "ui-icons")
    paths: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.png"):
            if path.stem in paths:
                continue
            paths[path.stem] = path
    return _LazyIconMap(paths, scale)


class _VerticalScrolledFrame(ttk.Frame):
    """A width-filling frame that scrolls only when its content is too tall."""

    def __init__(
        self,
        parent: object,
        *,
        padding: object = 0,
        style: str = "Surface.TFrame",
        background: str | None = None,
        initial_width: int | None = None,
    ) -> None:
        background = background or UI["surface"]
        super().__init__(parent, style=style)
        self.canvas = Canvas(
            self,
            borderwidth=0,
            highlightthickness=0,
            background=background,
            yscrollincrement=20,
            width=initial_width or 1,
        )
        self.scrollbar = _RoundedScrollbar(
            self,
            command=self.canvas.yview,
            background=background,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.content = ttk.Frame(
            self.canvas,
            padding=padding,
            style=style,
        )
        self._content_window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self._layout_after_id: str | None = None
        self._last_layout: tuple[int, int, int, bool] | None = None
        self._scrollbar_visible = False
        self._wheel_remainder = 0.0
        self.content.bind("<Configure>", self._queue_layout, add="+")
        self.canvas.bind("<Configure>", self._queue_layout, add="+")
        self.bind("<Configure>", self._queue_layout, add="+")
        self._wheel_router = _register_mousewheel_scroller(self)
        self.bind("<Destroy>", self._release_wheel_router, add="+")

    def _queue_layout(self, _event: object | None = None) -> None:
        if self._layout_after_id is not None:
            return
        self._layout_after_id = self.after_idle(self._sync_layout)

    def _sync_layout(
        self,
        _event: object | None = None,
        *,
        force: bool = False,
    ) -> None:
        self._layout_after_id = None
        width = max(1, self.canvas.winfo_width())
        viewport_height = max(1, self.canvas.winfo_height())
        requested_height = max(1, self.content.winfo_reqheight())
        overflow = requested_height > viewport_height + 1
        if overflow != self._scrollbar_visible:
            self._scrollbar_visible = overflow
            if overflow:
                self.scrollbar.pack(side=RIGHT, fill=Y, before=self.canvas)
            else:
                self.scrollbar.pack_forget()
            self._queue_layout()
        height = max(viewport_height, requested_height)
        signature = (width, viewport_height, requested_height, overflow)
        if not force and signature == self._last_layout:
            return
        self._last_layout = signature
        self.canvas.itemconfigure(
            self._content_window,
            width=width,
            height=height,
        )
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _contains(self, widget: object) -> bool:
        current = widget
        while current is not None:
            if current is self:
                return True
            current = getattr(current, "master", None)
        return False

    def _inside_independent_scroller(self, widget: object) -> bool:
        current = widget
        while current is not None and current is not self:
            if isinstance(current, (ttk.Treeview, ttk.Combobox, _RoundedCombobox)):
                return True
            current = getattr(current, "master", None)
        return False

    def _on_mousewheel(self, event: object) -> str | None:
        widget = getattr(event, "widget", None)
        if (
            widget is None
            or not self._contains(widget)
            or self._inside_independent_scroller(widget)
        ):
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0 or self.canvas.yview() == (0.0, 1.0):
            return None
        self._wheel_remainder += delta * 3 / 120
        units = int(self._wheel_remainder)
        if units == 0:
            return "break"
        self._wheel_remainder -= units
        self.canvas.yview_scroll(-units, "units")
        return "break"

    def scroll_to_bottom(self) -> None:
        self.update_idletasks()
        self._sync_layout(force=True)
        self.canvas.yview_moveto(1.0)

    def _release_wheel_router(self, event: object) -> None:
        if getattr(event, "widget", None) is self:
            self._wheel_router.unregister(self)


def _bind_coalesced_aspect_resize(
    container: object,
    surface: object,
    *,
    maximum_width: int,
    aspect_width: int = 16,
    aspect_height: int = 9,
) -> None:
    """Resize a preview once per idle cycle instead of on every geometry event."""

    state: dict[str, object] = {"after_id": None, "size": None}

    def apply() -> None:
        state["after_id"] = None
        size = state["size"]
        if not isinstance(size, tuple):
            return
        width, height = size
        if (
            int(surface.cget("width")) == width
            and int(surface.cget("height")) == height
        ):
            return
        surface.configure(width=width, height=height)

    def queue(event: object) -> None:
        available = max(1, int(getattr(event, "width", 1)))
        width = min(maximum_width, available)
        state["size"] = (
            width,
            max(1, width * aspect_height // aspect_width),
        )
        if state["after_id"] is None:
            state["after_id"] = container.after_idle(apply)

    container.bind("<Configure>", queue, add="+")


def _bind_responsive_header_layout(
    header: object,
    heading: object,
    actions: object,
    *,
    breakpoint: int = 700,
) -> None:
    """Stack crowded header actions once, after resize activity settles."""

    state: dict[str, object] = {"after_id": None, "stacked": None}

    def apply() -> None:
        state["after_id"] = None
        stacked = max(1, header.winfo_width()) < breakpoint
        if state["stacked"] == stacked:
            return
        state["stacked"] = stacked
        if stacked:
            heading.grid_configure(
                row=0,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=0,
            )
            actions.grid_configure(
                row=1,
                column=0,
                columnspan=2,
                sticky="w",
                pady=(10, 0),
            )
            return
        heading.grid_configure(
            row=0,
            column=0,
            columnspan=1,
            sticky="ew",
            padx=(0, 12),
        )
        actions.grid_configure(
            row=0,
            column=1,
            columnspan=1,
            sticky="ne",
            pady=0,
        )

    def queue(_event: object | None = None) -> None:
        if state["after_id"] is None:
            state["after_id"] = header.after_idle(apply)

    header.bind("<Configure>", queue, add="+")
    queue()


class MainWindow:
    def __init__(
        self,
        database: Database,
        api_server: LocalApiServer,
        processing: ProcessingService,
        external_tray: bool = False,
        start_hidden: bool = False,
        visual_capture_hidden: bool = False,
        visual_capture_geometry: str | None = None,
    ) -> None:
        window_started = time.perf_counter()
        self.database = database
        self.api_server = api_server
        self.media = api_server.api.media
        self.wechat_channels = api_server.api.wechat_channels
        self.processing = processing
        self.external_tray = external_tray
        self.start_hidden = start_hidden and external_tray
        self.closing = False
        self.performance_monitor = PerformanceMonitor.from_environment()
        self.performance_after_id: str | None = None
        self.performance_expected_at = 0.0
        self.current_ui_operation = "startup"
        self.eagle = EagleClient()
        self.pairing = PairingManager(database)
        self.ui_theme = _set_ui_theme(
            database.get_setting("ui_theme", DEFAULT_UI_THEME)
        )
        _enable_windows_dpi_awareness()
        self.root = Tk()
        if visual_capture_hidden:
            self.root.withdraw()
        self.ui_scale = _effective_ui_scale(
            _window_dpi(self.root),
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        self.metrics = _scaled_metrics(self.ui_scale)
        _set_window_icon(self.root)
        _configure_styles(self.root, self.ui_scale)
        self.brand_image = _load_product_image(max(16, round(16 * self.ui_scale)))
        self.ui_icons = _load_ui_icons(self.ui_scale)
        self.root.configure(background=UI["bg"])
        if self.start_hidden:
            self.root.withdraw()
        self.root.title(f"{APP_NAME} v{APP_VERSION} by{APP_AUTHOR}")
        initial_geometry = visual_capture_geometry or _scale_geometry(
            "1120x720",
            self.ui_scale,
        )
        self.root.geometry(initial_geometry)
        self.root.minsize(
            round(900 * self.ui_scale),
            round(600 * self.ui_scale),
        )
        self.root.protocol("WM_DELETE_WINDOW", self.hide if external_tray else self.quit)
        _apply_windows_dark_title_bar(
            self.root,
            dark=self.ui_theme == "dark",
        )
        self.root.after_idle(
            lambda: _apply_windows_dark_title_bar(
                self.root,
                dark=self.ui_theme == "dark",
            )
        )
        self.status_text = StringVar()
        self.page_title_text = StringVar(value="下载任务")
        self.eagle_status_text = StringVar(value="Eagle 正在检查 · 下载可用")
        self.service_status_text = StringVar(value="本机服务正常")
        self.chrome_status_text = StringVar(value="Chrome 未配对")
        self.pairing_text = StringVar()
        self.site_rules_text = StringVar(value="网站规则")
        self.network_proxy_text = StringVar(value="网络：自动")
        self.settings_proxy_status_text = StringVar(value="正在检测网络…")
        self.settings_site_summary_text = StringVar(value="正在读取网站规则…")
        self.update_button_text = StringVar(value="检查更新")
        self.theme_button_text = StringVar()
        self._update_theme_button_text()
        self.current_page = "media"
        self.page_frames: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, _RoundedNavButton] = {}
        self.control_signals = ControlSignals() if external_tray else None
        self.control_after_id: str | None = None
        self.refresh_after_id: str | None = None
        self.page_refresh_after_id: str | None = None
        self.prewarm_after_id: str | None = None
        self.update_poll_after_id: str | None = None
        self.auto_update_after_id: str | None = None
        self.media_change_after_id: str | None = None
        self.maintenance_after_id: str | None = None
        self.wechat_operation_after_id: str | None = None
        self.media_change_events: Queue[None] = Queue(maxsize=1)
        self._media_change_listener = self._queue_media_change
        self.update_events: Queue[tuple[str, object]] = Queue()
        self.update_progress_lock = threading.Lock()
        self.update_progress_latest: tuple[int, int] | None = None
        self.update_checking = False
        self.update_downloading = False
        self.maintenance_events: Queue[tuple[int, str, bool, object]] = Queue(
            maxsize=8
        )
        self.maintenance_generation = 0
        self.maintenance_busy = False
        self.maintenance_kind = ""
        self.visible = not self.start_hidden
        try:
            initial_width = round(
                int(initial_geometry.lower().split("x", 1)[0]) / self.ui_scale
            )
        except (ValueError, AttributeError):
            initial_width = 1120
        self.layout_mode = _layout_mode_for_width(initial_width)
        self.initial_client_width = initial_width
        self.layout_after_id: str | None = None
        self.window_settle_after_id: str | None = None
        self.window_interaction_active = False
        self.pending_refresh_force = False
        self.last_root_size: tuple[int, int] | None = None
        self.last_responsive_signature: tuple[str, bool] | None = None
        self.responsive_initialized = False
        self.last_jobs_revision: tuple[int, float] | None = None
        self.last_plans_revision: tuple[int, float] | None = None
        self.last_plan_detail_revision: tuple[object, ...] | None = None
        self.last_plan_preview_revision: tuple[object, ...] | None = None
        self.last_idm_detail_revision: tuple[object, ...] | None = None
        self.idm_detail_query_key: tuple[object, ...] | None = None
        self.idm_detail_query_value: dict | None = None
        self.idm_ellipsize_cache: OrderedDict[tuple[str, int], str] = OrderedDict()
        self.last_wechat_detail_revision: tuple[object, ...] | None = None
        self.plan_rows: dict[str, dict] = {}
        self.selected_plan_card_id = ""
        self.plan_card_widgets: dict[str, dict[str, object]] = {}
        self.plan_thumbnail_images: dict[str, PhotoImage] = {}
        self.plan_thumbnail_cache: OrderedDict[
            tuple[str, int, int],
            PhotoImage,
        ] = OrderedDict()
        self.preview_image: PhotoImage | None = None
        self.preview_cache = _PreviewImageCache()
        self.wechat_rows: dict[str, dict] = {}
        self.selected_wechat_card_id = ""
        self.wechat_card_widgets: dict[str, dict[str, object]] = {}
        self.wechat_variant_ids: list[str] = []
        self.wechat_revision: tuple[int, float] | None = None
        self.wechat_preview_events: Queue[tuple[int, str, bytes]] = Queue(maxsize=4)
        self.wechat_preview_lock = threading.Lock()
        self.wechat_preview_pending: tuple[int, str] | None = None
        self.wechat_preview_worker_running = False
        self.wechat_preview_generation = 0
        self.wechat_preview_object_id = ""
        self.wechat_preview_image: PhotoImage | None = None
        self.wechat_page = 0
        self.wechat_page_count = 1
        self.wechat_operation_results: Queue[tuple[int, str, object]] = Queue(
            maxsize=8
        )
        self.wechat_operation_busy = False
        self.wechat_operation_generation = 0
        self.idm_page = 0
        self.idm_page_count = 1
        self.last_media_summary: dict[str, int | float] = {
            "total": 0,
            "active": 0,
            "revision": 0.0,
        }
        self.current_settings_tab = "pairing"
        self.ui_ready = False
        self.last_eagle_check = 0.0
        self.eagle_connected = False
        self.eagle_probe = _AsyncProbe(
            _resolve_eagle_probe(
                self.api_server.api,
                self.eagle.is_available,
            ),
            name="eagle-health-probe",
        )
        self._build()
        self.ui_ready = True
        self.page_prewarm_queue = [
            "wechat",
            "idm",
            "settings",
            "diagnostics",
        ]
        add_change_listener = getattr(self.media, "add_change_listener", None)
        if callable(add_change_listener):
            add_change_listener(self._media_change_listener)
            self.media_change_after_id = self.root.after(
                250,
                self._poll_media_changes,
            )
        self.root.bind("<Configure>", self._queue_responsive_layout, add="+")
        self.root.after_idle(self._apply_responsive_layout)
        self.refresh()
        self.prewarm_after_id = self.root.after(250, self._prewarm_next_page)
        if self.control_signals:
            self.control_after_id = self.root.after(250, self._poll_control_signals)
        self.auto_update_after_id = self.root.after(10000, self._automatic_update_check)
        if self.performance_monitor.enabled:
            self.performance_expected_at = (
                time.perf_counter() + PERFORMANCE_HEARTBEAT_MS / 1000
            )
            self.performance_after_id = self.root.after(
                PERFORMANCE_HEARTBEAT_MS,
                self._performance_heartbeat,
            )
        self.current_ui_operation = ""
        self._record_performance("MainWindow.create", window_started)

    def _build(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill=BOTH, expand=True)

        self.topbar = ttk.Frame(
            shell,
            style="Topbar.TFrame",
            height=self.metrics["topbar_height"],
        )
        self.topbar.pack(fill=X)
        self.topbar.grid_propagate(False)
        self.topbar.columnconfigure(0, weight=1)

        self.topbar_statuses = ttk.Frame(self.topbar, style="Topbar.TFrame")
        self.topbar_statuses.grid(row=0, column=0, sticky="e", padx=(12, 16))
        self.status_dots: dict[str, _StatusIndicator] = {}
        for key, variable in (
            ("eagle", self.eagle_status_text),
            ("service", self.service_status_text),
            ("chrome", self.chrome_status_text),
        ):
            item = ttk.Frame(self.topbar_statuses, style="Topbar.TFrame")
            item.pack(side=LEFT, padx=(0, 16))
            dot = _StatusIndicator(item, size=7)
            dot.pack(side=LEFT, padx=(0, 6))
            ttk.Label(
                item,
                textvariable=variable,
                style="TopbarStatus.TLabel",
            ).pack(side=LEFT)
            self.status_dots[key] = dot

        body = ttk.Frame(shell, style="App.TFrame")
        body.pack(fill=BOTH, expand=True)
        self.sidebar = ttk.Frame(
            body,
            style="Sidebar.TFrame",
            width=self.metrics["sidebar_width"],
            padding=(8, 8),
        )
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

        nav = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        nav.pack(fill=X)
        for key, label, icon_name in (
            ("media", "下载任务", "downloads"),
            ("wechat", "视频号", "wechat"),
            ("idm", "IDM 导入", "idm"),
            ("settings", "设置", "settings"),
        ):
            button = _RoundedNavButton(
                nav,
                text=label,
                image=self.ui_icons.get(f"{icon_name}-muted"),
                command=lambda page=key: self._show_page(page),
            )
            button.pack(fill=X, pady=1)
            button._icon_name = icon_name  # type: ignore[attr-defined]
            self.nav_buttons[key] = button
        ttk.Frame(self.sidebar, style="Sidebar.TFrame").pack(fill=BOTH, expand=True)
        self.theme_button = _RoundedNavButton(
            self.sidebar,
            text=self.theme_button_text.get(),
            image=None,
            command=self._toggle_theme,
        )
        self.theme_button.pack(fill=X, pady=(8, 0))
        diagnose = _RoundedNavButton(
            self.sidebar,
            text="导出诊断信息",
            image=self.ui_icons.get("diagnostics-muted"),
            command=lambda: self._show_page("diagnostics"),
        )
        diagnose.pack(fill=X, pady=(8, 0))
        diagnose._icon_name = "diagnostics"  # type: ignore[attr-defined]
        self.nav_buttons["diagnostics"] = diagnose

        self.workspace = ttk.Frame(body, style="Surface.TFrame")
        self.workspace.pack(side=LEFT, fill=BOTH, expand=True)
        self.page_host = ttk.Frame(self.workspace, style="Surface.TFrame")
        self.page_host.pack(fill=BOTH, expand=True)
        self._build_media_tab()
        self._show_page("media")

    def _update_theme_button_text(self) -> None:
        label = (
            "切换到微亮主题"
            if self.ui_theme == "dark"
            else "切换到深色主题"
        )
        _set_var_if_changed(self.theme_button_text, label)
        button = getattr(self, "theme_button", None)
        if button is not None:
            button.set_text(label)

    @staticmethod
    def _theme_color_map(
        old_palette: dict[str, object],
        new_palette: dict[str, object],
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for key, old_value in old_palette.items():
            new_value = new_palette.get(key)
            if isinstance(old_value, str) and isinstance(new_value, str):
                mapping.setdefault(old_value.lower(), new_value)
            elif isinstance(old_value, tuple) and isinstance(new_value, tuple):
                for old_color, new_color in zip(old_value, new_value):
                    if isinstance(old_color, str) and isinstance(new_color, str):
                        mapping.setdefault(old_color.lower(), new_color)
        return mapping

    def _retheme_widget_tree(
        self,
        widget: object,
        color_map: dict[str, str],
    ) -> None:
        def mapped(value: object) -> object:
            if isinstance(value, str):
                return color_map.get(value.lower(), value)
            if isinstance(value, tuple):
                return tuple(mapped(part) for part in value)
            return value

        if isinstance(widget, Canvas):
            canvas_options: dict[str, object] = {}
            for option in ("background", "highlightbackground", "highlightcolor"):
                try:
                    value = str(widget.cget(option))
                except Exception:
                    continue
                replacement = mapped(value)
                if replacement != value:
                    canvas_options[option] = replacement
            if canvas_options:
                try:
                    widget.configure(**canvas_options)
                except Exception:
                    pass
            try:
                for item in widget.find_all():
                    options: dict[str, object] = {}
                    for option in ("fill", "outline"):
                        try:
                            value = str(widget.itemcget(item, option))
                        except Exception:
                            continue
                        replacement = mapped(value)
                        if replacement != value:
                            options[option] = replacement
                    if options:
                        widget.itemconfigure(item, **options)
            except Exception:
                pass

        for attribute in ("_fill", "_border", "_color", "_background", "_state"):
            if not hasattr(widget, attribute):
                continue
            current = getattr(widget, attribute)
            replacement = mapped(current)
            if replacement != current:
                setattr(widget, attribute, replacement)
        if hasattr(widget, "_last_draw_signature"):
            setattr(widget, "_last_draw_signature", None)
        for method_name in ("_queue_draw", "_queue_redraw"):
            method = getattr(widget, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        try:
            children = widget.winfo_children()
        except Exception:
            children = ()
        for child in children:
            self._retheme_widget_tree(child, color_map)

    def _toggle_theme(self) -> None:
        previous = dict(UI)
        target = "dark" if self.ui_theme == "light" else "light"
        self.ui_theme = _set_ui_theme(target)
        try:
            self.database.set_setting("ui_theme", self.ui_theme)
        except Exception:
            pass
        _configure_styles(self.root, self.ui_scale)
        self.root.configure(background=UI["bg"])
        self._retheme_widget_tree(
            self.root,
            self._theme_color_map(previous, UI),
        )
        self._update_theme_button_text()
        _apply_windows_dark_title_bar(
            self.root,
            dark=self.ui_theme == "dark",
        )
        self.root.after_idle(lambda: self.refresh(force=True))

    def _new_page(self, name: str) -> ttk.Frame:
        page = ttk.Frame(self.page_host, style="Surface.TFrame")
        self.page_frames[name] = page
        return page

    def _ensure_page(self, page: str) -> bool:
        if page in self.page_frames:
            return True
        builder = {
            "media": self._build_media_tab,
            "wechat": self._build_wechat_tab,
            "idm": self._build_idm_tab,
            "settings": self._build_settings_tab,
            "diagnostics": self._build_diagnostics_tab,
        }.get(page)
        if builder is None:
            return False
        started = time.perf_counter()
        previous_operation = self.current_ui_operation
        self.current_ui_operation = f"build-page:{page}"
        try:
            builder()
        finally:
            self.current_ui_operation = previous_operation
            self._record_performance(
                "page.build",
                started,
                f"build-page:{page}",
            )
        return page in self.page_frames

    def _queue_page_refresh(self) -> None:
        if not self.ui_ready or self.page_refresh_after_id is not None:
            return
        self.page_refresh_after_id = self.root.after_idle(
            self._refresh_after_page_change,
        )

    def _refresh_after_page_change(self) -> None:
        self.page_refresh_after_id = None
        self.refresh()

    def _prewarm_next_page(self) -> None:
        self.prewarm_after_id = None
        if not self.visible or self.window_interaction_active:
            self.prewarm_after_id = self.root.after(
                500,
                self._prewarm_next_page,
            )
            return
        while self.page_prewarm_queue:
            page = self.page_prewarm_queue.pop(0)
            if page not in self.page_frames:
                self._ensure_page(page)
                break
        if self.page_prewarm_queue:
            self.prewarm_after_id = self.root.after(
                250,
                self._prewarm_next_page,
            )

    def _show_page(self, page: str) -> None:
        started = time.perf_counter()
        previous_operation = self.current_ui_operation
        self.current_ui_operation = f"show-page:{page}"
        try:
            self._show_page_impl(page)
        finally:
            self.current_ui_operation = previous_operation
            self._record_performance(
                "page.show",
                started,
                f"show-page:{page}",
            )

    def _show_page_impl(self, page: str) -> None:
        if not self._ensure_page(page):
            return
        titles = {
            "media": "下载任务",
            "wechat": "视频号",
            "idm": "IDM 导入",
            "settings": "设置",
            "diagnostics": "诊断",
        }
        for name, frame in self.page_frames.items():
            if name == page:
                frame.pack(fill=BOTH, expand=True)
            else:
                frame.pack_forget()
        for name, button in self.nav_buttons.items():
            selected = name == page
            icon_name = getattr(button, "_icon_name", "")
            button.set_selected(
                selected,
                image=self.ui_icons.get(
                    f"{icon_name}-{'active' if selected else 'muted'}"
                ),
            )
        self.current_page = page
        _set_var_if_changed(self.page_title_text, titles.get(page, page))
        # Paned windows that were built while their page was hidden have a
        # one-pixel geometry and Tk clamps their sash to zero. Restore only
        # the page that has just become visible; touching the hidden pages
        # here would collapse them again before the next navigation.
        self.root.after_idle(self._apply_mode_to_page_layouts)
        self._queue_page_refresh()

    def _queue_responsive_layout(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        self.window_interaction_active = True
        if self.window_settle_after_id is not None:
            self.root.after_cancel(self.window_settle_after_id)
        self.window_settle_after_id = self.root.after(
            180,
            self._finish_window_interaction,
        )

        size = (
            max(1, int(getattr(event, "width", 0) or self.root.winfo_width())),
            max(1, int(getattr(event, "height", 0) or self.root.winfo_height())),
        )
        if size == self.last_root_size:
            return
        self.last_root_size = size
        if self.layout_after_id is not None:
            self.root.after_cancel(self.layout_after_id)
        self.layout_after_id = self.root.after(90, self._apply_responsive_layout)

    def _finish_window_interaction(self) -> None:
        self.window_settle_after_id = None
        self.window_interaction_active = False
        self._apply_responsive_layout()
        self.root.after_idle(lambda: _redraw_windows_client_area(self.root))
        if self.pending_refresh_force:
            self.pending_refresh_force = False
            self.root.after_idle(lambda: self.refresh(force=True))

    def _apply_responsive_layout(self) -> None:
        started = time.perf_counter()
        try:
            self._apply_responsive_layout_impl()
        finally:
            self._record_performance(
                "window.configure",
                started,
                "responsive-layout",
            )

    def _apply_responsive_layout_impl(self) -> None:
        if self.layout_after_id is not None:
            try:
                self.root.after_cancel(self.layout_after_id)
            except Exception:
                pass
        self.layout_after_id = None
        width = max(self.root.winfo_width(), 1)
        logical_width = max(1, round(width / self.ui_scale))
        mode = _layout_mode_for_width(logical_width)
        mode_changed = mode != self.layout_mode
        self.layout_mode = mode
        compact = mode == LAYOUT_COMPACT
        signature = (mode, compact)
        if signature == self.last_responsive_signature and self.responsive_initialized:
            return
        self.last_responsive_signature = signature
        self.sidebar.configure(
            width=(
                self.metrics["sidebar_compact_width"]
                if compact
                else self.metrics["sidebar_width"]
            )
        )
        self.topbar.configure(
            height=self.metrics["topbar_height"]
        )
        self.topbar_statuses.grid(
            row=0,
            column=0,
            sticky="e",
            padx=(12, 16),
            pady=0,
        )
        if hasattr(self, "settings_nav"):
            self.settings_nav.configure(
                width=(
                    self.metrics["secondary_nav_compact_width"]
                    if compact
                    else self.metrics["secondary_nav_width"]
                )
            )
        if mode_changed or not self.responsive_initialized:
            self.responsive_initialized = True
            self.root.after_idle(self._apply_mode_to_page_layouts)

    def _apply_mode_to_page_layouts(self) -> None:
        compact = self.layout_mode == LAYOUT_COMPACT
        metrics = getattr(self, "metrics", METRICS)
        ui_scale = getattr(self, "ui_scale", 1.0)
        split_name = {
            "media": "media_split",
            "wechat": "wechat_split",
            "idm": "idm_split",
        }.get(self.current_page)
        if not split_name:
            return
        split = getattr(self, split_name, None)
        if split is None:
            return
        if self.current_page == "idm":
            target = round((250 if compact else 330) * ui_scale)
        else:
            target = (
                metrics["master_compact_width"]
                if compact
                else metrics["master_width"]
            )
        try:
            split.sashpos(0, target)
        except Exception:
            pass

    def _build_media_tab(self) -> None:
        tab = self._new_page("media")
        self.media_split = ttk.Panedwindow(tab, orient="horizontal")
        self.media_split.pack(fill=BOTH, expand=True)
        compact = self.layout_mode == LAYOUT_COMPACT
        master_width = (
            self.metrics["master_compact_width"] if compact else self.metrics["master_width"]
        )
        sidebar_width = (
            self.metrics["sidebar_compact_width"] if compact else self.metrics["sidebar_width"]
        )
        detail_width = max(
            1,
            self.initial_client_width - sidebar_width - master_width,
        )
        master = ttk.Frame(
            self.media_split,
            style="Surface.TFrame",
            width=master_width,
        )
        detail = ttk.Frame(
            self.media_split,
            style="SurfaceRaised.TFrame",
            width=detail_width,
        )
        self.media_split.add(master, weight=3)
        self.media_split.add(detail, weight=2)

        toolbar = ttk.Frame(
            master,
            style="Surface.TFrame",
            padding=(14, 0),
            height=max(36, round(36 * self.ui_scale)),
        )
        toolbar.pack(fill=X)
        toolbar.pack_propagate(False)
        ttk.Label(
            toolbar,
            text="媒体任务",
            style="MediaToolbarTitle.TLabel",
        ).pack(side=LEFT)
        self.media_clear_button = _RoundedButton(
            toolbar,
            text="清除完成",
            style="MediaToolbar.TButton",
            command=self.clear_media_history,
        )
        self.media_clear_button.pack(side=RIGHT)

        self.plan_card_list = _ScrollableCardList(
            master,
            background=UI["surface"],
            initial_width=master_width,
        )
        self.plan_card_list.pack(fill=BOTH, expand=True)
        self.plan_empty_text = StringVar(value="暂无媒体任务")
        self.plan_empty_label = ttk.Label(
            self.plan_card_list.content,
            textvariable=self.plan_empty_text,
            style="Muted.TLabel",
            anchor="center",
            justify="center",
            image=self.ui_icons.get("downloads-muted"),
            compound="top",
            padding=(16, 40),
        )

        self.media_detail_scroller = _VerticalScrolledFrame(
            detail,
            padding=(20, 14),
            style="SurfaceRaised.TFrame",
            background=UI["surface_raised"],
            initial_width=detail_width,
        )
        self.media_detail_scroller.pack(fill=BOTH, expand=True)
        detail_content = self.media_detail_scroller.content

        self.plan_title_text = StringVar(value="选择一项任务查看详情")
        self.plan_status_text = StringVar(value="")
        self.plan_source_text = StringVar(value="")
        self.plan_file_text = StringVar(value="")
        self.plan_progress_text = StringVar(value="—")
        self.plan_size_text = StringVar(value="—")
        self.plan_domain_text = StringVar(value="—")
        self.plan_detail_text = StringVar(value="")
        self.plan_error_text = StringVar(value="")

        header = ttk.Frame(detail_content, style="SurfaceRaised.TFrame")
        header.pack(fill=X, pady=(0, 27))
        header.columnconfigure(0, weight=1)
        heading = ttk.Frame(header, style="SurfaceRaised.TFrame")
        heading.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.plan_title_label = ttk.Label(
            heading,
            textvariable=self.plan_title_text,
            style="Section.TLabel",
            anchor="w",
        )
        self.plan_title_label.pack(fill=X)
        _Tooltip(
            self.plan_title_label,
            lambda: str(
                (self.selected_plan() or {}).get("title")
                or (self.selected_plan() or {}).get("output_name")
                or ""
            ),
        )
        _DynamicWrapLabel(
            heading,
            textvariable=self.plan_source_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=720,
        ).pack(fill=X, pady=(2, 0))

        actions = ttk.Frame(header, style="SurfaceRaised.TFrame")
        actions.grid(row=0, column=1, sticky="ne")
        self.plan_secondary_actions = ttk.Frame(
            detail_content,
            style="SurfaceRaised.TFrame",
        )
        self.plan_action_buttons = {
            "stop": _RoundedButton(
                    actions,
                    text="停止",
                    image=self.ui_icons.get("stop-danger"),
                    kind="danger",
                    command=self.stop_selected_plan,
                    width=68,
            ),
            "retry": _RoundedButton(
                    actions,
                    text="重试",
                    image=self.ui_icons.get("retry-white"),
                    kind="accent",
                    command=self.retry_selected_plan,
                    width=68,
            ),
            "import": _RoundedButton(
                    actions,
                    text="补导 Eagle",
                    image=self.ui_icons.get("import-white"),
                    kind="accent",
                    command=self.import_selected_plan,
                    width=104,
            ),
            "open": _RoundedButton(
                    self.plan_secondary_actions,
                    text="文件位置",
                    image=self.ui_icons.get("folder-muted"),
                    kind="quiet",
                    command=self.open_plan_location,
                    width=92,
            ),
            "source": _RoundedButton(
                    self.plan_secondary_actions,
                    text="来源网页",
                    image=self.ui_icons.get("globe-muted"),
                    kind="quiet",
                    command=self.open_plan_source,
                    width=92,
            ),
        }
        for name in ("stop", "retry", "import"):
            self.plan_action_buttons[name].pack(side=LEFT, padx=(0, 6))
        for name in ("open", "source"):
            self.plan_action_buttons[name].pack(side=LEFT, padx=(0, 6))
        _bind_responsive_header_layout(header, heading, actions)

        self.preview_surface = _RoundedPanel(
            detail_content,
            fill=UI["surface"],
            outer_background=UI["surface_raised"],
            style="Soft.TFrame",
            radius=RADII["panel"],
            border=UI["border"],
            border_width=1,
            height=252,
            inset=3,
        )
        self.preview_surface.pack(anchor="center")
        self.preview_label = ttk.Label(
            self.preview_surface.inner,
            text="选择任务后显示本机预览",
            anchor="center",
            background=UI["surface"],
            foreground=UI["text_muted"],
            image=self.ui_icons.get("downloads-muted"),
            compound="top",
        )
        self.preview_label.pack(fill=BOTH, expand=True)

        _bind_coalesced_aspect_resize(
            detail_content,
            self.preview_surface,
            maximum_width=self.metrics["preview_max_width"],
        )

        info = ttk.Frame(detail_content, style="SurfaceRaised.TFrame")
        info.pack(fill=X, pady=(14, 0))
        info.columnconfigure(0, weight=1)
        info.columnconfigure(1, weight=1)
        for index, (label, variable) in enumerate(
            (
                ("状态", self.plan_status_text),
                ("进度", self.plan_progress_text),
                ("大小", self.plan_size_text),
                ("来源", self.plan_domain_text),
            )
        ):
            row, column = divmod(index, 2)
            cell = ttk.Frame(info, style="SurfaceRaised.TFrame")
            cell.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 12 if column == 0 else 0),
                pady=(0 if row == 0 else 10, 0),
            )
            ttk.Label(cell, text=label, style="RaisedMuted.TLabel").pack(anchor="w")
            _DynamicWrapLabel(
                cell,
                textvariable=variable,
                style=(
                    "DetailPrimaryValue.TLabel"
                    if index in (0, 1)
                    else "DetailValue.TLabel"
                ),
            ).pack(fill=X, pady=(3, 0))

        self.plan_progress = _RoundedProgressBar(
            detail_content,
            maximum=100,
            height=8,
            background=UI["surface_raised"],
        )
        self.plan_progress.pack(fill=X, pady=(8, 10))

        self.plan_phase_surface = _RoundedPanel(
            detail_content,
            fill=UI["surface"],
            outer_background=UI["surface_raised"],
            style="Surface.TFrame",
            radius=RADII["card"],
            border=UI["border"],
            border_width=1,
            height=42,
            inset=7,
        )
        self.plan_phase_surface.pack(fill=X)
        self.plan_phase_label = _DynamicWrapLabel(
            self.plan_phase_surface.inner,
            textvariable=self.plan_detail_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=720,
        )
        self.plan_phase_label.pack(fill=X, pady=(3, 0))

        _DynamicWrapLabel(
            detail_content,
            textvariable=self.plan_file_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=720,
        ).pack(fill=X, pady=(10, 0))

        self.plan_secondary_actions.pack(fill=X, pady=(10, 0))
        self.plan_error_label = _DynamicWrapLabel(
            detail_content,
            textvariable=self.plan_error_text,
            style="Error.TLabel",
            justify=LEFT,
            maximum=720,
            padding=(10, 8),
        )
        self.plan_error_label.pack(fill=X, pady=(8, 0))

    def _build_idm_tab(self) -> None:
        tab = self._new_page("idm")
        toolbar = ttk.Frame(tab, style="Surface.TFrame", padding=(16, 7))
        toolbar.pack(fill=X)
        self.idm_clear_button = _RoundedButton(
            toolbar,
            text="清除完成",
            style="Link.TButton",
            command=self.clear_history,
        )
        self.idm_clear_button.pack(side=RIGHT)
        _RoundedButton(
            toolbar,
            text="刷新",
            style="Link.TButton",
            command=lambda: self.refresh(force=True),
        ).pack(side=RIGHT, padx=(0, 4))
        self.idm_next_button = _RoundedButton(
            toolbar,
            text="›",
            width=2,
            style="Link.TButton",
            command=lambda: self._change_idm_page(1),
        )
        self.idm_next_button.pack(side=RIGHT)
        self.idm_page_text = StringVar(value="1/1")
        ttk.Label(
            toolbar,
            textvariable=self.idm_page_text,
            style="SectionOnSurface.TLabel",
        ).pack(side=RIGHT, padx=3)
        self.idm_previous_button = _RoundedButton(
            toolbar,
            text="‹",
            width=2,
            style="Link.TButton",
            command=lambda: self._change_idm_page(-1),
        )
        self.idm_previous_button.pack(side=RIGHT)
        ttk.Label(
            toolbar,
            text="IDM 导入",
            style="SectionOnSurface.TLabel",
        ).pack(side=LEFT)

        self.idm_eagle_hint_text = StringVar(
            value=str(_eagle_experience(False)["idm_hint"])
        )
        _DynamicWrapLabel(
            tab,
            textvariable=self.idm_eagle_hint_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=900,
            padding=(16, 7),
        ).pack(fill=X)

        self.idm_split = ttk.Panedwindow(tab, orient="vertical")
        self.idm_split.pack(fill=BOTH, expand=True)
        table_host = ttk.Frame(self.idm_split, style="Surface.TFrame")
        detail_host = ttk.Frame(self.idm_split, style="SurfaceRaised.TFrame")
        self.idm_split.add(table_host, weight=3)
        self.idm_split.add(detail_host, weight=2)

        columns = ("time", "status", "file", "source", "message")
        self.job_tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=12,
        )
        self.job_tree.heading("time", text="时间")
        self.job_tree.heading("status", text="状态")
        self.job_tree.heading("file", text="文件")
        self.job_tree.heading("source", text="来源网站")
        self.job_tree.heading("message", text="说明")
        self.job_tree.column("time", anchor="center")
        self.job_tree.column("status", anchor="w")
        self.job_tree.column("file", anchor="w")
        self.job_tree.column("source", anchor="w")
        self.job_tree.column("message", anchor="w")
        job_scrollbar = _RoundedScrollbar(
            table_host,
            command=self.job_tree.yview,
            background=UI["surface"],
        )
        self.job_tree.configure(yscrollcommand=job_scrollbar.set)
        job_scrollbar.pack(side=RIGHT, fill=Y)
        self.job_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.idm_column_layout = _ResponsiveTreeColumns(
            self.job_tree,
            [
                ("time", 100, 0),
                ("status", 112, 0),
                ("file", 180, 2),
                ("source", 110, 1),
                ("message", 180, 2),
            ],
            compact_minimums={
                "time": 90,
                "status": 104,
                "file": 140,
                "source": 90,
                "message": 140,
            },
        )
        self.job_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._update_idm_detail()
        )
        self.job_tree.bind("<Button-3>", self._show_job_context_menu, add="+")
        self.job_tree.bind("<Shift-F10>", self._show_job_context_menu, add="+")

        self.idm_detail_scroller = _VerticalScrolledFrame(
            detail_host,
            padding=(16, 12),
            style="SurfaceRaised.TFrame",
            background=UI["surface_raised"],
            initial_width=self.initial_client_width,
        )
        self.idm_detail_scroller.pack(fill=BOTH, expand=True)
        detail = self.idm_detail_scroller.content
        self.idm_detail_title_text = StringVar(value="选择一条记录查看完整内容")
        self.idm_detail_status_text = StringVar(value="")
        self.idm_detail_file_text = StringVar(value="")
        self.idm_detail_source_text = StringVar(value="")
        self.idm_detail_message_text = StringVar(value="")

        heading = ttk.Frame(detail, style="SurfaceRaised.TFrame")
        heading.pack(fill=X)
        _DynamicWrapLabel(
            heading,
            textvariable=self.idm_detail_title_text,
            style="Section.TLabel",
            maximum=900,
        ).pack(fill=X)
        _DynamicWrapLabel(
            heading,
            textvariable=self.idm_detail_status_text,
            style="RaisedMuted.TLabel",
            maximum=900,
        ).pack(fill=X, pady=(3, 0))

        actions = _ResponsiveActionGroup(
            detail,
            compact_breakpoint=820,
            vertical_breakpoint=320,
            style="SurfaceRaised.TFrame",
        )
        actions.pack(fill=X, pady=(10, 8))
        self.idm_action_buttons = {
            "retry": actions.add(
                _RoundedButton(
                    actions,
                    text="重试导入",
                    image=self.ui_icons.get("retry-white"),
                    compound=LEFT,
                    style="Accent.TButton",
                    command=self.retry_selected,
                )
            ),
            "open": actions.add(
                _RoundedButton(
                    actions,
                    text="原文件位置",
                    image=self.ui_icons.get("folder-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.open_file_location,
                )
            ),
            "source": actions.add(
                _RoundedButton(
                    actions,
                    text="可靠来源",
                    image=self.ui_icons.get("globe-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.open_source,
                )
            ),
            "assign": actions.add(
                _RoundedButton(
                    actions,
                    text="补充 / 修改来源",
                    image=self.ui_icons.get("source-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.assign_source,
                )
            ),
            "remove": actions.add(
                _RoundedButton(
                    actions,
                    text="清理记录",
                    style="Danger.TButton",
                    command=self.remove_selected_job,
                )
            ),
        }

        for label, variable in (
            ("完整文件", self.idm_detail_file_text),
            ("可靠来源", self.idm_detail_source_text),
            ("说明", self.idm_detail_message_text),
        ):
            ttk.Label(detail, text=label, style="RaisedMuted.TLabel").pack(
                anchor="w",
                pady=(7, 0),
            )
            _DynamicWrapLabel(
                detail,
                textvariable=variable,
                style="Section.TLabel",
                justify=LEFT,
                maximum=900,
            ).pack(fill=X, pady=(2, 0))

    def _build_wechat_tab(self) -> None:
        tab = self._new_page("wechat")
        self.wechat_status_text = StringVar(value="视频号捕获已关闭")
        self.wechat_action_text = StringVar(value="开始捕获")
        self.wechat_split = ttk.Panedwindow(tab, orient="horizontal")
        self.wechat_split.pack(fill=BOTH, expand=True)
        compact = self.layout_mode == LAYOUT_COMPACT
        master_width = (
            self.metrics["master_compact_width"] if compact else self.metrics["master_width"]
        )
        sidebar_width = (
            self.metrics["sidebar_compact_width"] if compact else self.metrics["sidebar_width"]
        )
        detail_width = max(1, self.initial_client_width - sidebar_width - master_width)
        master = ttk.Frame(
            self.wechat_split,
            style="Surface.TFrame",
            width=master_width,
        )
        detail = ttk.Frame(
            self.wechat_split,
            style="SurfaceRaised.TFrame",
            width=detail_width,
        )
        self.wechat_split.add(master, weight=3)
        self.wechat_split.add(detail, weight=2)

        capture = ttk.Frame(master, style="Surface.TFrame", padding=(16, 10))
        capture.pack(fill=X)
        ttk.Label(
            capture,
            text="视频号捕获",
            style="SectionOnSurface.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            capture,
            textvariable=self.wechat_status_text,
            style="Muted.TLabel",
            justify=LEFT,
        ).pack(fill=X, pady=(5, 8))
        self.wechat_action_button = _RoundedButton(
            capture,
            textvariable=self.wechat_action_text,
            image=self.ui_icons.get("play-white"),
            compound=LEFT,
            command=self.toggle_wechat_capture,
            style="Accent.TButton",
        )
        self.wechat_action_button.pack(fill=X)
        self.wechat_proxy_repair_button = _RoundedButton(
            capture,
            text="修复代理冲突",
            image=self.ui_icons.get("settings-muted"),
            compound=LEFT,
            command=self.repair_wechat_proxy_conflict,
            style="Quiet.TButton",
        )
        self.wechat_proxy_repair_button.pack(fill=X, pady=(7, 0))
        _DynamicWrapLabel(
            capture,
            text="正常代理会自动兼容；遇到失效代理或代理被其他软件抢占时，可使用“修复代理冲突”。",
            style="Muted.TLabel",
            justify=LEFT,
        ).pack(fill=X, pady=(7, 0))

        candidate_toolbar = ttk.Frame(master, style="Surface.TFrame", padding=(16, 6))
        candidate_toolbar.pack(fill=X)
        self.wechat_candidate_count_text = StringVar(value="当前视频 · 等待识别")
        ttk.Label(
            candidate_toolbar,
            textvariable=self.wechat_candidate_count_text,
            style="SectionOnSurface.TLabel",
        ).pack(side=LEFT)
        _RoundedButton(
            candidate_toolbar,
            text="清空",
            command=self.clear_wechat_candidates,
            style="Link.TButton",
        ).pack(side=RIGHT)
        self.wechat_next_button = _RoundedButton(
            candidate_toolbar,
            text="›",
            width=2,
            command=lambda: self._change_wechat_page(1),
            style="Link.TButton",
        )
        self.wechat_page_text = StringVar(value="1/1")
        self.wechat_page_label = ttk.Label(
            candidate_toolbar,
            textvariable=self.wechat_page_text,
            style="Muted.TLabel",
        )
        self.wechat_previous_button = _RoundedButton(
            candidate_toolbar,
            text="‹",
            width=2,
            command=lambda: self._change_wechat_page(-1),
            style="Link.TButton",
        )

        self.wechat_card_list = _ScrollableCardList(
            master,
            background=UI["surface"],
            initial_width=master_width,
        )
        self.wechat_card_list.pack(fill=BOTH, expand=True)

        self.wechat_detail_scroller = _VerticalScrolledFrame(
            detail,
            padding=(20, 14),
            style="SurfaceRaised.TFrame",
            background=UI["surface_raised"],
            initial_width=detail_width,
        )
        self.wechat_detail_scroller.pack(fill=BOTH, expand=True)
        detail_content = self.wechat_detail_scroller.content

        self.wechat_preview_surface = ttk.Frame(
            detail_content,
            style="Soft.TFrame",
            width=self.metrics["preview_max_width"],
            height=252,
        )
        self.wechat_preview_surface.pack(anchor="center")
        self.wechat_preview_surface.pack_propagate(False)
        self.wechat_preview_label = ttk.Label(
            self.wechat_preview_surface,
            text="封面将在识别后显示",
            anchor="center",
            compound="top",
            background=UI["surface_raised"],
            foreground=UI["text_muted"],
            image=self.ui_icons.get("wechat-muted"),
        )
        self.wechat_preview_label.pack(fill=BOTH, expand=True)
        self.wechat_detail_text = StringVar(value="开始捕获后，在微信中打开视频号内容。")
        self.wechat_quality_text = StringVar(value="")
        self.wechat_variant_text = StringVar(value="")
        self.wechat_author_text = StringVar(value="")
        self.wechat_full_metadata_text = StringVar(value="")
        self.wechat_title_label = _DynamicWrapLabel(
            detail_content,
            textvariable=self.wechat_detail_text,
            style="Section.TLabel",
            justify=LEFT,
            maximum=720,
        )
        self.wechat_title_label.pack(fill=X, pady=(14, 0))
        _Tooltip(
            self.wechat_title_label,
            lambda: str(
                (self._selected_wechat_candidate() or {}).get("title") or ""
            ),
        )
        _DynamicWrapLabel(
            detail_content,
            textvariable=self.wechat_author_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=720,
        ).pack(fill=X, pady=(3, 0))
        _DynamicWrapLabel(
            detail_content,
            textvariable=self.wechat_quality_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=720,
        ).pack(fill=X, pady=(6, 0))
        ttk.Label(
            detail_content,
            text="下载质量",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w", pady=(12, 4))
        self.wechat_variant_box = _RoundedCombobox(
            detail_content,
            state="readonly",
            textvariable=self.wechat_variant_text,
            values=(),
        )
        self.wechat_variant_box.pack(fill=X)
        self.wechat_import_to_eagle = BooleanVar(value=True)
        delivery = _ResponsiveActionGroup(
            detail_content,
            compact_breakpoint=520,
            vertical_breakpoint=620,
            style="SurfaceRaised.TFrame",
        )
        delivery.pack(fill=X, pady=(14, 0))
        self.wechat_delivery_buttons = {
            "eagle": delivery.add(
                _RoundedButton(
                    delivery,
                    text="导入 Eagle（完成后删除本机副本）",
                    image=self.ui_icons.get("import-white"),
                    compound=LEFT,
                    command=lambda: self._submit_wechat_delivery(True),
                    style="Accent.TButton",
                )
            ),
            "local": delivery.add(
                _RoundedButton(
                    delivery,
                    text="仅下载并保留本机文件",
                    image=self.ui_icons.get("downloads-muted"),
                    compound=LEFT,
                    command=lambda: self._submit_wechat_delivery(False),
                    style="Quiet.TButton",
                )
            ),
        }
        _DynamicWrapLabel(
            detail_content,
            textvariable=self.wechat_full_metadata_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=720,
        ).pack(fill=X, pady=(10, 0))

        _bind_coalesced_aspect_resize(
            detail_content,
            self.wechat_preview_surface,
            maximum_width=self.metrics["preview_max_width"],
        )

    def _build_settings_tab(self) -> None:
        tab = self._new_page("settings")

        self.settings_nav = ttk.Frame(
            tab,
            style="Sidebar.TFrame",
            width=self.metrics["secondary_nav_width"],
        )
        self.settings_nav.pack(side=LEFT, fill=Y)
        self.settings_nav.pack_propagate(False)
        self.settings_tab_buttons: dict[str, ttk.Button] = {}
        self.settings_sub_tabs: dict[str, ttk.Frame] = {}
        self.settings_sub_tab_builders = {
            "pairing": self._build_settings_pairing,
            "sites": self._build_settings_sites,
            "network": self._build_settings_network,
            "storage": self._build_settings_storage,
            "updates": self._build_settings_updates,
        }
        for key, label in (
            ("pairing", "浏览器连接"),
            ("sites", "网站规则"),
            ("network", "网络代理"),
            ("storage", "文件管理"),
            ("updates", "更新"),
        ):
            btn = _RoundedButton(
                self.settings_nav,
                text=label,
                style="Nav.TButton",
                command=lambda k=key: self._settings_show_tab(k),
            )
            btn.pack(fill=X, pady=1)
            self.settings_tab_buttons[key] = btn

        self.settings_panel = ttk.Frame(tab, style="Surface.TFrame")
        self.settings_panel.pack(side=LEFT, fill=BOTH, expand=True)

        self._settings_show_tab(self.current_settings_tab)

    def _settings_show_tab(self, name: str) -> None:
        if name not in self.settings_sub_tabs:
            builder = self.settings_sub_tab_builders.get(name)
            if builder is None:
                return
            builder()
        self.current_settings_tab = name
        for key, frame in self.settings_sub_tabs.items():
            if key == name:
                frame.pack(fill=BOTH, expand=True)
            else:
                frame.pack_forget()
        for key, button in self.settings_tab_buttons.items():
            _configure_if_changed(
                button,
                style="NavSelected.TButton" if key == name else "Nav.TButton",
            )
        if self.ui_ready and self.current_page == "settings":
            self._refresh_settings()

    def _build_settings_pairing(self) -> None:
        scroller = _VerticalScrolledFrame(
            self.settings_panel,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        self.settings_sub_tabs["pairing"] = scroller
        content = scroller.content
        ttk.Label(
            content,
            text="浏览器连接",
            style="Title.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            content,
            text="留底浏览器扩展会在本机自动连接留底桌面端，无需输入配对码。",
            style="Muted.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(6, 14))

        code_surface = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(20, 18),
        )
        code_surface.pack(fill=X)
        ttk.Label(
            code_surface,
            text="连接状态",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            code_surface,
            textvariable=self.pairing_text,
            style="Raised.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(8, 0))

    def _build_settings_sites(self) -> None:
        scroller = _VerticalScrolledFrame(
            self.settings_panel,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        self.settings_sub_tabs["sites"] = scroller
        content = scroller.content
        ttk.Label(content, text="网站规则", style="Title.TLabel").pack(anchor="w")
        _DynamicWrapLabel(
            content,
            textvariable=self.settings_site_summary_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(6, 12))

        add_row = ttk.Frame(content, style="Surface.TFrame")
        add_row.pack(fill=X, pady=(0, 10))
        self.settings_site_input = StringVar(value="")
        self.settings_site_entry = ttk.Entry(
            add_row,
            textvariable=self.settings_site_input,
        )
        self.settings_site_entry.pack(side=LEFT, fill=X, expand=True)
        _RoundedButton(
            add_row,
            text="新增并启用",
            image=self.ui_icons.get("plus-white"),
            compound=LEFT,
            style="Accent.TButton",
            command=self._settings_add_rule,
        ).pack(side=RIGHT, padx=(8, 0))

        tree_host = ttk.Frame(content, style="Surface.TFrame")
        tree_host.pack(fill=BOTH, expand=True)
        self.settings_site_tree = ttk.Treeview(
            tree_host,
            columns=("domain", "status", "subdomains", "updated"),
            show="headings",
            selectmode="browse",
            height=9,
        )
        for name, label in (("domain", "域名"), ("status", "状态"), ("subdomains", "子域名"), ("updated", "修改时间")):
            self.settings_site_tree.heading(name, text=label)
        self.settings_site_tree.column("status", anchor="center")
        self.settings_site_tree.column("subdomains", anchor="center")
        self.settings_site_tree.column("updated", anchor="center")
        site_scroll = _RoundedScrollbar(
            tree_host,
            command=self.settings_site_tree.yview,
            background=UI["surface"],
        )
        self.settings_site_tree.configure(yscrollcommand=site_scroll.set)
        site_scroll.pack(side=RIGHT, fill=Y)
        self.settings_site_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.settings_site_column_layout = _ResponsiveTreeColumns(
            self.settings_site_tree,
            [
                ("domain", 180, 2),
                ("status", 72, 0),
                ("subdomains", 84, 0),
                ("updated", 110, 1),
            ],
            compact_minimums={
                "domain": 150,
                "status": 64,
                "subdomains": 72,
                "updated": 96,
            },
        )

        site_actions = _ResponsiveActionGroup(
            content,
            compact_breakpoint=680,
            vertical_breakpoint=300,
            style="Surface.TFrame",
        )
        site_actions.pack(fill=X)
        for label, command in (
            ("启用 / 停用", self._settings_toggle_rule),
            ("切换子域名", self._settings_toggle_subdomains),
            ("删除", self._settings_delete_rule),
            ("清空", self._settings_clear_rules),
        ):
            site_actions.add(
                _RoundedButton(
                    site_actions,
                    text=label,
                    style="Danger.TButton" if label in {"删除", "清空"} else "Quiet.TButton",
                    command=command,
                )
            )

    def _build_settings_network(self) -> None:
        scroller = _VerticalScrolledFrame(
            self.settings_panel,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        self.settings_sub_tabs["network"] = scroller
        content = scroller.content
        ttk.Label(content, text="网络代理", style="Title.TLabel").pack(anchor="w")
        _DynamicWrapLabel(
            content,
            text="仅下载网络会使用这里的设置；本机服务与 Eagle 始终保持直连。",
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(6, 12))
        configuration = self.media.network_proxy.configuration()
        self.settings_proxy_mode = StringVar(value=configuration["mode"])
        self.settings_proxy_manual = StringVar(value=configuration["manualUrl"])
        modes = ttk.Frame(content, style="Surface.TFrame")
        modes.pack(fill=X)
        for value, title, description in (
            ("auto", "自动（推荐）", "跟随 Windows 系统代理，失败时最多切换一次线路。"),
            ("direct", "始终直连", "不使用任何代理，适合网络可直接访问来源网站。"),
            ("manual", "手动 HTTP / Mixed 代理", "使用代理软件显示的 HTTP 或 Mixed 端口。"),
        ):
            mode_card = ttk.Frame(
                modes,
                style="Soft.TFrame",
                padding=(12, 10),
            )
            mode_card.pack(fill=X, pady=(0, 8))
            ttk.Radiobutton(
                mode_card,
                text=title,
                value=value,
                variable=self.settings_proxy_mode,
                command=self._settings_proxy_mode_changed,
            ).pack(anchor="w")
            _DynamicWrapLabel(
                mode_card,
                text=description,
                style="RaisedMuted.TLabel",
                justify=LEFT,
                maximum=760,
            ).pack(fill=X, padx=(22, 0), pady=(3, 0))

        manual = ttk.Frame(content, style="Surface.TFrame")
        manual.pack(fill=X)
        ttk.Label(manual, text="代理地址", style="Muted.TLabel").pack(anchor="w")
        self.settings_proxy_entry = ttk.Entry(manual, textvariable=self.settings_proxy_manual)
        self.settings_proxy_entry.pack(fill=X, pady=(5, 0))
        _RoundedButton(
            content,
            text="保存并检测",
            style="Accent.TButton",
            command=self._settings_save_proxy,
        ).pack(anchor="w", pady=(10, 0))
        _DynamicWrapLabel(
            content,
            textvariable=self.settings_proxy_status_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(10, 0))
        self._settings_proxy_mode_changed()

    def _build_settings_storage(self) -> None:
        scroller = _VerticalScrolledFrame(
            self.settings_panel,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        self.settings_sub_tabs["storage"] = scroller
        content = scroller.content
        ttk.Label(content, text="文件管理", style="Title.TLabel").pack(anchor="w")
        _DynamicWrapLabel(
            content,
            text="管理本机下载副本，以及留底桌面端创建的临时文件、预览和旧版日志。",
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(6, 12))

        retention_card = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(14, 12),
        )
        retention_card.pack(fill=X, pady=(0, 12))
        ttk.Label(
            retention_card,
            text="导入后的本机副本",
            style="Section.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            retention_card,
            text="仅管理留底桌面端创建的文件；IDM 原文件不会移动或删除。",
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(4, 10))

        row = ttk.Frame(retention_card, style="Soft.TFrame")
        row.pack(fill=X)
        ttk.Label(row, text="自动清理", style="RaisedMuted.TLabel").pack(side=LEFT)
        self.storage_retention_days = StringVar()
        retention_spinbox = ttk.Spinbox(
            row,
            from_=0,
            to=365,
            increment=1,
            width=6,
            textvariable=self.storage_retention_days,
            validate="key",
            validatecommand=(self.root.register(self._validate_digits), "%P"),
            style="Settings.TSpinbox",
        )
        retention_spinbox.pack(side=LEFT, padx=(12, 7))
        ttk.Label(row, text="天后", style="RaisedMuted.TLabel").pack(side=LEFT)
        ttk.Label(
            retention_card,
            text="设为 0 表示始终保留。",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        cache_card = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(14, 12),
        )
        cache_card.pack(fill=X, pady=(0, 12))
        ttk.Label(
            cache_card,
            text="程序缓存",
            style="Section.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            cache_card,
            text="清理临时下载、任务预览和旧版下载日志；已完成目录不会清理，活动任务、IDM 原文件和用户文件始终保留。",
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(4, 10))

        self.cache_summary_text = StringVar(value="正在统计缓存占用…")
        _DynamicWrapLabel(
            cache_card,
            textvariable=self.cache_summary_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(0, 10))

        cache_row = ttk.Frame(cache_card, style="Soft.TFrame")
        cache_row.pack(fill=X)
        ttk.Label(cache_row, text="自动清理", style="RaisedMuted.TLabel").pack(side=LEFT)
        self.cache_retention_days = StringVar()
        cache_spinbox = ttk.Spinbox(
            cache_row,
            from_=0,
            to=365,
            increment=1,
            width=6,
            textvariable=self.cache_retention_days,
            validate="key",
            validatecommand=(self.root.register(self._validate_digits), "%P"),
            style="Settings.TSpinbox",
        )
        cache_spinbox.pack(side=LEFT, padx=(12, 7))
        ttk.Label(cache_row, text="天后", style="RaisedMuted.TLabel").pack(side=LEFT)
        ttk.Label(
            cache_card,
            text="设为 0 表示关闭自动缓存清理；手动清理仍然可用。",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        self.cache_clear_button = _RoundedButton(
            cache_card,
            text="立即清理缓存",
            style="Secondary.TButton",
            command=self.clear_program_cache,
        )
        self.cache_clear_button.pack(anchor="w", pady=(12, 0))

        self.storage_feedback_text = StringVar(value="")
        _DynamicWrapLabel(
            content,
            textvariable=self.storage_feedback_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(9, 0))

        _RoundedButton(
            content,
            text="保存设置",
            style="Accent.TButton",
            command=self._save_storage_settings,
        ).pack(anchor="w", pady=(12, 0))

        self._load_storage_settings()

    @staticmethod
    def _validate_digits(value: str) -> bool:
        return value == "" or value.isdigit()

    def _load_storage_settings(self) -> None:
        days = _bounded_retention_days(
            self.database.get_setting("file_retention_days", 7)
        )
        cache_days = _bounded_retention_days(
            self.database.get_setting("cache_retention_days", 7)
        )
        self.storage_retention_days.set(str(days))
        self.cache_retention_days.set(str(cache_days))
        self.storage_feedback_text.set(
            (
                "当前设置：本机副本始终保留"
                if days == 0
                else f"当前设置：导入 Eagle {days} 天后自动清理本机副本"
            )
            + "；"
            + (
                "缓存不自动清理"
                if cache_days == 0
                else f"缓存保留 {cache_days} 天"
            )
        )
        self.root.after_idle(self._refresh_cache_status)

    def _save_storage_settings(self) -> None:
        raw = self.storage_retention_days.get()
        cache_raw = self.cache_retention_days.get()
        try:
            days = max(0, min(365, int(raw)))
            cache_days = max(0, min(365, int(cache_raw)))
        except ValueError:
            self.storage_feedback_text.set("请输入 0-365 之间的数字")
            return
        try:
            self.database.set_settings(
                {
                    "file_retention_days": days,
                    "cache_retention_days": cache_days,
                }
            )
        except Exception as exc:
            self.storage_feedback_text.set(f"保存失败：{exc}")
            return
        self.storage_retention_days.set(str(days))
        self.cache_retention_days.set(str(cache_days))
        self.storage_feedback_text.set(
            (
                "已保存：本机副本始终保留"
                if days == 0
                else f"已保存：导入 Eagle {days} 天后自动清理本机副本"
            )
            + "；"
            + (
                "缓存不自动清理"
                if cache_days == 0
                else f"缓存保留 {cache_days} 天"
            )
        )

    @staticmethod
    def _cache_status_summary(payload: dict[str, object]) -> str:
        categories = dict(payload.get("categories") or {})
        temporary = dict(categories.get("temporary") or {})
        previews = dict(categories.get("previews") or {})
        log = dict(categories.get("log") or {})
        return (
            f"当前缓存 {_display_bytes(payload.get('totalBytes'))}，"
            f"共 {int(payload.get('fileCount') or 0)} 个文件 · "
            f"临时 {_display_bytes(temporary.get('bytes'))} · "
            f"预览 {_display_bytes(previews.get('bytes'))} · "
            f"日志 {_display_bytes(log.get('bytes'))}"
        )

    def _refresh_cache_status(self) -> None:
        if self.maintenance_busy or not hasattr(self, "cache_summary_text"):
            return
        self.cache_summary_text.set("正在统计缓存占用…")
        self._start_maintenance("cache-scan", self.media.cache_status)

    def clear_program_cache(self) -> None:
        if self.maintenance_busy:
            return
        if not messagebox.askyesno(
            "清理程序缓存",
            "将删除未被活动任务使用的临时下载、任务预览和旧版下载日志。"
            "“已完成”目录、IDM 原文件和用户文件不会删除。是否继续？",
            parent=self.root,
        ):
            return
        self.cache_summary_text.set("正在清理缓存…")
        self._start_maintenance("clear-cache", self.media.clear_cache)

    def _build_settings_updates(self) -> None:
        scroller = _VerticalScrolledFrame(
            self.settings_panel,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        self.settings_sub_tabs["updates"] = scroller
        content = scroller.content
        ttk.Label(content, text="应用更新", style="Title.TLabel").pack(anchor="w")
        version_surface = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(16, 14),
        )
        version_surface.pack(fill=X, pady=(12, 0))
        ttk.Label(
            version_surface,
            text="当前版本",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            version_surface,
            text=f"v{APP_VERSION}",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        _DynamicWrapLabel(
            content,
            text="每天最多自动检查一次；发现新版本后必须由你确认下载和安装。签名和哈希校验全部通过后才会启动安装。",
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(12, 0))
        self.update_button = _RoundedButton(
            content,
            textvariable=self.update_button_text,
            image=self.ui_icons.get("downloads-muted"),
            compound=LEFT,
            command=self.check_for_updates,
            style="Quiet.TButton",
        )
        self.update_button.pack(anchor="w", pady=(14, 0))
        self.update_status_text = StringVar(value="尚未检查更新")
        _DynamicWrapLabel(
            content,
            textvariable=self.update_status_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(8, 0))

    def _build_diagnostics_tab(self) -> None:
        tab = self._new_page("diagnostics")
        scroller = _VerticalScrolledFrame(
            tab,
            padding=(20, 16),
            style="Surface.TFrame",
            background=UI["surface"],
            initial_width=self.initial_client_width,
        )
        scroller.pack(fill=BOTH, expand=True)
        content = scroller.content
        self.diagnostics_summary_text = StringVar()
        self.diagnostics_feedback_text = StringVar(value="")
        ttk.Label(
            content,
            text="脱敏诊断",
            style="Title.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            content,
            text="导出内容只包含版本、状态、计数、错误码和脱敏端点。",
            style="Body.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(6, 0))
        _DynamicWrapLabel(
            content,
            text="不会包含令牌、Cookie、完整路径、完整来源网址、网站规则或代理认证信息。",
            style="Muted.TLabel",
            justify=LEFT,
            maximum=820,
        ).pack(fill=X, pady=(5, 14))

        summary_surface = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(16, 14),
        )
        summary_surface.pack(fill=X)
        ttk.Label(
            summary_surface,
            text="当前快照",
            style="Section.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            summary_surface,
            textvariable=self.diagnostics_summary_text,
            style="RaisedMuted.TLabel",
            justify=LEFT,
            maximum=780,
        ).pack(fill=X, pady=(6, 0))
        self.diagnostics_export_button = _RoundedButton(
            content,
            text="导出脱敏诊断",
            image=self.ui_icons.get("diagnostics-white"),
            compound=LEFT,
            style="Accent.TButton",
            command=self.export_diagnostics,
        )
        self.diagnostics_export_button.pack(anchor="w", pady=(14, 0))
        ttk.Label(
            content,
            textvariable=self.diagnostics_feedback_text,
            style="Success.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        window = ttk.Frame(
            content,
            style="Soft.TFrame",
            padding=(16, 14),
        )
        window.pack(fill=X, pady=(12, 0))
        ttk.Label(
            window,
            text="窗口",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        if self.external_tray:
            _RoundedButton(
                window,
                text="隐藏到右下角",
                style="Quiet.TButton",
                command=self.hide,
            ).pack(side=LEFT)
        else:
            _RoundedButton(
                window,
                text="最小化窗口",
                style="Quiet.TButton",
                command=self.root.iconify,
            ).pack(side=LEFT)

    def _selected_settings_rule(self) -> dict | None:
        selected = self.settings_site_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个网站", parent=self.root)
            return None
        return next(
            (
                rule
                for rule in self.database.list_site_rules()
                if str(rule["domain"]) == selected[0]
            ),
            None,
        )

    def _settings_add_rule(self) -> None:
        value = self.settings_site_input.get().strip()
        if not value:
            self.settings_site_entry.focus_set()
            return
        try:
            domain = normalize_domain(value)
            self.database.set_site_rule(domain, True, True)
        except InvalidPageUrl as exc:
            messagebox.showerror("域名无效", str(exc), parent=self.root)
            return
        self.settings_site_input.set("")
        self._refresh_settings(select_domain=domain)
        self.refresh(force=True)

    def _settings_toggle_rule(self) -> None:
        rule = self._selected_settings_rule()
        if not rule:
            return
        self.database.set_site_rule(
            rule["domain"],
            not bool(rule["enabled"]),
            bool(rule["include_subdomains"]),
        )
        self._refresh_settings(select_domain=str(rule["domain"]))
        self.refresh(force=True)

    def _settings_toggle_subdomains(self) -> None:
        rule = self._selected_settings_rule()
        if not rule:
            return
        self.database.set_site_rule(
            rule["domain"],
            bool(rule["enabled"]),
            not bool(rule["include_subdomains"]),
        )
        self._refresh_settings(select_domain=str(rule["domain"]))

    def _settings_delete_rule(self) -> None:
        rule = self._selected_settings_rule()
        if not rule:
            return
        if not messagebox.askyesno(
            "删除网站规则",
            f"删除 {rule['domain']} 后，该网站恢复默认不记录 IDM 来源。是否继续？",
            parent=self.root,
        ):
            return
        self.database.delete_site_rule(rule["domain"])
        self._refresh_settings()
        self.refresh(force=True)

    def _settings_clear_rules(self) -> None:
        rules = self.database.list_site_rules()
        if not rules:
            messagebox.showinfo("规则列表为空", "当前没有网站规则。", parent=self.root)
            return
        if not messagebox.askyesno(
            "清空网站规则",
            "所有网站将恢复默认不记录 IDM 来源；浏览器和视频号下载、文件、任务及 Eagle 内容都不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        self.database.clear_site_rules()
        self._refresh_settings()
        self.refresh(force=True)

    def _settings_proxy_mode_changed(self) -> None:
        _configure_if_changed(
            self.settings_proxy_entry,
            state="normal" if self.settings_proxy_mode.get() == "manual" else "disabled"
        )

    def _settings_save_proxy(self) -> None:
        try:
            configuration = self.media.network_proxy.configure(
                self.settings_proxy_mode.get(),
                self.settings_proxy_manual.get(),
            )
        except ProxyConfigurationError as exc:
            messagebox.showerror("代理地址无效", str(exc), parent=self.root)
            return
        except Exception as exc:
            messagebox.showerror("保存代理设置失败", str(exc), parent=self.root)
            return
        _set_var_if_changed(self.settings_proxy_mode, configuration["mode"])
        _set_var_if_changed(
            self.settings_proxy_manual,
            configuration["manualUrl"],
        )
        self.media._health_cache = None
        self._refresh_settings()
        self.refresh(force=True)

    def _refresh_settings(self, select_domain: str | None = None) -> None:
        active_tab = getattr(self, "current_settings_tab", "pairing")
        if active_tab == "pairing":
            _set_var_if_changed(
                self.pairing_text,
                "Chrome 已自动连接" if self.pairing.paired_origin else "等待 Chrome 扩展自动连接",
            )
            return
        if active_tab == "sites" and hasattr(self, "settings_site_tree"):
            selected = select_domain
            if not selected and self.settings_site_tree.selection():
                selected = self.settings_site_tree.selection()[0]
            rules = self.database.list_site_rules()
            rows = []
            for rule in rules:
                updated = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(rule["updated_at"]),
                )
                rows.append(
                    (
                        str(rule["domain"]),
                        (
                            rule["domain"],
                            "已启用" if rule["enabled"] else "已停用",
                            "包含" if rule["include_subdomains"] else "不包含",
                            updated,
                        ),
                    )
                )
            _sync_tree_rows(self.settings_site_tree, rows)
            if selected and self.settings_site_tree.exists(selected):
                self.settings_site_tree.selection_set(selected)
                self.settings_site_tree.see(selected)
            enabled = sum(1 for rule in rules if rule["enabled"])
            _set_var_if_changed(
                self.settings_site_summary_text,
                f"共 {len(rules)} 条规则 · 已启用 {enabled} 条 · 仅用于给 IDM 下载匹配来源，不影响浏览器和视频号下载",
            )
            return
        if active_tab != "network" or not hasattr(self, "settings_proxy_mode"):
            return
        # Do not overwrite an unsaved radio/entry edit during the periodic UI
        # refresh. The form is initialized when built and normalized on save.
        self._settings_proxy_mode_changed()
        status = self.media.network_proxy.status()
        _set_var_if_changed(
            self.settings_proxy_status_text,
            f"检测来源：{status.get('source') or '无'} · 端点：{status.get('endpoint') or '直连'} · {status['summary']}",
        )

    def _refresh_diagnostics_summary(self) -> None:
        if not hasattr(self, "diagnostics_summary_text"):
            return
        health = self.wechat_channels.health()
        host, port = self.api_server.address
        network = self.media.network_proxy.status()
        self.diagnostics_summary_text.set(
            f"应用 v{APP_VERSION} · 数据库 schema 6\n"
            f"本机服务 {host}:{port} · "
            f"{_eagle_experience(self.eagle_connected)['summary']} · "
            f"Chrome {'已连接' if self.pairing.paired_origin else '等待连接'}\n"
            f"媒体任务 {int(self.last_media_summary.get('total') or 0)} 条 · "
            f"视频号 {health.get('state') or 'off'} · "
            f"网络 {network.get('summary') or network.get('mode') or '未知'}"
        )

    def _performance_context(
        self,
        operation: str = "",
        *,
        background: bool = False,
    ) -> dict[str, object]:
        queues: dict[str, int] = {}
        for name in (
            "media_change_events",
            "update_events",
            "wechat_preview_events",
            "wechat_operation_results",
            "maintenance_events",
        ):
            value = getattr(self, name, None)
            if value is not None:
                try:
                    queues[name] = int(value.qsize())
                except (AttributeError, NotImplementedError):
                    pass
        return {
            "page": str(getattr(self, "current_page", "")),
            "operation": operation or str(getattr(self, "current_ui_operation", "")),
            "threadCount": threading.active_count(),
            "queues": queues,
            "background": bool(background),
        }

    def _record_performance(
        self,
        name: str,
        started: float,
        operation: str = "",
        *,
        background: bool = False,
    ) -> None:
        if not self.performance_monitor.enabled:
            return
        duration_ms = (time.perf_counter() - started) * 1000
        if duration_ms < self.performance_monitor.threshold_ms:
            return
        self.performance_monitor.record(
            name,
            duration_ms,
            self._performance_context(operation, background=background),
        )

    def _performance_heartbeat(self) -> None:
        self.performance_after_id = None
        if self.closing:
            return
        now = time.perf_counter()
        delay_ms = max(0.0, (now - self.performance_expected_at) * 1000)
        if delay_ms >= self.performance_monitor.threshold_ms:
            self.performance_monitor.record(
                "tk.heartbeat",
                delay_ms,
                self._performance_context("event-loop-delay"),
            )
        self.performance_expected_at = now + PERFORMANCE_HEARTBEAT_MS / 1000
        self.performance_after_id = self.root.after(
            PERFORMANCE_HEARTBEAT_MS,
            self._performance_heartbeat,
        )

    def run(self) -> None:
        self.root.mainloop()

    def show(self) -> None:
        self.visible = True
        self.root.deiconify()
        _apply_windows_dark_title_bar(
            self.root,
            dark=self.ui_theme == "dark",
        )
        self.root.lift()
        self.root.focus_force()
        self.refresh(force=True)

    def hide(self) -> None:
        self.visible = False
        self.root.withdraw()

    def _poll_control_signals(self) -> None:
        if not self.control_signals:
            return
        if self.control_signals.poll_quit():
            self.quit()
            return
        if self.control_signals.poll_show():
            self.show()
        if self.control_signals.poll_rules():
            self.show()
            self._show_page("settings")
        if self.control_signals.poll_update():
            self.show()
            self.check_for_updates()
        self.control_after_id = self.root.after(250, self._poll_control_signals)

    def _automatic_update_check(self) -> None:
        self.auto_update_after_id = None
        if automatic_check_due():
            self.check_for_updates(silent=True)

    def check_for_updates(self, silent: bool = False) -> None:
        if self.update_checking or self.update_downloading:
            if not silent:
                messagebox.showinfo("正在更新", "更新检查或下载正在进行，请稍候。")
            return
        self.update_checking = True
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        _set_var_if_changed(self.update_button_text, "正在检查…")
        if hasattr(self, "update_status_text"):
            self.update_status_text.set("正在检查可用更新…")
        threading.Thread(
            target=self._check_update_worker,
            args=(silent,),
            daemon=True,
        ).start()
        self._ensure_update_poll()

    def _check_update_worker(self, silent: bool) -> None:
        try:
            update = check_for_update()
            record_successful_check()
            self.update_events.put(("check_ok", (silent, update)))
        except Exception as exc:
            self.update_events.put(("check_error", (silent, exc)))

    def _queue_media_change(self) -> None:
        try:
            self.media_change_events.put_nowait(None)
        except Full:
            pass

    def _poll_media_changes(self) -> None:
        started = time.perf_counter()
        self.media_change_after_id = None
        changed = False
        while True:
            try:
                self.media_change_events.get_nowait()
                changed = True
            except Empty:
                break
        if changed:
            self.refresh(force=True)
        if callable(getattr(self.media, "add_change_listener", None)):
            self.media_change_after_id = self.root.after(
                250,
                self._poll_media_changes,
            )
        self._record_performance(
            "queue.media-changes",
            started,
            "consume-media-changes",
        )

    def _ensure_update_poll(self) -> None:
        if self.update_poll_after_id is None:
            self.update_poll_after_id = self.root.after(150, self._poll_update_events)

    def _poll_update_events(self) -> None:
        started = time.perf_counter()
        self.update_poll_after_id = None
        with self.update_progress_lock:
            progress = self.update_progress_latest
            self.update_progress_latest = None
        if progress is not None:
            downloaded, total = progress
            percent = min(99, int(int(downloaded) * 100 / max(1, int(total))))
            _set_var_if_changed(self.update_button_text, f"正在下载 {percent}%")
            if hasattr(self, "update_status_text"):
                _set_var_if_changed(
                    self.update_status_text,
                    f"正在下载并校验安装包：{percent}%",
                )
        for _index in range(UI_QUEUE_DRAIN_LIMIT):
            try:
                event, payload = self.update_events.get_nowait()
            except Empty:
                break
            if event == "check_ok":
                silent, update = payload
                self._handle_update_check(bool(silent), update)
            elif event == "check_error":
                silent, error = payload
                self._handle_update_error(bool(silent), error)
            elif event == "download_ok":
                self._handle_download_ready(payload)
            elif event == "download_error":
                self._handle_download_error(payload)
        with self.update_progress_lock:
            more_progress = self.update_progress_latest is not None
        if (
            self.update_checking
            or self.update_downloading
            or more_progress
            or not self.update_events.empty()
        ):
            self._ensure_update_poll()
        self._record_performance(
            "queue.update-events",
            started,
            "consume-update-events",
        )

    def _reset_update_button(self) -> None:
        _set_var_if_changed(self.update_button_text, "检查更新")
        if hasattr(self, "update_button"):
            self.update_button.configure(state="normal")

    def _handle_update_check(self, silent: bool, update: object) -> None:
        self.update_checking = False
        self._reset_update_button()
        if update is None:
            if hasattr(self, "update_status_text"):
                self.update_status_text.set(f"当前 v{APP_VERSION} 已是最新版")
            if not silent:
                messagebox.showinfo("已经是最新版", f"当前版本 v{APP_VERSION} 已是最新版。")
            return
        if not isinstance(update, UpdateInfo):
            self._handle_update_error(silent, UpdateError("更新信息无效"))
            return
        if hasattr(self, "update_status_text"):
            self.update_status_text.set(f"发现新版本 v{update.version}，等待你的确认")
        if not self.visible:
            self.show()
        details = f"发现新版本 v{update.version}，是否现在一键更新？"
        if update.notes:
            details += "\n\n" + update.notes[:1200]
        if not messagebox.askyesno("发现新版本", details, parent=self.root):
            return
        self._start_update_download(update)

    def _handle_update_error(self, silent: bool, error: object) -> None:
        self.update_checking = False
        self._reset_update_button()
        if hasattr(self, "update_status_text"):
            self.update_status_text.set(f"检查更新失败：{error}")
        if not silent:
            messagebox.showwarning("检查更新失败", str(error), parent=self.root)

    def _start_update_download(self, update: UpdateInfo) -> None:
        self.update_downloading = True
        with self.update_progress_lock:
            self.update_progress_latest = None
        if hasattr(self, "update_button"):
            self.update_button.configure(state="disabled")
        _set_var_if_changed(self.update_button_text, "正在下载 0%")
        if hasattr(self, "update_status_text"):
            self.update_status_text.set("正在下载并验证安装包")
        threading.Thread(
            target=self._download_update_worker,
            args=(update,),
            daemon=True,
        ).start()
        self._ensure_update_poll()

    def _download_update_worker(self, update: UpdateInfo) -> None:
        try:
            installer = prepare_update(
                update,
                self._queue_update_progress,
            )
            self.update_events.put(("download_ok", installer))
        except Exception as exc:
            self.update_events.put(("download_error", exc))

    def _queue_update_progress(self, current: int, total: int) -> None:
        with self.update_progress_lock:
            self.update_progress_latest = (int(current), int(total))

    def _handle_download_ready(self, installer: object) -> None:
        self.update_downloading = False
        self.update_button_text.set("正在安装…")
        if hasattr(self, "update_status_text"):
            self.update_status_text.set("签名和哈希校验通过，正在启动安装")
        try:
            launch_installer(Path(installer))
        except Exception as exc:
            self._handle_download_error(exc)
            return
        self.root.after(350, self.quit)

    def _handle_download_error(self, error: object) -> None:
        self.update_downloading = False
        self._reset_update_button()
        if hasattr(self, "update_status_text"):
            self.update_status_text.set(f"更新失败：{error}")
        messagebox.showerror("更新失败", str(error), parent=self.root)

    def _fit_idm_column_text(
        self,
        value: object,
        maximum_width: int,
        measure,
    ) -> str:
        text = " ".join(str(value or "").split())
        key = (text, max(1, int(maximum_width)))
        cached = self.idm_ellipsize_cache.pop(key, None)
        if cached is not None:
            self.idm_ellipsize_cache[key] = cached
            return cached
        fitted = _pixel_ellipsize(text, key[1], measure)
        self.idm_ellipsize_cache[key] = fitted
        while len(self.idm_ellipsize_cache) > 1024:
            self.idm_ellipsize_cache.popitem(last=False)
        return fitted

    def refresh(self, force: bool = False) -> None:
        started = time.perf_counter()
        previous_operation = self.current_ui_operation
        self.current_ui_operation = "refresh"
        try:
            self._refresh_impl(force)
        finally:
            self.current_ui_operation = previous_operation
            self._record_performance(
                "ui.refresh",
                started,
                "refresh",
            )

    def _refresh_impl(self, force: bool = False) -> None:
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if self.page_refresh_after_id:
            self.root.after_cancel(self.page_refresh_after_id)
            self.page_refresh_after_id = None
        if self.window_interaction_active:
            self.pending_refresh_force = self.pending_refresh_force or force
            self.refresh_after_id = self.root.after(240, self.refresh)
            return
        if not self.visible and not force:
            self.refresh_after_id = self.root.after(30000, self.refresh)
            return

        now = time.monotonic()
        eagle_result_available, eagle_result = self.eagle_probe.poll()
        if eagle_result_available:
            previous_eagle_connected = self.eagle_connected
            self.eagle_connected = bool(eagle_result)
            if self.eagle_connected != previous_eagle_connected:
                # Eagle availability changes which actions are safe. Invalidate
                # cached detail revisions so every visible button is redrawn.
                self.last_wechat_detail_revision = None
                self.last_plan_detail_revision = None
                self.last_idm_detail_revision = None
        if force or now - self.last_eagle_check >= 10:
            if self.eagle_probe.request():
                self.last_eagle_check = now
        eagle_experience = _eagle_experience(self.eagle_connected)
        eagle_text = str(eagle_experience["summary"])
        host, port = self.api_server.address
        dashboard = self.database.ui_snapshot()
        counts = dashboard["status_counts"]
        job_active_count = sum(
            counts.get(status, 0)
            for status in ("waiting_source", "queued", "waiting_eagle", "retry")
        )
        plans: list[dict] = []
        summary_reader = getattr(self.media, "ui_summary", None)
        if callable(summary_reader):
            self.last_media_summary = dict(summary_reader())
            media_active_count = int(self.last_media_summary.get("active") or 0)
        else:
            plans = self.media.list_plans(200)
            media_active_count = sum(
                1
                for plan in plans
                if str(plan.get("status")) in MEDIA_ACTIVE_STATUSES
            )
            self.last_media_summary = {
                "total": len(plans),
                "active": media_active_count,
                "revision": max(
                    (
                        float(plan.get("updated_at") or 0)
                        for plan in plans
                    ),
                    default=0.0,
                ),
            }
        if self.current_page == "media" and not plans:
            plans = self.media.list_plans(200)
        status_parts = [f"v{APP_VERSION}", eagle_text, f"本机服务 {host}:{port}"]
        if media_active_count:
            status_parts.append(f"媒体任务 {media_active_count}")
        if job_active_count:
            status_parts.append(f"导入队列 {job_active_count}")
        wechat_health = self.wechat_channels.health()
        if wechat_health.get("running"):
            status_parts.append(f"视频号候选 {wechat_health.get('candidateCount', 0)}")
        if counts.get("failed_permanent", 0):
            status_parts.append(f"失败 {counts['failed_permanent']}")
        _set_var_if_changed(self.status_text, " · ".join(status_parts))
        _set_var_if_changed(
            self.eagle_status_text,
            str(eagle_experience["status"]),
        )
        if hasattr(self, "idm_eagle_hint_text"):
            _set_var_if_changed(
                self.idm_eagle_hint_text,
                str(eagle_experience["idm_hint"]),
            )
        _set_var_if_changed(self.service_status_text, "服务正常")
        if hasattr(self, "status_dots"):
            self.status_dots["eagle"].set_color(
                UI["success"] if self.eagle_connected else UI["warning"]
            )
            self.status_dots["service"].set_color(UI["success"])
        enabled_sites = dashboard["enabled_site_count"]
        _set_var_if_changed(
            self.site_rules_text,
            f"网站规则（已开启 {enabled_sites}）",
        )
        proxy_status = self.media.network_proxy.status()
        _set_var_if_changed(
            self.network_proxy_text,
            f"网络：{proxy_status['summary']}",
        )
        if self.pairing.paired_origin:
            _set_var_if_changed(self.pairing_text, "Chrome 已自动连接")
            _set_var_if_changed(self.chrome_status_text, "Chrome 已连接")
            if hasattr(self, "status_dots"):
                self.status_dots["chrome"].set_color(UI["success"])
        else:
            _set_var_if_changed(
                self.pairing_text,
                "等待 Chrome 扩展自动连接",
            )
            _set_var_if_changed(self.chrome_status_text, "Chrome 等待连接")
            if hasattr(self, "status_dots"):
                self.status_dots["chrome"].set_color(UI["text_muted"])

        if self.current_page == "media":
            self._refresh_media_tasks(plans, force)
        elif self.current_page == "wechat":
            self._refresh_wechat_candidates(wechat_health, force)

        revision = dashboard["jobs_revision"]
        if (
            self.current_page == "idm"
            and hasattr(self, "job_tree")
            and revision != self.last_jobs_revision
        ):
            projection_started = time.perf_counter()
            selected = self.selected_job_id()
            job_rows = []
            tree_font = tkfont.nametofont("Ui12")

            def fit_column(value: object, column: str) -> str:
                width = int(self.job_tree.column(column, "width") or 24)
                return self._fit_idm_column_text(
                    value,
                    max(24, width - 16),
                    tree_font.measure,
                )

            jobs = self.database.list_jobs(500)
            visible_jobs, self.idm_page, self.idm_page_count = _page_slice(
                jobs,
                self.idm_page,
                TREE_PAGE_SIZE,
            )
            self._update_pager(
                self.idm_previous_button,
                self.idm_next_button,
                self.idm_page_text,
                self.idm_page,
                self.idm_page_count,
            )
            for job in visible_jobs:
                created = _relative_time_label(float(job["created_at"] or 0))
                source = "未记录"
                if job.get("source_url"):
                    source = urlsplit(job["source_url"]).hostname or "已记录"
                message = job.get("error_message") or ""
                if job["status"] == "imported" and not job.get("source_url"):
                    message = "已直接导入，未保存来源网页"
                job_rows.append(
                    (
                        str(job["id"]),
                        (
                        created,
                        STATUS_TEXT.get(job["status"], job["status"]),
                        fit_column(job["file_name"], "file"),
                        fit_column(source, "source"),
                        fit_column(message, "message"),
                    ),
                    )
                )
            _sync_tree_rows(self.job_tree, job_rows)
            if selected and self.job_tree.exists(selected):
                self.job_tree.selection_set(selected)
            elif job_rows:
                self.job_tree.selection_set(job_rows[0][0])
            self.last_jobs_revision = revision
            self._record_performance(
                "idm.list-project",
                projection_started,
                "refresh-idm-list",
            )
        if self.current_page == "idm":
            self._update_idm_detail()
        elif self.current_page == "settings":
            self._refresh_settings()
        elif self.current_page == "diagnostics":
            self._refresh_diagnostics_summary()
        if self.current_page == "wechat" and wechat_health.get("running"):
            refresh_delay = 750
        elif (
            self.current_page == "media"
            and media_active_count
        ):
            refresh_delay = 1000
        else:
            refresh_delay = 3000 if media_active_count else 4000
        self.refresh_after_id = self.root.after(
            refresh_delay,
            self.refresh,
        )

    @staticmethod
    def _update_pager(
        previous: ttk.Button,
        following: ttk.Button,
        text: StringVar,
        page: int,
        total_pages: int,
    ) -> None:
        _set_var_if_changed(text, f"{page + 1}/{total_pages}")
        previous.state(["!disabled"] if page > 0 else ["disabled"])
        following.state(["!disabled"] if page + 1 < total_pages else ["disabled"])

    def _change_wechat_page(self, delta: int) -> None:
        target = max(0, min(self.wechat_page + delta, self.wechat_page_count - 1))
        if target == self.wechat_page:
            return
        self.wechat_page = target
        self.refresh(force=True)

    def _change_idm_page(self, delta: int) -> None:
        target = max(0, min(self.idm_page + delta, self.idm_page_count - 1))
        if target == self.idm_page:
            return
        self.idm_page = target
        self.refresh(force=True)

    @staticmethod
    def _duration_text(milliseconds: object) -> str:
        try:
            total = max(0, int(milliseconds or 0) // 1000)
        except (TypeError, ValueError):
            return "未知"
        if not total:
            return "未知"
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    def _bind_wechat_card(self, widget: object, object_id: str) -> None:
        widget.bind(
            "<Button-1>",
            lambda _event, value=object_id: self._activate_wechat_card(value),
            add="+",
        )
        widget.bind(
            "<Return>",
            lambda _event, value=object_id: self._activate_wechat_card(value),
            add="+",
        )
        widget.bind(
            "<space>",
            lambda _event, value=object_id: self._activate_wechat_card(value),
            add="+",
        )

    def _activate_wechat_card(self, object_id: str) -> str:
        self._select_wechat_card(object_id)
        row = self.wechat_card_widgets.get(object_id, {}).get("row")
        if row is not None:
            row.focus_set()
        return "break"

    def _render_wechat_cards(self, candidates: list[dict]) -> None:
        self.wechat_card_list.clear()
        self.wechat_card_widgets.clear()
        if not candidates:
            ttk.Label(
                self.wechat_card_list.content,
                text=getattr(
                    self,
                    "wechat_empty_message",
                    "尚未识别到视频号内容\n开始捕获后在微信中打开目标视频",
                ),
                style="Muted.TLabel",
                anchor="center",
                justify="center",
                image=self.ui_icons.get("wechat-muted"),
                compound="top",
                padding=(16, 36),
            ).pack(fill=BOTH, expand=True)
            return

        for candidate in candidates:
            object_id = str(candidate["objectId"])
            selected = object_id == self.selected_wechat_card_id
            frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
            title_style = (
                "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
            )
            meta_style = (
                "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
            )
            row = _RoundedPanel(
                self.wechat_card_list.content,
                fill=UI["selected"] if selected else UI["surface"],
                outer_background=UI["surface"],
                style=frame_style,
                radius=RADII["card"],
                height=self.metrics["wechat_row_height"] - max(1, round(4 * self.ui_scale)),
                inset=4,
                takefocus=True,
            )
            row.pack(fill=X, padx=6, pady=2)
            body = ttk.Frame(
                row.inner,
                style=frame_style,
                padding=(12, 6, 10, 5),
            )
            body.pack(fill=BOTH, expand=True)
            body.columnconfigure(1, weight=1)
            thumbnail_host = _RoundedPanel(
                body,
                fill=UI["surface_overlay"],
                outer_background=UI["selected"] if selected else UI["surface"],
                style="Soft.TFrame",
                width=64,
                height=40,
                radius=RADII["thumbnail"],
                inset=2,
            )
            thumbnail_host.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 8))
            thumbnail = ttk.Label(
                thumbnail_host.inner,
                image=self.ui_icons.get("wechat-muted"),
                style="Soft.TLabel",
                anchor="center",
            )
            thumbnail.pack(fill=BOTH, expand=True)

            title = ttk.Label(
                body,
                text=_ellipsize(candidate.get("title") or "微信视频号视频", 24),
                style=title_style,
                anchor="w",
            )
            title.grid(row=0, column=1, sticky="ew")
            author = ttk.Label(
                body,
                text=_ellipsize(candidate.get("author") or "未知作者", 20),
                style=meta_style,
                anchor="w",
            )
            author.grid(row=1, column=1, sticky="ew", pady=(2, 0))
            variants = (
                candidate.get("variants")
                if isinstance(candidate.get("variants"), list)
                else []
            )
            quality = str(variants[0].get("quality") or "自动") if variants else "自动"
            updated = float(candidate.get("updatedAt") or 0)
            time_text = (
                time.strftime("%H:%M", time.localtime(updated)) if updated else "—"
            )
            metadata = ttk.Label(
                body,
                text=f"{self._duration_text(candidate.get('durationMs'))}  {quality}  {time_text}",
                style=meta_style,
                anchor="w",
            )
            metadata.grid(row=2, column=1, sticky="ew", pady=(3, 0))
            self.wechat_card_widgets[object_id] = {
                "row": row,
                "body": body,
                "thumbnail_host": thumbnail_host,
                "title": title,
                "author": author,
                "metadata": metadata,
            }
            for widget in (
                row,
                row.inner,
                body,
                thumbnail_host,
                thumbnail_host.inner,
                thumbnail,
                title,
                author,
                metadata,
            ):
                self._bind_wechat_card(widget, object_id)

    def _update_wechat_card_widget(
        self,
        object_id: str,
        candidate: dict,
    ) -> None:
        widgets = self.wechat_card_widgets.get(object_id)
        if not widgets:
            return
        selected = object_id == self.selected_wechat_card_id
        frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
        title_style = (
            "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
        )
        meta_style = (
            "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
        )
        variants = (
            candidate.get("variants")
            if isinstance(candidate.get("variants"), list)
            else []
        )
        quality = str(variants[0].get("quality") or "自动") if variants else "自动"
        updated = float(candidate.get("updatedAt") or 0)
        time_text = time.strftime("%H:%M", time.localtime(updated)) if updated else "—"
        row = widgets["row"]
        if isinstance(row, _RoundedPanel):
            row.set_surface(
                fill=UI["selected"] if selected else UI["surface"],
                style=frame_style,
            )
        _configure_if_changed(widgets["body"], style=frame_style)
        thumbnail_host = widgets.get("thumbnail_host")
        if isinstance(thumbnail_host, _RoundedPanel):
            thumbnail_host.configure(
                background=UI["selected"] if selected else UI["surface"],
            )
        _configure_if_changed(
            widgets["title"],
            text=_ellipsize(candidate.get("title") or "微信视频号视频", 24),
            style=title_style,
        )
        _configure_if_changed(
            widgets["author"],
            text=_ellipsize(candidate.get("author") or "未知作者", 20),
            style=meta_style,
        )
        _configure_if_changed(
            widgets["metadata"],
            text=(
                f"{self._duration_text(candidate.get('durationMs'))}"
                f"  {quality}  {time_text}"
            ),
            style=meta_style,
        )

    def _select_wechat_card(self, object_id: str) -> None:
        if object_id not in self.wechat_rows:
            return
        self.selected_wechat_card_id = object_id
        for current_id in self.wechat_card_widgets:
            candidate = self.wechat_rows.get(current_id)
            if candidate is not None:
                self._update_wechat_card_widget(current_id, candidate)
        self.last_wechat_detail_revision = None
        self._update_wechat_detail()

    def _refresh_wechat_candidates(self, health: dict, _force: bool) -> None:
        self._drain_wechat_preview_events()
        state = str(health.get("state") or "off")
        labels = {
            "off": "视频号捕获已关闭",
            "preparing": "正在准备视频号捕获…",
            "waiting_wechat": "等待微信中打开视频号内容",
            "capturing": f"捕获中 · {health.get('endpoint') or '本机代理'}",
            "needs_recovery": "需要确认代理恢复状态",
            "failed": "视频号捕获启动失败",
        }
        summary = labels.get(state, state)
        if health.get("lastEvent"):
            summary += f" · {health['lastEvent']}"
        if health.get("error"):
            summary += f" · {health['error']}"
        if health.get("running") and not health.get("candidateCount"):
            diagnostics = health.get("proxyDiagnostics") or {}
            summary += (
                f" · 资源脚本 {diagnostics.get('resourceScriptsInstrumented', 0)}"
                f"/{diagnostics.get('resourceScriptsSeen', 0)}"
                f" · 内部数据 {health.get('internalApiObserved', 0)}"
            )
        _set_var_if_changed(self.wechat_status_text, summary)
        _set_var_if_changed(
            self.wechat_action_text,
            "停止捕获" if health.get("running") else "开始捕获",
        )
        _configure_if_changed(
            self.wechat_action_button,
            style="Danger.TButton" if health.get("running") else "Accent.TButton",
            image=self.ui_icons.get(
                "stop-danger" if health.get("running") else "play-white"
            ),
        )

        candidates = self.wechat_channels.candidates()
        self.wechat_empty_message = (
            "正在等待视频号内容\n请在微信中打开目标视频"
            if health.get("running")
            else "尚未识别到视频号内容\n开始捕获后在微信中打开目标视频"
        )
        _set_var_if_changed(
            self.wechat_candidate_count_text,
            "当前视频 · 已识别" if candidates else "当前视频 · 等待识别"
        )
        revision = (
            len(candidates),
            max((float(item.get("updatedAt") or 0) for item in candidates), default=0.0),
        )
        self.wechat_rows = {str(item["objectId"]): item for item in candidates}
        selected_id = self.selected_wechat_card_id
        if revision != self.wechat_revision:
            previous_count = self.wechat_revision[0] if self.wechat_revision else 0
            if len(candidates) > previous_count:
                self.wechat_page = max(
                    0,
                    (len(candidates) - 1) // CARD_PAGE_SIZE,
                )
            visible_candidates, self.wechat_page, self.wechat_page_count = _page_slice(
                candidates,
                self.wechat_page,
                CARD_PAGE_SIZE,
            )
            self._update_pager(
                self.wechat_previous_button,
                self.wechat_next_button,
                self.wechat_page_text,
                self.wechat_page,
                self.wechat_page_count,
            )
            if selected_id not in self.wechat_rows:
                selected_id = str(candidates[-1]["objectId"]) if candidates else ""
            visible_ids = {
                str(candidate["objectId"])
                for candidate in visible_candidates
            }
            if selected_id not in visible_ids:
                selected_id = (
                    str(visible_candidates[-1]["objectId"])
                    if visible_candidates
                    else ""
                )
            self.selected_wechat_card_id = selected_id
            visible_order = [
                str(candidate["objectId"])
                for candidate in visible_candidates
            ]
            if visible_order != list(self.wechat_card_widgets):
                self._render_wechat_cards(visible_candidates)
            else:
                for candidate in visible_candidates:
                    self._update_wechat_card_widget(
                        str(candidate["objectId"]),
                        candidate,
                    )
            self.wechat_revision = revision
        self._update_wechat_detail()

    def _selected_wechat_candidate(self) -> dict | None:
        return self.wechat_rows.get(self.selected_wechat_card_id)

    def _update_wechat_detail(self) -> None:
        candidate = self._selected_wechat_candidate()
        if not candidate:
            if self.last_wechat_detail_revision == ("empty",):
                return
            self.last_wechat_detail_revision = ("empty",)
            _set_var_if_changed(
                self.wechat_detail_text,
                "开始捕获后，在微信中打开视频号内容。",
            )
            _set_var_if_changed(self.wechat_author_text, "")
            _set_var_if_changed(self.wechat_quality_text, "")
            _set_var_if_changed(self.wechat_full_metadata_text, "")
            self.wechat_variant_ids = []
            _configure_if_changed(self.wechat_variant_box, values=())
            _set_var_if_changed(self.wechat_variant_text, "")
            self.wechat_preview_object_id = ""
            self.wechat_preview_image = None
            _configure_if_changed(
                self.wechat_preview_label,
                image=self.ui_icons.get("wechat-muted"),
                text="封面将在识别后显示",
            )
            for button in self.wechat_delivery_buttons.values():
                _configure_if_changed(button, state="disabled")
            return
        object_id = str(candidate.get("objectId") or "")
        if object_id != self.wechat_preview_object_id:
            self.wechat_preview_generation += 1
            preview_generation = self.wechat_preview_generation
            self.wechat_preview_object_id = object_id
            self.wechat_preview_image = None
            self.wechat_preview_label.configure(
                image=self.ui_icons.get("wechat-muted"),
                text="正在读取封面…",
            )
            if object_id and candidate.get("coverUrl"):
                self._request_wechat_preview(preview_generation, object_id)
            elif not candidate.get("coverUrl"):
                self.wechat_preview_label.configure(
                    image=self.ui_icons.get("wechat-muted"),
                    text="该内容未提供封面",
                )
        full_title = str(candidate.get("title") or "微信视频号视频")
        full_author = str(candidate.get("author") or "未知作者")
        source = str(
            candidate.get("sourceUrl")
            or candidate.get("pageUrl")
            or candidate.get("url")
            or "本机捕获候选"
        )
        output_name = str(
            candidate.get("outputName") or "微信视频号视频.mp4"
        )
        source_domain = urlsplit(source).hostname if source.startswith(("http://", "https://")) else source
        variants = candidate.get("variants") if isinstance(candidate.get("variants"), list) else []
        revision = (
            object_id,
            float(candidate.get("updatedAt") or 0),
            self.layout_mode,
            full_title,
            full_author,
            source,
            output_name,
            candidate.get("durationMs"),
            str(candidate.get("coverUrl") or ""),
            tuple(
                (
                    str(variant.get("id") or ""),
                    str(variant.get("quality") or ""),
                    str(variant.get("fileSize") or ""),
                    bool(variant.get("encrypted")),
                )
                for variant in variants
            ),
            self.eagle_connected,
        )
        if revision == self.last_wechat_detail_revision:
            return
        self.last_wechat_detail_revision = revision
        _set_var_if_changed(self.wechat_detail_text, _ellipsize(full_title, 48))
        _set_var_if_changed(
            self.wechat_author_text,
            f"作者：{_ellipsize(full_author, 44)}",
        )
        _set_var_if_changed(
            self.wechat_quality_text,
            f"内容 ID：{candidate.get('objectId')} · 时长 {self._duration_text(candidate.get('durationMs'))}\n"
            f"预计输出：{_ellipsize(output_name, 52)}\n"
            f"来源：{source_domain or source}",
        )
        _set_var_if_changed(
            self.wechat_full_metadata_text,
            f"完整标题：{full_title}\n"
            f"完整作者：{full_author}\n"
            f"完整输出：{output_name}\n"
            f"完整来源：{source}",
        )
        values = []
        variant_ids = []
        for variant in variants:
            size = _display_bytes(variant.get("fileSize"))
            encrypted = " · 本机解密" if variant.get("encrypted") else ""
            values.append(f"{variant.get('quality') or '自动质量'} · {size}{encrypted}")
            variant_ids.append(str(variant.get("id") or ""))
        previous_id = ""
        current_index = self.wechat_variant_box.current()
        if 0 <= current_index < len(self.wechat_variant_ids):
            previous_id = self.wechat_variant_ids[current_index]
        self.wechat_variant_ids = variant_ids
        _configure_if_changed(self.wechat_variant_box, values=values)
        selected_index = (
            variant_ids.index(previous_id)
            if previous_id and previous_id in variant_ids
            else 0
        )
        if values and self.wechat_variant_box.current() != selected_index:
            self.wechat_variant_box.current(selected_index)
        _set_var_if_changed(
            self.wechat_variant_text,
            values[selected_index] if values else "自动质量",
        )
        experience = _eagle_experience(self.eagle_connected)
        eagle_button = self.wechat_delivery_buttons["eagle"]
        local_button = self.wechat_delivery_buttons["local"]
        eagle_button.configure(
            text=(
                "导入 Eagle（完成后删除本机副本）"
                if self.eagle_connected
                else str(experience["import_button"])
            ),
            style="Accent.TButton" if self.eagle_connected else "Quiet.TButton",
        )
        eagle_button.set_enabled(bool(experience["can_import"]))
        local_button.configure(
            style="Quiet.TButton" if self.eagle_connected else "Accent.TButton"
        )
        local_button.set_enabled(True)

    def _request_wechat_preview(self, generation: int, object_id: str) -> None:
        with self.wechat_preview_lock:
            self.wechat_preview_pending = (generation, object_id)
            if self.wechat_preview_worker_running:
                return
            self.wechat_preview_worker_running = True
        threading.Thread(
            target=self._load_wechat_preview_worker,
            name="wechat-cover-preview",
            daemon=True,
        ).start()

    def _load_wechat_preview_worker(self) -> None:
        while not self.closing:
            with self.wechat_preview_lock:
                request = self.wechat_preview_pending
                self.wechat_preview_pending = None
                if request is None:
                    self.wechat_preview_worker_running = False
                    return
            generation, object_id = request
            try:
                preview = self.wechat_channels.preview_png(object_id)
            except Exception:
                preview = b""
            item = (generation, object_id, preview)
            try:
                self.wechat_preview_events.put_nowait(item)
            except Full:
                try:
                    self.wechat_preview_events.get_nowait()
                except Empty:
                    pass
                try:
                    self.wechat_preview_events.put_nowait(item)
                except Full:
                    pass
        with self.wechat_preview_lock:
            self.wechat_preview_worker_running = False

    def _drain_wechat_preview_events(self) -> None:
        started = time.perf_counter()
        for _index in range(UI_QUEUE_DRAIN_LIMIT):
            try:
                generation, object_id, preview = (
                    self.wechat_preview_events.get_nowait()
                )
            except Empty:
                break
            if (
                generation != self.wechat_preview_generation
                or object_id != self.wechat_preview_object_id
            ):
                continue
            if not preview:
                self.wechat_preview_label.configure(
                    image=self.ui_icons.get("wechat-muted"),
                    text="封面暂不可用",
                )
                continue
            try:
                image = PhotoImage(data=preview, format="png")
            except Exception:
                self.wechat_preview_label.configure(
                    image=self.ui_icons.get("wechat-muted"),
                    text="封面暂不可用",
                )
                continue
            target_height = 220 if self.layout_mode == LAYOUT_COMPACT else 252
            factor = max(
                1,
                (image.width() + self.metrics["preview_max_width"] - 1)
                // self.metrics["preview_max_width"],
                (image.height() + target_height - 1) // target_height,
            )
            self.wechat_preview_image = (
                image.subsample(factor, factor) if factor > 1 else image
            )
            self.wechat_preview_label.configure(image=self.wechat_preview_image, text="")
        self._record_performance(
            "queue.wechat-preview",
            started,
            "consume-wechat-preview",
        )

    def _submit_wechat_delivery(self, import_to_eagle: bool) -> None:
        self.wechat_import_to_eagle.set(import_to_eagle)
        self.submit_selected_wechat_candidate()

    def toggle_wechat_capture(self) -> None:
        if self.wechat_operation_busy:
            return
        running = bool(self.wechat_channels.health().get("running"))
        self.wechat_operation_busy = True
        self.wechat_operation_generation += 1
        generation = self.wechat_operation_generation
        self._set_wechat_operation_buttons(True)
        self.wechat_status_text.set(
            "正在停止视频号捕获…"
            if running
            else "正在后台检查视频号捕获环境…"
        )
        target = self._run_wechat_operation if running else self._run_wechat_preflight
        threading.Thread(
            target=target,
            args=(generation, running) if running else (generation,),
            name=(
                "wechat-capture-toggle"
                if running
                else "wechat-capture-preflight"
            ),
            daemon=True,
        ).start()
        self._schedule_wechat_operation_poll()

    def _set_wechat_operation_buttons(self, busy: bool) -> None:
        state = ["disabled"] if busy else ["!disabled"]
        self.wechat_action_button.state(state)
        if hasattr(self, "wechat_proxy_repair_button"):
            self.wechat_proxy_repair_button.state(state)

    def repair_wechat_proxy_conflict(self) -> None:
        if self.wechat_operation_busy:
            return
        if not messagebox.askokcancel(
            "修复视频号代理",
            "修复会清除已经无法连接的本机代理；如果捕获期间代理被其他软件改写，会重新接管，并在停止捕获后恢复该软件的代理。\n\n"
            "正常运行的 Clash、VPN 或公司代理不会被关闭。是否继续？",
            parent=self.root,
        ):
            return
        self.wechat_operation_busy = True
        self.wechat_operation_generation += 1
        generation = self.wechat_operation_generation
        self._set_wechat_operation_buttons(True)
        self.wechat_status_text.set("正在检查并修复代理冲突…")
        threading.Thread(
            target=self._run_wechat_proxy_repair,
            args=(generation,),
            name="wechat-proxy-repair",
            daemon=True,
        ).start()
        self._schedule_wechat_operation_poll()

    def _put_wechat_operation_result(
        self,
        generation: int,
        event: str,
        payload: object,
    ) -> None:
        try:
            self.wechat_operation_results.put_nowait(
                (generation, event, payload)
            )
        except Full:
            pass

    def _run_wechat_proxy_repair(self, generation: int) -> None:
        try:
            result = self.wechat_channels.repair_proxy_conflict()
        except Exception as exc:
            self._put_wechat_operation_result(
                generation,
                "proxy_repair",
                (False, str(exc)),
            )
            return
        self._put_wechat_operation_result(
            generation,
            "proxy_repair",
            (True, str(result.get("message") or "代理检查完成")),
        )

    def _run_wechat_preflight(self, generation: int) -> None:
        try:
            existing = self.wechat_channels.certificate.existing()
            needs_trust = (
                not existing
                or not self.wechat_channels.certificate.is_trusted(
                    existing.fingerprint
                )
            )
        except Exception as exc:
            self._put_wechat_operation_result(
                generation,
                "preflight_error",
                str(exc),
            )
            return
        self._put_wechat_operation_result(
            generation,
            "preflight",
            needs_trust,
        )

    def _run_wechat_operation(
        self,
        generation: int,
        was_running: bool,
        trust_certificate: bool = True,
    ) -> None:
        try:
            if was_running:
                self.wechat_channels.stop()
            else:
                self.wechat_channels.start(trust_certificate=trust_certificate)
        except Exception as exc:
            self._put_wechat_operation_result(
                generation,
                "completed",
                (False, str(exc)),
            )
            return
        self._put_wechat_operation_result(
            generation,
            "completed",
            (True, ""),
        )

    def _schedule_wechat_operation_poll(self) -> None:
        if self.closing or not self.wechat_operation_busy:
            return
        if self.wechat_operation_after_id is None:
            self.wechat_operation_after_id = self.root.after(
                200,
                self._poll_wechat_operation,
            )

    def _poll_wechat_operation(self) -> None:
        started = time.perf_counter()
        self._poll_wechat_operation_impl(started)

    def _poll_wechat_operation_impl(self, started: float) -> None:
        self.wechat_operation_after_id = None
        result: tuple[str, object] | None = None
        for _index in range(UI_QUEUE_DRAIN_LIMIT):
            try:
                generation, event, payload = (
                    self.wechat_operation_results.get_nowait()
                )
            except Empty:
                break
            if generation == self.wechat_operation_generation:
                result = (event, payload)
                break
        self._record_performance(
            "queue.wechat-operation",
            started,
            "consume-wechat-operation",
        )
        if result is None:
            if self.wechat_operation_busy:
                self._schedule_wechat_operation_poll()
            return
        event, payload = result
        if event == "preflight_error":
            self.wechat_operation_busy = False
            self._set_wechat_operation_buttons(False)
            messagebox.showerror(
                "无法检查视频号证书",
                str(payload),
                parent=self.root,
            )
            self.refresh(force=True)
            return
        if event == "preflight":
            if bool(payload) and not messagebox.askokcancel(
                "首次启用视频号捕获",
                "留底桌面端将为当前 Windows 用户生成并信任一张仅用于微信视频号本机捕获的根证书。\n\n"
                "Windows 随后会显示“安全警告”，请核对证书名称为“留底下载器 微信视频号本机捕获根证书”后亲自确认。停止捕获会恢复系统代理；卸载会按精确指纹移除此证书。\n\n"
                "是否继续？",
                parent=self.root,
            ):
                self.wechat_operation_busy = False
                self._set_wechat_operation_buttons(False)
                self.refresh(force=True)
                return
            self.wechat_status_text.set("正在准备视频号捕获…")
            threading.Thread(
                target=self._run_wechat_operation,
                args=(
                    self.wechat_operation_generation,
                    False,
                    bool(payload),
                ),
                name="wechat-capture-toggle",
                daemon=True,
            ).start()
            self._schedule_wechat_operation_poll()
            return
        if event == "proxy_repair":
            succeeded, message = payload
            self.wechat_operation_busy = False
            self._set_wechat_operation_buttons(False)
            if succeeded:
                messagebox.showinfo(
                    "代理修复完成",
                    message or "代理检查完成",
                    parent=self.root,
                )
            else:
                messagebox.showerror(
                    "代理修复失败",
                    message or "无法修复视频号代理",
                    parent=self.root,
                )
            self.refresh(force=True)
            return
        succeeded, error = payload
        self.wechat_operation_busy = False
        self._set_wechat_operation_buttons(False)
        if not succeeded:
            messagebox.showerror("视频号捕获失败", error or "视频号捕获操作失败", parent=self.root)
        self.refresh(force=True)

    def submit_selected_wechat_candidate(self) -> None:
        candidate = self._selected_wechat_candidate()
        if not candidate:
            messagebox.showinfo("没有候选", "请先在微信中打开并选择一条视频号内容。")
            return
        index = self.wechat_variant_box.current()
        variant_id = self.wechat_variant_ids[index] if 0 <= index < len(self.wechat_variant_ids) else ""
        try:
            import_to_eagle = bool(self.wechat_import_to_eagle.get())
            if import_to_eagle and not self.eagle_connected:
                messagebox.showinfo(
                    "Eagle 未连接",
                    "Eagle 未安装或未启动，但不影响下载。请使用“仅下载并保留本机文件”；启动 Eagle 后可从下载任务补导。",
                    parent=self.root,
                )
                return
            self.wechat_channels.submit(
                str(candidate["objectId"]),
                variant_id,
                import_to_eagle=import_to_eagle,
                delete_after_import=import_to_eagle,
            )
        except Exception as exc:
            messagebox.showerror("创建任务失败", str(exc), parent=self.root)
            return
        self._show_page("media")
        self.refresh(force=True)

    def clear_wechat_candidates(self) -> None:
        count = len(self.wechat_channels.candidates())
        if not count:
            messagebox.showinfo("候选列表为空", "当前没有可清除的视频号候选。", parent=self.root)
            return
        if not messagebox.askyesno(
            "清除视频号候选",
            f"将清除当前识别到的 {count} 条候选；捕获会保持当前状态，下载任务和文件不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        removed = self.wechat_channels.clear_candidates()
        self.wechat_revision = None
        self.refresh(force=True)
        messagebox.showinfo("清理完成", f"已清除 {removed} 条视频号候选。", parent=self.root)

    def _plan_thumbnail(self, plan_id: str, plan: dict) -> PhotoImage | None:
        preview_path = Path(str(plan.get("preview_path") or ""))
        revision = _path_render_revision(preview_path)
        cached = self.plan_thumbnail_cache.pop(revision, None)
        if cached is not None:
            self.plan_thumbnail_cache[revision] = cached
            self.plan_thumbnail_images[plan_id] = cached
            return cached
        try:
            image = PhotoImage(file=str(preview_path))
        except Exception:
            return self.brand_image
        image = _fit_photo_image(image, 48, 32)
        self.plan_thumbnail_cache[revision] = image
        while len(self.plan_thumbnail_cache) > 64:
            self.plan_thumbnail_cache.popitem(last=False)
        self.plan_thumbnail_images[plan_id] = image
        return image

    def _bind_plan_card(self, widget: object, plan_id: str) -> None:
        widget.bind(
            "<Button-1>",
            lambda _event, value=plan_id: self._activate_plan_card(value),
            add="+",
        )
        widget.bind(
            "<Return>",
            lambda _event, value=plan_id: self._activate_plan_card(value),
            add="+",
        )
        widget.bind(
            "<space>",
            lambda _event, value=plan_id: self._activate_plan_card(value),
            add="+",
        )
        widget.bind(
            "<Button-3>",
            lambda event, value=plan_id: self._show_plan_context_menu(event, value),
            add="+",
        )
        widget.bind(
            "<Shift-F10>",
            lambda event, value=plan_id: self._show_plan_context_menu(event, value),
            add="+",
        )

    def _activate_plan_card(self, plan_id: str) -> str:
        self._select_plan_card(plan_id)
        row = self.plan_card_widgets.get(plan_id, {}).get("row")
        if row is not None:
            row.focus_set()
        return "break"

    def _show_plan_context_menu(self, event: object, plan_id: str) -> str:
        self._select_plan_card(plan_id)
        plan = self.plan_rows.get(plan_id) or {}
        menu = Menu(
            self.root,
            tearoff=False,
            background=UI["surface_overlay"],
            foreground=UI["text"],
            activebackground=UI["selected"],
            activeforeground=UI["text"],
            disabledforeground=UI["text_disabled"],
            borderwidth=1,
            relief="flat",
        )
        if plan.get("final_path"):
            menu.add_command(
                label="打开文件位置",
                command=self.open_plan_location,
            )
        if plan.get("page_url"):
            menu.add_command(
                label="打开来源网页",
                command=self.open_plan_source,
            )
        if plan.get("final_path") or plan.get("page_url"):
            menu.add_separator()
        menu.add_command(
            label="清理任务（保留文件）",
            command=lambda value=plan_id: self.remove_media_plan(value),
        )
        x = int(getattr(event, "x_root", 0) or self.root.winfo_pointerx())
        y = int(getattr(event, "y_root", 0) or self.root.winfo_pointery())
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
        return "break"

    def _render_plan_cards(self, plans: list[dict]) -> None:
        self.plan_card_list.clear()
        self.plan_card_widgets.clear()
        self.plan_thumbnail_images.clear()
        if not plans:
            self.plan_empty_label = ttk.Label(
                self.plan_card_list.content,
                text="暂无媒体任务\n从浏览器扩展或视频号提交后会显示在这里",
                style="Muted.TLabel",
                anchor="center",
                justify="center",
                image=self.ui_icons.get("downloads-muted"),
                compound="top",
                padding=(16, 40),
            )
            self.plan_empty_label.pack(fill=BOTH, expand=True)
            return

        for plan in plans:
            plan_id = str(plan["id"])
            view = _media_plan_view(plan)
            selected = plan_id == self.selected_plan_card_id
            frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
            title_style = (
                "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
            )
            meta_style = (
                "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
            )
            row = _RoundedPanel(
                self.plan_card_list.content,
                fill=UI["selected"] if selected else UI["surface"],
                outer_background=UI["surface"],
                style=frame_style,
                radius=RADII["card"],
                height=self.metrics["task_row_height"] - max(1, round(4 * self.ui_scale)),
                inset=4,
                takefocus=True,
            )
            row.pack(fill=X, padx=6, pady=2)
            body = ttk.Frame(
                row.inner,
                style=frame_style,
                padding=(8, 5, 8, 4),
            )
            body.pack(fill=BOTH, expand=True)
            body.columnconfigure(1, weight=1)

            thumbnail_host = _RoundedPanel(
                body,
                fill=UI["surface_overlay"],
                outer_background=UI["selected"] if selected else UI["surface"],
                style="Soft.TFrame",
                width=48,
                height=32,
                radius=RADII["thumbnail"],
                inset=2,
            )
            thumbnail_host.grid(
                row=0,
                column=0,
                rowspan=2,
                sticky="nw",
                padx=(0, 8),
            )
            thumbnail = ttk.Label(
                thumbnail_host.inner,
                image=self._plan_thumbnail(plan_id, plan),
                text="" if self.brand_image else "视频",
                style="Soft.TLabel",
                anchor="center",
            )
            thumbnail.pack(fill=BOTH, expand=True)

            title = ttk.Label(
                body,
                text=_ellipsize(
                    plan.get("title") or plan.get("output_name") or "未命名任务",
                    22,
                ),
                style=title_style,
                anchor="w",
            )
            title.grid(row=0, column=1, columnspan=2, sticky="ew")
            page_url = str(plan.get("page_url") or "")
            domain = urlsplit(page_url).hostname if page_url else ""
            source = ttk.Label(
                body,
                text=_ellipsize(domain or "未记录来源", 28),
                style=meta_style,
                anchor="w",
            )
            source.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(2, 0))

            status_key = str(view.get("status") or "queued")
            if status_key == "ready_to_import" and str(plan.get("job_status") or "") == "waiting_eagle":
                status_key = "waiting_eagle"
            status_colors = UI.get(
                f"status_{status_key}",
                (UI["text_muted"], UI["surface_overlay"]),
            )
            status = _RoundedBadge(
                body,
                text=MEDIA_CARD_STATUS_TEXT.get(
                    status_key,
                    str(view["status_label"]),
                ),
                foreground=status_colors[0],
                fill=status_colors[1],
                outer_background=UI["selected"] if selected else UI["surface"],
            )
            status.grid(row=2, column=0, sticky="w", pady=(4, 0))
            timestamp = float(plan.get("created_at") or plan.get("updated_at") or 0)
            time_text = _relative_time_label(timestamp)
            size_text = view["total"] if view["total"] != "未知" else view["processed"]
            size = ttk.Label(
                body,
                text=size_text,
                style=meta_style,
                anchor="w",
            )
            size.grid(row=2, column=1, sticky="w", pady=(4, 0), padx=(6, 0))
            timestamp_label = ttk.Label(
                body,
                text=time_text,
                style=meta_style,
                anchor="e",
            )
            timestamp_label.grid(row=2, column=2, sticky="e", pady=(4, 0))

            progress = _RoundedProgressBar(
                row.inner,
                height=4,
                background=UI["selected"] if selected else UI["surface"],
            )
            progress.pack(fill=X, side="bottom")
            progress_style = (
                "Progress.Emerald.Horizontal.TProgressbar"
                if view["status"] in ("completed_local", "imported")
                else "Progress.Orange.Horizontal.TProgressbar"
                if view["status"] == "waiting_eagle"
                else "Progress.Indigo.Horizontal.TProgressbar"
            )
            progress.configure(value=view["progress"], style=progress_style)
            self.plan_card_widgets[plan_id] = {
                "row": row,
                "body": body,
                "thumbnail_host": thumbnail_host,
                "thumbnail": thumbnail,
                "thumbnail_signature": _path_render_revision(
                    plan.get("preview_path"),
                ),
                "title": title,
                "source": source,
                "status": status,
                "size": size,
                "timestamp": timestamp_label,
                "progress": progress,
            }
            for widget in (
                row,
                row.inner,
                body,
                thumbnail_host,
                thumbnail_host.inner,
                thumbnail,
                title,
                source,
                status,
                size,
                timestamp_label,
                progress,
            ):
                self._bind_plan_card(widget, plan_id)

    def _update_plan_card_widget(self, plan_id: str, plan: dict) -> None:
        widgets = self.plan_card_widgets.get(plan_id)
        if not widgets:
            return
        view = _media_plan_view(plan)
        selected = plan_id == self.selected_plan_card_id
        frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
        title_style = (
            "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
        )
        meta_style = (
            "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
        )
        surface = UI["selected"] if selected else UI["surface"]
        row = widgets["row"]
        if isinstance(row, _RoundedPanel):
            row.set_surface(fill=surface, style=frame_style)
        _configure_if_changed(widgets["body"], style=frame_style)
        thumbnail_host = widgets["thumbnail_host"]
        if isinstance(thumbnail_host, _RoundedPanel):
            _configure_if_changed(thumbnail_host, background=surface)

        title_text = _ellipsize(
            plan.get("title") or plan.get("output_name") or "未命名任务",
            22,
        )
        page_url = str(plan.get("page_url") or "")
        domain = urlsplit(page_url).hostname if page_url else ""
        timestamp = float(plan.get("created_at") or plan.get("updated_at") or 0)
        size_text = view["total"] if view["total"] != "未知" else view["processed"]
        _configure_if_changed(widgets["title"], text=title_text, style=title_style)
        _configure_if_changed(
            widgets["source"],
            text=_ellipsize(domain or "未记录来源", 28),
            style=meta_style,
        )
        _configure_if_changed(widgets["size"], text=size_text, style=meta_style)
        _configure_if_changed(
            widgets["timestamp"],
            text=_relative_time_label(timestamp),
            style=meta_style,
        )

        status_key = str(view.get("status") or "queued")
        if (
            status_key == "ready_to_import"
            and str(plan.get("job_status") or "") == "waiting_eagle"
        ):
            status_key = "waiting_eagle"
        status_colors = UI.get(
            f"status_{status_key}",
            (UI["text_muted"], UI["surface_overlay"]),
        )
        status = widgets["status"]
        if isinstance(status, _RoundedBadge):
            status.set_badge(
                text=MEDIA_CARD_STATUS_TEXT.get(
                    status_key,
                    str(view["status_label"]),
                ),
                foreground=status_colors[0],
                fill=status_colors[1],
                outer_background=surface,
            )
        progress_style = (
            "Progress.Emerald.Horizontal.TProgressbar"
            if view["status"] in ("completed_local", "imported")
            else "Progress.Orange.Horizontal.TProgressbar"
            if view["status"] == "waiting_eagle"
            else "Progress.Indigo.Horizontal.TProgressbar"
        )
        progress = widgets["progress"]
        if isinstance(progress, _RoundedProgressBar):
            progress.configure(
                background=surface,
                value=view["progress"],
                style=progress_style,
            )

        preview_signature = _path_render_revision(plan.get("preview_path"))
        if preview_signature != widgets.get("thumbnail_signature"):
            widgets["thumbnail_signature"] = preview_signature
            image = self._plan_thumbnail(plan_id, plan)
            widgets["thumbnail"].configure(
                image=image,
                text="" if image is not None else "视频",
            )

    def _select_plan_card(self, plan_id: str) -> None:
        if plan_id not in self.plan_rows:
            return
        self.selected_plan_card_id = plan_id
        for current_id in self.plan_card_widgets:
            plan = self.plan_rows.get(current_id)
            if plan is not None:
                self._update_plan_card_widget(current_id, plan)
        self.last_plan_detail_revision = None
        self._update_plan_detail()

    def _refresh_media_tasks(self, plans: list[dict], _force: bool) -> None:
        revision = (
            len(plans),
            max((float(plan.get("updated_at") or 0) for plan in plans), default=0.0),
        )
        self.plan_rows = {str(plan["id"]): plan for plan in plans}
        selected = self.selected_plan_id()
        if revision != self.last_plans_revision:
            previous_count = self.last_plans_revision[0] if self.last_plans_revision else 0
            if len(plans) > previous_count:
                selected = str(plans[0]["id"]) if plans else ""
            if selected not in self.plan_rows:
                selected = str(plans[0]["id"]) if plans else ""
            self.selected_plan_card_id = selected or ""
            plan_order = [str(plan["id"]) for plan in plans]
            if plan_order != list(self.plan_card_widgets):
                self._render_plan_cards(plans)
            else:
                for plan in plans:
                    self._update_plan_card_widget(str(plan["id"]), plan)
            self.last_plans_revision = revision
        self._update_plan_detail()

    def selected_plan_id(self) -> str | None:
        return self.selected_plan_card_id or None

    def selected_plan(self) -> dict | None:
        plan_id = self.selected_plan_id()
        return self.plan_rows.get(plan_id) if plan_id else None

    def _update_plan_detail(self) -> None:
        plan = self.selected_plan()
        if not plan:
            if self.last_plan_detail_revision == ("empty",):
                return
            self.last_plan_detail_revision = ("empty",)
            self.last_plan_preview_revision = None
            _set_var_if_changed(self.plan_title_text, "选择一项任务查看详情")
            _set_var_if_changed(self.plan_status_text, "")
            _set_var_if_changed(self.plan_source_text, "")
            _set_var_if_changed(self.plan_file_text, "")
            _set_var_if_changed(self.plan_progress_text, "—")
            _set_var_if_changed(self.plan_size_text, "—")
            _set_var_if_changed(self.plan_domain_text, "—")
            _set_var_if_changed(self.plan_detail_text, "")
            _set_var_if_changed(self.plan_error_text, "")
            if self.plan_error_label.winfo_manager():
                self.plan_error_label.pack_forget()
            self.plan_progress.configure(value=0, style="Progress.Indigo.Horizontal.TProgressbar")
            self.preview_image = None
            self.preview_cache.clear()
            _configure_if_changed(
                self.preview_label,
                image=self.ui_icons.get("downloads-muted"),
                text="暂无预览",
            )
            self._update_plan_actions(None)
            return
        view = _media_plan_view(plan)
        detail = str(plan.get("phase_detail") or "")
        error = str(plan.get("error_message") or plan.get("job_error") or "")
        full_title = str(
            plan.get("title") or plan.get("output_name") or "未命名任务"
        )
        title_limit = (
            24
            if self.layout_mode == LAYOUT_COMPACT
            else 38
            if self.layout_mode == LAYOUT_NORMAL
            else 48
        )
        source = str(plan.get("page_url") or "")
        domain = urlsplit(source).hostname if source else ""
        output = str(plan.get("final_path") or plan.get("output_name") or "")
        preview_revision = _path_render_revision(plan.get("preview_path"))
        detail_revision = (
            str(plan.get("id") or ""),
            float(plan.get("updated_at") or 0),
            self.layout_mode,
            str(view.get("status") or ""),
            float(view.get("progress") or 0),
            str(view.get("processed") or ""),
            str(view.get("total") or ""),
            full_title,
            source,
            output,
            detail,
            error,
            preview_revision,
            bool(output and Path(output).is_file()),
            self.eagle_connected,
        )
        if detail_revision == self.last_plan_detail_revision:
            return
        self.last_plan_detail_revision = detail_revision
        _set_var_if_changed(
            self.plan_title_text,
            _ellipsize(full_title, title_limit),
        )
        _set_var_if_changed(self.plan_status_text, str(view["status_label"]))
        _set_var_if_changed(
            self.plan_source_text,
            domain or "未记录来源网页",
        )
        _set_var_if_changed(self.plan_domain_text, domain or "未记录")
        _set_var_if_changed(
            self.plan_progress_text,
            f"{view['progress']:.0f}%",
        )
        _set_var_if_changed(
            self.plan_size_text,
            f"{view['processed']} / {view['total']}",
        )
        _set_var_if_changed(
            self.plan_detail_text,
            detail or "等待新的阶段信息",
        )
        _set_var_if_changed(self.plan_error_text, error)
        if error:
            if not self.plan_error_label.winfo_manager():
                self.plan_error_label.pack(fill=X, pady=(8, 0))
        elif self.plan_error_label.winfo_manager():
            self.plan_error_label.pack_forget()
        _set_var_if_changed(
            self.plan_file_text,
            f"完整标题：{full_title}\n"
            f"来源：{source or '未记录来源网页'}\n"
            f"输出：{output or '尚未生成'}",
        )
        status = view.get("status", "")
        if status in ("completed_local", "imported"):
            prog_style = "Progress.Emerald.Horizontal.TProgressbar"
        elif status == "waiting_eagle":
            prog_style = "Progress.Orange.Horizontal.TProgressbar"
        else:
            prog_style = "Progress.Indigo.Horizontal.TProgressbar"
        self.plan_progress.configure(value=view["progress"], style=prog_style)
        self._update_plan_actions(view)
        if preview_revision == self.last_plan_preview_revision:
            return
        self.last_plan_preview_revision = preview_revision
        preview = Path(str(plan.get("preview_path") or ""))
        image = self.preview_cache.resolve(preview)
        if image is not None:
            target_height = 180 if self.layout_mode == LAYOUT_COMPACT else 252
            self.preview_image = _fit_photo_image(
                image,
                self.metrics["preview_max_width"],
                target_height,
            )
            self.preview_label.configure(image=self.preview_image, text="")
            return
        self.preview_image = None
        self.preview_label.configure(
            image=self.ui_icons.get("downloads-muted"),
            text="下载完成后显示视频预览",
        )

    def _update_plan_actions(self, view: dict | None) -> None:
        if not hasattr(self, "plan_action_buttons"):
            return
        plan = self.selected_plan()
        final_path = str(plan.get("final_path") or "") if plan else ""
        final_exists = bool(final_path and Path(final_path).is_file())
        permissions = {
            "stop": bool(view and view["active"]),
            "retry": bool(view and view["can_retry"]),
            "import": bool(
                self.eagle_connected
                and view
                and view["can_import_existing"]
                and final_exists
            ),
            "open": bool(view and view["can_open_output"] and final_exists),
            "source": bool(view and view["can_open_source"]),
        }
        for name, button in self.plan_action_buttons.items():
            button.set_enabled(permissions[name])
        self.plan_action_buttons["import"].configure(
            text="补导 Eagle" if self.eagle_connected else "Eagle 未连接",
            style="Accent.TButton" if self.eagle_connected else "Quiet.TButton",
        )

    def stop_selected_plan(self) -> None:
        plan = self.selected_plan()
        if not plan:
            messagebox.showinfo("提示", "请先选择一项媒体任务")
            return
        try:
            self.media.stop_plan(str(plan["id"]))
        except Exception as exc:
            messagebox.showerror("停止失败", str(exc), parent=self.root)
        self.refresh(force=True)

    def retry_selected_plan(self) -> None:
        plan = self.selected_plan()
        if not plan:
            messagebox.showinfo("提示", "请先选择一项媒体任务")
            return
        try:
            self.media.retry_plan(str(plan["id"]))
        except Exception as exc:
            messagebox.showerror("无法重试", str(exc), parent=self.root)
            return
        self.refresh(force=True)

    def open_plan_location(self) -> None:
        plan = self.selected_plan()
        if not plan or not plan.get("final_path"):
            messagebox.showinfo("文件尚未完成", "任务完成下载后才能打开文件位置")
            return
        try:
            self.media.open_plan_output(str(plan["id"]))
        except Exception as exc:
            messagebox.showerror("无法打开文件位置", str(exc), parent=self.root)

    def import_selected_plan(self) -> None:
        plan = self.selected_plan()
        if not plan:
            messagebox.showinfo("提示", "请先选择一项媒体任务")
            return
        if not self.eagle_connected:
            messagebox.showinfo(
                "Eagle 未连接",
                "本机文件已安全保留。安装或启动 Eagle 后，此按钮会自动恢复，可直接补导而无需重新下载。",
                parent=self.root,
            )
            return
        try:
            self.media.import_completed_plan(str(plan["id"]))
        except Exception as exc:
            messagebox.showerror("无法导入", str(exc), parent=self.root)
            return
        self.processing.wake()
        self.refresh(force=True)

    def remove_media_plan(self, plan_id: str) -> None:
        plan = self.plan_rows.get(plan_id)
        if not plan:
            self.refresh(force=True)
            return
        status = str(plan.get("status") or "")
        active_note = (
            "该任务仍在处理，将先停止并退出待处理队列。\n\n"
            if status in MEDIA_ACTIVE_STATUSES
            else ""
        )
        if not messagebox.askyesno(
            "清理媒体任务",
            f"{active_note}只清理这条任务记录，不删除已经下载的本机文件、预览文件或 Eagle 内容。是否继续？",
            parent=self.root,
        ):
            return
        try:
            result = self.media.remove_plan(plan_id)
        except Exception as exc:
            messagebox.showerror("无法清理任务", str(exc), parent=self.root)
            return
        if self.selected_plan_card_id == plan_id:
            self.selected_plan_card_id = ""
        self.last_plans_revision = None
        self.refresh(force=True)
        messagebox.showinfo(
            "清理完成",
            (
                "任务已从列表和待处理队列移除，本机下载文件已保留。"
                if result.get("filePreserved")
                else "任务已从列表和待处理队列移除。"
            ),
            parent=self.root,
        )

    def open_plan_source(self) -> None:
        plan = self.selected_plan()
        if not plan or not plan.get("page_url"):
            messagebox.showinfo("没有来源", "这项任务没有记录来源网页")
            return
        try:
            opened = webbrowser.open(str(plan["page_url"]))
        except Exception as exc:
            messagebox.showerror("无法打开来源网页", str(exc), parent=self.root)
            return
        if not opened:
            messagebox.showerror(
                "无法打开来源网页",
                "系统没有可用的默认浏览器，请复制来源地址后手动打开。",
                parent=self.root,
            )

    def selected_job_id(self) -> str | None:
        selected = self.job_tree.selection()
        return selected[0] if selected else None

    def selected_job(self) -> dict | None:
        job_id = self.selected_job_id()
        return self.database.get_job(job_id) if job_id else None

    def _show_job_context_menu(self, event: object) -> str:
        keyboard_open = str(getattr(event, "keysym", "")) == "F10"
        y = int(getattr(event, "y", 0) or 0)
        job_id = (
            ""
            if keyboard_open
            else str(self.job_tree.identify_row(y) or "")
        )
        if job_id:
            self.job_tree.selection_set(job_id)
        else:
            job_id = self.selected_job_id() or ""
        job = self.database.get_job(job_id) if job_id else None
        if not job:
            return "break"
        menu = Menu(
            self.root,
            tearoff=False,
            background=UI["surface_overlay"],
            foreground=UI["text"],
            activebackground=UI["selected"],
            activeforeground=UI["text"],
            disabledforeground=UI["text_disabled"],
            borderwidth=1,
            relief="flat",
        )
        file_path = str(job.get("file_path") or "")
        if file_path and Path(file_path).is_file():
            menu.add_command(label="打开原文件位置", command=self.open_file_location)
        if job.get("source_url"):
            menu.add_command(label="打开来源网页", command=self.open_source)
        if (file_path and Path(file_path).exists()) or job.get("source_url"):
            menu.add_separator()
        menu.add_command(label="清理记录（保留文件）", command=self.remove_selected_job)
        x = int(getattr(event, "x_root", 0) or self.root.winfo_pointerx())
        y_root = int(getattr(event, "y_root", 0) or self.root.winfo_pointery())
        try:
            menu.tk_popup(x, y_root)
        finally:
            menu.grab_release()
        return "break"

    def _update_idm_detail(self) -> None:
        job_id = self.selected_job_id()
        query_key = (job_id, self.last_jobs_revision)
        if query_key == self.idm_detail_query_key:
            job = self.idm_detail_query_value
        else:
            job = self.database.get_job(job_id) if job_id else None
            self.idm_detail_query_key = query_key
            self.idm_detail_query_value = job
        if not job:
            if self.last_idm_detail_revision == ("empty",):
                return
            self.last_idm_detail_revision = ("empty",)
            _set_var_if_changed(
                self.idm_detail_title_text,
                "选择一条记录查看完整内容",
            )
            _set_var_if_changed(self.idm_detail_status_text, "")
            _set_var_if_changed(self.idm_detail_file_text, "—")
            _set_var_if_changed(self.idm_detail_source_text, "—")
            _set_var_if_changed(self.idm_detail_message_text, "—")
            self._update_idm_actions(None)
            return
        revision = (
            str(job.get("id") or ""),
            float(job.get("updated_at") or 0),
            str(job.get("status") or ""),
            str(job.get("file_name") or ""),
            str(job.get("file_path") or ""),
            str(job.get("source_url") or ""),
            str(job.get("error_message") or ""),
            bool(
                job.get("file_path")
                and Path(str(job.get("file_path"))).is_file()
            ),
            self.eagle_connected,
        )
        if revision == self.last_idm_detail_revision:
            return
        self.last_idm_detail_revision = revision
        created = time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(float(job.get("created_at") or 0)),
        )
        status = str(job.get("status") or "")
        _set_var_if_changed(
            self.idm_detail_title_text,
            str(job.get("file_name") or "未命名文件"),
        )
        _set_var_if_changed(
            self.idm_detail_status_text,
            f"{STATUS_TEXT.get(status, status)} · {created}"
        )
        _set_var_if_changed(
            self.idm_detail_file_text,
            str(job.get("file_path") or "—"),
        )
        _set_var_if_changed(
            self.idm_detail_source_text,
            str(job.get("source_url") or "未记录可靠来源")
        )
        message = str(job.get("error_message") or "")
        if status == "imported" and not job.get("source_url"):
            message = "已直接导入；Eagle 网站字段保持为空。"
        _set_var_if_changed(
            self.idm_detail_message_text,
            message or "暂无补充说明",
        )
        self._update_idm_actions(job)

    def _update_idm_actions(self, job: dict | None) -> None:
        if not hasattr(self, "idm_action_buttons"):
            return
        status = str(job.get("status") or "") if job else ""
        retryable = status in {
            "waiting_source",
            "queued",
            "waiting_eagle",
            "retry",
            "failed_permanent",
        }
        file_path = str(job.get("file_path") or "") if job else ""
        file_exists = bool(file_path and Path(file_path).is_file())
        permissions = {
            "retry": retryable and self.eagle_connected and file_exists,
            "open": file_exists,
            "source": bool(job and job.get("source_url")),
            "assign": bool(
                job
                and status != "skipped_duplicate"
                and (
                    status != "imported"
                    or (
                        self.eagle_connected
                        and bool(job.get("eagle_item_id"))
                    )
                )
            ),
            "remove": bool(job),
        }
        if self.maintenance_busy:
            permissions["retry"] = False
            permissions["assign"] = False
            permissions["remove"] = False
        for name, button in self.idm_action_buttons.items():
            button.configure(state="normal" if permissions[name] else "disabled")
        self.idm_action_buttons["retry"].configure(
            text="重试导入" if self.eagle_connected else "Eagle 未连接",
            style="Accent.TButton" if self.eagle_connected else "Quiet.TButton",
        )

    def retry_selected(self) -> None:
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        job_id = str(job["id"])
        if not self.eagle_connected:
            messagebox.showinfo(
                "Eagle 未连接",
                "IDM 原文件已保留。安装或启动 Eagle 后再重试导入；浏览器和视频号仅下载不受影响。",
                parent=self.root,
            )
            return
        file_path = Path(str(job.get("file_path") or ""))
        if not file_path.is_file():
            messagebox.showwarning(
                "无法重试导入",
                "IDM 原文件已经不在记录的位置，无法导入 Eagle。记录仍会保留，可选择清理记录。",
                parent=self.root,
            )
            return
        if not self.database.retry_job(job_id):
            self.refresh(force=True)
            messagebox.showinfo("无需重试", "这条记录已经处理完成，不需要再次重试。")
            return
        self.processing.wake()
        self.refresh()

    def remove_selected_job(self) -> None:
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        status = str(job.get("status") or "")
        active_note = (
            "该记录仍在导入队列，清理后将不再自动处理。\n\n"
            if status in {"waiting_source", "queued", "waiting_eagle", "retry"}
            else ""
        )
        if not messagebox.askyesno(
            "清理 IDM 导入记录",
            f"{active_note}只清理这条记录，不删除 IDM 原文件或 Eagle 内容。是否继续？",
            parent=self.root,
        ):
            return
        try:
            removed = self.database.remove_job(str(job["id"]))
        except ValueError as exc:
            messagebox.showerror("无法清理记录", str(exc), parent=self.root)
            return
        self.processing.wake()
        self.last_jobs_revision = None
        self.refresh(force=True)
        messagebox.showinfo(
            "清理完成",
            "记录已从列表和导入队列移除，原文件已保留。"
            if removed
            else "这条记录已经被清理。",
            parent=self.root,
        )

    def open_file_location(self) -> None:
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        path = Path(job["file_path"])
        if not path.is_file():
            messagebox.showwarning("文件不存在", "下载文件已经不在原位置")
            return
        try:
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
        except OSError as exc:
            messagebox.showerror(
                "无法打开文件位置",
                str(exc),
                parent=self.root,
            )

    def open_source(self) -> None:
        job = self.selected_job()
        if not job or not job.get("source_url"):
            messagebox.showinfo("没有来源", "这条记录还没有匹配到来源网页")
            return
        try:
            opened = webbrowser.open(str(job["source_url"]))
        except Exception as exc:
            messagebox.showerror("无法打开来源网页", str(exc), parent=self.root)
            return
        if not opened:
            messagebox.showerror(
                "无法打开来源网页",
                "系统没有可用的默认浏览器，请复制来源地址后手动打开。",
                parent=self.root,
            )

    def assign_source(self) -> None:
        if self.maintenance_busy:
            return
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if job["status"] == "imported":
            if not self.eagle_connected:
                messagebox.showinfo(
                    "Eagle 未连接",
                    "这条记录已经在 Eagle 中；启动 Eagle 后才能同步修改来源。本机记录和文件不会受影响。",
                    parent=self.root,
                )
                return
            if not job.get("eagle_item_id"):
                messagebox.showwarning(
                    "无法更新",
                    "这条旧记录没有 Eagle 项目编号，无法自动补写来源。",
                    parent=self.root,
                )
                return
        value = simpledialog.askstring(
            "补充来源网页",
            "请输入视频所在网页地址：",
            parent=self.root,
        )
        if not value:
            return
        try:
            cleaned = clean_page_url(value)
        except ValueError as exc:
            messagebox.showerror("网址无效", str(exc))
            return

        if job["status"] == "imported":
            self._start_maintenance(
                "update-eagle-source",
                self._update_eagle_source_worker,
                str(job["id"]),
                str(job["eagle_item_id"]),
                cleaned,
            )
            return

        if job["status"] == "skipped_duplicate":
            messagebox.showinfo("重复项目", "这条记录因内容重复被跳过，没有新的 Eagle 项目可以补写来源。")
            return

        self.database.assign_source(job["id"], cleaned)
        self.processing.wake()
        self.refresh(force=True)

    def _update_eagle_source_worker(
        self,
        job_id: str,
        eagle_item_id: str,
        source_url: str,
    ) -> bool:
        self.eagle.update_source(eagle_item_id, source_url)
        if not self.database.record_imported_source(job_id, source_url):
            raise RuntimeError("任务状态已经变化，来源记录未能同步到本机数据库")
        return True

    def export_diagnostics(self) -> None:
        if self.maintenance_busy:
            return
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出诊断记录",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="idm-eagle-diagnostics.json",
        )
        if not target:
            return
        if hasattr(self, "diagnostics_feedback_text"):
            self.diagnostics_feedback_text.set("正在后台生成诊断文件…")
        self._start_maintenance(
            "diagnostics-export",
            self._export_diagnostics_worker,
            target,
            self.performance_monitor.snapshot(),
        )

    def _export_diagnostics_worker(
        self,
        target: str,
        performance_snapshot: dict[str, object],
    ) -> str:
        rows = []
        for job in self.database.list_jobs(500):
            source_domain = ""
            if job.get("source_url"):
                source_domain = urlsplit(job["source_url"]).hostname or ""
            rows.append(
                {
                    "time": job["created_at"],
                    "status": job["status"],
                    "fileName": job["file_name"],
                    "sourceDomain": source_domain,
                    "attempts": job["attempt_count"],
                    "errorCode": job.get("error_code"),
                    "errorMessage": job.get("error_message"),
                }
            )
        media_rows = []
        for plan in self.media.list_plans(200):
            source_domain = ""
            if plan.get("page_url"):
                source_domain = urlsplit(str(plan["page_url"])).hostname or ""
            media_rows.append(
                {
                    "time": plan["created_at"],
                    "status": plan["status"],
                    "title": plan.get("title"),
                    "outputName": plan.get("output_name"),
                    "sourceDomain": source_domain,
                    "progress": plan.get("progress"),
                    "downloadedBytes": plan.get("downloaded_bytes"),
                    "totalBytes": plan.get("total_bytes"),
                    "phase": plan.get("phase_detail"),
                    "errorCode": plan.get("error_code"),
                    "errorMessage": plan.get("error_message") or plan.get("job_error"),
                }
            )
        Path(target).write_text(
            json.dumps(
                {
                    "formatVersion": 3,
                    "appVersion": APP_VERSION,
                    "networkProxy": {
                        key: value
                        for key, value in self.media.network_proxy.status().items()
                        if key in {"mode", "active", "source", "endpoint", "summary"}
                    },
                    "performance": performance_snapshot,
                    "mediaPlans": media_rows,
                    "jobs": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    def _set_maintenance_buttons(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for name in (
            "media_clear_button",
            "idm_clear_button",
            "diagnostics_export_button",
            "cache_clear_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)
        if hasattr(self, "idm_action_buttons"):
            self._update_idm_actions(self.idm_detail_query_value)

    def _start_maintenance(self, kind: str, worker, *args: object) -> None:
        if self.maintenance_busy or self.closing:
            return
        self.maintenance_generation += 1
        generation = self.maintenance_generation
        self.maintenance_busy = True
        self.maintenance_kind = kind
        self._set_maintenance_buttons(True)
        threading.Thread(
            target=self._run_maintenance,
            args=(generation, kind, worker, args),
            name=f"ui-{kind}",
            daemon=True,
        ).start()
        self._schedule_maintenance_poll()

    def _run_maintenance(
        self,
        generation: int,
        kind: str,
        worker,
        args: tuple[object, ...],
    ) -> None:
        started = time.perf_counter()
        try:
            result = worker(*args)
            succeeded = True
        except Exception as exc:
            result = str(exc)
            succeeded = False
        finally:
            self._record_performance(
                f"background.{kind}",
                started,
                kind,
                background=True,
            )
        if self.closing:
            return
        try:
            self.maintenance_events.put_nowait(
                (generation, kind, succeeded, result)
            )
        except Full:
            pass

    def _schedule_maintenance_poll(self) -> None:
        if self.closing or not self.maintenance_busy:
            return
        if self.maintenance_after_id is None:
            self.maintenance_after_id = self.root.after(
                100,
                self._poll_maintenance,
            )

    def _poll_maintenance(self) -> None:
        started = time.perf_counter()
        self.maintenance_after_id = None
        result: tuple[str, bool, object] | None = None
        for _index in range(UI_QUEUE_DRAIN_LIMIT):
            try:
                generation, kind, succeeded, payload = (
                    self.maintenance_events.get_nowait()
                )
            except Empty:
                break
            if generation == self.maintenance_generation:
                result = (kind, succeeded, payload)
                break
        if result is None:
            self._schedule_maintenance_poll()
            self._record_performance(
                "queue.maintenance",
                started,
                "consume-maintenance",
            )
            return
        kind, succeeded, payload = result
        self.maintenance_busy = False
        self.maintenance_kind = ""
        self._set_maintenance_buttons(False)
        self._record_performance(
            "queue.maintenance",
            started,
            "consume-maintenance",
        )
        if kind == "diagnostics-export":
            if succeeded:
                if hasattr(self, "diagnostics_feedback_text"):
                    self.diagnostics_feedback_text.set("诊断文件已安全导出")
                messagebox.showinfo(
                    "导出完成",
                    "诊断记录已保存。完整路径、来源网址和代理密码未包含在文件中。",
                    parent=self.root,
                )
            else:
                if hasattr(self, "diagnostics_feedback_text"):
                    self.diagnostics_feedback_text.set(
                        "导出失败，请更换保存位置后重试"
                    )
                messagebox.showerror(
                    "导出失败",
                    str(payload),
                    parent=self.root,
                )
        elif kind == "clear-idm":
            if succeeded:
                self.last_jobs_revision = None
                self.idm_detail_query_key = None
                self.refresh(force=True)
                messagebox.showinfo(
                    "清理完成",
                    f"已清除 {int(payload)} 条 IDM 导入记录。",
                    parent=self.root,
                )
            else:
                messagebox.showerror(
                    "清理失败",
                    str(payload),
                    parent=self.root,
                )
        elif kind == "clear-media":
            if succeeded:
                self.last_plans_revision = None
                self.refresh(force=True)
                messagebox.showinfo(
                    "清理完成",
                    f"已清除 {int(payload)} 条媒体任务记录。",
                    parent=self.root,
                )
            else:
                messagebox.showerror(
                    "清理失败",
                    str(payload),
                    parent=self.root,
                )
        elif kind == "cache-scan":
            if succeeded and hasattr(self, "cache_summary_text"):
                self.cache_summary_text.set(self._cache_status_summary(dict(payload)))
            elif hasattr(self, "cache_summary_text"):
                self.cache_summary_text.set("缓存统计失败，可稍后重试")
        elif kind == "clear-cache":
            if succeeded:
                result = dict(payload)
                self.preview_cache.clear()
                self.last_plan_preview_revision = None
                if hasattr(self, "cache_summary_text"):
                    self.cache_summary_text.set(
                        f"清理完成：释放 {_display_bytes(result.get('freedBytes'))}，"
                        f"剩余 {_display_bytes(result.get('remainingBytes'))}"
                    )
                self.refresh(force=True)
                messagebox.showinfo(
                    "缓存清理完成",
                    f"已释放 {_display_bytes(result.get('freedBytes'))}，"
                    f"删除 {int(result.get('removedFiles') or 0)} 个缓存文件。"
                    f"活动任务跳过 {int(result.get('skippedActive') or 0)} 项；"
                    "已完成文件、IDM 原文件和用户文件均已保留。",
                    parent=self.root,
                )
            else:
                if hasattr(self, "cache_summary_text"):
                    self.cache_summary_text.set("缓存清理失败，可稍后重试")
                messagebox.showerror(
                    "缓存清理失败",
                    str(payload),
                    parent=self.root,
                )
        elif kind == "update-eagle-source":
            if succeeded:
                self.last_jobs_revision = None
                self.idm_detail_query_key = None
                self.refresh(force=True)
                messagebox.showinfo(
                    "更新完成",
                    "来源网址已经写入现有 Eagle 项目，不会重复导入文件。",
                    parent=self.root,
                )
            else:
                messagebox.showerror(
                    "更新失败",
                    str(payload),
                    parent=self.root,
                )

    def clear_history(self) -> None:
        if self.maintenance_busy:
            return
        if not messagebox.askyesno(
            "清除 IDM 导入记录",
            "只清除成功、失败和已跳过的终态记录；等待中的任务会保留。下载文件和 Eagle 内容不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        self._start_maintenance(
            "clear-idm",
            self.database.clear_terminal_history,
        )

    def clear_media_history(self) -> None:
        if self.maintenance_busy:
            return
        if not messagebox.askyesno(
            "清除媒体任务记录",
            "只清除已导入、已下载、下载失败和已停止的任务记录；进行中及等待导入的任务会保留。"
            "下载文件、预览文件和 Eagle 内容不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        self._start_maintenance(
            "clear-media",
            self.media.clear_terminal_history,
        )

    def quit(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.wechat_operation_generation += 1
        self.maintenance_generation += 1
        with self.wechat_preview_lock:
            self.wechat_preview_generation += 1
            self.wechat_preview_pending = None
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if self.page_refresh_after_id:
            self.root.after_cancel(self.page_refresh_after_id)
            self.page_refresh_after_id = None
        if self.prewarm_after_id:
            self.root.after_cancel(self.prewarm_after_id)
            self.prewarm_after_id = None
        if self.control_after_id:
            self.root.after_cancel(self.control_after_id)
            self.control_after_id = None
        if self.layout_after_id:
            self.root.after_cancel(self.layout_after_id)
            self.layout_after_id = None
        if self.window_settle_after_id:
            self.root.after_cancel(self.window_settle_after_id)
            self.window_settle_after_id = None
        if self.update_poll_after_id:
            self.root.after_cancel(self.update_poll_after_id)
            self.update_poll_after_id = None
        if self.auto_update_after_id:
            self.root.after_cancel(self.auto_update_after_id)
            self.auto_update_after_id = None
        if self.media_change_after_id:
            self.root.after_cancel(self.media_change_after_id)
            self.media_change_after_id = None
        if self.wechat_operation_after_id:
            self.root.after_cancel(self.wechat_operation_after_id)
            self.wechat_operation_after_id = None
        if self.maintenance_after_id:
            self.root.after_cancel(self.maintenance_after_id)
            self.maintenance_after_id = None
        if self.performance_after_id:
            self.root.after_cancel(self.performance_after_id)
            self.performance_after_id = None
        remove_change_listener = getattr(self.media, "remove_change_listener", None)
        if callable(remove_change_listener):
            remove_change_listener(self._media_change_listener)
        if self.control_signals:
            self.control_signals.close()
            self.control_signals = None
        self.root.quit()
        self.root.destroy()
