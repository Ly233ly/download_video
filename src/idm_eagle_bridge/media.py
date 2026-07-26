from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

from .constants import TERMINAL_MEDIA_PLAN_STATUSES
from .database import Database
from .network_proxy import (
    NetworkProxyManager,
    ProxyConfigurationError,
    ProxyRoute,
)
from .paths import download_station_root
from .wechat_channels_crypto import WechatVideoDecryptor


ALLOWED_CONTAINERS = frozenset({"mp4", "mkv", "webm", "m4a", "mp3", "ts"})
ALLOWED_STREAM_ROLES = frozenset({"video", "audio", "subtitle", "media"})
SUBTITLE_EXTENSIONS = frozenset({"vtt", "srt", "ass", "ssa", "ttml"})
MANIFEST_EXTENSIONS = frozenset({"m3u8", "m3u", "mpd"})
NETWORK_RETRYABLE_ERRORS = frozenset(
    {
        "desktop_download_failed",
        "page_resolver_failed",
        "youtube_resolver_failed",
        "subtitle_download_failed",
        "wechat_download_failed",
    }
)
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


class MediaPlanError(RuntimeError):
    """A user-visible media plan failure."""

    def __init__(self, message: str, code: str = "media_plan_error") -> None:
        super().__init__(message)
        self.code = code


def _safe_text(value: Any, maximum: int = 500) -> str:
    return str(value or "").replace("\x00", "")[:maximum]


def _safe_extension(value: Any, fallback: str = "bin") -> str:
    result = re.sub(r"[^a-z0-9]", "", str(value or "").lower())[:10]
    return result or fallback


def safe_output_name(value: Any, container: str) -> str:
    name = Path(_safe_text(value, 220)).name
    if name.lower().endswith("." + container.lower()):
        name = name[: -(len(container) + 1)]
    else:
        name = Path(name).stem
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "media"
    if name.upper() in WINDOWS_RESERVED_NAMES:
        name = "_" + name
    return f"{name[:180]}.{container}"


def redact_media_url(value: Any) -> str:
    raw = _safe_text(value, 8192)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https", "blob"}:
        return ""
    if parsed.scheme == "blob":
        return "blob:"
    # Signed queries and fragments routinely contain authorization data.
    # The full URL stays in process memory only for the lifetime of the task.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:2048]


def canonical_page_resolver_url(value: Any) -> str:
    raw = _safe_text(value, 8192)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw
    hostname = (parsed.hostname or "").lower()
    if hostname == "douyin.com" or hostname.endswith(".douyin.com"):
        path_match = re.fullmatch(r"/video/(\d{10,30})/?", parsed.path)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        modal_id = str(query.get("modal_id") or "")
        video_id = path_match.group(1) if path_match else (
            modal_id if re.fullmatch(r"\d{10,30}", modal_id) else ""
        )
        if video_id:
            return f"https://www.douyin.com/video/{video_id}"
    return raw


def _is_fixed_byte_range_url(value: str, size: int | None = None) -> bool:
    """Return True when the URL itself identifies one byte slice, not a file."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return False

    def valid_range(start: str, end: str) -> tuple[bool, int]:
        try:
            first = int(start)
            last = int(end)
        except ValueError:
            return False, 0
        if first < 0 or last < first:
            return False, 0
        span = last - first + 1
        return span > 0, span

    def matches(start: str, end: str) -> bool:
        valid, span = valid_range(start, end)
        return valid and (size is None or size <= 0 or size == span)

    def named_range(text: str) -> bool:
        match = re.fullmatch(r"(?:range|bytes)=(\d+)-(\d+)", text.strip(), re.IGNORECASE)
        return bool(match and matches(match.group(1), match.group(2)))

    query = {name.lower(): raw for name, raw in parse_qsl(parsed.query, keep_blank_values=True)}
    for name in ("range", "bytes"):
        match = re.fullmatch(r"(\d+)-(\d+)", query.get(name, ""))
        if match and valid_range(match.group(1), match.group(2))[0]:
            return True
    if "start" in query and "end" in query and valid_range(query["start"], query["end"])[0]:
        return True
    if "bytestart" in query and "byteend" in query and valid_range(query["bytestart"], query["byteend"])[0]:
        return True

    for raw_segment in parsed.path.split("/"):
        segment = unquote(raw_segment)
        if named_range(segment):
            return True
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,300}", segment):
            continue
        try:
            padding = "=" * ((4 - len(segment) % 4) % 4)
            decoded = base64.urlsafe_b64decode(segment + padding).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            continue
        if named_range(decoded):
            return True
    return False


def _tool_candidates(name: str) -> list[Path]:
    executable = name + (".exe" if os.name == "nt" else "")
    candidates: list[Path] = []
    override = os.environ.get(f"IDM_EAGLE_{name.upper()}")
    if override:
        candidates.append(Path(override))
    if getattr(sys, "frozen", False):
        frozen = Path(sys.executable).resolve()
        candidates.extend(
            [
                frozen.parent / "media-tools" / executable,
                frozen.parent.parent / "media-tools" / executable,
                frozen.parent.parent.parent / "media-tools" / executable,
            ]
        )
    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root / "media-tools" / executable)
    system = shutil.which(name)
    if system:
        candidates.append(Path(system))
    return candidates


def resolve_media_tool(name: str) -> Path:
    for candidate in _tool_candidates(name):
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    raise MediaPlanError(
        f"未找到 {name}。请修复 1.2.5 媒体工具安装后重试。",
        f"{name}_missing",
    )


class MediaCoordinator:
    """Own every media download from URL reception through Eagle queueing."""

    def __init__(
        self,
        database: Database,
        workers: int = 2,
        ready_callback: Callable[[], None] | None = None,
    ) -> None:
        self.database = database
        self.network_proxy = NetworkProxyManager(database)
        self.ready_callback = ready_callback
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, workers), thread_name_prefix="media-plan"
        )
        self._scheduled: set[str] = set()
        self._remote_inputs: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._stop_requested: set[str] = set()
        self._health_cache: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()
        self._recover_interrupted_plans()

    def _recover_interrupted_plans(self) -> None:
        """Full signed URLs are memory-only, so an interrupted task cannot be guessed."""
        now = time.time()
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET
                    status = 'retry', progress = 0,
                    error_code = 'download_context_expired',
                    error_message = '本机软件已重新启动，请回到来源网页重新创建任务',
                    phase_detail = '需要重新创建任务', updated_at = ?
                WHERE status IN ('queued', 'downloading', 'merging', 'validating')
                """,
                (now,),
            )

    def close(self) -> None:
        """Stop active FFmpeg jobs and release worker threads during app shutdown."""
        with self._lock:
            processes = list(self._processes.values())
            self._stop_requested.update(self._processes)
        for process in processes:
            self._request_process_stop(process)
        deadline = time.monotonic() + 3
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.terminate()
        self.executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _request_process_stop(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None or not process.stdin:
            return
        try:
            process.stdin.write("q\n")
            process.stdin.flush()
        except (OSError, ValueError):
            pass

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        streams = payload.get("streams")
        if not isinstance(streams, list) or not streams or len(streams) > 16:
            raise MediaPlanError("下载方案必须包含 1–16 个媒体流", "invalid_streams")
        if any(bool(item.get("drm")) for item in streams if isinstance(item, dict)):
            raise MediaPlanError("检测到 DRM 保护，本程序不会下载或尝试绕过", "blocked_drm")

        container = _safe_extension(payload.get("outputContainer"), "mkv")
        if container not in ALLOWED_CONTAINERS:
            raise MediaPlanError("不支持该输出容器", "invalid_container")
        output_name = safe_output_name(payload.get("outputName"), container)
        import_to_eagle = bool(payload.get("importToEagle", True))
        # 覆盖安装无法替 Chrome 重启已经加载的旧 service worker。旧扩展仍会
        # 明确发送 importToEagle，却不知道 deleteAfterImport；把导入动作本身
        # 视为新计划的清理选择，避免同一按钮因 worker 版本不同而改变语义。
        delete_after_import = bool(
            payload.get("deleteAfterImport", import_to_eagle)
        )
        delete_after_import = delete_after_import and import_to_eagle
        merge_mode = _safe_text(
            payload.get("mergeMode") or ("direct" if len(streams) == 1 else "local_streamcopy"),
            40,
        )
        if merge_mode not in {"direct", "local_streamcopy", "local_transcode"}:
            raise MediaPlanError("不支持该合并方式", "invalid_merge_mode")

        plan_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        now = time.time()
        page_url = redact_media_url(payload.get("pageUrl"))
        page_title = _safe_text(payload.get("pageTitle"), 500)
        thumbnail_url = redact_media_url(payload.get("thumbnailUrl"))
        tab_id = payload.get("tabId") if isinstance(payload.get("tabId"), int) else None
        group_key = hashlib.sha256(
            f"{tab_id}|{page_url}|{page_title}".encode("utf-8")
        ).hexdigest()
        runtime_headers = payload.get("runtimeHeaders")
        source_type = _safe_text(payload.get("sourceType"), 40).lower()
        contexts: list[dict[str, Any]] = []
        known_total = 0
        known_size_count = 0
        has_video = False
        has_audio = False
        has_manifest = False

        for index, raw in enumerate(streams):
            if not isinstance(raw, dict):
                raise MediaPlanError("媒体流格式无效", "invalid_stream")
            url = _safe_text(raw.get("url"), 8192)
            try:
                parsed = urlsplit(url)
            except ValueError as exc:
                raise MediaPlanError("媒体地址无效", "invalid_media_url") from exc
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or "\r" in url or "\n" in url:
                if parsed.scheme == "blob":
                    raise MediaPlanError(
                        "浏览器 blob 地址无法由本机软件访问，请选择捕获到的真实直链或 HLS/DASH 清单",
                        "blob_url_not_downloadable",
                    )
                raise MediaPlanError("媒体地址无效或不受支持", "invalid_media_url")
            role = _safe_text(raw.get("role") or "media", 20).lower()
            if not any(role.startswith(allowed) for allowed in ALLOWED_STREAM_ROLES):
                role = "media"
            extension = _safe_extension(raw.get("extension"), "bin")
            size = raw.get("size") if isinstance(raw.get("size"), int) and raw.get("size") >= 0 else None
            if extension not in MANIFEST_EXTENSIONS and _is_fixed_byte_range_url(url, size):
                raise MediaPlanError(
                    "捕获到固定字节分片，请继续播放并选择完整视频或 HLS/DASH 清单",
                    "fixed_range_fragment",
                )
            duration_value = raw.get("duration")
            duration = (
                float(duration_value)
                if isinstance(duration_value, (int, float)) and 0 < float(duration_value) < 7 * 86400
                else None
            )
            preferred_quality = _safe_text(raw.get("preferredQuality"), 20).lower()
            if not re.fullmatch(r"\d{2,5}p", preferred_quality):
                preferred_quality = ""
            resolver = _safe_text(raw.get("resolver"), 40).lower()
            if resolver:
                if resolver not in {"youtube", "page"}:
                    raise MediaPlanError("不支持该媒体解析器", "invalid_resolver")
                hostname = (parsed.hostname or "").lower()
                if resolver == "youtube" and (
                    not re.fullmatch(r"(?:www\.)?youtube\.com", hostname) or not preferred_quality
                ):
                    raise MediaPlanError("YouTube 下载方案缺少有效页面或画质", "invalid_youtube_plan")
                if resolver == "page":
                    if hostname in {"localhost", "localhost.localdomain"} or not hostname:
                        raise MediaPlanError("页面解析地址无效", "invalid_page_resolver_url")
                    try:
                        address = ipaddress.ip_address(hostname.strip("[]"))
                    except ValueError:
                        address = None
                    if address and not address.is_global:
                        raise MediaPlanError("页面解析不允许访问本机或内网地址", "invalid_page_resolver_url")
            headers = (
                runtime_headers[index]
                if isinstance(runtime_headers, list) and index < len(runtime_headers)
                else {}
            )
            wechat_decode_key: int | None = None
            wechat_encrypted_bytes = 0
            if source_type == "wechat_channels":
                raw_key = _safe_text(raw.get("wechatDecodeKey"), 32)
                if raw_key:
                    try:
                        wechat_decode_key = int(raw_key, 0)
                    except ValueError as exc:
                        raise MediaPlanError("视频号解密键无效", "wechat_decode_key_invalid") from exc
                    if not 0 <= wechat_decode_key < 2**64:
                        raise MediaPlanError("视频号解密键无效", "wechat_decode_key_invalid")
                    raw_encrypted_bytes = raw.get("wechatEncryptedBytes")
                    if not isinstance(raw_encrypted_bytes, int) or not 1 <= raw_encrypted_bytes <= 8 * 1024 * 1024:
                        raise MediaPlanError("视频号加密长度无效", "wechat_encrypted_length_invalid")
                    wechat_encrypted_bytes = raw_encrypted_bytes
            contexts.append(
                {
                    "url": url,
                    "role": role,
                    "headers": self._safe_runtime_headers(headers),
                    "extension": extension,
                    "name": _safe_text(raw.get("name"), 220),
                    "language": _safe_text(raw.get("language"), 40),
                    "label": _safe_text(raw.get("label"), 120),
                    "duration": duration,
                    "size": size,
                    "preferred_quality": preferred_quality,
                    "resolver": resolver,
                    "wechat_decode_key": wechat_decode_key,
                    "wechat_encrypted_bytes": wechat_encrypted_bytes,
                }
            )
            if size is not None and size > 0:
                known_total += size
                known_size_count += 1
            has_video = has_video or role.startswith("video")
            has_audio = has_audio or role.startswith("audio")
            has_manifest = has_manifest or extension in MANIFEST_EXTENSIONS

        if any(context.get("resolver") for context in contexts):
            media_kind = "resolver"
        elif has_manifest:
            media_kind = "manifest"
        elif has_video and has_audio:
            media_kind = "dash"
        else:
            media_kind = "direct"
        total_bytes = known_total if known_size_count == len(contexts) else None

        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO capture_sessions(id, tab_id, page_url, page_title, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
                (session_id, tab_id, page_url, page_title, now, now),
            )
            connection.execute(
                """
                INSERT INTO media_groups(
                    id, session_id, group_key, title, page_url, thumbnail_url,
                    media_kind, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    session_id,
                    group_key,
                    page_title or Path(output_name).stem,
                    page_url,
                    thumbnail_url,
                    media_kind,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO download_plans(
                    id, group_id, output_name, output_container, merge_mode,
                    route, import_to_eagle, delete_after_import,
                    status, progress, downloaded_bytes, total_bytes,
                    phase_detail, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'desktop', ?, ?, 'queued', 0, 0, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    group_id,
                    output_name,
                    container,
                    merge_mode,
                    1 if import_to_eagle else 0,
                    1 if delete_after_import else 0,
                    total_bytes,
                    "等待本机下载",
                    now,
                    now,
                ),
            )
            role_counts: dict[str, int] = {}
            for index, (raw, context) in enumerate(zip(streams, contexts, strict=True)):
                stream_id = str(uuid.uuid4())
                base_role = str(context["role"])
                count = role_counts.get(base_role, 0) + 1
                role_counts[base_role] = count
                role = base_role if count == 1 else f"{base_role}{count}"
                context["role"] = role
                connection.execute(
                    """
                    INSERT INTO media_streams(
                        id, group_id, client_index, role, source_url_redacted,
                        name, extension, mime_type, size, width, height, codec,
                        duration, language, label, drm, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        stream_id,
                        group_id,
                        index,
                        role,
                        redact_media_url(context["url"]),
                        context["name"],
                        context["extension"],
                        _safe_text(raw.get("mimeType"), 100),
                        context["size"],
                        raw.get("width") if isinstance(raw.get("width"), int) and raw.get("width") > 0 else None,
                        raw.get("height") if isinstance(raw.get("height"), int) and raw.get("height") > 0 else None,
                        _safe_text(raw.get("codec"), 100),
                        context["duration"],
                        context["language"],
                        context["label"],
                        now,
                    ),
                )

        with self._lock:
            self._remote_inputs[plan_id] = {"streams": contexts}
        self.schedule(plan_id)
        return {
            "id": plan_id,
            "groupId": group_id,
            "status": "queued",
            "progress": 0,
            "route": "desktop",
            "deleteAfterImport": delete_after_import,
            "outputName": output_name,
            "title": page_title or Path(output_name).stem,
            "thumbnailUrl": thumbnail_url,
        }

    @staticmethod
    def _safe_runtime_headers(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        allowed: dict[str, str] = {}
        for key, raw in value.items():
            name = str(key).lower()
            if name not in {"referer", "origin", "user-agent", "authorization", "cookie"} or not isinstance(raw, str):
                continue
            maximum = 16_384 if name == "cookie" else 8_192 if name == "authorization" else 4_096
            if "\r" in raw or "\n" in raw or len(raw) > maximum:
                continue
            allowed[name] = raw
        return allowed

    def schedule(self, plan_id: str) -> None:
        with self._lock:
            if plan_id in self._scheduled:
                return
            self._scheduled.add(plan_id)
        self.executor.submit(self._process_guarded, plan_id)

    def _process_guarded(self, plan_id: str) -> None:
        try:
            with self._lock:
                runtime = dict(self._remote_inputs.get(plan_id, {}))
            streams = runtime.get("streams") if isinstance(runtime.get("streams"), list) else []
            target_url = str(streams[0].get("url") or "") if streams else ""
            try:
                routes = self.network_proxy.routes_for(target_url)
            except ProxyConfigurationError as exc:
                raise MediaPlanError(f"网络代理设置无效：{exc}", "proxy_configuration_invalid") from exc
            failures: list[tuple[ProxyRoute, MediaPlanError]] = []
            for index, route in enumerate(routes):
                try:
                    self._process_remote(plan_id, route)
                    break
                except MediaPlanError as exc:
                    failures.append((route, exc))
                    can_switch = (
                        index + 1 < len(routes)
                        and exc.code in NETWORK_RETRYABLE_ERRORS
                        and exc.code != "canceled"
                    )
                    if not can_switch:
                        raise self._network_failure_with_guidance(
                            exc, target_url, failures
                        ) from exc
                    next_route = routes[index + 1]
                    self._prepare_network_route_retry(plan_id, route, next_route)
        except MediaPlanError as exc:
            if exc.code == "canceled":
                self._cancel(plan_id, str(exc))
            else:
                self._fail(plan_id, exc.code, str(exc))
        except Exception as exc:  # pragma: no cover - final safety net
            self._fail(plan_id, "media_processing_failed", f"媒体处理失败：{exc}")
        finally:
            with self.database.session() as connection:
                row = connection.execute(
                    "SELECT status FROM download_plans WHERE id = ?", (plan_id,)
                ).fetchone()
            status = str(row[0]) if row else ""
            reschedule = False
            with self._lock:
                self._scheduled.discard(plan_id)
                self._processes.pop(plan_id, None)
                self._stop_requested.discard(plan_id)
                reschedule = status == "queued" and plan_id in self._remote_inputs
                if status not in {"retry", "queued"}:
                    self._remote_inputs.pop(plan_id, None)
            if reschedule:
                self.schedule(plan_id)

    def _prepare_network_route_retry(
        self,
        plan_id: str,
        failed_route: ProxyRoute,
        next_route: ProxyRoute,
    ) -> None:
        now = time.time()
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'retry', progress = 2,
                    downloaded_bytes = 0,
                    phase_detail = ?, error_code = NULL, error_message = NULL,
                    updated_at = ?
                WHERE id = ? AND status IN ('downloading', 'merging', 'validating')
                """,
                (
                    f"{failed_route.label}连接失败，正在改用{next_route.label}（仅重试一次）",
                    now,
                    plan_id,
                ),
            )

    def _network_failure_with_guidance(
        self,
        error: MediaPlanError,
        target_url: str,
        failures: list[tuple[ProxyRoute, MediaPlanError]],
    ) -> MediaPlanError:
        if error.code not in NETWORK_RETRYABLE_ERRORS:
            return error
        raw = str(error)
        lower = raw.lower()
        looks_like_network_denial = any(
            marker in lower
            for marker in (
                "403",
                "forbidden",
                "timed out",
                "timeout",
                "network is unreachable",
                "connection refused",
                "connection reset",
                "server returned",
            )
        )
        if not looks_like_network_denial:
            return error
        status = self.network_proxy.status(target_url)
        if len(failures) > 1:
            suffix = "已自动尝试系统代理和直连，均未成功；请检查代理线路或改用手动代理。"
        elif status.get("mode") == "manual":
            suffix = "请确认手动代理地址、端口和代理软件运行状态。"
        elif status.get("mode") == "direct":
            suffix = "当前设置为始终直连；该网站需要代理时，请改为自动或手动代理。"
        elif not status.get("active"):
            suffix = "浏览器可能正在使用独立代理，但本机未检测到系统代理；请开启系统代理/TUN，或在网络设置中填写 HTTP/混合端口。"
        else:
            suffix = "系统代理连接未成功；请检查代理线路，或在网络设置中填写代理软件的 HTTP/混合端口。"
        return MediaPlanError(f"{raw}；{suffix}", error.code)

    def _process_remote(self, plan_id: str, proxy_route: ProxyRoute) -> None:
        with self._lock:
            runtime = dict(self._remote_inputs.get(plan_id, {}))
        contexts = [dict(item) for item in runtime.get("streams", [])]
        if not contexts:
            raise MediaPlanError(
                "下载地址上下文已失效，请回到来源网页重新创建任务",
                "download_context_expired",
            )
        for item in contexts:
            extension = str(item.get("extension") or "")
            size = item.get("size") if isinstance(item.get("size"), int) else None
            if extension not in MANIFEST_EXTENSIONS and _is_fixed_byte_range_url(
                str(item.get("url") or ""), size
            ):
                raise MediaPlanError(
                    "该任务只是固定字节分片，请回来源页选择完整视频或 HLS/DASH 清单",
                    "fixed_range_fragment",
                )
        is_manifest = any(
            str(item.get("extension") or "") in MANIFEST_EXTENSIONS for item in contexts
        )
        is_youtube_resolver = len(contexts) == 1 and contexts[0].get("resolver") == "youtube"
        is_page_resolver = len(contexts) == 1 and contexts[0].get("resolver") == "page"
        media_count = sum(
            1 for item in contexts if not str(item.get("role", "")).startswith("subtitle")
        )
        initial_detail = (
            "本机软件正在解析 YouTube 所选画质"
            if is_youtube_resolver
            else "本机软件正在识别当前内容页面的最佳媒体"
            if is_page_resolver
            else "本机软件正在解析并下载 HLS/DASH"
            if is_manifest
            else "本机软件正在下载并合并音视频"
            if media_count > 1
            else "本机软件正在下载直链媒体"
        )
        initial_detail += f"（{proxy_route.label}）"
        now = time.time()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE download_plans SET status = 'downloading', progress = 2,
                    downloaded_bytes = 0, phase_detail = ?,
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'retry')
                """,
                (initial_detail, now, plan_id),
            )
            if cursor.rowcount != 1:
                return
            row = connection.execute(
                """
                SELECT plan.*, groups.page_url, groups.title AS page_title
                FROM download_plans AS plan
                JOIN media_groups AS groups ON groups.id = plan.group_id
                WHERE plan.id = ?
                """,
                (plan_id,),
            ).fetchone()
        if row is None:
            raise MediaPlanError("下载方案不存在", "plan_unknown")
        plan = dict(row)
        station_root = self._default_station_root()
        plan_root = station_root / "临时" / plan_id
        completed_root = station_root / "已完成"
        preview_root = station_root / "预览"
        plan_root.mkdir(parents=True, exist_ok=True)
        completed_root.mkdir(parents=True, exist_ok=True)
        preview_root.mkdir(parents=True, exist_ok=True)
        work_path = plan_root / f"download-output.{plan['output_container']}"
        work_path.unlink(missing_ok=True)
        destination = self._unique_destination(completed_root / str(plan["output_name"]))
        media_contexts = [
            item for item in contexts if not str(item.get("role", "")).startswith("subtitle")
        ]
        subtitle_contexts = [
            item for item in contexts if str(item.get("role", "")).startswith("subtitle")
        ]
        if not media_contexts:
            raise MediaPlanError("下载方案缺少音视频内容", "plan_missing_media")
        preprocessed = False
        prepared_contexts: list[dict[str, Any]] = []
        for index, context in enumerate(media_contexts):
            if context.get("wechat_decode_key") is None:
                prepared_contexts.append(context)
                continue
            prepared_contexts.append(
                self._download_and_decrypt_wechat_stream(
                    plan_id,
                    context,
                    plan_root / f"wechat-decrypted-{index}.mp4",
                    proxy_route.url,
                )
            )
            preprocessed = True
        media_contexts = prepared_contexts
        if is_youtube_resolver:
            media_contexts = self._resolve_youtube_streams(
                plan_id, media_contexts[0], plan_root, proxy_route.url
            )
            self._set_status(
                plan_id,
                "downloading",
                3,
                f"YouTube 画质已解析，本机正在下载并合并音视频（{proxy_route.label}）",
            )
        elif is_page_resolver:
            media_contexts = self._resolve_page_streams(
                plan_id, media_contexts[0], plan_root, proxy_route.url
            )
            self._set_status(
                plan_id,
                "downloading",
                3,
                f"页面媒体已识别，本机正在下载并合并音视频（{proxy_route.label}）",
            )

        ffmpeg = resolve_media_tool("ffmpeg")
        command = [str(ffmpeg), "-hide_banner", "-y"]
        for context in media_contexts:
            command.extend(self._ffmpeg_input_arguments(context, proxy_route.url))
        video_index = next(
            (i for i, item in enumerate(media_contexts) if str(item.get("role", "")).startswith("video")),
            None,
        )
        audio_index = next(
            (i for i, item in enumerate(media_contexts) if str(item.get("role", "")).startswith("audio")),
            None,
        )
        if len(media_contexts) == 1:
            if is_manifest:
                video_stream, audio_stream = self._probe_manifest_stream_indexes(
                    media_contexts[0], proxy_route.url
                )
                if video_stream is not None:
                    command.extend(["-map", f"0:{video_stream}"])
                if audio_stream is not None:
                    command.extend(["-map", f"0:{audio_stream}"])
                if video_stream is None and audio_stream is None:
                    command.extend(["-map", "0:v:0?", "-map", "0:a:0?"])
            else:
                command.extend(["-map", "0:v:0?", "-map", "0:a:0?"])
        else:
            if video_index is not None:
                command.extend(["-map", f"{video_index}:v:0"])
            if audio_index is not None:
                command.extend(["-map", f"{audio_index}:a:0"])
            if video_index is None and audio_index is None:
                command.extend(["-map", "0:v:0?", "-map", "0:a:0?"])
        command.extend(["-c", "copy", "-progress", "pipe:1", "-nostats", str(work_path)])
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with self._lock:
            self._processes[plan_id] = process
            stop_now = plan_id in self._stop_requested
        if stop_now:
            self._request_process_stop(process)
        assert process.stdout is not None
        last_output = ""
        latest_bytes = 0
        latest_time_us = 0
        progress_floor = 62.0 if preprocessed else 2.0
        last_progress = progress_floor
        last_update = 0.0
        expected_bytes = int(plan.get("total_bytes") or 0)
        expected_duration = max(
            (float(item.get("duration") or 0) for item in media_contexts),
            default=0.0,
        )
        for line in process.stdout:
            stripped = line.strip()
            last_output = stripped or last_output
            key, _, value = stripped.partition("=")
            if key == "total_size":
                try:
                    latest_bytes = max(latest_bytes, int(value))
                except ValueError:
                    pass
            elif key in {"out_time_us", "out_time_ms"}:
                try:
                    latest_time_us = max(latest_time_us, int(value))
                except ValueError:
                    pass
            if key != "progress":
                continue
            ratios = []
            if expected_bytes > 0 and latest_bytes > 0:
                ratios.append(latest_bytes / expected_bytes)
            if expected_duration > 0 and latest_time_us > 0:
                ratios.append((latest_time_us / 1_000_000) / expected_duration)
            if ratios:
                next_progress = progress_floor + min(1.0, max(ratios)) * (78 - progress_floor)
            elif value == "continue":
                next_progress = min(72 if not preprocessed else 77, last_progress + 1)
            else:
                next_progress = last_progress
            timestamp = time.monotonic()
            if next_progress >= last_progress + 0.5 or timestamp - last_update >= 1:
                last_progress = max(last_progress, next_progress)
                last_update = timestamp
                self._set_progress(
                    plan_id,
                    min(78, last_progress),
                    downloaded_bytes=latest_bytes,
                    detail=self._download_detail(latest_bytes, expected_bytes),
                )
        process.wait()
        process.stdout.close()
        if process.stdin:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
        with self._lock:
            stopped = plan_id in self._stop_requested
        if stopped:
            work_path.unlink(missing_ok=True)
            raise MediaPlanError("任务已由用户停止", "canceled")
        if process.returncode != 0 or not work_path.is_file() or work_path.stat().st_size <= 0:
            work_path.unlink(missing_ok=True)
            raise MediaPlanError(
                "本机 FFmpeg 下载失败：" + _safe_text(last_output or "未知错误", 300),
                "desktop_download_failed",
            )

        self._set_status(plan_id, "validating", 82, "正在检查媒体完整性")
        probe = self._probe(
            work_path,
            require_video=any(str(item.get("role", "")).startswith("video") for item in media_contexts),
            require_audio=any(str(item.get("role", "")).startswith("audio") for item in media_contexts),
        )
        if not probe.get("streams"):
            raise MediaPlanError("下载结果没有可用媒体流", "output_no_streams")
        try:
            self._validate_output_duration(probe, media_contexts, is_manifest=is_manifest)
        except MediaPlanError:
            work_path.unlink(missing_ok=True)
            raise
        subtitle_files = self._download_subtitles(
            plan_id,
            subtitle_contexts,
            plan_root,
            destination,
            proxy_route.url,
        )
        os.replace(work_path, destination)
        completed_subtitles: list[Path] = []
        for temporary, target in subtitle_files:
            os.replace(temporary, target)
            completed_subtitles.append(target)
        preview_path = self._create_preview(destination, preview_root / f"{plan_id}.png")

        now = time.time()
        final_size = destination.stat().st_size
        if not bool(plan.get("import_to_eagle")):
            with self.database.session() as connection:
                connection.execute(
                    """
                    UPDATE download_plans SET status = 'completed_local', progress = 100,
                        downloaded_bytes = ?, total_bytes = COALESCE(total_bytes, ?),
                        phase_detail = '已下载到本机', final_path = ?, preview_path = ?,
                        error_code = NULL, error_message = NULL, completed_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        final_size,
                        final_size,
                        str(destination),
                        str(preview_path) if preview_path else None,
                        now,
                        now,
                        plan_id,
                    ),
                )
            self._remove_empty_plan_root(plan_root)
            return

        job_id = self.database.add_job(str(destination))
        if plan.get("page_url"):
            try:
                self.database.assign_source(
                    job_id, str(plan["page_url"]), str(plan.get("page_title") or "")
                )
            except (ValueError, PermissionError):
                pass
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'ready_to_import', progress = 90,
                    downloaded_bytes = ?, total_bytes = COALESCE(total_bytes, ?),
                    phase_detail = '等待 Eagle 导入', final_path = ?, preview_path = ?,
                    job_id = ?, error_code = NULL, error_message = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    final_size,
                    final_size,
                    str(destination),
                    str(preview_path) if preview_path else None,
                    job_id,
                    now,
                    plan_id,
                ),
            )
        self._remove_empty_plan_root(plan_root)
        if self.ready_callback:
            try:
                self.ready_callback()
            except Exception:
                pass

    @staticmethod
    def _download_detail(downloaded: int, total: int) -> str:
        def display(value: int) -> str:
            size = float(max(0, value))
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if size < 1024 or unit == "TB":
                    return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
                size /= 1024
            return f"{int(value)} B"

        if downloaded <= 0:
            return "本机软件正在建立媒体连接"
        if total > 0:
            return f"已下载 {display(downloaded)} / {display(total)}"
        return f"已处理 {display(downloaded)}"

    def _download_and_decrypt_wechat_stream(
        self,
        plan_id: str,
        context: dict[str, Any],
        target: Path,
        proxy_url: str | None = None,
    ) -> dict[str, Any]:
        key = context.get("wechat_decode_key")
        encrypted_bytes = context.get("wechat_encrypted_bytes")
        if not isinstance(key, int) or not isinstance(encrypted_bytes, int):
            raise MediaPlanError("视频号解密上下文无效", "wechat_decode_context_invalid")
        headers = {
            name.title(): str(value)
            for name, value in dict(context.get("headers") or {}).items()
        }
        request = Request(str(context.get("url") or ""), headers=headers)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
        opener = build_opener(ProxyHandler(proxies))
        target.unlink(missing_ok=True)
        try:
            response_context = opener.open(request, timeout=60)
            with response_context as response, target.open("wb") as output:
                content_length = response.headers.get("Content-Length", "")
                try:
                    expected = int(content_length) if content_length else int(context.get("size") or 0)
                except ValueError:
                    expected = int(context.get("size") or 0)
                decryptor = WechatVideoDecryptor(key, encrypted_bytes)
                downloaded = 0
                last_update = 0.0
                while chunk := response.read(256 * 1024):
                    with self._lock:
                        if plan_id in self._stop_requested:
                            raise MediaPlanError("任务已由用户停止", "canceled")
                    downloaded += len(chunk)
                    output.write(decryptor.transform(chunk))
                    now = time.monotonic()
                    if now - last_update >= 0.5:
                        ratio = min(1.0, downloaded / expected) if expected > 0 else 0.0
                        self._set_progress(
                            plan_id,
                            4 + ratio * 54 if ratio else min(55, 4 + downloaded / (8 * 1024 * 1024)),
                            downloaded_bytes=downloaded,
                            detail=(
                                f"视频号媒体已下载并解密 {self._download_detail(downloaded, expected).removeprefix('已下载 ')}"
                                if expected > 0
                                else f"视频号媒体{self._download_detail(downloaded, 0)}并解密"
                            ),
                        )
                        last_update = now
                if content_length and downloaded != int(content_length):
                    raise MediaPlanError("视频号媒体下载长度不完整", "wechat_download_incomplete")
        except MediaPlanError:
            target.unlink(missing_ok=True)
            raise
        except (HTTPError, URLError, OSError, ValueError) as exc:
            target.unlink(missing_ok=True)
            raise MediaPlanError(f"视频号媒体下载失败：{exc}", "wechat_download_failed") from exc
        if not target.is_file() or target.stat().st_size <= 0:
            target.unlink(missing_ok=True)
            raise MediaPlanError("视频号媒体下载结果为空", "wechat_download_failed")
        self._set_status(plan_id, "downloading", 60, "视频号媒体已下载并解密，正在校验封装")
        prepared = dict(context)
        prepared.update(
            {
                "url": str(target),
                "headers": {},
                "size": target.stat().st_size,
                "extension": "mp4",
                "wechat_decode_key": None,
                "wechat_encrypted_bytes": 0,
                "local_input": True,
            }
        )
        return prepared

    @staticmethod
    def _resolver_cookie_lines(cookie_header: str, hostname: str) -> list[str]:
        lines = ["# Netscape HTTP Cookie File"]
        host = hostname.strip(".").lower()
        if not re.fullmatch(r"[a-z0-9.-]+", host):
            return lines
        cookie_domain = "." + (host[4:] if host.startswith("www.") else host)
        for pair in cookie_header.split(";"):
            name, separator, value = pair.strip().partition("=")
            if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}", name):
                continue
            if not value or any(character in value for character in "\r\n\t\x00"):
                continue
            lines.append(f"{cookie_domain}\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
        return lines

    @staticmethod
    def _youtube_cookie_lines(cookie_header: str) -> list[str]:
        return MediaCoordinator._resolver_cookie_lines(cookie_header, "www.youtube.com")

    def _resolve_youtube_streams(
        self,
        plan_id: str,
        context: dict[str, Any],
        plan_root: Path,
        proxy_url: str | None = None,
    ) -> list[dict[str, Any]]:
        quality = str(context.get("preferred_quality") or "").lower()
        match = re.fullmatch(r"(\d{2,5})p", quality)
        if not match:
            raise MediaPlanError("YouTube 下载画质无效", "invalid_youtube_quality")
        height = int(match.group(1))
        if height < 100 or height > 10000:
            raise MediaPlanError("YouTube 下载画质超出范围", "invalid_youtube_quality")
        url = str(context.get("url") or "")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not re.fullmatch(
            r"(?:www\.)?youtube\.com", (parsed.hostname or "").lower()
        ):
            raise MediaPlanError("YouTube 来源页面无效", "invalid_youtube_url")

        yt_dlp = resolve_media_tool("yt-dlp")
        deno = resolve_media_tool("deno")
        plan_root.mkdir(parents=True, exist_ok=True)
        cookie_path = plan_root / "youtube-cookies.txt"
        cookie_header = str((context.get("headers") or {}).get("cookie") or "")
        command = [
            str(yt_dlp),
            "--ignore-config",
            "--no-playlist",
            "--no-cache-dir",
            "--quiet",
            "--no-warnings",
            "--js-runtimes",
            f"deno:{deno}",
            "--get-url",
            "--format",
            f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height={height}]+bestaudio/best[height={height}]",
        ]
        if proxy_url:
            command.extend(["--proxy", proxy_url])
        headers = context.get("headers") if isinstance(context.get("headers"), dict) else {}
        user_agent = _safe_text(headers.get("user-agent"), 500)
        referer = _safe_text(headers.get("referer"), 2048)
        if user_agent and "\r" not in user_agent and "\n" not in user_agent:
            command.extend(["--user-agent", user_agent])
        if referer and "\r" not in referer and "\n" not in referer:
            command.extend(["--referer", referer])
        if cookie_header:
            cookie_lines = self._youtube_cookie_lines(cookie_header)
            if len(cookie_lines) > 1:
                cookie_path.write_text("\r\n".join(cookie_lines) + "\r\n", encoding="utf-8", newline="")
                command.extend(["--cookies", str(cookie_path)])
        command.append(url)

        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                self._processes[plan_id] = process
                stop_now = plan_id in self._stop_requested
            if stop_now:
                process.terminate()
            stdout, stderr = process.communicate()
        finally:
            cookie_path.unlink(missing_ok=True)
            with self._lock:
                if process is not None and self._processes.get(plan_id) is process:
                    self._processes.pop(plan_id, None)

        with self._lock:
            stopped = plan_id in self._stop_requested
        if stopped:
            raise MediaPlanError("任务已由用户停止", "canceled")
        if process is None or process.returncode != 0:
            safe_error = re.sub(r"https?://\S+", "[媒体地址]", _safe_text(stderr, 500)).strip()
            raise MediaPlanError(
                "YouTube 画质解析失败：" + (safe_error or "请刷新视频页面后重试"),
                "youtube_resolve_failed",
            )
        resolved_urls = []
        for line in stdout.splitlines():
            candidate = line.strip()
            parsed_candidate = urlsplit(candidate)
            if parsed_candidate.scheme in {"http", "https"} and parsed_candidate.netloc:
                resolved_urls.append(candidate)
        if not 1 <= len(resolved_urls) <= 2:
            raise MediaPlanError("YouTube 没有返回所选画质的可下载媒体", "youtube_quality_unavailable")
        resolved: list[dict[str, Any]] = []
        for index, resolved_url in enumerate(resolved_urls):
            item = dict(context)
            item.update({
                "url": resolved_url,
                "resolver": "",
                "role": "video" if index == 0 else "audio",
                "extension": "mp4" if index == 0 else "m4a",
                "size": None,
                "label": quality if index == 0 else "自动最佳音轨",
            })
            resolved.append(item)
        return resolved

    def _resolve_page_streams(
        self,
        plan_id: str,
        context: dict[str, Any],
        plan_root: Path,
        proxy_url: str | None = None,
    ) -> list[dict[str, Any]]:
        url = canonical_page_resolver_url(context.get("url"))
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise MediaPlanError("内容页面地址无效", "invalid_page_resolver_url")

        yt_dlp = resolve_media_tool("yt-dlp")
        deno = resolve_media_tool("deno")
        plan_root.mkdir(parents=True, exist_ok=True)
        cookie_path = plan_root / "page-resolver-cookies.txt"
        headers = context.get("headers") if isinstance(context.get("headers"), dict) else {}
        cookie_header = str(headers.get("cookie") or "")
        command = [
            str(yt_dlp),
            "--ignore-config",
            "--no-playlist",
            "--no-cache-dir",
            "--quiet",
            "--no-warnings",
            "--js-runtimes",
            f"deno:{deno}",
            "--get-url",
            "--format",
            (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[ext=mp4]+bestaudio[ext=mp4]/"
                "best[ext=mp4]/"
                "bestvideo[ext=mp4]+bestaudio/"
                "bestvideo+bestaudio/"
                "best"
            ),
        ]
        if proxy_url:
            command.extend(["--proxy", proxy_url])
        user_agent = _safe_text(headers.get("user-agent"), 500)
        referer = _safe_text(headers.get("referer"), 2048)
        if user_agent and "\r" not in user_agent and "\n" not in user_agent:
            command.extend(["--user-agent", user_agent])
        if referer and "\r" not in referer and "\n" not in referer:
            command.extend(["--referer", referer])
        if cookie_header:
            cookie_lines = self._resolver_cookie_lines(cookie_header, hostname)
            if len(cookie_lines) > 1:
                cookie_path.write_text("\r\n".join(cookie_lines) + "\r\n", encoding="utf-8", newline="")
                command.extend(["--cookies", str(cookie_path)])
        command.append(url)

        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                self._processes[plan_id] = process
                stop_now = plan_id in self._stop_requested
            if stop_now:
                process.terminate()
            stdout, stderr = process.communicate()
        finally:
            cookie_path.unlink(missing_ok=True)
            with self._lock:
                if process is not None and self._processes.get(plan_id) is process:
                    self._processes.pop(plan_id, None)

        with self._lock:
            stopped = plan_id in self._stop_requested
        if stopped:
            raise MediaPlanError("任务已由用户停止", "canceled")
        if process is None or process.returncode != 0:
            raw_error = _safe_text(stderr, 500).strip()
            if hostname == "douyin.com" or hostname.endswith(".douyin.com"):
                if "Unsupported URL" in raw_error:
                    raise MediaPlanError(
                        "抖音内容页不是受支持的视频详情地址，请刷新当前视频后重试",
                        "douyin_page_unsupported",
                    )
                if "Fresh cookies" in raw_error or "cookies" in raw_error.lower():
                    raise MediaPlanError(
                        "抖音需要当前浏览器的新鲜会话，请刷新抖音页面后重试",
                        "douyin_session_expired",
                    )
            safe_error = re.sub(r"https?://\S+", "[媒体地址]", raw_error).strip()
            raise MediaPlanError(
                "页面媒体解析失败：" + (safe_error or "请刷新内容页面后重试"),
                "page_resolve_failed",
            )
        resolved_urls = []
        for line in stdout.splitlines():
            candidate = line.strip()
            parsed_candidate = urlsplit(candidate)
            if parsed_candidate.scheme in {"http", "https"} and parsed_candidate.netloc:
                resolved_urls.append(candidate)
        if not 1 <= len(resolved_urls) <= 2:
            raise MediaPlanError("当前页面没有返回可下载的完整媒体", "page_media_unavailable")
        resolved: list[dict[str, Any]] = []
        for index, resolved_url in enumerate(resolved_urls):
            item = dict(context)
            item.update({
                "url": resolved_url,
                "resolver": "",
                "role": "video" if index == 0 else "audio",
                "extension": "mp4" if index == 0 else "m4a",
                "size": None,
                "label": "最佳可用视频" if index == 0 else "最佳可用音轨",
            })
            resolved.append(item)
        return resolved

    @staticmethod
    def _ffmpeg_input_arguments(
        context: dict[str, Any], proxy_url: str | None = None
    ) -> list[str]:
        url = str(context.get("url") or "")
        headers = context.get("headers") if isinstance(context.get("headers"), dict) else {}
        arguments: list[str] = []
        if proxy_url and not context.get("local_input"):
            arguments.extend(["-http_proxy", proxy_url])
        user_agent = headers.get("user-agent")
        if user_agent:
            arguments.extend(["-user_agent", str(user_agent)])
        header_text = "".join(
            f"{name.title()}: {headers[name]}\r\n"
            for name in ("referer", "origin", "authorization", "cookie")
            if headers.get(name)
        )
        if header_text:
            arguments.extend(["-headers", header_text])
        arguments.extend(["-i", url])
        return arguments

    @staticmethod
    def _select_manifest_stream_indexes(
        probe: dict[str, Any], preferred_height: int | None
    ) -> tuple[int | None, int | None]:
        choices: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        programs = probe.get("programs") if isinstance(probe, dict) else None
        for program in programs if isinstance(programs, list) else []:
            streams = program.get("streams") if isinstance(program, dict) else None
            if not isinstance(streams, list):
                continue
            videos = [
                stream for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "video"
                and isinstance(stream.get("index"), int)
            ]
            audios = [
                stream for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "audio"
                and isinstance(stream.get("index"), int)
            ]
            if not videos:
                continue
            video = max(
                videos,
                key=lambda stream: (
                    int(stream.get("height") or 0),
                    int(stream.get("width") or 0),
                    int(stream.get("bit_rate") or 0),
                ),
            )
            audio = max(audios, key=lambda stream: int(stream.get("bit_rate") or 0), default=None)
            choices.append((video, audio))

        if not choices:
            streams = probe.get("streams") if isinstance(probe, dict) else None
            streams = streams if isinstance(streams, list) else []
            videos = [
                stream for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "video"
                and isinstance(stream.get("index"), int)
            ]
            audios = [
                stream for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "audio"
                and isinstance(stream.get("index"), int)
            ]
            if videos:
                for video in videos:
                    choices.append((video, audios[0] if audios else None))

        if not choices:
            return None, None

        if preferred_height:
            selected = min(
                choices,
                key=lambda choice: (
                    abs(int(choice[0].get("height") or 0) - preferred_height),
                    int(choice[0].get("height") or 0) > preferred_height,
                    -int(choice[0].get("height") or 0),
                    -int(choice[0].get("bit_rate") or 0),
                ),
            )
        else:
            selected = max(
                choices,
                key=lambda choice: (
                    int(choice[0].get("height") or 0),
                    int(choice[0].get("width") or 0),
                    int(choice[0].get("bit_rate") or 0),
                ),
            )
        video_index = selected[0].get("index")
        audio_index = selected[1].get("index") if selected[1] else None
        return (
            video_index if isinstance(video_index, int) else None,
            audio_index if isinstance(audio_index, int) else None,
        )

    def _probe_manifest_stream_indexes(
        self, context: dict[str, Any], proxy_url: str | None = None
    ) -> tuple[int | None, int | None]:
        preferred_match = re.fullmatch(
            r"(\d{2,5})p", str(context.get("preferred_quality") or "").lower()
        )
        preferred_height = int(preferred_match.group(1)) if preferred_match else None
        command = [
            str(resolve_media_tool("ffprobe")),
            "-v", "error",
            "-show_programs",
            "-show_streams",
            "-of", "json",
            *self._ffmpeg_input_arguments(context, proxy_url),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            payload = json.loads(completed.stdout or "{}")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None, None
        return self._select_manifest_stream_indexes(payload, preferred_height)

    def _download_subtitles(
        self,
        plan_id: str,
        contexts: list[dict[str, Any]],
        plan_root: Path,
        media_destination: Path,
        proxy_url: str | None = None,
    ) -> list[tuple[Path, Path]]:
        results: list[tuple[Path, Path]] = []
        for index, context in enumerate(contexts, start=1):
            extension = _safe_extension(context.get("extension"), "vtt")
            if extension not in SUBTITLE_EXTENSIONS:
                extension = "vtt"
            descriptor = _safe_text(
                context.get("language") or context.get("label") or f"subtitle-{index}",
                60,
            )
            descriptor = re.sub(
                r"[^\w\-\u4e00-\u9fff]+", "-", descriptor, flags=re.UNICODE
            ).strip("-_") or f"subtitle-{index}"
            temporary = plan_root / f"subtitle-{index}.{extension}"
            target = self._unique_destination(
                media_destination.parent
                / f"{media_destination.stem}.{descriptor}.{extension}"
            )
            self._download_direct_subtitle(plan_id, context, temporary, proxy_url)
            results.append((temporary, target))
        return results

    def _download_direct_subtitle(
        self,
        plan_id: str,
        context: dict[str, Any],
        target: Path,
        proxy_url: str | None = None,
    ) -> None:
        headers = {
            name.title(): str(value)
            for name, value in dict(context.get("headers") or {}).items()
        }
        request = Request(str(context.get("url") or ""), headers=headers)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
        opener = build_opener(ProxyHandler(proxies))
        try:
            response_context = opener.open(request, timeout=60)
            with response_context as response, target.open("wb") as output:
                total = 0
                while chunk := response.read(256 * 1024):
                    with self._lock:
                        if plan_id in self._stop_requested:
                            raise MediaPlanError("任务已由用户停止", "canceled")
                    total += len(chunk)
                    if total > 50 * 1024 * 1024:
                        raise MediaPlanError("字幕文件超过 50 MB，已停止处理", "subtitle_too_large")
                    output.write(chunk)
        except MediaPlanError:
            target.unlink(missing_ok=True)
            raise
        except (HTTPError, URLError, OSError) as exc:
            target.unlink(missing_ok=True)
            raise MediaPlanError(f"字幕下载失败：{exc}", "subtitle_download_failed") from exc
        if not target.is_file() or target.stat().st_size <= 0:
            target.unlink(missing_ok=True)
            raise MediaPlanError("字幕下载结果为空", "subtitle_download_failed")

    def _create_preview(self, media_path: Path, target: Path) -> Path | None:
        target.unlink(missing_ok=True)
        try:
            ffmpeg = resolve_media_tool("ffmpeg")
            result = subprocess.run(
                [
                    str(ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    "0.1",
                    "-i",
                    str(media_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=240:-2",
                    str(target),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (MediaPlanError, OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0 and target.is_file() and target.stat().st_size > 0:
            return target
        target.unlink(missing_ok=True)
        return None

    @staticmethod
    def _default_station_root() -> Path:
        return download_station_root()

    def retry_plan(self, plan_id: str) -> dict[str, Any]:
        plan_id = _safe_text(plan_id, 80)
        with self._lock:
            has_context = plan_id in self._remote_inputs
        if not has_context:
            raise MediaPlanError(
                "下载地址上下文已失效，请回到来源网页重新创建任务",
                "download_context_expired",
            )
        now = time.time()
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                UPDATE download_plans SET status = 'queued', progress = 0,
                    downloaded_bytes = 0, phase_detail = '等待本机重试',
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE id = ? AND status = 'retry'
                """,
                (now, plan_id),
            )
        if cursor.rowcount != 1:
            raise MediaPlanError("当前任务不需要重试", "plan_not_retryable")
        self.schedule(plan_id)
        return self.get_plan(plan_id)

    def stop_plan(self, plan_id: str) -> dict[str, Any]:
        plan_id = _safe_text(plan_id, 80)
        with self._lock:
            self._stop_requested.add(plan_id)
            process = self._processes.get(plan_id)
        if process:
            self._request_process_stop(process)
        now = time.time()
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'canceled', progress = 0,
                    error_code = 'canceled', error_message = '任务已由用户停止',
                    phase_detail = '已停止', updated_at = ?
                WHERE id = ? AND status IN ('queued', 'downloading', 'merging', 'validating', 'retry')
                """,
                (now, plan_id),
            )
        return self.get_plan(plan_id)

    def _probe(self, path: Path, require_video: bool, require_audio: bool) -> dict[str, Any]:
        ffprobe = resolve_media_tool("ffprobe")
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0:
            raise MediaPlanError("ffprobe 无法读取媒体输出", "ffprobe_failed")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaPlanError("ffprobe 返回无效结果", "ffprobe_invalid") from exc
        streams = payload.get("streams") if isinstance(payload, dict) else None
        if not isinstance(streams, list) or not streams:
            raise MediaPlanError("媒体文件没有可用音视频流", "output_no_streams")
        kinds = {
            str(stream.get("codec_type"))
            for stream in streams
            if isinstance(stream, dict)
        }
        if require_video and "video" not in kinds:
            raise MediaPlanError("下载结果缺少所选视频流", "output_no_video")
        if require_audio and "audio" not in kinds:
            raise MediaPlanError("下载结果缺少所选音频流", "output_no_audio")
        return payload

    @staticmethod
    def _validate_output_duration(
        probe: dict[str, Any],
        media_contexts: list[dict[str, Any]],
        *,
        is_manifest: bool,
    ) -> None:
        """Reject a direct URL whose output cannot be the selected media identity."""
        if is_manifest:
            return
        expected_values = [
            float(item.get("duration") or 0)
            for item in media_contexts
            if float(item.get("duration") or 0) > 0
        ]
        expected = max(expected_values, default=0.0)
        if expected < 5:
            return
        actual_values: list[float] = []
        format_data = probe.get("format")
        if isinstance(format_data, dict):
            try:
                actual_values.append(float(format_data.get("duration") or 0))
            except (TypeError, ValueError):
                pass
        streams = probe.get("streams")
        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                try:
                    actual_values.append(float(stream.get("duration") or 0))
                except (TypeError, ValueError):
                    continue
        actual = max((value for value in actual_values if value > 0), default=0.0)
        if actual <= 0:
            return
        tolerance = max(3.0, expected * 0.08)
        if abs(actual - expected) <= tolerance:
            return
        raise MediaPlanError(
            f"下载结果时长 {actual:.1f} 秒与所选内容 {expected:.1f} 秒不一致，已阻止导入，请刷新页面后重新选择",
            "output_duration_mismatch",
        )

    def _set_progress(
        self,
        plan_id: str,
        progress: float,
        downloaded_bytes: int | None = None,
        detail: str | None = None,
    ) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET progress = ?,
                    downloaded_bytes = COALESCE(?, downloaded_bytes),
                    phase_detail = COALESCE(?, phase_detail), updated_at = ?
                WHERE id = ? AND status = 'downloading'
                """,
                (
                    max(0.0, min(100.0, progress)),
                    downloaded_bytes,
                    _safe_text(detail, 220) if detail is not None else None,
                    time.time(),
                    plan_id,
                ),
            )

    def _set_status(self, plan_id: str, status: str, progress: float, detail: str) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = ?, progress = ?,
                    phase_detail = ?, updated_at = ? WHERE id = ?
                """,
                (status, max(0.0, min(100.0, progress)), _safe_text(detail, 220), time.time(), plan_id),
            )

    def _fail(self, plan_id: str, code: str, message: str) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'retry', error_code = ?,
                    error_message = ?, phase_detail = '下载失败，可在本次运行中重试',
                    updated_at = ? WHERE id = ? AND status != 'canceled'
                """,
                (_safe_text(code, 80), _safe_text(message, 500), time.time(), plan_id),
            )

    def _cancel(self, plan_id: str, message: str) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE download_plans SET status = 'canceled', progress = 0,
                    error_code = 'canceled', error_message = ?, phase_detail = '已停止',
                    updated_at = ? WHERE id = ?
                """,
                (_safe_text(message, 500), time.time(), plan_id),
            )

    @staticmethod
    def _unique_destination(path: Path) -> Path:
        if not path.exists():
            return path
        for index in range(1, 10_000):
            candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
            if not candidate.exists():
                return candidate
        raise MediaPlanError("输出目录中同名文件过多", "output_name_exhausted")

    @staticmethod
    def _remove_empty_plan_root(plan_root: Path) -> None:
        try:
            plan_root.rmdir()
        except OSError:
            pass

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT plan.*, groups.title, groups.page_url, groups.thumbnail_url,
                       groups.media_kind, jobs.status AS job_status,
                       jobs.error_message AS job_error
                FROM download_plans AS plan
                JOIN media_groups AS groups ON groups.id = plan.group_id
                LEFT JOIN jobs ON jobs.id = plan.job_id
                WHERE plan.id = ?
                """,
                (plan_id,),
            ).fetchone()
            if row is None:
                raise MediaPlanError("下载方案不存在", "plan_unknown")
        data = dict(row)
        if data.get("job_status") == "imported" and data.get("status") != "imported":
            now = time.time()
            with self.database.session() as connection:
                connection.execute(
                    """
                    UPDATE download_plans SET status = 'imported', progress = 100,
                        phase_detail = '已导入 Eagle', error_code = NULL,
                        error_message = NULL, completed_at = COALESCE(completed_at, ?),
                        updated_at = ? WHERE id = ?
                    """,
                    (now, now, plan_id),
                )
            data.update(
                {
                    "status": "imported",
                    "progress": 100,
                    "phase_detail": "已导入 Eagle",
                    "error_code": None,
                    "error_message": None,
                }
            )
        return data

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.session() as connection:
            now = time.time()
            connection.execute(
                """
                UPDATE download_plans SET status = 'imported', progress = 100,
                    phase_detail = '已导入 Eagle', error_code = NULL,
                    error_message = NULL,
                    completed_at = COALESCE(
                        completed_at,
                        (SELECT jobs.completed_at FROM jobs WHERE jobs.id = download_plans.job_id),
                        ?
                    ), updated_at = ?
                WHERE status != 'imported'
                  AND job_id IN (SELECT id FROM jobs WHERE status = 'imported')
                """,
                (now, now),
            )
            rows = connection.execute(
                """
                SELECT plan.id, plan.output_name, plan.output_container, plan.route,
                       plan.import_to_eagle, plan.delete_after_import,
                       plan.status, plan.progress, plan.downloaded_bytes,
                       plan.total_bytes, plan.phase_detail, plan.final_path,
                       plan.preview_path, plan.error_code, plan.error_message,
                       plan.created_at, plan.updated_at, plan.completed_at,
                       groups.title, groups.page_url, groups.thumbnail_url,
                       groups.media_kind, jobs.status AS job_status,
                       jobs.error_message AS job_error
                FROM download_plans AS plan
                JOIN media_groups AS groups ON groups.id = plan.group_id
                LEFT JOIN jobs ON jobs.id = plan.job_id
                ORDER BY plan.created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_terminal_history(self) -> int:
        """Forget terminal plan records without deleting any output or preview files."""
        statuses = tuple(TERMINAL_MEDIA_PLAN_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        with self.database.transaction() as connection:
            rows = connection.execute(
                f"SELECT id FROM download_plans WHERE status IN ({placeholders})",
                statuses,
            ).fetchall()
            plan_ids = [str(row["id"]) for row in rows]
            if plan_ids:
                id_placeholders = ",".join("?" for _ in plan_ids)
                connection.execute(
                    f"DELETE FROM download_plans WHERE id IN ({id_placeholders})",
                    plan_ids,
                )
        if not plan_ids:
            return 0
        with self._lock:
            for plan_id in plan_ids:
                self._remote_inputs.pop(plan_id, None)
                self._scheduled.discard(plan_id)
                self._stop_requested.discard(plan_id)
        return len(plan_ids)

    def _owned_plan_file(self, plan_id: str, field: str, directory: str) -> Path:
        plan = self.get_plan(_safe_text(plan_id, 80))
        raw_path = plan.get(field)
        if not isinstance(raw_path, str) or not raw_path:
            if field == "preview_path":
                raise MediaPlanError("任务还没有可用的视频预览", "preview_unavailable")
            raise MediaPlanError("任务尚未生成可打开的下载文件", "output_unavailable")
        try:
            candidate = Path(raw_path).resolve(strict=True)
            owned_root = (self._default_station_root() / directory).resolve(strict=True)
        except OSError as exc:
            raise MediaPlanError("任务文件不存在或已经不可用", "plan_file_missing") from exc
        if not candidate.is_file() or not candidate.is_relative_to(owned_root):
            label = "预览目录" if field == "preview_path" else "下载目录"
            raise MediaPlanError(f"任务文件不属于本程序的{label}", "plan_file_not_owned")
        return candidate

    def get_plan_preview(self, plan_id: str) -> dict[str, Any]:
        preview = self._owned_plan_file(plan_id, "preview_path", "预览")
        size = preview.stat().st_size
        if size <= 8 or size > 2 * 1024 * 1024:
            raise MediaPlanError("视频预览文件无效或过大", "preview_invalid")
        data = preview.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise MediaPlanError("视频预览格式无效", "preview_invalid")
        encoded = base64.b64encode(data).decode("ascii")
        return {
            "dataUrl": f"data:image/png;base64,{encoded}",
            "mimeType": "image/png",
            "fileName": preview.name,
        }

    def open_plan_output(self, plan_id: str) -> dict[str, Any]:
        output = self._owned_plan_file(plan_id, "final_path", "已完成")
        startfile = getattr(os, "startfile", None)
        if not callable(startfile):
            raise MediaPlanError("当前系统无法打开文件夹", "open_folder_unavailable")
        startfile(str(output.parent))
        return {"opened": True, "fileName": output.name}

    def import_completed_plan(self, plan_id: str) -> dict[str, Any]:
        """Queue a program-owned download-only result for Eagle without downloading again."""
        plan_id = _safe_text(plan_id, 80)
        plan = self.get_plan(plan_id)
        if plan.get("job_id") and plan.get("status") in {"ready_to_import", "imported"}:
            return plan
        if plan.get("status") != "completed_local":
            raise MediaPlanError("只有已下载到本机的任务可以直接导入 Eagle", "plan_not_importable")

        output = self._owned_plan_file(plan_id, "final_path", "已完成")
        job_id = self.database.add_job(str(output))
        if plan.get("page_url"):
            try:
                self.database.assign_source(
                    job_id,
                    str(plan["page_url"]),
                    str(plan.get("title") or ""),
                )
            except (ValueError, PermissionError):
                pass
        now = time.time()
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                UPDATE download_plans SET import_to_eagle = 1,
                    delete_after_import = 1,
                    status = 'ready_to_import', progress = 90,
                    phase_detail = '等待 Eagle 导入', job_id = ?,
                    error_code = NULL, error_message = NULL,
                    completed_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'completed_local' AND job_id IS NULL
                """,
                (job_id, now, plan_id),
            )
        if cursor.rowcount != 1:
            latest = self.get_plan(plan_id)
            if latest.get("job_id"):
                return latest
            raise MediaPlanError("任务状态已变化，请刷新后重试", "plan_state_changed")
        if self.ready_callback:
            try:
                self.ready_callback()
            except Exception:
                pass
        return self.get_plan(plan_id)

    def health(self) -> dict[str, Any]:
        if self._health_cache and time.time() - self._health_cache[0] < 60:
            cached = dict(self._health_cache[1])
            cached["networkProxy"] = self.network_proxy.status()
            return cached
        with self.database.session() as connection:
            schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        result: dict[str, Any] = {
            "databaseSchema": schema,
            "downloadEngine": "desktop_ffmpeg",
        }
        commands = {
            "ffmpeg": ["-version"],
            "ffprobe": ["-version"],
            "yt-dlp": ["--version"],
            "deno": ["--version"],
        }
        for name, arguments in commands.items():
            try:
                tool = resolve_media_tool(name)
                version = subprocess.run(
                    [str(tool), *arguments],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
                result[name] = {
                    "ok": version.returncode == 0,
                    "path": str(tool),
                    "version": version.stdout.splitlines()[0] if version.stdout else "",
                }
            except (MediaPlanError, OSError, subprocess.SubprocessError) as exc:
                result[name] = {"ok": False, "error": str(exc)}
        result["ok"] = bool(result["ffmpeg"].get("ok") and result["ffprobe"].get("ok"))
        result["youtubeResolver"] = bool(result["yt-dlp"].get("ok") and result["deno"].get("ok"))
        result["networkProxy"] = self.network_proxy.status()
        cached = dict(result)
        cached.pop("networkProxy", None)
        self._health_cache = (time.time(), cached)
        return result
