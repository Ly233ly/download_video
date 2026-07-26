from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
import json
import threading
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
    "imported": "已导入 Eagle",
    "completed_local": "已下载到本机",
    "retry": "下载失败",
    "canceled": "已停止",
}

MEDIA_ACTIVE_STATUSES = {"queued", "downloading", "merging", "validating", "ready_to_import"}


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


class _VerticalScrolledFrame(ttk.Frame):
    """A width-filling frame that scrolls only when its content is too tall."""

    def __init__(self, parent: object, *, padding: object = 0) -> None:
        super().__init__(parent)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.canvas = Canvas(
            self,
            borderwidth=0,
            highlightthickness=0,
            background=background,
            yscrollincrement=20,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.content = ttk.Frame(self.canvas, padding=padding)
        self._content_window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.content.bind("<Configure>", self._sync_layout, add="+")
        self.canvas.bind("<Configure>", self._sync_layout, add="+")
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

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)

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


class SiteRulesWindow:
    def __init__(self, parent: "MainWindow") -> None:
        self.parent = parent
        self.database = parent.database
        self.window = Toplevel(parent.root)
        self.window.title("自动导入网站")
        self.window.geometry("720x430")
        self.window.minsize(580, 340)
        self.window.transient(parent.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.summary_text = StringVar()
        self.refresh_after_id: str | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill=BOTH, expand=True)

        ttk.Label(
            outer,
            text="自动导入网站",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="只有列表中已开启的网站会自动保存来源；未列出的网站默认不导入。",
            foreground="#475569",
        ).pack(fill=X, pady=(6, 2))
        ttk.Label(outer, textvariable=self.summary_text).pack(fill=X, pady=(0, 10))

        columns = ("domain", "status", "subdomains", "updated")
        self.tree = ttk.Treeview(
            outer,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("domain", text="网站")
        self.tree.heading("status", text="自动导入")
        self.tree.heading("subdomains", text="子域名")
        self.tree.heading("updated", text="最近修改")
        self.tree.column("domain", width=280)
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("subdomains", width=120, anchor="center")
        self.tree.column("updated", width=150, anchor="center")
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda _event: self.toggle_enabled())

        primary_actions = ttk.Frame(outer, padding=(0, 10, 0, 0))
        primary_actions.pack(fill=X)
        ttk.Button(
            primary_actions,
            text="刷新",
            command=lambda: self.refresh(force=True),
        ).pack(side=LEFT)
        ttk.Button(primary_actions, text="新增并开启", command=self.add_rule).pack(side=LEFT, padx=6)
        ttk.Button(primary_actions, text="开启 / 关闭", command=self.toggle_enabled).pack(side=LEFT)
        ttk.Button(primary_actions, text="切换子域名", command=self.toggle_subdomains).pack(side=LEFT, padx=6)

        secondary_actions = ttk.Frame(outer, padding=(0, 6, 0, 0))
        secondary_actions.pack(fill=X)
        ttk.Button(secondary_actions, text="删除选中规则", command=self.delete_rule).pack(side=LEFT)
        ttk.Button(secondary_actions, text="清空全部规则", command=self.clear_rules).pack(side=LEFT, padx=6)
        ttk.Button(secondary_actions, text="关闭", command=self.close).pack(side=RIGHT)

    def selected_rule(self) -> dict | None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个网站", parent=self.window)
            return None
        domain = self.tree.item(selected[0], "values")[0]
        return next(
            (rule for rule in self.database.list_site_rules() if rule["domain"] == domain),
            None,
        )

    def add_rule(self) -> None:
        value = simpledialog.askstring(
            "新增网站",
            "输入网站域名，例如：www.example.com",
            parent=self.window,
        )
        if not value:
            return
        try:
            domain = normalize_domain(value)
            self.database.set_site_rule(domain, True, True)
        except InvalidPageUrl as exc:
            messagebox.showerror("域名无效", str(exc), parent=self.window)
            return
        self.refresh(force=True, select_domain=domain)

    def toggle_enabled(self) -> None:
        rule = self.selected_rule()
        if not rule:
            return
        self.database.set_site_rule(
            rule["domain"],
            not bool(rule["enabled"]),
            bool(rule["include_subdomains"]),
        )
        self.refresh(force=True, select_domain=rule["domain"])

    def toggle_subdomains(self) -> None:
        rule = self.selected_rule()
        if not rule:
            return
        self.database.set_site_rule(
            rule["domain"],
            bool(rule["enabled"]),
            not bool(rule["include_subdomains"]),
        )
        self.refresh(force=True, select_domain=rule["domain"])

    def delete_rule(self) -> None:
        rule = self.selected_rule()
        if not rule:
            return
        if not messagebox.askyesno(
            "删除规则",
            f"删除 {rule['domain']} 后，该网站将按默认规则处理（不自动导入）。是否继续？",
            parent=self.window,
        ):
            return
        self.database.delete_site_rule(rule["domain"])
        self.refresh(force=True)

    def clear_rules(self) -> None:
        rules = self.database.list_site_rules()
        if not rules:
            messagebox.showinfo("规则列表为空", "当前没有可清除的网站规则。", parent=self.window)
            return
        if not messagebox.askyesno(
            "清空全部规则",
            "清空后，所有网站都将恢复为默认不自动导入；下载文件、任务记录和 Eagle 内容不会受到影响。是否继续？",
            parent=self.window,
        ):
            return
        count = self.database.clear_site_rules()
        self.refresh(force=True)
        self.parent.refresh(force=True)
        messagebox.showinfo("清理完成", f"已清除 {count} 条网站规则。", parent=self.window)

    def refresh(self, force: bool = False, select_domain: str | None = None) -> None:
        if not self.window.winfo_exists():
            return
        if self.refresh_after_id:
            self.window.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        selected = select_domain
        if not selected and self.tree.selection():
            selected = str(self.tree.item(self.tree.selection()[0], "values")[0])

        rules = self.database.list_site_rules()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for rule in rules:
            updated = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(rule["updated_at"]),
            )
            self.tree.insert(
                "",
                END,
                iid=rule["domain"],
                values=(
                    rule["domain"],
                    "已开启" if rule["enabled"] else "已关闭",
                    "包含子域名" if rule["include_subdomains"] else "仅此域名",
                    updated,
                ),
            )
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)
        enabled_count = sum(1 for rule in rules if rule["enabled"])
        disabled_count = len(rules) - enabled_count
        self.summary_text.set(
            f"已开启 {enabled_count} 个 · 已关闭 {disabled_count} 个 · 双击可快速切换"
        )
        self.parent.refresh(force=True)
        self.refresh_after_id = self.window.after(3000, self.refresh)

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        if self.refresh_after_id:
            self.window.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        self.parent.site_rules_window = None
        self.window.destroy()


class ProxySettingsWindow:
    def __init__(self, parent: "MainWindow") -> None:
        self.parent = parent
        self.manager = parent.media.network_proxy
        self.window = Toplevel(parent.root)
        self.window.title("网络连接")
        self.window.geometry("560x360")
        self.window.resizable(False, False)
        self.window.transient(parent.root)
        _set_window_icon(self.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        configuration = self.manager.configuration()
        self.mode = StringVar(value=configuration["mode"])
        self.manual_url = StringVar(value=configuration["manualUrl"])
        self.detected_text = StringVar()
        self._build()
        self._mode_changed()
        self.refresh_status()

    def _build(self) -> None:
        outer = ttk.Frame(self.window, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(
            outer,
            text="网络连接",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="默认自动跟随 Windows 系统代理，下载 Behance 等网站时不需要强制开启 TUN。",
            foreground="#475569",
            wraplength=515,
        ).pack(fill=X, pady=(7, 12))

        options = ttk.LabelFrame(outer, text="连接方式", padding=12)
        options.pack(fill=X)
        for value, label in (
            ("auto", "自动（推荐）— 跟随 Windows 系统代理，失败时最多切换一次线路"),
            ("direct", "始终直连 — 不使用任何代理"),
            ("manual", "手动代理 — 适合只给 Chrome 配置代理的情况"),
        ):
            ttk.Radiobutton(
                options,
                text=label,
                value=value,
                variable=self.mode,
                command=self._mode_changed,
            ).pack(anchor="w", pady=2)

        manual = ttk.Frame(outer, padding=(0, 12, 0, 0))
        manual.pack(fill=X)
        ttk.Label(manual, text="HTTP/混合端口：").pack(side=LEFT)
        self.manual_entry = ttk.Entry(manual, textvariable=self.manual_url)
        self.manual_entry.pack(side=LEFT, fill=X, expand=True, padx=(8, 0))
        ttk.Label(
            outer,
            text="示例：127.0.0.1:7890。请填写代理软件显示的 HTTP 或 Mixed 端口。",
            foreground="#64748b",
        ).pack(fill=X, pady=(5, 0))

        detected = ttk.Frame(outer, padding=(0, 14, 0, 0))
        detected.pack(fill=X)
        ttk.Label(detected, textvariable=self.detected_text).pack(side=LEFT)
        ttk.Button(detected, text="重新检测", command=self.refresh_status).pack(side=RIGHT)

        actions = ttk.Frame(outer, padding=(0, 16, 0, 0))
        actions.pack(fill=X)
        ttk.Button(actions, text="取消", command=self.close).pack(side=RIGHT)
        ttk.Button(actions, text="保存", command=self.save).pack(side=RIGHT, padx=(0, 8))

    def _mode_changed(self) -> None:
        self.manual_entry.configure(
            state="normal" if self.mode.get() == "manual" else "disabled"
        )

    def refresh_status(self) -> None:
        status = self.manager.status()
        self.detected_text.set(f"当前检测：{status['summary']}")

    def save(self) -> None:
        try:
            self.manager.configure(self.mode.get(), self.manual_url.get())
        except ProxyConfigurationError as exc:
            messagebox.showerror("代理地址无效", str(exc), parent=self.window)
            return
        self.parent.media._health_cache = None
        self.parent.refresh(force=True)
        messagebox.showinfo(
            "保存完成",
            "网络设置已保存，新任务和重新创建的任务会自动使用。",
            parent=self.window,
        )
        self.close()

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        self.parent.proxy_settings_window = None
        self.window.destroy()


class MainWindow:
    def __init__(
        self,
        database: Database,
        api_server: LocalApiServer,
        processing: ProcessingService,
        external_tray: bool = False,
        start_hidden: bool = False,
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
        self.root = Tk()
        _set_window_icon(self.root)
        if self.start_hidden:
            self.root.withdraw()
        self.root.title("下载中转站")
        self.root.geometry("1120x720")
        self.root.minsize(900, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.hide if external_tray else self.quit)
        self.status_text = StringVar()
        self.pairing_text = StringVar()
        self.site_rules_text = StringVar(value="网站规则")
        self.network_proxy_text = StringVar(value="网络：自动")
        self.update_button_text = StringVar(value="检查更新")
        self.control_signals = ControlSignals() if external_tray else None
        self.control_after_id: str | None = None
        self.refresh_after_id: str | None = None
        self.update_poll_after_id: str | None = None
        self.auto_update_after_id: str | None = None
        self.update_events: Queue[tuple[str, object]] = Queue()
        self.update_checking = False
        self.update_downloading = False
        self.visible = not self.start_hidden
        self.site_rules_window: SiteRulesWindow | None = None
        self.proxy_settings_window: ProxySettingsWindow | None = None
        self.last_jobs_revision: tuple[int, float] | None = None
        self.last_plans_revision: tuple[int, float] | None = None
        self.plan_rows: dict[str, dict] = {}
        self.preview_image: PhotoImage | None = None
        self.wechat_rows: dict[str, dict] = {}
        self.wechat_variant_ids: list[str] = []
        self.wechat_revision: tuple[int, float] | None = None
        self.wechat_preview_events: Queue[tuple[str, bytes]] = Queue()
        self.wechat_preview_requests: set[str] = set()
        self.wechat_preview_object_id = ""
        self.wechat_preview_image: PhotoImage | None = None
        self.wechat_operation_results: Queue[tuple[bool, str]] = Queue()
        self.wechat_operation_busy = False
        self.last_eagle_check = 0.0
        self.eagle_connected = False
        self._build()
        self.refresh()
        if self.control_signals:
            self.control_after_id = self.root.after(250, self._poll_control_signals)
        self.auto_update_after_id = self.root.after(10000, self._automatic_update_check)

    def _build(self) -> None:
        self.main_scroller = _VerticalScrolledFrame(self.root, padding=16)
        self.main_scroller.pack(fill=BOTH, expand=True)
        outer = self.main_scroller.content

        heading = ttk.Frame(outer)
        heading.pack(fill=X)
        ttk.Label(
            heading,
            text="下载中转站",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(side=LEFT)
        ttk.Label(heading, textvariable=self.status_text).pack(side=RIGHT)

        ttk.Label(
            outer,
            text="浏览器插件只负责发现媒体；普通直链、分离音视频和 HLS/DASH 全部由本机软件下载、校验并按需导入 Eagle。",
            foreground="#475569",
        ).pack(fill=X, pady=(8, 0))

        pairing = ttk.Frame(outer, padding=(0, 12, 0, 8))
        pairing.pack(fill=X)
        ttk.Label(pairing, textvariable=self.pairing_text).pack(side=LEFT)
        ttk.Button(pairing, text="复制配对码", command=self.copy_pairing_code).pack(
            side=LEFT, padx=(10, 0)
        )
        ttk.Button(pairing, text="解除 Chrome 配对", command=self.unpair).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Button(pairing, textvariable=self.site_rules_text, command=self.show_site_rules).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Button(
            pairing,
            textvariable=self.network_proxy_text,
            command=self.show_proxy_settings,
        ).pack(side=LEFT, padx=(8, 0))
        self.update_button = ttk.Button(
            pairing,
            textvariable=self.update_button_text,
            command=self.check_for_updates,
        )
        self.update_button.pack(side=RIGHT)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=BOTH, expand=True)
        self.notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _event: self.main_scroller.scroll_to_top(),
            add="+",
        )
        self._build_media_tab()
        self._build_wechat_tab()
        self._build_idm_tab()

        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill=X)
        ttk.Button(footer, text="导出诊断", command=self.export_diagnostics).pack(side=LEFT)
        if self.external_tray:
            ttk.Button(footer, text="隐藏到右下角", command=self.hide).pack(side=RIGHT)
        else:
            ttk.Button(footer, text="最小化窗口", command=self.root.iconify).pack(side=RIGHT)

    def _build_media_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="媒体下载")
        columns = ("status", "progress", "title", "source", "updated")
        self.plan_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse", height=12)
        for name, label in (
            ("status", "状态"),
            ("progress", "进度"),
            ("title", "下载内容"),
            ("source", "来源网站"),
            ("updated", "最近更新"),
        ):
            self.plan_tree.heading(name, text=label)
        self.plan_tree.column("status", width=125, anchor="center")
        self.plan_tree.column("progress", width=75, anchor="center")
        self.plan_tree.column("title", width=420)
        self.plan_tree.column("source", width=170)
        self.plan_tree.column("updated", width=135, anchor="center")
        self.plan_tree.pack(fill=BOTH, expand=True)
        self.plan_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_plan_detail())

        detail = ttk.LabelFrame(tab, text="任务详情", padding=10)
        detail.pack(fill=X, pady=(10, 0))
        self.preview_label = ttk.Label(detail, text="暂无预览", width=32, anchor="center")
        self.preview_label.pack(side=LEFT, padx=(0, 14))
        copy = ttk.Frame(detail)
        copy.pack(side=LEFT, fill=BOTH, expand=True)
        self.plan_title_text = StringVar(value="选择一项任务查看详情")
        self.plan_status_text = StringVar(value="")
        self.plan_source_text = StringVar(value="")
        self.plan_file_text = StringVar(value="")
        ttk.Label(copy, textvariable=self.plan_title_text, font=("Microsoft YaHei UI", 12, "bold")).pack(fill=X)
        ttk.Label(copy, textvariable=self.plan_status_text).pack(fill=X, pady=(5, 0))
        self.plan_progress = ttk.Progressbar(copy, maximum=100)
        self.plan_progress.pack(fill=X, pady=(6, 4))
        ttk.Label(copy, textvariable=self.plan_source_text, foreground="#475569").pack(fill=X)
        ttk.Label(copy, textvariable=self.plan_file_text, foreground="#475569").pack(fill=X, pady=(3, 0))

        actions = ttk.Frame(tab, padding=(0, 10, 0, 0))
        actions.pack(fill=X)
        ttk.Button(actions, text="刷新", command=lambda: self.refresh(force=True)).pack(side=LEFT)
        ttk.Button(actions, text="清除已完成记录", command=self.clear_media_history).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="停止任务", command=self.stop_selected_plan).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="重试下载", command=self.retry_selected_plan).pack(side=LEFT)
        ttk.Button(actions, text="导入现有文件到 Eagle", command=self.import_selected_plan).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="打开文件位置", command=self.open_plan_location).pack(side=LEFT)
        ttk.Button(actions, text="打开来源网页", command=self.open_plan_source).pack(side=LEFT, padx=6)

    def _build_idm_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="IDM 导入记录")
        columns = ("time", "status", "file", "source", "message")
        self.job_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse")
        self.job_tree.heading("time", text="时间")
        self.job_tree.heading("status", text="状态")
        self.job_tree.heading("file", text="文件")
        self.job_tree.heading("source", text="来源网站")
        self.job_tree.heading("message", text="说明")
        self.job_tree.column("time", width=130, anchor="center")
        self.job_tree.column("status", width=100, anchor="center")
        self.job_tree.column("file", width=300)
        self.job_tree.column("source", width=180)
        self.job_tree.column("message", width=260)
        self.job_tree.pack(fill=BOTH, expand=True)
        actions = ttk.Frame(tab, padding=(0, 10, 0, 0))
        actions.pack(fill=X)
        ttk.Button(actions, text="刷新", command=lambda: self.refresh(force=True)).pack(side=LEFT)
        ttk.Button(actions, text="重试导入", command=self.retry_selected).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="打开文件位置", command=self.open_file_location).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="打开来源网页", command=self.open_source).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="补充/修改来源", command=self.assign_source).pack(side=LEFT, padx=6)
        ttk.Button(actions, text="清除已完成记录", command=self.clear_history).pack(side=LEFT, padx=6)

    def _build_wechat_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="微信视频号")

        header = ttk.Frame(tab)
        header.pack(fill=X, pady=(0, 10))
        self.wechat_status_text = StringVar(value="视频号捕获已关闭")
        self.wechat_action_text = StringVar(value="开始捕获")
        ttk.Label(
            header,
            textvariable=self.wechat_status_text,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side=LEFT)
        self.wechat_action_button = ttk.Button(
            header,
            textvariable=self.wechat_action_text,
            command=self.toggle_wechat_capture,
        )
        self.wechat_action_button.pack(side=RIGHT)
        ttk.Label(
            tab,
            text="仅在你点击开始后，本机才为微信桌面客户端启用受控 HTTPS 捕获；停止或退出会恢复开启前的系统代理。浏览器扩展与 IDM 不参与此过程。",
            foreground="#475569",
            wraplength=1020,
            justify=LEFT,
        ).pack(fill=X, pady=(0, 10))

        columns = ("title", "author", "duration", "quality", "updated")
        self.wechat_tree = ttk.Treeview(
            tab, columns=columns, show="headings", selectmode="browse", height=13
        )
        for name, label in (
            ("title", "视频内容"),
            ("author", "作者"),
            ("duration", "时长"),
            ("quality", "可用质量"),
            ("updated", "最近识别"),
        ):
            self.wechat_tree.heading(name, text=label)
        self.wechat_tree.column("title", width=420)
        self.wechat_tree.column("author", width=150)
        self.wechat_tree.column("duration", width=80, anchor="center")
        self.wechat_tree.column("quality", width=190)
        self.wechat_tree.column("updated", width=130, anchor="center")
        self.wechat_tree.pack(fill=BOTH, expand=True)
        self.wechat_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_wechat_detail())

        detail = ttk.LabelFrame(tab, text="候选详情", padding=10)
        detail.pack(fill=X, pady=(10, 0))
        self.wechat_preview_label = ttk.Label(
            detail,
            text="封面将在识别后显示",
            width=34,
            anchor="center",
            compound="center",
        )
        self.wechat_preview_label.pack(side=LEFT, fill="y", padx=(0, 12))
        detail_text = ttk.Frame(detail)
        detail_text.pack(side=LEFT, fill=BOTH, expand=True)
        self.wechat_detail_text = StringVar(value="开始捕获后，在微信中打开视频号内容。")
        self.wechat_quality_text = StringVar(value="")
        self.wechat_variant_text = StringVar(value="")
        ttk.Label(
            detail_text,
            textvariable=self.wechat_detail_text,
            font=("Microsoft YaHei UI", 11, "bold"),
            wraplength=980,
            justify=LEFT,
        ).pack(fill=X)
        ttk.Label(detail_text, textvariable=self.wechat_quality_text, foreground="#475569").pack(fill=X, pady=(4, 0))
        self.wechat_variant_box = ttk.Combobox(
            detail_text,
            state="readonly",
            textvariable=self.wechat_variant_text,
            values=(),
        )
        self.wechat_variant_box.pack(fill=X, pady=(8, 0))

        actions = ttk.Frame(tab, padding=(0, 10, 0, 0))
        actions.pack(fill=X)
        self.wechat_import_to_eagle = BooleanVar(value=True)
        ttk.Checkbutton(
            actions,
            text="下载完成后导入 Eagle",
            variable=self.wechat_import_to_eagle,
        ).pack(side=LEFT)
        ttk.Button(
            actions,
            text="创建下载任务",
            command=self.submit_selected_wechat_candidate,
        ).pack(side=LEFT, padx=8)
        ttk.Button(
            actions,
            text="刷新候选",
            command=lambda: self.refresh(force=True),
        ).pack(side=LEFT)
        ttk.Button(
            actions,
            text="清除全部候选",
            command=self.clear_wechat_candidates,
        ).pack(side=LEFT, padx=8)

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
            self.show_site_rules()
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
            if not silent:
                messagebox.showinfo("已经是最新版", f"当前版本 v{APP_VERSION} 已是最新版。")
            return
        if not isinstance(update, UpdateInfo):
            self._handle_update_error(silent, UpdateError("更新信息无效"))
            return
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
        if not silent:
            messagebox.showwarning("检查更新失败", str(error), parent=self.root)

    def _start_update_download(self, update: UpdateInfo) -> None:
        self.update_downloading = True
        self.update_button.configure(state="disabled")
        self.update_button_text.set("正在下载 0%")
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
        try:
            launch_installer(Path(installer))
        except Exception as exc:
            self._handle_download_error(exc)
            return
        self.root.after(350, self.quit)

    def _handle_download_error(self, error: object) -> None:
        self.update_downloading = False
        self._reset_update_button()
        messagebox.showerror("更新失败", str(error), parent=self.root)

    def refresh(self, force: bool = False) -> None:
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if not self.visible and not force:
            self.refresh_after_id = self.root.after(30000, self.refresh)
            return

        now = time.time()
        if force or now - self.last_eagle_check >= 10:
            self.eagle_connected = self.eagle.is_available()
            self.last_eagle_check = now
        eagle_text = "Eagle 已连接" if self.eagle_connected else "正在等待 Eagle"
        host, port = self.api_server.address
        counts = self.database.job_status_counts()
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
        enabled_sites = sum(
            1 for rule in self.database.list_site_rules() if rule["enabled"]
        )
        self.site_rules_text.set(f"网站规则（已开启 {enabled_sites}）")
        proxy_status = self.media.network_proxy.status()
        self.network_proxy_text.set(f"网络：{proxy_status['summary']}")
        if self.pairing.paired_origin:
            self.pairing_text.set("Chrome 已安全配对")
        else:
            self.pairing_text.set(f"Chrome 配对码：{self.pairing.pairing_code}")

        self._refresh_media_tasks(plans, force)
        self._refresh_wechat_candidates(wechat_health, force)

        revision = self.database.jobs_revision()
        if force or revision != self.last_jobs_revision:
            selected = self.selected_job_id()
            for item in self.job_tree.get_children():
                self.job_tree.delete(item)
            for job in self.database.list_jobs(500):
                created = time.strftime("%Y-%m-%d %H:%M", time.localtime(job["created_at"]))
                source = "未记录"
                if job.get("source_url"):
                    source = urlsplit(job["source_url"]).hostname or "已记录"
                message = job.get("error_message") or ""
                if job["status"] == "imported" and not job.get("source_url"):
                    message = "已直接导入，未保存来源网页"
                self.job_tree.insert(
                    "",
                    END,
                    iid=job["id"],
                    values=(
                        created,
                        STATUS_TEXT.get(job["status"], job["status"]),
                        job["file_name"],
                        source,
                        message,
                    ),
                )
            if selected and self.job_tree.exists(selected):
                self.job_tree.selection_set(selected)
            self.last_jobs_revision = revision
        self.refresh_after_id = self.root.after(
            1000 if media_active_count or wechat_health.get("running") else 4000,
            self.refresh,
        )

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

        candidates = self.wechat_channels.candidates()
        revision = (
            len(candidates),
            max((float(item.get("updatedAt") or 0) for item in candidates), default=0.0),
        )
        self.wechat_rows = {str(item["objectId"]): item for item in candidates}
        selected = self.wechat_tree.selection()
        selected_id = selected[0] if selected else ""
        if force or revision != self.wechat_revision:
            for item in self.wechat_tree.get_children():
                self.wechat_tree.delete(item)
            for item in candidates:
                variants = item.get("variants") if isinstance(item.get("variants"), list) else []
                qualities = "、".join(str(variant.get("quality") or "自动") for variant in variants[:6])
                if len(variants) > 6:
                    qualities += f" 等 {len(variants)} 档"
                updated = time.strftime(
                    "%H:%M:%S", time.localtime(float(item.get("updatedAt") or 0))
                )
                self.wechat_tree.insert(
                    "",
                    END,
                    iid=str(item["objectId"]),
                    values=(
                        str(item.get("title") or "微信视频号视频"),
                        str(item.get("author") or "未知作者"),
                        self._duration_text(item.get("durationMs")),
                        qualities or "自动质量",
                        updated,
                    ),
                )
            if selected_id and self.wechat_tree.exists(selected_id):
                self.wechat_tree.selection_set(selected_id)
            elif candidates:
                latest_id = str(candidates[-1]["objectId"])
                self.wechat_tree.selection_set(latest_id)
                self.wechat_tree.see(latest_id)
            self.wechat_revision = revision
        self._update_wechat_detail()

    def _selected_wechat_candidate(self) -> dict | None:
        selected = self.wechat_tree.selection()
        return self.wechat_rows.get(selected[0]) if selected else None

    def _update_wechat_detail(self) -> None:
        candidate = self._selected_wechat_candidate()
        if not candidate:
            self.wechat_detail_text.set("开始捕获后，在微信中打开视频号内容。")
            self.wechat_quality_text.set("")
            self.wechat_variant_ids = []
            self.wechat_variant_box.configure(values=())
            self.wechat_variant_text.set("")
            self.wechat_preview_object_id = ""
            self.wechat_preview_image = None
            self.wechat_preview_label.configure(image="", text="封面将在识别后显示")
            return
        object_id = str(candidate.get("objectId") or "")
        if object_id != self.wechat_preview_object_id:
            self.wechat_preview_object_id = object_id
            self.wechat_preview_image = None
            self.wechat_preview_label.configure(image="", text="正在读取封面…")
            if object_id and candidate.get("coverUrl") and object_id not in self.wechat_preview_requests:
                self.wechat_preview_requests.add(object_id)
                threading.Thread(
                    target=self._load_wechat_preview,
                    args=(object_id,),
                    name="wechat-cover-preview",
                    daemon=True,
                ).start()
            elif not candidate.get("coverUrl"):
                self.wechat_preview_label.configure(text="该内容未提供封面")
        self.wechat_detail_text.set(
            f"{candidate.get('title') or '微信视频号视频'} · {candidate.get('author') or '未知作者'}"
        )
        self.wechat_quality_text.set(
            f"内容 ID：{candidate.get('objectId')} · 视频 · 时长 {self._duration_text(candidate.get('durationMs'))}\n"
            f"预计输出：{candidate.get('outputName') or '微信视频号视频.mp4'}"
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
                self.wechat_preview_label.configure(image="", text="封面暂不可用")
                continue
            try:
                image = PhotoImage(data=preview, format="png")
            except Exception:
                self.wechat_preview_label.configure(image="", text="封面暂不可用")
                continue
            self.wechat_preview_image = image
            self.wechat_preview_label.configure(image=image, text="")

    def toggle_wechat_capture(self) -> None:
        if self.wechat_operation_busy:
            return
        running = bool(self.wechat_channels.health().get("running"))
        if not running:
            try:
                existing = self.wechat_channels.certificate.existing()
                needs_trust = not existing or not self.wechat_channels.certificate.is_trusted(
                    existing.fingerprint
                )
            except Exception as exc:
                messagebox.showerror("无法检查视频号证书", str(exc), parent=self.root)
                return
            if needs_trust and not messagebox.askokcancel(
                "首次启用视频号捕获",
                "下载中转站将为当前 Windows 用户生成并信任一张仅用于微信视频号本机捕获的根证书。\n\n"
                "Windows 随后会显示“安全警告”，请核对证书名称为“下载中转站 微信视频号本机捕获根证书”后亲自确认。停止捕获会恢复系统代理；卸载会按精确指纹移除此证书。\n\n"
                "是否继续？",
                parent=self.root,
            ):
                return
        self.wechat_operation_busy = True
        self.wechat_action_button.state(["disabled"])
        self.wechat_status_text.set("正在停止视频号捕获…" if running else "正在准备视频号捕获…")
        threading.Thread(
            target=self._run_wechat_operation,
            args=(running,),
            name="wechat-capture-toggle",
            daemon=True,
        ).start()
        self.root.after(200, self._poll_wechat_operation)

    def _run_wechat_operation(self, was_running: bool) -> None:
        try:
            if was_running:
                self.wechat_channels.stop()
            else:
                self.wechat_channels.start()
        except Exception as exc:
            self.wechat_operation_results.put((False, str(exc)))
            return
        self.wechat_operation_results.put((True, ""))

    def _poll_wechat_operation(self) -> None:
        try:
            succeeded, error = self.wechat_operation_results.get_nowait()
        except Empty:
            if self.wechat_operation_busy:
                self.root.after(200, self._poll_wechat_operation)
            return
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
            self.wechat_channels.submit(
                str(candidate["objectId"]),
                variant_id,
                import_to_eagle=bool(self.wechat_import_to_eagle.get()),
            )
        except Exception as exc:
            messagebox.showerror("创建任务失败", str(exc), parent=self.root)
            return
        self.notebook.select(0)
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

    def _refresh_media_tasks(self, plans: list[dict], force: bool) -> None:
        revision = (
            len(plans),
            max((float(plan.get("updated_at") or 0) for plan in plans), default=0.0),
        )
        self.plan_rows = {str(plan["id"]): plan for plan in plans}
        selected = self.selected_plan_id()
        if force or revision != self.last_plans_revision:
            for item in self.plan_tree.get_children():
                self.plan_tree.delete(item)
            for plan in plans:
                status = str(plan.get("status") or "")
                job_status = str(plan.get("job_status") or "")
                if status == "ready_to_import" and job_status == "waiting_eagle":
                    status_label = "等待 Eagle"
                elif status == "ready_to_import" and job_status == "failed_permanent":
                    status_label = "Eagle 导入失败"
                else:
                    status_label = MEDIA_STATUS_TEXT.get(status, status)
                source = "未记录"
                if plan.get("page_url"):
                    source = urlsplit(str(plan["page_url"])).hostname or "已记录"
                title = str(plan.get("title") or plan.get("output_name") or "未命名任务")
                updated = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(float(plan.get("updated_at") or 0))
                )
                self.plan_tree.insert(
                    "",
                    END,
                    iid=str(plan["id"]),
                    values=(
                        status_label,
                        f"{float(plan.get('progress') or 0):.0f}%",
                        title,
                        source,
                        updated,
                    ),
                )
            if selected and self.plan_tree.exists(selected):
                self.plan_tree.selection_set(selected)
            elif plans:
                first = str(plans[0]["id"])
                self.plan_tree.selection_set(first)
            self.last_plans_revision = revision
        self._update_plan_detail()

    def selected_plan_id(self) -> str | None:
        selected = self.plan_tree.selection()
        return selected[0] if selected else None

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
            self.plan_progress.configure(value=0)
            self.preview_image = None
            self.preview_label.configure(image="", text="暂无预览")
            return
        status = str(plan.get("status") or "")
        status_label = MEDIA_STATUS_TEXT.get(status, status)
        if status == "ready_to_import" and plan.get("job_status") == "waiting_eagle":
            status_label = "等待 Eagle"
        elif status == "ready_to_import" and plan.get("job_status") == "failed_permanent":
            status_label = "Eagle 导入失败"
        detail = str(plan.get("phase_detail") or "")
        error = str(plan.get("error_message") or plan.get("job_error") or "")
        self.plan_title_text.set(str(plan.get("title") or plan.get("output_name") or "未命名任务"))
        self.plan_status_text.set(" · ".join(value for value in (status_label, detail, error) if value))
        source = str(plan.get("page_url") or "未记录来源网页")
        self.plan_source_text.set(f"来源：{source}")
        downloaded = _display_bytes(plan.get("downloaded_bytes"))
        total = _display_bytes(plan.get("total_bytes"))
        output = str(plan.get("final_path") or plan.get("output_name") or "")
        self.plan_file_text.set(f"文件：{output} · 已处理 {downloaded} / {total}")
        self.plan_progress.configure(value=max(0.0, min(100.0, float(plan.get("progress") or 0))))
        preview = Path(str(plan.get("preview_path") or ""))
        if preview.is_file():
            try:
                self.preview_image = PhotoImage(file=str(preview))
                self.preview_label.configure(image=self.preview_image, text="")
                return
            except Exception:
                pass
        self.preview_image = None
        self.preview_label.configure(image="", text="下载完成后显示视频预览")

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
        path = Path(str(plan.get("final_path") or "")) if plan else None
        if not path or not path.is_file():
            messagebox.showinfo("文件尚未完成", "任务完成下载后才能打开文件位置")
            return
        subprocess.Popen(["explorer.exe", "/select,", str(path)])

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

    def show_site_rules(self) -> None:
        if self.site_rules_window and self.site_rules_window.window.winfo_exists():
            self.site_rules_window.focus()
            return
        self.site_rules_window = SiteRulesWindow(self)

    def show_proxy_settings(self) -> None:
        if (
            self.proxy_settings_window
            and self.proxy_settings_window.window.winfo_exists()
        ):
            self.proxy_settings_window.focus()
            return
        self.proxy_settings_window = ProxySettingsWindow(self)

    def unpair(self) -> None:
        if not self.pairing.paired_origin:
            messagebox.showinfo("未配对", "当前没有已配对的 Chrome 扩展")
            return
        if not messagebox.askyesno("解除配对", "解除后需要重新输入配对码，是否继续？"):
            return
        self.pairing.unpair()
        self.refresh(force=True)

    def quit(self) -> None:
        if self.site_rules_window and self.site_rules_window.window.winfo_exists():
            self.site_rules_window.close()
        if self.proxy_settings_window and self.proxy_settings_window.window.winfo_exists():
            self.proxy_settings_window.close()
        if self.refresh_after_id:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if self.control_after_id:
            self.root.after_cancel(self.control_after_id)
            self.control_after_id = None
        if self.update_poll_after_id:
            self.root.after_cancel(self.update_poll_after_id)
            self.update_poll_after_id = None
        if self.auto_update_after_id:
            self.root.after_cancel(self.auto_update_after_id)
            self.auto_update_after_id = None
        if self.control_signals:
            self.control_signals.close()
            self.control_signals = None
        self.root.quit()
        self.root.destroy()
