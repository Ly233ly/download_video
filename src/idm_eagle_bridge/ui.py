from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
import json
import re
import threading
import ctypes
from fractions import Fraction
from pathlib import Path
from queue import Empty, Queue
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    BooleanVar,
    Canvas,
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
from .constants import APP_VERSION
from .control_signal import ControlSignals
from .database import Database
from .eagle import EagleClient, EagleImportError, EagleUnavailable
from .network_proxy import ProxyConfigurationError
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

UI = {
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
    "task_row_height": 100,
    "wechat_row_height": 88,
    "table_row_height": 46,
}

RADII = {
    "thumbnail": 6,
    "badge": 9,
    "control": 10,
    "card": 12,
    "panel": 14,
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
        "PairingCode.TLabel",
        background=UI["surface_raised"],
        foreground=UI["accent_text"],
        font="Mono24Bold",
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
        self.bind("<Configure>", self._update_wrap, add="+")

    def _update_wrap(self, event: object | None = None) -> None:
        width = int(getattr(event, "width", 0) or self.winfo_width() or 1)
        wrap = max(80, width - self._horizontal_padding)
        if self._maximum is not None:
            wrap = min(wrap, self._maximum)
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
        tree.bind("<Configure>", self._queue_resize, add="+")
        self._queue_resize()

    def _queue_resize(self, _event: object | None = None) -> None:
        if self._pending_after is not None:
            return
        self._pending_after = self.tree.after_idle(self._resize)

    def _resize(self) -> None:
        self._pending_after = None
        available = max(1, self.tree.winfo_width() - self.reserved_width)
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
            self.tree.column(name, width=width, minwidth=24, stretch=False)


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
    """A compact status dot with no text-glyph or emoji dependency."""

    def __init__(
        self,
        parent: object,
        *,
        color: str = UI["text_muted"],
        background: str = UI["bg"],
        size: int = 8,
    ) -> None:
        super().__init__(
            parent,
            width=size,
            height=size,
            background=background,
            highlightthickness=0,
            borderwidth=0,
        )
        self._size = size
        self._dot = self.create_oval(1, 1, size - 1, size - 1, fill=color, outline="")

    def set_color(self, color: str) -> None:
        self.itemconfigure(self._dot, fill=color)


def _rounded_polygon_points(
    left: int,
    top: int,
    right: int,
    bottom: int,
    radius: int,
) -> list[int]:
    radius = max(1, min(radius, (right - left) // 2, (bottom - top) // 2))
    return [
        left + radius,
        top,
        right - radius,
        top,
        right,
        top,
        right,
        top + radius,
        right,
        bottom - radius,
        right,
        bottom,
        right - radius,
        bottom,
        left + radius,
        bottom,
        left,
        bottom,
        left,
        bottom - radius,
        left,
        top + radius,
        left,
        top,
    ]


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
        self._radius = radius
        self._inset = max(2, inset)
        self.inner = ttk.Frame(self, style=style)
        self._inner_window = self.create_window(
            (self._inset, self._inset),
            window=self.inner,
            anchor="nw",
        )
        self.bind("<Configure>", self._redraw, add="+")

    def set_surface(
        self,
        *,
        fill: str,
        style: str,
        border: str | None = None,
    ) -> None:
        self._fill = fill
        if border is not None:
            self._border = border
        self.inner.configure(style=style)
        self._redraw()

    def _redraw(self, _event: object | None = None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("surface")
        points = _rounded_polygon_points(1, 1, width - 1, height - 1, self._radius)
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=self._fill,
            outline=self._border,
            width=self._border_width,
            tags=("surface",),
        )
        self.tag_lower("surface")
        self.coords(self._inner_window, self._inset, self._inset)
        self.itemconfigure(
            self._inner_window,
            width=max(1, width - self._inset * 2),
            height=max(1, height - self._inset * 2),
        )


class _RoundedButton(Canvas):
    """Small accessible rounded action button used in the media detail header."""

    def __init__(
        self,
        parent: object,
        *,
        text: str,
        command,
        image: PhotoImage | None = None,
        kind: str = "quiet",
        width: int = 88,
    ) -> None:
        ui_scale = _widget_ui_scale(parent)
        self._font = tkfont.Font(
            root=parent,
            family=FONT_FAMILIES["ui"],
            size=10,
            weight="normal" if kind == "quiet" else "bold",
        )
        content_width = self._font.measure(text)
        if image is not None:
            content_width += image.width() + round(6 * ui_scale)
        super().__init__(
            parent,
            width=max(
                round(width * ui_scale),
                content_width + round(24 * ui_scale),
            ),
            height=max(1, round(METRICS["button_height"] * ui_scale)),
            background=UI["surface_raised"],
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._image = image
        self._kind = kind
        self._enabled = True
        self._hovered = False
        self.bind("<Configure>", self._draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._activate, add="+")
        self.bind("<Return>", self._activate, add="+")
        self.bind("<space>", self._activate, add="+")
        self.bind("<FocusIn>", self._draw, add="+")
        self.bind("<FocusOut>", self._draw, add="+")
        self.after_idle(self._draw)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def _palette(self) -> tuple[str, str]:
        if not self._enabled:
            return UI["border"], UI["text_disabled"]
        if self._kind == "danger":
            return (
                "#3A1B22" if self._hovered else UI["danger_subtle"],
                UI["danger"],
            )
        if self._kind == "accent":
            return (
                UI["accent_hover"] if self._hovered else UI["accent_button"],
                "#FFFFFF",
            )
        return (
            UI["surface_overlay"] if self._hovered else UI["surface"],
            UI["text_secondary"],
        )

    def _draw(self, _event: object | None = None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        fill, foreground = self._palette()
        self.delete("all")
        self.create_polygon(
            _rounded_polygon_points(
                1,
                1,
                width - 1,
                height - 1,
                RADII["control"],
            ),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=UI["accent"] if self.focus_get() is self else "",
            width=1,
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
        self._hovered = True
        self._draw()

    def _leave(self, _event: object | None = None) -> None:
        self._hovered = False
        self._draw()

    def _activate(self, _event: object | None = None) -> str:
        if self._enabled:
            self._command()
        return "break"


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
        width = self._font.measure(text) + round(14 * ui_scale)
        height = max(
            round(22 * ui_scale),
            self._font.metrics("linespace") + round(4 * ui_scale),
        )
        super().__init__(
            parent,
            width=width,
            height=height,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
        )
        self.create_polygon(
            _rounded_polygon_points(0, 1, width, height - 1, RADII["badge"]),
            smooth=True,
            splinesteps=18,
            fill=fill,
            outline="",
        )
        self.create_text(
            width // 2,
            height // 2,
            text=text,
            fill=foreground,
            font=self._font,
        )


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
        self.bind("<Configure>", self._draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._activate, add="+")
        self.bind("<Return>", self._activate, add="+")
        self.bind("<space>", self._activate, add="+")
        self.bind("<FocusIn>", self._draw, add="+")
        self.bind("<FocusOut>", self._draw, add="+")
        self.after_idle(self._draw)

    def set_selected(
        self,
        selected: bool,
        *,
        image: PhotoImage | None = None,
    ) -> None:
        self._selected = bool(selected)
        if image is not None:
            self._image = image
        self._draw()

    def _draw(self, _event: object | None = None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("all")
        if self._selected or self._hovered:
            fill = UI["selected"] if self._selected else UI["surface_overlay"]
            self.create_polygon(
                _rounded_polygon_points(
                    1,
                    2,
                    width - 1,
                    height - 2,
                    RADII["control"],
                ),
                smooth=True,
                splinesteps=24,
                fill=fill,
                outline=UI["accent"] if self.focus_get() is self else "",
                width=1,
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
        self._hovered = True
        self._draw()

    def _leave(self, _event: object | None = None) -> None:
        self._hovered = False
        self._draw()

    def _activate(self, _event: object | None = None) -> str:
        self._command()
        return "break"


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
        self.bind("<Configure>", self._draw, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<Button-1>", self._press, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")

    def set(self, first: object, last: object) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        self._draw()

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

    def _draw(self, _event: object | None = None) -> None:
        self.delete("all")
        geometry = self._thumb_geometry()
        if geometry is None:
            return
        left, top, right, bottom = geometry
        fill = UI["text_secondary"] if self._hovered else UI["text_muted"]
        self.create_polygon(
            _rounded_polygon_points(
                left,
                top,
                right,
                bottom,
                max(2, (right - left) // 2),
            ),
            smooth=True,
            splinesteps=20,
            fill=fill,
            outline="",
            tags=("thumb",),
        )

    def _enter(self, _event: object | None = None) -> None:
        self._hovered = True
        self._draw()

    def _leave(self, _event: object | None = None) -> None:
        self._hovered = False
        self._draw()

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
        self.bind("<Configure>", self._draw, add="+")

    def configure(self, cnf: object | None = None, **kwargs: object) -> object:
        if "value" in kwargs:
            try:
                self._value = max(0.0, min(self._maximum, float(kwargs.pop("value"))))
            except (TypeError, ValueError):
                self._value = 0.0
        style_name = str(kwargs.pop("style", "") or "")
        if style_name:
            if "Emerald" in style_name:
                self._color = UI["success"]
            elif "Orange" in style_name:
                self._color = UI["status_waiting_eagle"][0]
            else:
                self._color = UI["accent"]
        result = super().configure(cnf, **kwargs)
        if hasattr(self, "_value"):
            self._draw()
        return result

    config = configure

    def _draw(self, _event: object | None = None) -> None:
        if not hasattr(self, "_value"):
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("all")
        radius = max(2, height // 2)
        self.create_polygon(
            _rounded_polygon_points(0, 0, width, height, radius),
            smooth=True,
            splinesteps=20,
            fill=UI["progress_track"],
            outline="",
        )
        fill_width = int(width * self._value / self._maximum)
        if fill_width <= 0:
            return
        self.create_polygon(
            _rounded_polygon_points(
                0,
                0,
                max(height, fill_width),
                height,
                min(radius, max(2, fill_width // 2)),
            ),
            smooth=True,
            splinesteps=20,
            fill=self._color,
            outline="",
        )


class _ScrollableCardList(ttk.Frame):
    """A vertically scrolling host for task and candidate card rows."""

    def __init__(
        self,
        parent: object,
        *,
        background: str = UI["bg"],
        initial_width: int | None = None,
    ) -> None:
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
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._sync, add="+")
        self.content.bind("<Configure>", self._sync, add="+")
        self.canvas.bind("<MouseWheel>", self._wheel, add="+")
        self.content.bind("<MouseWheel>", self._wheel, add="+")

    def _sync(self, _event: object | None = None) -> None:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.content.winfo_reqheight())
        self.canvas.itemconfigure(self._window, width=width)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _wheel(self, event: object) -> str:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self.canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self._sync()


def _set_window_icon(window: Tk | Toplevel) -> None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "assets" / "download-transfer-station.ico")
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "assets"
        / "download-transfer-station.ico"
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            window.iconbitmap(default=str(candidate))
            return
        except Exception:
            continue


def _load_product_image(maximum_size: int = 30) -> PhotoImage | None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(
            Path(bundle_root)
            / "idm_eagle_bridge"
            / "assets"
            / "download-transfer-station.png"
        )
        candidates.append(
            Path(bundle_root) / "assets" / "download-transfer-station.png"
        )
    candidates.append(
        Path(__file__).resolve().parent
        / "assets"
        / "download-transfer-station.png"
    )
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "assets"
        / "download-transfer-station.png"
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


def _load_ui_icons(scale: float = 1.0) -> dict[str, PhotoImage]:
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
    loaded: dict[str, PhotoImage] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.png"):
            if path.stem in loaded:
                continue
            try:
                loaded[path.stem] = _scale_photo_image(
                    PhotoImage(file=str(path)),
                    scale,
                )
            except Exception:
                continue
    return loaded


class _VerticalScrolledFrame(ttk.Frame):
    """A width-filling frame that scrolls only when its content is too tall."""

    def __init__(
        self,
        parent: object,
        *,
        padding: object = 0,
        style: str = "Surface.TFrame",
        background: str = UI["surface"],
        initial_width: int | None = None,
    ) -> None:
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
        self.scrollbar.pack(side=RIGHT, fill=Y)
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
        self.content.bind("<Configure>", self._sync_layout, add="+")
        self.canvas.bind("<Configure>", self._sync_layout, add="+")
        self.bind(
            "<Configure>",
            lambda _event: self.after_idle(self._sync_layout),
            add="+",
        )
        self._wheel_binding = self.winfo_toplevel().bind(
            "<MouseWheel>",
            self._on_mousewheel,
            add="+",
        )
        self.bind("<Destroy>", self._release_wheel_binding, add="+")

    def _sync_layout(self, _event: object | None = None) -> None:
        width = max(1, self.canvas.winfo_width())
        height = max(self.canvas.winfo_height(), self.content.winfo_reqheight(), 1)
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
            if isinstance(current, (ttk.Treeview, ttk.Combobox)):
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
        units = max(1, abs(delta) // 120)
        self.canvas.yview_scroll(-units if delta > 0 else units, "units")
        return "break"

    def scroll_to_bottom(self) -> None:
        self.update_idletasks()
        self._sync_layout()
        self.canvas.yview_moveto(1.0)

    def _release_wheel_binding(self, event: object) -> None:
        if getattr(event, "widget", None) is not self or not self._wheel_binding:
            return
        try:
            self.winfo_toplevel().unbind("<MouseWheel>", self._wheel_binding)
        except Exception:
            pass
        self._wheel_binding = ""


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
        self.database = database
        self.api_server = api_server
        self.media = api_server.api.media
        self.wechat_channels = api_server.api.wechat_channels
        self.processing = processing
        self.external_tray = external_tray
        self.start_hidden = start_hidden and external_tray
        self.eagle = EagleClient()
        self.pairing = PairingManager(database)
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
        self.root.title("下载中转站")
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
        self.status_text = StringVar()
        self.page_title_text = StringVar(value="下载任务")
        self.eagle_status_text = StringVar(value="Eagle 正在检查")
        self.service_status_text = StringVar(value="本机服务正常")
        self.chrome_status_text = StringVar(value="Chrome 未配对")
        self.pairing_text = StringVar()
        self.site_rules_text = StringVar(value="网站规则")
        self.network_proxy_text = StringVar(value="网络：自动")
        self.settings_proxy_status_text = StringVar(value="正在检测网络…")
        self.settings_site_summary_text = StringVar(value="正在读取网站规则…")
        self.update_button_text = StringVar(value="检查更新")
        self.current_page = "media"
        self.page_frames: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, _RoundedNavButton] = {}
        self.control_signals = ControlSignals() if external_tray else None
        self.control_after_id: str | None = None
        self.refresh_after_id: str | None = None
        self.update_poll_after_id: str | None = None
        self.auto_update_after_id: str | None = None
        self.copy_feedback_after_id: str | None = None
        self.media_change_after_id: str | None = None
        self.media_change_events: Queue[None] = Queue()
        self._media_change_listener = self._queue_media_change
        self.update_events: Queue[tuple[str, object]] = Queue()
        self.update_checking = False
        self.update_downloading = False
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
        self.responsive_initialized = False
        self.last_jobs_revision: tuple[int, float] | None = None
        self.last_plans_revision: tuple[int, float] | None = None
        self.plan_rows: dict[str, dict] = {}
        self.selected_plan_card_id = ""
        self.plan_card_widgets: dict[str, tuple[ttk.Frame, list[ttk.Label], Canvas]] = {}
        self.plan_thumbnail_images: dict[str, PhotoImage] = {}
        self.media_page = 0
        self.media_page_count = 1
        self.preview_image: PhotoImage | None = None
        self.preview_cache = _PreviewImageCache()
        self.wechat_rows: dict[str, dict] = {}
        self.selected_wechat_card_id = ""
        self.wechat_card_widgets: dict[str, tuple[ttk.Frame, list[ttk.Label]]] = {}
        self.wechat_variant_ids: list[str] = []
        self.wechat_revision: tuple[int, float] | None = None
        self.wechat_preview_events: Queue[tuple[str, bytes]] = Queue()
        self.wechat_preview_requests: set[str] = set()
        self.wechat_preview_object_id = ""
        self.wechat_preview_image: PhotoImage | None = None
        self.wechat_page = 0
        self.wechat_page_count = 1
        self.wechat_operation_results: Queue[tuple[str, object]] = Queue()
        self.wechat_operation_busy = False
        self.idm_page = 0
        self.idm_page_count = 1
        self.last_eagle_check = 0.0
        self.eagle_connected = False
        self.eagle_probe = _AsyncProbe(
            self.eagle.is_available,
            name="eagle-health-probe",
        )
        self._build()
        add_change_listener = getattr(self.media, "add_change_listener", None)
        if callable(add_change_listener):
            add_change_listener(self._media_change_listener)
            self.media_change_after_id = self.root.after(
                150,
                self._poll_media_changes,
            )
        self.root.bind("<Configure>", self._queue_responsive_layout, add="+")
        self.root.after_idle(self._apply_responsive_layout)
        self.refresh()
        if self.control_signals:
            self.control_after_id = self.root.after(250, self._poll_control_signals)
        self.auto_update_after_id = self.root.after(10000, self._automatic_update_check)

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
        self.topbar.columnconfigure(1, weight=1)
        self.topbar_left = ttk.Frame(self.topbar, style="Topbar.TFrame")
        self.topbar_left.grid(row=0, column=0, sticky="w", padx=(16, 0))
        ttk.Label(
            self.topbar_left,
            image=self.brand_image,
            style="Topbar.TLabel",
        ).pack(side=LEFT, padx=(0, 7))
        ttk.Label(
            self.topbar_left,
            text="下载中转站",
            style="TopbarBrand.TLabel",
        ).pack(side=LEFT)
        ttk.Label(
            self.topbar_left,
            text=f"v{APP_VERSION}",
            style="TopbarVersion.TLabel",
        ).pack(side=LEFT, padx=(8, 0))

        self.topbar_statuses = ttk.Frame(self.topbar, style="Topbar.TFrame")
        self.topbar_statuses.grid(row=0, column=1, sticky="e", padx=(12, 16))
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
        self._build_wechat_tab()
        self._build_idm_tab()
        self._build_settings_tab()
        self._build_diagnostics_tab()
        self._show_page("media")

    def _new_page(self, name: str) -> ttk.Frame:
        page = ttk.Frame(self.page_host, style="Surface.TFrame")
        self.page_frames[name] = page
        return page

    def _show_page(self, page: str) -> None:
        if page not in self.page_frames:
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
        self.page_title_text.set(titles.get(page, page))
        # Paned windows that were built while their page was hidden have a
        # one-pixel geometry and Tk clamps their sash to zero. Restore only
        # the page that has just become visible; touching the hidden pages
        # here would collapse them again before the next navigation.
        self.root.after_idle(self._apply_mode_to_page_layouts)
        if page == "settings":
            if hasattr(self, "settings_tab_buttons"):
                self._settings_show_tab("pairing")
            self._refresh_settings()
        elif page == "diagnostics":
            self._refresh_diagnostics_summary()

    def _queue_responsive_layout(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        if self.layout_after_id is not None:
            self.root.after_cancel(self.layout_after_id)
        self.layout_after_id = self.root.after(120, self._apply_responsive_layout)

    def _apply_responsive_layout(self) -> None:
        self.layout_after_id = None
        width = max(self.root.winfo_width(), 1)
        logical_width = max(1, round(width / self.ui_scale))
        mode = _layout_mode_for_width(logical_width)
        mode_changed = mode != self.layout_mode
        self.layout_mode = mode
        compact = mode == LAYOUT_COMPACT
        self.sidebar.configure(
            width=(
                self.metrics["sidebar_compact_width"]
                if compact
                else self.metrics["sidebar_width"]
            )
        )
        self.topbar.configure(
            height=(
                self.metrics["topbar_compact_height"]
                if compact
                else self.metrics["topbar_height"]
            )
        )
        if compact:
            self.topbar_left.grid(
                row=0,
                column=0,
                columnspan=2,
                sticky="w",
                padx=(16, 0),
                pady=(2, 0),
            )
            self.topbar_statuses.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="e",
                padx=(16, 16),
                pady=(0, 5),
            )
        else:
            self.topbar_left.grid(
                row=0,
                column=0,
                columnspan=1,
                sticky="w",
                padx=(16, 0),
                pady=0,
            )
            self.topbar_statuses.grid(
                row=0,
                column=1,
                columnspan=1,
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
        ttk.Button(
            toolbar,
            text="清除完成",
            style="MediaToolbar.TButton",
            command=self.clear_media_history,
        ).pack(side=RIGHT)
        self.media_next_button = ttk.Button(
            toolbar,
            text="›",
            width=2,
            style="MediaToolbar.TButton",
            command=lambda: self._change_media_page(1),
        )
        self.media_next_button.pack(side=RIGHT)
        self.media_page_text = StringVar(value="1/1")
        ttk.Label(
            toolbar,
            textvariable=self.media_page_text,
            style="MediaToolbarTitle.TLabel",
        ).pack(side=RIGHT, padx=3)
        self.media_previous_button = ttk.Button(
            toolbar,
            text="‹",
            width=2,
            style="MediaToolbar.TButton",
            command=lambda: self._change_media_page(-1),
        )
        self.media_previous_button.pack(side=RIGHT)

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

        def resize_preview(event: object) -> None:
            available = max(1, int(getattr(event, "width", 1)))
            width = min(self.metrics["preview_max_width"], available)
            self.preview_surface.configure(width=width, height=max(1, width * 9 // 16))

        detail_content.bind("<Configure>", resize_preview, add="+")

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
        ttk.Button(
            toolbar,
            text="清除完成",
            style="Link.TButton",
            command=self.clear_history,
        ).pack(side=RIGHT)
        ttk.Button(
            toolbar,
            text="刷新",
            style="Link.TButton",
            command=lambda: self.refresh(force=True),
        ).pack(side=RIGHT, padx=(0, 4))
        self.idm_next_button = ttk.Button(
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
        self.idm_previous_button = ttk.Button(
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

        _DynamicWrapLabel(
            tab,
            text="IDM 与用户原文件始终保留；没有可靠来源时仍会导入，Eagle 网站字段保持为空。",
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
                ttk.Button(
                    actions,
                    text="重试导入",
                    image=self.ui_icons.get("retry-white"),
                    compound=LEFT,
                    style="Accent.TButton",
                    command=self.retry_selected,
                )
            ),
            "open": actions.add(
                ttk.Button(
                    actions,
                    text="原文件位置",
                    image=self.ui_icons.get("folder-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.open_file_location,
                )
            ),
            "source": actions.add(
                ttk.Button(
                    actions,
                    text="可靠来源",
                    image=self.ui_icons.get("globe-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.open_source,
                )
            ),
            "assign": actions.add(
                ttk.Button(
                    actions,
                    text="补充 / 修改来源",
                    image=self.ui_icons.get("source-muted"),
                    compound=LEFT,
                    style="Quiet.TButton",
                    command=self.assign_source,
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
        self.wechat_action_button = ttk.Button(
            capture,
            textvariable=self.wechat_action_text,
            image=self.ui_icons.get("play-white"),
            compound=LEFT,
            command=self.toggle_wechat_capture,
            style="Accent.TButton",
        )
        self.wechat_action_button.pack(fill=X)
        _DynamicWrapLabel(
            capture,
            text="仅在手动开始后为微信启用本机受控捕获；停止或退出会恢复开启前的系统代理。",
            style="Muted.TLabel",
            justify=LEFT,
        ).pack(fill=X, pady=(7, 0))

        candidate_toolbar = ttk.Frame(master, style="Surface.TFrame", padding=(16, 6))
        candidate_toolbar.pack(fill=X)
        self.wechat_candidate_count_text = StringVar(value="候选 0")
        ttk.Label(
            candidate_toolbar,
            textvariable=self.wechat_candidate_count_text,
            style="SectionOnSurface.TLabel",
        ).pack(side=LEFT)
        ttk.Button(
            candidate_toolbar,
            text="清空",
            command=self.clear_wechat_candidates,
            style="Link.TButton",
        ).pack(side=RIGHT)
        self.wechat_next_button = ttk.Button(
            candidate_toolbar,
            text="›",
            width=2,
            command=lambda: self._change_wechat_page(1),
            style="Link.TButton",
        )
        self.wechat_next_button.pack(side=RIGHT)
        self.wechat_page_text = StringVar(value="1/1")
        ttk.Label(
            candidate_toolbar,
            textvariable=self.wechat_page_text,
            style="Muted.TLabel",
        ).pack(side=RIGHT, padx=3)
        self.wechat_previous_button = ttk.Button(
            candidate_toolbar,
            text="‹",
            width=2,
            command=lambda: self._change_wechat_page(-1),
            style="Link.TButton",
        )
        self.wechat_previous_button.pack(side=RIGHT)

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
        self.wechat_variant_box = ttk.Combobox(
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
                ttk.Button(
                    delivery,
                    text="导入 Eagle（完成后删除本机副本）",
                    image=self.ui_icons.get("import-white"),
                    compound=LEFT,
                    command=lambda: self._submit_wechat_delivery(True),
                    style="Accent.TButton",
                )
            ),
            "local": delivery.add(
                ttk.Button(
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

        def resize_preview(event: object) -> None:
            available = max(1, int(getattr(event, "width", 1)))
            width = min(self.metrics["preview_max_width"], available)
            self.wechat_preview_surface.configure(
                width=width,
                height=max(1, width * 9 // 16),
            )

        detail_content.bind("<Configure>", resize_preview, add="+")

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
        for key, label in (
            ("pairing", "浏览器配对"),
            ("sites", "网站规则"),
            ("network", "网络代理"),
            ("updates", "更新"),
        ):
            btn = ttk.Button(
                self.settings_nav,
                text=label,
                style="Nav.TButton",
                command=lambda k=key: self._settings_show_tab(k),
            )
            btn.pack(fill=X, pady=1)
            self.settings_tab_buttons[key] = btn

        self.settings_panel = ttk.Frame(tab, style="Surface.TFrame")
        self.settings_panel.pack(side=LEFT, fill=BOTH, expand=True)

        self._build_settings_pairing()
        self._build_settings_sites()
        self._build_settings_network()
        self._build_settings_updates()
        self._settings_show_tab("pairing")

    def _settings_show_tab(self, name: str) -> None:
        for key, frame in self.settings_sub_tabs.items():
            if key == name:
                frame.pack(fill=BOTH, expand=True)
            else:
                frame.pack_forget()
        for key, button in self.settings_tab_buttons.items():
            button.configure(style="NavSelected.TButton" if key == name else "Nav.TButton")

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
            text="浏览器配对",
            style="Title.TLabel",
        ).pack(anchor="w")
        _DynamicWrapLabel(
            content,
            text="在 Chrome 扩展中输入下面的六位码。配对只允许本机回环服务和已验证来源。",
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
        pairing_code = self.pairing.pairing_code
        self.pairing_code_text = StringVar(
            value=f"{pairing_code[:3]}  {pairing_code[3:]}"
        )
        self.pairing_code_font = tkfont.Font(
            root=self.root,
            family=FONT_FAMILIES["mono"],
            size=24,
            weight="bold",
        )
        ttk.Label(
            code_surface,
            text="六位配对码",
            style="RaisedMuted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            code_surface,
            textvariable=self.pairing_code_text,
            style="PairingCode.TLabel",
            font=self.pairing_code_font,
        ).pack(anchor="w", pady=(6, 0))
        self.pairing_feedback_text = StringVar(value="")
        ttk.Label(
            code_surface,
            textvariable=self.pairing_feedback_text,
            style="RaisedMuted.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        _DynamicWrapLabel(
            content,
            textvariable=self.pairing_text,
            style="Muted.TLabel",
            justify=LEFT,
            maximum=760,
        ).pack(fill=X, pady=(12, 0))
        actions = _ResponsiveActionGroup(
            content,
            compact_breakpoint=620,
            vertical_breakpoint=300,
            style="Surface.TFrame",
        )
        actions.pack(fill=X, pady=(14, 0))
        actions.add(
            ttk.Button(
                actions,
                text="复制六位码",
                image=self.ui_icons.get("copy-white"),
                compound=LEFT,
                style="Accent.TButton",
                command=self.copy_pairing_code,
            )
        )
        actions.add(
            ttk.Button(
                actions,
                text="解除配对",
                image=self.ui_icons.get("trash-danger"),
                compound=LEFT,
                style="Danger.TButton",
                command=self.unpair,
            )
        )

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
        ttk.Button(
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
                ttk.Button(
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
        ttk.Button(
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
        self.update_button = ttk.Button(
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
        ttk.Button(
            content,
            text="导出脱敏诊断",
            image=self.ui_icons.get("diagnostics-white"),
            compound=LEFT,
            style="Accent.TButton",
            command=self.export_diagnostics,
        ).pack(anchor="w", pady=(14, 0))
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
            ttk.Button(
                window,
                text="隐藏到右下角",
                style="Quiet.TButton",
                command=self.hide,
            ).pack(side=LEFT)
        else:
            ttk.Button(
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
            f"删除 {rule['domain']} 后，该网站恢复默认不自动导入。是否继续？",
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
            "所有网站将恢复默认不自动导入；文件、任务和 Eagle 内容不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        self.database.clear_site_rules()
        self._refresh_settings()
        self.refresh(force=True)

    def _settings_proxy_mode_changed(self) -> None:
        self.settings_proxy_entry.configure(
            state="normal" if self.settings_proxy_mode.get() == "manual" else "disabled"
        )

    def _settings_save_proxy(self) -> None:
        try:
            self.media.network_proxy.configure(
                self.settings_proxy_mode.get(),
                self.settings_proxy_manual.get(),
            )
        except ProxyConfigurationError as exc:
            messagebox.showerror("代理地址无效", str(exc), parent=self.root)
            return
        self.media._health_cache = None
        self._refresh_settings()
        self.refresh(force=True)

    def _refresh_settings(self, select_domain: str | None = None) -> None:
        if not hasattr(self, "settings_site_tree"):
            return
        if hasattr(self, "pairing_code_text"):
            code = self.pairing.pairing_code
            self.pairing_code_text.set(f"{code[:3]}  {code[3:]}")
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
        self.settings_site_summary_text.set(
            f"共 {len(rules)} 条规则 · 已启用 {enabled} 条 · 未列出的网站默认不自动导入"
        )
        configuration = self.media.network_proxy.configuration()
        self.settings_proxy_mode.set(configuration["mode"])
        self.settings_proxy_manual.set(configuration["manualUrl"])
        self._settings_proxy_mode_changed()
        status = self.media.network_proxy.status()
        self.settings_proxy_status_text.set(
            f"检测来源：{status.get('source') or '无'} · 端点：{status.get('endpoint') or '直连'} · {status['summary']}"
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
            f"Eagle {'已连接' if self.eagle_connected else '未连接'} · "
            f"Chrome {'已配对' if self.pairing.paired_origin else '待配对'}\n"
            f"媒体任务 {len(self.plan_rows)} 条 · "
            f"视频号 {health.get('state') or 'off'} · "
            f"网络 {network.get('summary') or network.get('mode') or '未知'}"
        )

    def run(self) -> None:
        self.root.mainloop()

    def show(self) -> None:
        self.visible = True
        self.root.deiconify()
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
        self.update_button.configure(state="disabled")
        self.update_button_text.set("正在检查…")
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
        self.media_change_events.put(None)

    def _poll_media_changes(self) -> None:
        self.media_change_after_id = None
        changed = False
        while True:
            try:
                self.media_change_events.get_nowait()
                changed = True
            except Empty:
                break
        if changed:
            self.media_page = 0
            self.refresh(force=True)
        if callable(getattr(self.media, "add_change_listener", None)):
            self.media_change_after_id = self.root.after(
                150,
                self._poll_media_changes,
            )

    def _ensure_update_poll(self) -> None:
        if self.update_poll_after_id is None:
            self.update_poll_after_id = self.root.after(150, self._poll_update_events)

    def _poll_update_events(self) -> None:
        self.update_poll_after_id = None
        while True:
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
            elif event == "download_progress":
                downloaded, total = payload
                percent = min(99, int(int(downloaded) * 100 / max(1, int(total))))
                self.update_button_text.set(f"正在下载 {percent}%")
                if hasattr(self, "update_status_text"):
                    self.update_status_text.set(f"正在下载并校验安装包：{percent}%")
            elif event == "download_ok":
                self._handle_download_ready(payload)
            elif event == "download_error":
                self._handle_download_error(payload)
        if self.update_checking or self.update_downloading:
            self._ensure_update_poll()

    def _reset_update_button(self) -> None:
        self.update_button_text.set("检查更新")
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
        self.update_button.configure(state="disabled")
        self.update_button_text.set("正在下载 0%")
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
                lambda current, total: self.update_events.put(
                    ("download_progress", (current, total))
                ),
            )
            self.update_events.put(("download_ok", installer))
        except Exception as exc:
            self.update_events.put(("download_error", exc))

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

    def refresh(self, force: bool = False) -> None:
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if not self.visible and not force:
            self.refresh_after_id = self.root.after(30000, self.refresh)
            return

        now = time.monotonic()
        eagle_result_available, eagle_result = self.eagle_probe.poll()
        if eagle_result_available:
            self.eagle_connected = bool(eagle_result)
        if force or now - self.last_eagle_check >= 10:
            if self.eagle_probe.request():
                self.last_eagle_check = now
        eagle_text = "Eagle 已连接" if self.eagle_connected else "正在等待 Eagle"
        host, port = self.api_server.address
        dashboard = self.database.ui_snapshot()
        counts = dashboard["status_counts"]
        job_active_count = sum(
            counts.get(status, 0)
            for status in ("waiting_source", "queued", "waiting_eagle", "retry")
        )
        plans = self.media.list_plans(200)
        media_active_count = sum(
            1 for plan in plans if str(plan.get("status")) in MEDIA_ACTIVE_STATUSES
        )
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
        self.status_text.set(" · ".join(status_parts))
        self.eagle_status_text.set(
            "Eagle 已连接" if self.eagle_connected else "Eagle 未连接"
        )
        self.service_status_text.set("服务正常")
        if hasattr(self, "status_dots"):
            self.status_dots["eagle"].set_color(
                UI["success"] if self.eagle_connected else UI["text_muted"]
            )
            self.status_dots["service"].set_color(UI["success"])
        enabled_sites = dashboard["enabled_site_count"]
        self.site_rules_text.set(f"网站规则（已开启 {enabled_sites}）")
        proxy_status = self.media.network_proxy.status()
        self.network_proxy_text.set(f"网络：{proxy_status['summary']}")
        if self.pairing.paired_origin:
            self.pairing_text.set("Chrome 已安全配对")
            self.chrome_status_text.set("Chrome 已配对")
            if hasattr(self, "status_dots"):
                self.status_dots["chrome"].set_color(UI["success"])
        else:
            self.pairing_text.set(f"Chrome 配对码：{self.pairing.pairing_code}")
            self.chrome_status_text.set("Chrome 待配对")
            if hasattr(self, "status_dots"):
                self.status_dots["chrome"].set_color(UI["text_muted"])

        self._refresh_media_tasks(plans, force)
        self._refresh_wechat_candidates(wechat_health, force)

        revision = dashboard["jobs_revision"]
        if force or revision != self.last_jobs_revision:
            selected = self.selected_job_id()
            job_rows = []
            tree_font = tkfont.nametofont("Ui12")

            def fit_column(value: object, column: str) -> str:
                width = int(self.job_tree.column(column, "width") or 24)
                return _pixel_ellipsize(value, max(24, width - 16), tree_font.measure)

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
        self._update_idm_detail()
        if self.current_page == "settings":
            self._refresh_settings()
        if self.current_page == "diagnostics":
            self._refresh_diagnostics_summary()
        self.refresh_after_id = self.root.after(
            1000 if media_active_count or wechat_health.get("running") else 4000,
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
        text.set(f"{page + 1}/{total_pages}")
        previous.state(["!disabled"] if page > 0 else ["disabled"])
        following.state(["!disabled"] if page + 1 < total_pages else ["disabled"])

    def _change_media_page(self, delta: int) -> None:
        target = max(0, min(self.media_page + delta, self.media_page_count - 1))
        if target == self.media_page:
            return
        self.media_page = target
        self.refresh(force=True)

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
            lambda _event, value=object_id: self._select_wechat_card(value),
            add="+",
        )
        widget.bind(
            "<Return>",
            lambda _event, value=object_id: self._select_wechat_card(value),
            add="+",
        )

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
            row = ttk.Frame(
                self.wechat_card_list.content,
                style=frame_style,
                height=self.metrics["wechat_row_height"],
                takefocus=True,
            )
            row.pack(fill=X)
            row.pack_propagate(False)
            body = ttk.Frame(row, style=frame_style, padding=(16, 9, 12, 7))
            body.pack(fill=BOTH, expand=True)
            body.columnconfigure(1, weight=1)
            thumbnail_host = ttk.Frame(
                body,
                style="Soft.TFrame",
                width=64,
                height=40,
            )
            thumbnail_host.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 8))
            thumbnail_host.grid_propagate(False)
            thumbnail = ttk.Label(
                thumbnail_host,
                image=self.ui_icons.get("wechat-muted"),
                style="SurfaceRaised.TLabel",
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
            self.wechat_card_widgets[object_id] = (row, [title, author, metadata])
            for widget in (
                row,
                body,
                thumbnail_host,
                thumbnail,
                title,
                author,
                metadata,
            ):
                self._bind_wechat_card(widget, object_id)
            ttk.Separator(self.wechat_card_list.content).pack(fill=X)

    def _select_wechat_card(self, object_id: str) -> None:
        if object_id not in self.wechat_rows:
            return
        self.selected_wechat_card_id = object_id
        for current_id, (row, labels) in self.wechat_card_widgets.items():
            selected = current_id == object_id
            frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
            title_style = (
                "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
            )
            meta_style = (
                "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
            )
            row.configure(style=frame_style)
            labels[0].configure(style=title_style)
            for label in labels[1:]:
                label.configure(style=meta_style)
            body = next(
                (child for child in row.winfo_children() if isinstance(child, ttk.Frame)),
                None,
            )
            if body is not None:
                body.configure(style=frame_style)
        self._update_wechat_detail()

    def _refresh_wechat_candidates(self, health: dict, force: bool) -> None:
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
        self.wechat_status_text.set(summary)
        self.wechat_action_text.set("停止捕获" if health.get("running") else "开始捕获")
        self.wechat_action_button.configure(
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
        self.wechat_candidate_count_text.set(f"候选 {len(candidates)}")
        revision = (
            len(candidates),
            max((float(item.get("updatedAt") or 0) for item in candidates), default=0.0),
        )
        self.wechat_rows = {str(item["objectId"]): item for item in candidates}
        selected_id = self.selected_wechat_card_id
        if force or revision != self.wechat_revision:
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
            self._render_wechat_cards(visible_candidates)
            self.wechat_revision = revision
        self._update_wechat_detail()

    def _selected_wechat_candidate(self) -> dict | None:
        return self.wechat_rows.get(self.selected_wechat_card_id)

    def _update_wechat_detail(self) -> None:
        candidate = self._selected_wechat_candidate()
        if not candidate:
            self.wechat_detail_text.set("开始捕获后，在微信中打开视频号内容。")
            self.wechat_author_text.set("")
            self.wechat_quality_text.set("")
            self.wechat_full_metadata_text.set("")
            self.wechat_variant_ids = []
            self.wechat_variant_box.configure(values=())
            self.wechat_variant_text.set("")
            self.wechat_preview_object_id = ""
            self.wechat_preview_image = None
            self.wechat_preview_label.configure(
                image=self.ui_icons.get("wechat-muted"),
                text="封面将在识别后显示",
            )
            for button in self.wechat_delivery_buttons.values():
                button.configure(state="disabled")
            return
        object_id = str(candidate.get("objectId") or "")
        if object_id != self.wechat_preview_object_id:
            self.wechat_preview_object_id = object_id
            self.wechat_preview_image = None
            self.wechat_preview_label.configure(
                image=self.ui_icons.get("wechat-muted"),
                text="正在读取封面…",
            )
            if object_id and candidate.get("coverUrl") and object_id not in self.wechat_preview_requests:
                self.wechat_preview_requests.add(object_id)
                threading.Thread(
                    target=self._load_wechat_preview,
                    args=(object_id,),
                    name="wechat-cover-preview",
                    daemon=True,
                ).start()
            elif not candidate.get("coverUrl"):
                self.wechat_preview_label.configure(
                    image=self.ui_icons.get("wechat-muted"),
                    text="该内容未提供封面",
                )
        full_title = str(candidate.get("title") or "微信视频号视频")
        full_author = str(candidate.get("author") or "未知作者")
        self.wechat_detail_text.set(_ellipsize(full_title, 48))
        self.wechat_author_text.set(f"作者：{_ellipsize(full_author, 44)}")
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
        self.wechat_quality_text.set(
            f"内容 ID：{candidate.get('objectId')} · 时长 {self._duration_text(candidate.get('durationMs'))}\n"
            f"预计输出：{_ellipsize(output_name, 52)}\n"
            f"来源：{source_domain or source}"
        )
        self.wechat_full_metadata_text.set(
            f"完整标题：{full_title}\n"
            f"完整作者：{full_author}\n"
            f"完整输出：{output_name}\n"
            f"完整来源：{source}"
        )
        variants = candidate.get("variants") if isinstance(candidate.get("variants"), list) else []
        values = []
        self.wechat_variant_ids = []
        for variant in variants:
            size = _display_bytes(variant.get("fileSize"))
            encrypted = " · 本机解密" if variant.get("encrypted") else ""
            values.append(f"{variant.get('quality') or '自动质量'} · {size}{encrypted}")
            self.wechat_variant_ids.append(str(variant.get("id") or ""))
        self.wechat_variant_box.configure(values=values)
        self.wechat_variant_text.set(values[0] if values else "自动质量")
        for button in self.wechat_delivery_buttons.values():
            button.configure(state="normal")

    def _load_wechat_preview(self, object_id: str) -> None:
        try:
            preview = self.wechat_channels.preview_png(object_id)
        except Exception:
            preview = b""
        self.wechat_preview_events.put((object_id, preview))

    def _drain_wechat_preview_events(self) -> None:
        while True:
            try:
                object_id, preview = self.wechat_preview_events.get_nowait()
            except Empty:
                return
            self.wechat_preview_requests.discard(object_id)
            if object_id != self.wechat_preview_object_id:
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

    def _submit_wechat_delivery(self, import_to_eagle: bool) -> None:
        self.wechat_import_to_eagle.set(import_to_eagle)
        self.submit_selected_wechat_candidate()

    def toggle_wechat_capture(self) -> None:
        if self.wechat_operation_busy:
            return
        running = bool(self.wechat_channels.health().get("running"))
        self.wechat_operation_busy = True
        self.wechat_action_button.state(["disabled"])
        self.wechat_status_text.set(
            "正在停止视频号捕获…"
            if running
            else "正在后台检查视频号捕获环境…"
        )
        target = self._run_wechat_operation if running else self._run_wechat_preflight
        threading.Thread(
            target=target,
            args=(running,) if running else (),
            name=(
                "wechat-capture-toggle"
                if running
                else "wechat-capture-preflight"
            ),
            daemon=True,
        ).start()
        self.root.after(200, self._poll_wechat_operation)

    def _run_wechat_preflight(self) -> None:
        try:
            existing = self.wechat_channels.certificate.existing()
            needs_trust = (
                not existing
                or not self.wechat_channels.certificate.is_trusted(
                    existing.fingerprint
                )
            )
        except Exception as exc:
            self.wechat_operation_results.put(("preflight_error", str(exc)))
            return
        self.wechat_operation_results.put(("preflight", needs_trust))

    def _run_wechat_operation(self, was_running: bool) -> None:
        try:
            if was_running:
                self.wechat_channels.stop()
            else:
                self.wechat_channels.start()
        except Exception as exc:
            self.wechat_operation_results.put(("completed", (False, str(exc))))
            return
        self.wechat_operation_results.put(("completed", (True, "")))

    def _poll_wechat_operation(self) -> None:
        try:
            event, payload = self.wechat_operation_results.get_nowait()
        except Empty:
            if self.wechat_operation_busy:
                self.root.after(200, self._poll_wechat_operation)
            return
        if event == "preflight_error":
            self.wechat_operation_busy = False
            self.wechat_action_button.state(["!disabled"])
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
                "下载中转站将为当前 Windows 用户生成并信任一张仅用于微信视频号本机捕获的根证书。\n\n"
                "Windows 随后会显示“安全警告”，请核对证书名称为“下载中转站 微信视频号本机捕获根证书”后亲自确认。停止捕获会恢复系统代理；卸载会按精确指纹移除此证书。\n\n"
                "是否继续？",
                parent=self.root,
            ):
                self.wechat_operation_busy = False
                self.wechat_action_button.state(["!disabled"])
                self.refresh(force=True)
                return
            self.wechat_status_text.set("正在准备视频号捕获…")
            threading.Thread(
                target=self._run_wechat_operation,
                args=(False,),
                name="wechat-capture-toggle",
                daemon=True,
            ).start()
            self.root.after(200, self._poll_wechat_operation)
            return
        succeeded, error = payload
        self.wechat_operation_busy = False
        self.wechat_action_button.state(["!disabled"])
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
        try:
            image = PhotoImage(file=str(preview_path))
        except Exception:
            return self.brand_image
        image = _fit_photo_image(image, 48, 32)
        self.plan_thumbnail_images[plan_id] = image
        return image

    def _bind_plan_card(self, widget: object, plan_id: str) -> None:
        widget.bind(
            "<Button-1>",
            lambda _event, value=plan_id: self._select_plan_card(value),
            add="+",
        )
        widget.bind(
            "<Return>",
            lambda _event, value=plan_id: self._select_plan_card(value),
            add="+",
        )

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
                style="SurfaceRaised.TLabel",
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

            progress = Canvas(
                row.inner,
                height=4,
                background=UI["selected"] if selected else UI["surface"],
                highlightthickness=0,
                borderwidth=0,
            )
            progress.pack(fill=X, side="bottom")
            progress_color = (
                UI["success"]
                if view["status"] in ("completed_local", "imported")
                else UI["warning"]
                if view["status"] == "waiting_eagle"
                else UI["accent"]
            )

            def draw_progress(
                event: object,
                canvas: Canvas = progress,
                percent: float = float(view["progress"]),
                color: str = progress_color,
            ) -> None:
                width = max(0, int(getattr(event, "width", 0) or canvas.winfo_width()))
                canvas.delete("all")
                canvas.create_polygon(
                    _rounded_polygon_points(0, 0, width, 4, 2),
                    smooth=True,
                    splinesteps=12,
                    fill=UI["progress_track"],
                    outline="",
                )
                fill_width = int(width * percent / 100)
                if fill_width > 0:
                    canvas.create_polygon(
                        _rounded_polygon_points(
                            0,
                            0,
                            max(4, fill_width),
                            4,
                            2,
                        ),
                        smooth=True,
                        splinesteps=12,
                        fill=color,
                        outline="",
                    )

            progress.bind("<Configure>", draw_progress, add="+")
            styled_labels = [title, source, size, timestamp_label]
            self.plan_card_widgets[plan_id] = (row, styled_labels, progress)
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

    def _select_plan_card(self, plan_id: str) -> None:
        if plan_id not in self.plan_rows:
            return
        self.selected_plan_card_id = plan_id
        for current_id, (row, labels, progress) in self.plan_card_widgets.items():
            selected = current_id == plan_id
            frame_style = "TaskCardSelected.TFrame" if selected else "TaskCard.TFrame"
            title_style = (
                "TaskCardTitleSelected.TLabel" if selected else "TaskCardTitle.TLabel"
            )
            meta_style = (
                "TaskCardMetaSelected.TLabel" if selected else "TaskCardMeta.TLabel"
            )
            if isinstance(row, _RoundedPanel):
                row.set_surface(
                    fill=UI["selected"] if selected else UI["surface"],
                    style=frame_style,
                )
            if len(labels) >= 4:
                labels[0].configure(style=title_style)
                labels[1].configure(style=meta_style)
                labels[2].configure(style=meta_style)
                labels[3].configure(style=meta_style)
            progress.configure(
                background=UI["selected"] if selected else UI["surface"],
            )
            body = next(
                (
                    child
                    for child in getattr(row, "inner", row).winfo_children()
                    if isinstance(child, ttk.Frame)
                ),
                None,
            )
            if body is not None:
                body.configure(style=frame_style)
        self._update_plan_detail()

    def _refresh_media_tasks(self, plans: list[dict], force: bool) -> None:
        revision = (
            len(plans),
            max((float(plan.get("updated_at") or 0) for plan in plans), default=0.0),
        )
        self.plan_rows = {str(plan["id"]): plan for plan in plans}
        selected = self.selected_plan_id()
        if force or revision != self.last_plans_revision:
            previous_count = self.last_plans_revision[0] if self.last_plans_revision else 0
            if len(plans) > previous_count:
                self.media_page = 0
                selected = str(plans[0]["id"]) if plans else ""
            visible_plans, self.media_page, self.media_page_count = _page_slice(
                plans,
                self.media_page,
                CARD_PAGE_SIZE,
            )
            self._update_pager(
                self.media_previous_button,
                self.media_next_button,
                self.media_page_text,
                self.media_page,
                self.media_page_count,
            )
            if selected not in self.plan_rows:
                selected = str(plans[0]["id"]) if plans else ""
            visible_ids = {str(plan["id"]) for plan in visible_plans}
            if selected not in visible_ids:
                selected = str(visible_plans[0]["id"]) if visible_plans else ""
            self.selected_plan_card_id = selected or ""
            self._render_plan_cards(visible_plans)
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
            self.plan_title_text.set("选择一项任务查看详情")
            self.plan_status_text.set("")
            self.plan_source_text.set("")
            self.plan_file_text.set("")
            self.plan_progress_text.set("—")
            self.plan_size_text.set("—")
            self.plan_domain_text.set("—")
            self.plan_detail_text.set("")
            self.plan_error_text.set("")
            self.plan_error_label.pack_forget()
            self.plan_progress.configure(value=0, style="Progress.Indigo.Horizontal.TProgressbar")
            self.preview_image = None
            self.preview_cache.clear()
            self.preview_label.configure(
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
        self.plan_title_text.set(_ellipsize(full_title, title_limit))
        self.plan_status_text.set(str(view["status_label"]))
        source = str(plan.get("page_url") or "")
        domain = urlsplit(source).hostname if source else ""
        self.plan_source_text.set(domain or "未记录来源网页")
        self.plan_domain_text.set(domain or "未记录")
        self.plan_progress_text.set(f"{view['progress']:.0f}%")
        self.plan_size_text.set(f"{view['processed']} / {view['total']}")
        self.plan_detail_text.set(detail or "等待新的阶段信息")
        self.plan_error_text.set(error)
        if error:
            self.plan_error_label.pack(fill=X, pady=(8, 0))
        else:
            self.plan_error_label.pack_forget()
        output = str(plan.get("final_path") or plan.get("output_name") or "")
        self.plan_file_text.set(
            f"完整标题：{full_title}\n"
            f"来源：{source or '未记录来源网页'}\n"
            f"输出：{output or '尚未生成'}"
        )
        self.plan_progress.configure(value=view["progress"])
        status = view.get("status", "")
        if status in ("completed_local", "imported"):
            prog_style = "Progress.Emerald.Horizontal.TProgressbar"
        elif status == "waiting_eagle":
            prog_style = "Progress.Orange.Horizontal.TProgressbar"
        else:
            prog_style = "Progress.Indigo.Horizontal.TProgressbar"
        self.plan_progress.configure(style=prog_style)
        self._update_plan_actions(view)
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
            "import": bool(view and view["can_import_existing"] and final_exists),
            "open": bool(view and view["can_open_output"] and final_exists),
            "source": bool(view and view["can_open_source"]),
        }
        for name, button in self.plan_action_buttons.items():
            button.set_enabled(permissions[name])

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
        try:
            self.media.import_completed_plan(str(plan["id"]))
        except Exception as exc:
            messagebox.showerror("无法导入", str(exc), parent=self.root)
            return
        self.processing.wake()
        self.refresh(force=True)

    def open_plan_source(self) -> None:
        plan = self.selected_plan()
        if not plan or not plan.get("page_url"):
            messagebox.showinfo("没有来源", "这项任务没有记录来源网页")
            return
        webbrowser.open(str(plan["page_url"]))

    def selected_job_id(self) -> str | None:
        selected = self.job_tree.selection()
        return selected[0] if selected else None

    def selected_job(self) -> dict | None:
        job_id = self.selected_job_id()
        return self.database.get_job(job_id) if job_id else None

    def _update_idm_detail(self) -> None:
        job = self.selected_job()
        if not job:
            self.idm_detail_title_text.set("选择一条记录查看完整内容")
            self.idm_detail_status_text.set("")
            self.idm_detail_file_text.set("—")
            self.idm_detail_source_text.set("—")
            self.idm_detail_message_text.set("—")
            self._update_idm_actions()
            return
        created = time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(float(job.get("created_at") or 0)),
        )
        status = str(job.get("status") or "")
        self.idm_detail_title_text.set(str(job.get("file_name") or "未命名文件"))
        self.idm_detail_status_text.set(
            f"{STATUS_TEXT.get(status, status)} · {created}"
        )
        self.idm_detail_file_text.set(str(job.get("file_path") or "—"))
        self.idm_detail_source_text.set(
            str(job.get("source_url") or "未记录可靠来源")
        )
        message = str(job.get("error_message") or "")
        if status == "imported" and not job.get("source_url"):
            message = "已直接导入；Eagle 网站字段保持为空。"
        self.idm_detail_message_text.set(message or "暂无补充说明")
        self._update_idm_actions()

    def _update_idm_actions(self) -> None:
        if not hasattr(self, "idm_action_buttons"):
            return
        job = self.selected_job()
        status = str(job.get("status") or "") if job else ""
        retryable = status in {
            "waiting_source",
            "queued",
            "waiting_eagle",
            "retry",
            "failed_permanent",
        }
        file_path = str(job.get("file_path") or "") if job else ""
        permissions = {
            "retry": retryable,
            "open": bool(file_path and Path(file_path).exists()),
            "source": bool(job and job.get("source_url")),
            "assign": bool(job and status != "skipped_duplicate"),
        }
        for name, button in self.idm_action_buttons.items():
            button.configure(state="normal" if permissions[name] else "disabled")

    def retry_selected(self) -> None:
        job_id = self.selected_job_id()
        if not job_id:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if not self.database.retry_job(job_id):
            self.refresh(force=True)
            messagebox.showinfo("无需重试", "这条记录已经处理完成，不需要再次重试。")
            return
        self.processing.wake()
        self.refresh()

    def open_file_location(self) -> None:
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        path = Path(job["file_path"])
        if not path.exists():
            messagebox.showwarning("文件不存在", "下载文件已经不在原位置")
            return
        subprocess.Popen(["explorer.exe", "/select,", str(path)])

    def open_source(self) -> None:
        job = self.selected_job()
        if not job or not job.get("source_url"):
            messagebox.showinfo("没有来源", "这条记录还没有匹配到来源网页")
            return
        webbrowser.open(job["source_url"])

    def assign_source(self) -> None:
        job = self.selected_job()
        if not job:
            messagebox.showinfo("提示", "请先选择一条记录")
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
            if not job.get("eagle_item_id"):
                messagebox.showwarning("无法更新", "这条旧记录没有 Eagle 项目编号，无法自动补写来源。")
                return
            try:
                self.eagle.update_source(str(job["eagle_item_id"]), cleaned)
            except (EagleUnavailable, EagleImportError) as exc:
                messagebox.showerror("更新失败", str(exc))
                return
            self.database.record_imported_source(job["id"], cleaned)
            self.refresh(force=True)
            messagebox.showinfo("更新完成", "来源网址已经写入现有 Eagle 项目，不会重复导入文件。")
            return

        if job["status"] == "skipped_duplicate":
            messagebox.showinfo("重复项目", "这条记录因内容重复被跳过，没有新的 Eagle 项目可以补写来源。")
            return

        self.database.assign_source(job["id"], cleaned)
        self.processing.wake()
        self.refresh(force=True)

    def export_diagnostics(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出诊断记录",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="idm-eagle-diagnostics.json",
        )
        if not target:
            return
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
        try:
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
                        "mediaPlans": media_rows,
                        "jobs": rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            if hasattr(self, "diagnostics_feedback_text"):
                self.diagnostics_feedback_text.set("导出失败，请更换保存位置后重试")
            messagebox.showerror("导出失败", str(exc), parent=self.root)
            return
        if hasattr(self, "diagnostics_feedback_text"):
            self.diagnostics_feedback_text.set("诊断文件已安全导出")
        messagebox.showinfo(
            "导出完成",
            "诊断记录已保存。完整路径、来源网址和代理密码未包含在文件中。",
        )

    def clear_history(self) -> None:
        if not messagebox.askyesno(
            "清除 IDM 导入记录",
            "只清除成功、失败和已跳过的终态记录；等待中的任务会保留。下载文件和 Eagle 内容不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        count = self.database.clear_terminal_history()
        self.refresh(force=True)
        messagebox.showinfo("清理完成", f"已清除 {count} 条 IDM 导入记录。", parent=self.root)

    def clear_media_history(self) -> None:
        if not messagebox.askyesno(
            "清除媒体任务记录",
            "只清除已导入、已下载、下载失败和已停止的任务记录；进行中及等待导入的任务会保留。"
            "下载文件、预览文件和 Eagle 内容不会受到影响。是否继续？",
            parent=self.root,
        ):
            return
        count = self.media.clear_terminal_history()
        self.last_plans_revision = None
        self.refresh(force=True)
        messagebox.showinfo("清理完成", f"已清除 {count} 条媒体任务记录。", parent=self.root)

    def copy_pairing_code(self) -> None:
        code = self.pairing.pairing_code
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.root.update()
        if hasattr(self, "pairing_feedback_text"):
            self.pairing_feedback_text.set("已复制到剪贴板")
            if self.copy_feedback_after_id:
                self.root.after_cancel(self.copy_feedback_after_id)
            self.copy_feedback_after_id = self.root.after(
                1500,
                lambda: self.pairing_feedback_text.set(""),
            )

    def unpair(self) -> None:
        if not self.pairing.paired_origin:
            messagebox.showinfo("未配对", "当前没有已配对的 Chrome 扩展")
            return
        if not messagebox.askyesno("解除配对", "解除后需要重新输入配对码，是否继续？"):
            return
        self.pairing.unpair()
        self.refresh(force=True)

    def quit(self) -> None:
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if self.control_after_id:
            self.root.after_cancel(self.control_after_id)
            self.control_after_id = None
        if self.layout_after_id:
            self.root.after_cancel(self.layout_after_id)
            self.layout_after_id = None
        if self.update_poll_after_id:
            self.root.after_cancel(self.update_poll_after_id)
            self.update_poll_after_id = None
        if self.auto_update_after_id:
            self.root.after_cancel(self.auto_update_after_id)
            self.auto_update_after_id = None
        if self.copy_feedback_after_id:
            self.root.after_cancel(self.copy_feedback_after_id)
            self.copy_feedback_after_id = None
        if self.media_change_after_id:
            self.root.after_cancel(self.media_change_after_id)
            self.media_change_after_id = None
        remove_change_listener = getattr(self.media, "remove_change_listener", None)
        if callable(remove_change_listener):
            remove_change_listener(self._media_change_listener)
        if self.control_signals:
            self.control_signals.close()
            self.control_signals = None
        self.root.quit()
        self.root.destroy()
