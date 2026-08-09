from __future__ import annotations

import hashlib
import ipaddress
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .media import MediaCoordinator, MediaPlanError, resolve_media_tool
from .paths import ensure_data_dir
from .wechat_channels_certificate import WechatCertificateAuthority
from .wechat_channels_proxy import (
    ProxySnapshot,
    RegistryValue,
    WechatLoopbackProxy,
    WinInetProxyLease,
    parse_proxy_server,
    proxy_endpoint_is_loopback,
    proxy_endpoint_reachable,
    upstream_auto_proxy_resolver,
    upstream_http_proxy,
    upstream_proxy_bypass,
)


class WechatChannelsError(RuntimeError):
    pass


def cleanup_wechat_capture(root: str | Path | None = None) -> dict[str, bool]:
    capture_root = Path(root) if root else ensure_data_dir() / "wechat-channels"
    lease = WinInetProxyLease(capture_root / "proxy-lease.json")
    had_lease = lease.path.exists()
    proxy_restored = lease.recover_orphan() if had_lease else False
    if had_lease and lease.path.exists():
        # The current proxy is no longer provably ours — someone else changed it.
        # Delete the stale lease and continue cleanup.
        try:
            lease.path.unlink()
        except FileNotFoundError:
            pass
    certificate = WechatCertificateAuthority(capture_root / "certificate")
    certificate_removed = certificate.uninstall()
    certificate_root = capture_root / "certificate"
    for name in (
        "certificate.json",
        "root.cer",
        "root.pem",
        "root.key",
        "channels.pem",
        "channels.key",
    ):
        try:
            (certificate_root / name).unlink()
        except FileNotFoundError:
            pass
    for directory in (certificate_root, capture_root):
        try:
            directory.rmdir()
        except (FileNotFoundError, OSError):
            pass
    return {
        "proxyRestored": proxy_restored,
        "certificateRemoved": certificate_removed,
    }


def _text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _number(value: Any, maximum: int = 2**63 - 1) -> int:
    try:
        result = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0
    return result if 0 <= result <= maximum else 0


def _public_https_url(value: Any) -> str:
    raw = _text(value, 16_384)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    host = parsed.hostname.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"}:
        return ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        if not all(part and len(part) <= 63 for part in host.split(".")):
            return ""
    return raw


def _wechat_original_url(value: Any) -> str:
    raw = _public_https_url(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    selected: list[str] = []
    for required_name in ("encfilekey", "token"):
        argument = ""
        for item in parts.query.split("&"):
            name, separator, encoded_value = item.partition("=")
            if separator and encoded_value and name.lower() == required_name:
                argument = item
                break
        if not argument:
            return ""
        selected.append(argument)
    original = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "&".join(selected), "")
    )
    return _public_https_url(original)


def _public_image_url(value: Any) -> str:
    raw = _text(value, 16_384)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    host = parsed.hostname.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"}:
        return ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        if not all(part and len(part) <= 63 for part in host.split(".")):
            return ""
    return raw


def _source_https_url(value: Any) -> str:
    raw = _public_https_url(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    safe_query = urlencode([
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() in {"objectid", "object_id", "oid", "nid", "eid"}
        and len(item) <= 256
    ])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))


def _runtime_headers(
    values: dict[str, str] | None, media_url: str
) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    result: dict[str, str] = {}
    media_host = (urlsplit(media_url).hostname or "").lower()
    referer_host = ""
    for name, value in values.items():
        lowered = str(name).lower()
        text = str(value or "")
        if "\r" in text or "\n" in text:
            continue
        if lowered == "referer":
            referer_host = (urlsplit(text).hostname or "").lower()
        if lowered in {"user-agent", "referer", "origin", "accept-language"}:
            result["-".join(part.capitalize() for part in lowered.split("-"))] = text[:4096]
    cookie = next(
        (str(value or "") for name, value in values.items() if str(name).lower() == "cookie"),
        "",
    )
    if cookie and media_host and "\r" not in cookie and "\n" not in cookie:
        # 微信媒体 CDN 依赖登录态（Cookie）返回完整清晰度；捕获来源与媒体
        # 主机属于同一微信域时附带 Cookie，避免无关站点的 Cookie 跨域泄露。
        if referer_host == media_host or _same_tencent_origin(referer_host, media_host):
            result["Cookie"] = cookie[:16_384]
    return result


def _same_tencent_origin(referer_host: str, media_host: str) -> bool:
    if not referer_host or not media_host:
        return False
    for base in (".qq.com", ".weixin.qq.com", ".wx.qq.com"):
        if referer_host.endswith(base) and media_host.endswith(base):
            return True
    return False


class _PublicImageRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        if not _public_image_url(new_url):
            raise WechatChannelsError("封面重定向到了不安全地址")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


@dataclass
class WechatMediaVariant:
    variant_id: str
    url: str
    decode_key: int | None
    width: int
    height: int
    duration_ms: int
    file_size: int
    media_type: int
    delivery_spec: str = ""
    original: bool = False
    format: str = "mp4"
    bitrate: int = 0
    headers: dict[str, str] = field(default_factory=dict)

    def view(self) -> dict[str, Any]:
        dimensions = [value for value in (self.width, self.height) if value]
        quality_edge = min(dimensions) if len(dimensions) == 2 else (dimensions[0] if dimensions else 0)
        quality = f"{quality_edge}p" if quality_edge else "自动质量"
        if self.original:
            quality += " · 原始视频"
        elif self.delivery_spec:
            quality += f" · {self.delivery_spec}"
        else:
            quality += " · 自动质量"
        return {
            "id": self.variant_id,
            "quality": quality,
            "width": self.width,
            "height": self.height,
            "durationMs": self.duration_ms,
            "fileSize": self.file_size,
            "format": self.format,
            "deliverySpec": self.delivery_spec,
            "isOriginal": self.original,
            "bitrate": self.bitrate,
            "encrypted": self.decode_key is not None,
        }


@dataclass
class WechatCandidate:
    object_id: str
    title: str
    author: str
    author_id: str
    cover_url: str
    source_url: str
    duration_ms: int
    created_at: int
    variants: dict[str, WechatMediaVariant]
    first_seen: float
    updated_at: float

    def view(self) -> dict[str, Any]:
        variants = sorted(
            (item.view() for item in self.variants.values()),
            key=lambda item: (item["height"], item["bitrate"], item["fileSize"]),
            reverse=True,
        )
        return {
            "groupKey": f"wechat-channel:{self.object_id}",
            "objectId": self.object_id,
            "title": self.title or "微信视频号视频",
            "author": self.author,
            "authorId": self.author_id,
            "coverUrl": self.cover_url,
            "sourceUrl": self.source_url,
            "durationMs": self.duration_ms,
            "createdAt": self.created_at,
            "variants": variants,
            "updatedAt": self.updated_at,
            "outputName": f"{self.author + ' - ' if self.author else ''}{self.title or self.object_id}.mp4",
        }


class WechatCandidateRegistry:
    MAX_CANDIDATES = 500

    def __init__(self) -> None:
        self._items: dict[str, WechatCandidate] = {}
        self._current_object_id = ""
        self._active_version = 0
        self._lock = threading.RLock()

    def ingest(
        self,
        payload: dict[str, Any],
        request_headers: dict[str, str] | None = None,
        *,
        make_current: bool = True,
    ) -> WechatCandidate:
        object_id = _text(payload.get("objectId"), 128)
        if not object_id or not all(character.isalnum() or character in "_-" for character in object_id):
            raise WechatChannelsError("视频号内容身份无效")
        raw_media = payload.get("media")
        if not isinstance(raw_media, list) or not raw_media or len(raw_media) > 32:
            raise WechatChannelsError("视频号候选没有有效媒体")
        variants: dict[str, WechatMediaVariant] = {}
        cover_url = ""
        duration_ms = 0
        for raw in raw_media:
            if not isinstance(raw, dict):
                continue
            base_url = _public_https_url(raw.get("url"))
            if not base_url:
                continue
            token = _text(raw.get("urlToken"), 8_192)
            url = base_url + token
            if not _public_https_url(url):
                continue
            raw_key = _text(raw.get("decodeKey"), 32)
            try:
                decode_key = int(raw_key, 0) if raw_key and int(raw_key, 0) != 0 else None
            except ValueError as exc:
                raise WechatChannelsError("视频号候选包含无效解密键") from exc
            if decode_key is not None and not 0 <= decode_key < 2**64:
                raise WechatChannelsError("视频号候选包含无效解密键")
            width = _number(raw.get("width"), 16_384)
            height = _number(raw.get("height"), 16_384)
            item_duration = _number(raw.get("durationMs"), 24 * 60 * 60 * 1000)
            file_size = _number(raw.get("fileSize"), 2**63 - 1)
            bitrate = 0
            specs = raw.get("specs")
            if isinstance(specs, list):
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    if not height:
                        height = _number(spec.get("height"), 16_384)
                    if not width:
                        width = _number(spec.get("width"), 16_384)
                    bitrate = max(bitrate, _number(spec.get("bitrate"), 1_000_000_000))
            parsed_media = urlsplit(base_url)
            media_type = _number(raw.get("mediaType"), 100)

            def add_variant(
                variant_url: str,
                variant_width: int,
                variant_height: int,
                variant_duration: int,
                variant_bitrate: int,
                delivery_spec: str = "",
                variant_file_size: int = 0,
                original: bool = False,
            ) -> None:
                identity = (
                    f"{object_id}\0{parsed_media.hostname}\0{parsed_media.path}\0"
                    f"{variant_width}x{variant_height}\0{media_type}\0{delivery_spec}"
                )
                variant_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
                variants[variant_id] = WechatMediaVariant(
                    variant_id=variant_id,
                    url=variant_url,
                    decode_key=decode_key,
                    width=variant_width,
                    height=variant_height,
                    duration_ms=variant_duration,
                    file_size=variant_file_size,
                    media_type=media_type,
                    delivery_spec=delivery_spec,
                    original=original,
                    bitrate=variant_bitrate,
                    headers=_runtime_headers(request_headers, variant_url),
                )

            original_url = _wechat_original_url(url)
            add_variant(
                original_url or url,
                width,
                height,
                item_duration,
                bitrate,
                variant_file_size=file_size,
                original=bool(original_url),
            )
            if isinstance(specs, list):
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    delivery_spec = _text(spec.get("fileFormat"), 64)
                    if not delivery_spec:
                        continue
                    spec_width = _number(spec.get("width"), 16_384) or width
                    spec_height = _number(spec.get("height"), 16_384) or height
                    spec_duration = _number(
                        spec.get("durationMs"), 24 * 60 * 60 * 1000
                    ) or item_duration
                    spec_bitrate = _number(spec.get("bitrate"), 1_000_000_000)
                    parts = urlsplit(url)
                    # Keep the captured signed query byte-for-byte. Re-encoding an
                    # existing CDN token can invalidate it, so only append our
                    # bounded quality selector.
                    selector = urlencode({"X-snsvideoflag": delivery_spec})
                    query = f"{parts.query}&{selector}" if parts.query else selector
                    spec_url = urlunsplit(
                        (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
                    )
                    add_variant(
                        spec_url,
                        spec_width,
                        spec_height,
                        spec_duration,
                        spec_bitrate,
                        delivery_spec,
                        0,
                    )
            cover_url = cover_url or _public_image_url(raw.get("coverUrl"))
            duration_ms = max(duration_ms, item_duration)
        if not variants:
            raise WechatChannelsError("视频号候选没有可用的 HTTPS 媒体")
        now = time.time()
        with self._lock:
            existing = self._items.get(object_id)
            if existing:
                existing.title = _text(payload.get("title"), 500) or existing.title
                existing.author = _text(payload.get("author"), 160) or existing.author
                existing.author_id = _text(payload.get("authorId"), 160) or existing.author_id
                existing.cover_url = cover_url or existing.cover_url
                existing.source_url = _source_https_url(payload.get("sourceUrl")) or existing.source_url
                existing.duration_ms = duration_ms or existing.duration_ms
                existing.created_at = _number(payload.get("createdAt")) or existing.created_at
                existing.variants.update(variants)
                existing.updated_at = now
                if make_current:
                    self._current_object_id = object_id
                return existing
            if len(self._items) >= self.MAX_CANDIDATES:
                removable = [
                    item
                    for item in self._items.values()
                    if item.object_id != self._current_object_id
                ] or list(self._items.values())
                oldest = min(removable, key=lambda item: item.updated_at)
                self._items.pop(oldest.object_id, None)
                if oldest.object_id == self._current_object_id:
                    self._current_object_id = ""
            candidate = WechatCandidate(
                object_id=object_id,
                title=_text(payload.get("title"), 500),
                author=_text(payload.get("author"), 160),
                author_id=_text(payload.get("authorId"), 160),
                cover_url=cover_url,
                source_url=_source_https_url(payload.get("sourceUrl")),
                duration_ms=duration_ms,
                created_at=_number(payload.get("createdAt")),
                variants=variants,
                first_seen=now,
                updated_at=now,
            )
            self._items[object_id] = candidate
            if make_current:
                self._current_object_id = object_id
            return candidate

    def activate(
        self,
        object_id: str,
        version: int = 0,
    ) -> tuple[dict[str, Any] | None, bool]:
        with self._lock:
            candidate = self._items.get(object_id)
            if not candidate:
                return None, False
            if version and version < self._active_version:
                current = self._items.get(self._current_object_id)
                return (current.view() if current else None), False
            self._current_object_id = object_id
            self._active_version = max(self._active_version, version)
            return candidate.view(), True

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._items.values(),
                key=lambda item: (
                    item.object_id != self._current_object_id,
                    -item.updated_at,
                ),
            )
            return [item.view() for item in ordered]

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def retained_count(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._current_object_id = ""
            self._active_version = 0

    def preview_request(self, object_id: str) -> tuple[str, dict[str, str]]:
        with self._lock:
            candidate = self._items.get(object_id)
            if not candidate or not candidate.cover_url:
                return "", {}
            variant = next(iter(candidate.variants.values()), None)
            headers = _runtime_headers(variant.headers if variant else {}, candidate.cover_url)
            return candidate.cover_url, headers

    def plan_payload(
        self,
        object_id: str,
        variant_id: str = "",
        *,
        import_to_eagle: bool = True,
        delete_after_import: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            candidate = self._items.get(object_id)
            if not candidate:
                raise WechatChannelsError("视频号候选已过期，请重新打开内容")
            if variant_id:
                variant = candidate.variants.get(variant_id)
                if variant is None:
                    raise WechatChannelsError("视频号质量已过期，请重新打开内容")
            else:
                variant = max(
                    candidate.variants.values(),
                    key=lambda item: (item.width * item.height, item.bitrate, item.file_size),
                )
            output_name = f"{candidate.author + ' - ' if candidate.author else ''}{candidate.title or candidate.object_id}.mp4"
            return {
                "sourceType": "wechat_channels",
                "groupKey": f"wechat-channel:{candidate.object_id}",
                "pageTitle": candidate.title or "微信视频号视频",
                "pageUrl": candidate.source_url,
                "thumbnailUrl": candidate.cover_url,
                "outputName": output_name,
                "outputContainer": "mp4",
                "mergeMode": "direct",
                "importToEagle": import_to_eagle,
                "deleteAfterImport": delete_after_import and import_to_eagle,
                "runtimeHeaders": [dict(variant.headers)],
                "streams": [{
                    "id": variant.variant_id,
                    "role": "video",
                    "url": variant.url,
                    "mime": "video/mp4",
                    "mimeType": "video/mp4",
                    "extension": "mp4",
                    "width": variant.width,
                    "height": variant.height,
                    "size": variant.file_size,
                    "duration": variant.duration_ms / 1000 if variant.duration_ms else 0,
                    "headers": dict(variant.headers),
                    "wechatDecodeKey": str(variant.decode_key) if variant.decode_key is not None else "",
                    "wechatEncryptedBytes": 131_072 if variant.decode_key is not None else 0,
                }],
            }


class WechatChannelsCaptureService:
    def __init__(
        self,
        media: MediaCoordinator,
        root: str | Path | None = None,
        proxy_factory: Callable[..., WechatLoopbackProxy] = WechatLoopbackProxy,
        eagle_available: Callable[[], bool] | None = None,
    ) -> None:
        self.media = media
        self.root = Path(root) if root else ensure_data_dir() / "wechat-channels"
        self.certificate = WechatCertificateAuthority(self.root / "certificate")
        self.proxy_lease = WinInetProxyLease(self.root / "proxy-lease.json")
        self.proxy_factory = proxy_factory
        # Eagle is optional.  Missing or broken capability providers must fail
        # closed to a local download, never turn an ordinary download click
        # into an unavailable import operation.
        self.eagle_available = eagle_available or (lambda: False)
        self.registry = WechatCandidateRegistry()
        self.proxy: WechatLoopbackProxy | None = None
        self.state = "off"
        self.error = ""
        self.last_event = ""
        self.error_code = ""
        self.rejected_count = 0
        self.internal_api_observed = 0
        self._certificate_trusted = False
        self._system_proxy_configured = False
        self._preview_cache: dict[str, bytes] = {}
        self._preview_order: list[str] = []
        self._PREVIEW_CACHE_MAX = 50
        self._preview_failures: set[str] = set()
        self._static_health_cache: tuple[float, dict[str, str]] | None = None
        self._lock = threading.RLock()
        orphaned = self.proxy_lease.path.exists()
        restored = self.proxy_lease.recover_orphan()
        if orphaned and restored:
            self.last_event = "已恢复上次异常退出前的系统代理"
        elif orphaned and self.proxy_lease.path.exists():
            # Stale lease that can't be recovered — proxy was changed externally.
            # Delete it so it doesn't block future captures.
            try:
                self.proxy_lease.path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def bridge_script_path() -> Path:
        return Path(__file__).resolve().parent / "assets" / "wechat_channels_bridge.js"

    def start(self, *, configure_system_proxy: bool = True, trust_certificate: bool = True) -> dict[str, Any]:
        with self._lock:
            if self.proxy:
                return self.health()
            if self.state == "needs_recovery":
                restored = (
                    self.proxy_lease.release()
                    if self.proxy_lease.snapshot is not None
                    else self.proxy_lease.recover_orphan()
                )
                if not restored:
                    current = self.proxy_lease.backend.snapshot()
                    enabled = current.values.get("ProxyEnable", RegistryValue(False))
                    if enabled.exists and int(enabled.value or 0) == 1:
                        raise WechatChannelsError(
                            self.error or "系统代理已由其他程序修改，请先恢复后再开始捕获"
                        )
                    # 系统代理已被外部禁用，没有需要保护的活跃代理，允许重新捕获
                self.state = "off"
                self.error = ""
                self.error_code = ""
                self.error = ""
                self.error_code = ""
            self.state = "preparing"
            self.error = ""
            self.error_code = ""
            self.rejected_count = 0
            self.internal_api_observed = 0
            proxy: WechatLoopbackProxy | None = None
            upstream_resolver = None
            try:
                files = self.certificate.ensure()
                certificate_trusted = self.certificate.is_trusted(files.fingerprint)
                if trust_certificate and not certificate_trusted:
                    files = self.certificate.install()
                    certificate_trusted = self.certificate.is_trusted(files.fingerprint)
                self._static_health_cache = None
                self._certificate_trusted = certificate_trusted
                bridge_script = self.bridge_script_path().read_bytes()
                snapshot = self.proxy_lease.backend.snapshot()
                upstream_resolver = upstream_auto_proxy_resolver(snapshot)
                upstream_proxy = upstream_http_proxy(snapshot)
                if (
                    upstream_resolver is None
                    and proxy_endpoint_is_loopback(upstream_proxy)
                    and not proxy_endpoint_reachable(upstream_proxy)
                ):
                    endpoint = f"{upstream_proxy[0]}:{upstream_proxy[1]}"
                    raise WechatChannelsError(
                        f"检测到已失效的本机代理 {endpoint}，请先点击“修复代理冲突”"
                    )
                if upstream_resolver:
                    # Resolve before replacing WinINET so an invalid/unavailable PAC
                    # cannot silently strand WeChat behind the capture proxy.
                    upstream_resolver.resolve("https://channels.weixin.qq.com/")
                proxy = self.proxy_factory(
                    files,
                    bridge_script,
                    self._handle_page_message,
                    upstream_proxy=upstream_proxy,
                    upstream_bypass=upstream_proxy_bypass(snapshot),
                    upstream_resolver=upstream_resolver,
                )
                upstream_resolver = None
                proxy.start()
                endpoint = f"{proxy.address[0]}:{proxy.address[1]}"
                if configure_system_proxy:
                    self.proxy_lease.acquire(endpoint)
                    self._system_proxy_configured = True
                self.proxy = proxy
                self.state = "waiting_wechat"
                self.last_event = "捕获已开启，请在微信中打开视频号内容"
            except Exception as exc:
                configured = (
                    self._system_proxy_configured
                    or self.proxy_lease.snapshot is not None
                    or self.proxy_lease.path.exists()
                )
                restored = False
                restore_error = ""
                if configured:
                    try:
                        restored = (
                            self.proxy_lease.release()
                            if self.proxy_lease.snapshot is not None
                            else self.proxy_lease.recover_orphan()
                        )
                    except Exception as restore_exc:
                        restore_error = str(restore_exc) or "原系统代理暂未恢复"
                if proxy:
                    proxy.stop()
                elif upstream_resolver:
                    upstream_resolver.close()
                self.proxy = None
                self._system_proxy_configured = False
                recovery_pending = configured and not restored
                self.state = "needs_recovery" if recovery_pending else "failed"
                self.error_code = (
                    "proxy_restore_pending" if recovery_pending else "capture_start_failed"
                )
                self.error = (
                    restore_error or "原系统代理未恢复；恢复记录已保留"
                    if recovery_pending
                    else str(exc) or "视频号捕获启动失败"
                )
                raise WechatChannelsError(self.error) from exc
            return self.health()

    def repair_proxy_conflict(self) -> dict[str, Any]:
        with self._lock:
            backend = self.proxy_lease.backend
            if self.proxy:
                local_endpoint = f"{self.proxy.address[0]}:{self.proxy.address[1]}"
                current = backend.snapshot()
                resolver = upstream_auto_proxy_resolver(current)
                upstream = upstream_http_proxy(current)
                removed_dead_proxy = (
                    resolver is None
                    and proxy_endpoint_is_loopback(upstream)
                    and not proxy_endpoint_reachable(upstream)
                )
                if removed_dead_proxy:
                    backend.disable_manual_proxy()
                    current = backend.snapshot()
                    upstream = None
                if resolver:
                    try:
                        resolver.resolve("https://channels.weixin.qq.com/")
                    except Exception:
                        resolver.close()
                        raise
                bypass = upstream_proxy_bypass(current)
                replace_upstream = getattr(self.proxy, "replace_upstream", None)
                if callable(replace_upstream):
                    replace_upstream(upstream, bypass, resolver)
                else:
                    self.proxy.upstream_proxy = upstream
                    self.proxy.upstream_bypass = bypass
                    self.proxy.upstream_resolver = resolver
                changed = self.proxy_lease.reacquire(local_endpoint)
                self._system_proxy_configured = True
                self.error = ""
                self.error_code = ""
                self.last_event = (
                    "已清除失效代理并重新接管视频号流量"
                    if removed_dead_proxy
                    else (
                        "已重新接管视频号流量；停止捕获后会恢复原代理"
                        if changed
                        else "视频号捕获代理工作正常"
                    )
                )
                return {
                    "changed": changed or removed_dead_proxy,
                    "running": True,
                    "message": self.last_event,
                }

            if self.proxy_lease.path.exists() and self.proxy_lease.recover_orphan():
                self.state = "off"
                self.error = ""
                self.error_code = ""
                self.last_event = "已恢复上次捕获前的系统代理"
                return {
                    "changed": True,
                    "running": False,
                    "message": self.last_event,
                }

            current = backend.snapshot()
            upstream = upstream_http_proxy(current)
            if not upstream:
                enabled = current.values.get("ProxyEnable", RegistryValue(False))
                server = current.values.get("ProxyServer", RegistryValue(False))
                stale_disabled = (
                    enabled.exists
                    and int(enabled.value or 0) == 0
                    and server.exists
                    and str(server.value or "").strip()
                )
                if stale_disabled:
                    stale_endpoint = parse_proxy_server(str(server.value))
                    if (
                        stale_endpoint
                        and proxy_endpoint_is_loopback(stale_endpoint)
                        and not proxy_endpoint_reachable(stale_endpoint)
                    ):
                        cleanup = ProxySnapshot(dict(current.values))
                        cleanup.values["ProxyEnable"] = RegistryValue(True, 0, 4)
                        cleanup.values["ProxyServer"] = RegistryValue(False)
                        backend.restore(cleanup)
                        self.state = "off"
                        self.error = ""
                        self.error_code = ""
                        self.last_event = (
                            f"已清除残留的本机代理 {stale_endpoint[0]}:{stale_endpoint[1]}，"
                            "现在可以开始捕获"
                        )
                        return {
                            "changed": True,
                            "running": False,
                            "message": self.last_event,
                        }
                self.last_event = "未发现需要修复的系统代理"
                return {
                    "changed": False,
                    "running": False,
                    "message": self.last_event,
                }
            if not proxy_endpoint_is_loopback(upstream):
                self.last_event = "检测到正常的网络代理，开始捕获时会自动兼容"
                return {
                    "changed": False,
                    "running": False,
                    "message": self.last_event,
                }
            if proxy_endpoint_reachable(upstream):
                self.last_event = "检测到正在运行的本机代理，开始捕获时会自动接入"
                return {
                    "changed": False,
                    "running": False,
                    "message": self.last_event,
                }

            backend.disable_manual_proxy()
            self.state = "off"
            self.error = ""
            self.error_code = ""
            self.last_event = (
                f"已清除失效的本机代理 {upstream[0]}:{upstream[1]}，现在可以开始捕获"
            )
            return {
                "changed": True,
                "running": False,
                "message": self.last_event,
            }

    def stop(self) -> dict[str, Any]:
        with self._lock:
            proxy = self.proxy
            self.proxy = None
            configured = (
                self._system_proxy_configured
                or self.proxy_lease.snapshot is not None
                or self.proxy_lease.path.exists()
            )
            restored = False
            restore_error = ""
            if configured:
                try:
                    restored = (
                        self.proxy_lease.release()
                        if self.proxy_lease.snapshot is not None
                        else self.proxy_lease.recover_orphan()
                    )
                except Exception as exc:
                    restore_error = str(exc) or "原系统代理暂未恢复"
            if proxy:
                proxy.stop()
            self._system_proxy_configured = False
            self.registry.clear()
            self._preview_cache.clear()
            self._preview_order.clear()
            self._preview_failures.clear()
            self.state = "needs_recovery" if configured and not restored else "off"
            self.error_code = "" if restored or not configured else "proxy_restore_skipped"
            self.error = (
                ""
                if restored or not configured
                else restore_error or "系统代理已被其他程序修改，未覆盖当前设置"
            )
            self.last_event = (
                "视频号捕获已停止，但代理需要人工恢复"
                if configured and not restored
                else "视频号捕获已停止"
            )
            return self.health()

    def close(self) -> None:
        self.stop()

    def _handle_page_message(
        self, payload: dict[str, Any], request_headers: dict[str, str]
    ) -> dict[str, Any]:
        action = _text(payload.get("action"), 32)
        if action == "candidate":
            make_current = payload.get("current") is True
            candidate = self.registry.ingest(
                payload,
                request_headers,
                make_current=make_current,
            )
            self._preview_cache.pop(candidate.object_id, None)
            if candidate.object_id in self._preview_order:
                self._preview_order.remove(candidate.object_id)
            self._preview_failures.discard(candidate.object_id)
            if make_current:
                self.last_event = f"当前视频：{candidate.title or candidate.object_id}"
            else:
                self.last_event = f"已识别视频号内容：{candidate.title or candidate.object_id}"
            self.state = "capturing"
            return {"action": "candidate", "candidate": candidate.view()}
        if action == "active":
            object_id = _text(payload.get("objectId"), 128)
            version = _number(payload.get("version"), 10**16)
            candidate, activated = self.registry.activate(object_id, version)
            if not candidate:
                raise WechatChannelsError("当前视频媒体信息尚未就绪")
            if activated:
                self.last_event = f"当前视频：{candidate.get('title') or object_id}"
                self.state = "capturing"
            return {
                "action": "active",
                "accepted": activated,
                "candidate": candidate,
            }
        if action == "download":
            object_id = _text(payload.get("objectId"), 128)
            variant_id = _text(payload.get("variantId"), 128)
            if not object_id or not variant_id:
                raise WechatChannelsError("视频号页面下载请求缺少内容或质量身份")
            try:
                import_to_eagle = bool(self.eagle_available())
            except Exception:
                import_to_eagle = False
            plan = self.submit(
                object_id,
                variant_id,
                import_to_eagle=import_to_eagle,
                # The injected page control is labelled only "下载". Keep the
                # local copy even when Eagle is available; deletion requires
                # the explicitly labelled desktop action.
                delete_after_import=False,
            )
            return {
                "action": "download",
                "plan": {
                    "id": str(plan.get("id") or ""),
                    "status": str(plan.get("status") or ""),
                    "title": str(plan.get("title") or plan.get("output_name") or ""),
                    "delivery": "eagle" if import_to_eagle else "local",
                },
            }
        if action == "diagnostic":
            count = _number(payload.get("count"), 1000)
            reason = _text(payload.get("reason"), 64)
            if reason == "internal_api_observed":
                self.internal_api_observed = min(1_000_000, self.internal_api_observed + count)
                self.last_event = "已接收微信内部媒体数据，正在识别内容"
                return {"action": "diagnostic"}
            self.rejected_count = min(1_000_000, self.rejected_count + count)
            self.last_event = f"已忽略 {self.rejected_count} 条缺少内容身份的媒体数据"
            return {"action": "diagnostic"}
        raise WechatChannelsError("视频号页面请求类型无效")

    def submit(
        self,
        object_id: str,
        variant_id: str = "",
        *,
        import_to_eagle: bool = True,
        delete_after_import: bool = False,
    ) -> dict[str, Any]:
        payload = self.registry.plan_payload(
            object_id,
            variant_id,
            import_to_eagle=import_to_eagle,
            delete_after_import=delete_after_import,
        )
        plan = self.media.create_plan(payload)
        self.last_event = f"任务已创建：{payload['pageTitle']}"
        return plan

    def preview_png(self, object_id: str) -> bytes:
        with self._lock:
            if object_id in self._preview_cache:
                return self._preview_cache[object_id]
            if object_id in self._preview_failures:
                return b""
        url, headers = self.registry.preview_request(object_id)
        if not url:
            return b""
        try:
            request = Request(url, headers=headers)
            with build_opener(_PublicImageRedirectHandler()).open(request, timeout=15) as response:
                if not _public_image_url(response.geturl()):
                    raise WechatChannelsError("封面响应地址不安全")
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if content_type and "image" not in content_type and "octet-stream" not in content_type:
                    raise WechatChannelsError("封面响应不是图片")
                source = response.read(6 * 1024 * 1024 + 1)
            if not source or len(source) > 6 * 1024 * 1024:
                raise WechatChannelsError("封面文件过大或为空")
            ffmpeg = resolve_media_tool("ffmpeg")
            with tempfile.TemporaryDirectory(prefix="download-station-wechat-preview-") as directory:
                root = Path(directory)
                input_path = root / "source-image"
                output_path = root / "preview.png"
                input_path.write_bytes(source)
                result = subprocess.run(
                    [
                        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(input_path), "-vf",
                        "scale=320:180:force_original_aspect_ratio=decrease",
                        "-frames:v", "1", str(output_path),
                    ],
                    capture_output=True,
                    timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
                if result.returncode != 0 or not output_path.exists():
                    raise WechatChannelsError("封面转换失败")
                preview = output_path.read_bytes()
            if len(preview) > 2 * 1024 * 1024:
                raise WechatChannelsError("封面预览过大")
        except (OSError, HTTPError, URLError, subprocess.SubprocessError, MediaPlanError, WechatChannelsError):
            with self._lock:
                self._preview_failures.add(object_id)
            return b""
        with self._lock:
            while len(self._preview_cache) >= self._PREVIEW_CACHE_MAX:
                oldest = self._preview_order.pop(0)
                self._preview_cache.pop(oldest, None)
            self._preview_cache[object_id] = preview
            self._preview_order.append(object_id)
        return preview

    def candidates(self) -> list[dict[str, Any]]:
        return self.registry.list()

    def clear_candidates(self) -> int:
        """Clear the current candidate view while leaving capture state unchanged."""
        with self._lock:
            count = len(self.registry.list())
            self.registry.clear()
            self._preview_cache.clear()
            self._preview_order.clear()
            self._preview_failures.clear()
            self.last_event = f"已清除 {count} 条视频候选" if count else "候选列表已经为空"
            return count

    def health(self) -> dict[str, Any]:
        proxy = self.proxy
        proxy_diagnostics = (
            proxy.diagnostics()
            if proxy and callable(getattr(proxy, "diagnostics", None))
            else {
                "resourceScriptsSeen": 0,
                "resourceScriptsInstrumented": 0,
                "finderHooksInstalled": 0,
            }
        )
        static_identity = self._static_health_identity()
        return {
            "state": self.state,
            "running": bool(proxy),
            "endpoint": f"{proxy.address[0]}:{proxy.address[1]}" if proxy else "",
            "certificateTrusted": self._certificate_trusted,
            "candidateCount": self.registry.count(),
            "rejectedCount": self.rejected_count,
            "internalApiObserved": self.internal_api_observed,
            "proxyDiagnostics": proxy_diagnostics,
            **static_identity,
            "lastEvent": self.last_event,
            "errorCode": self.error_code,
            "error": self.error,
        }

    def _static_health_identity(self) -> dict[str, str]:
        now = time.monotonic()
        with self._lock:
            if self._static_health_cache:
                return dict(self._static_health_cache[1])
            existing_certificate = self.certificate.existing()
            try:
                bridge_hash = hashlib.sha256(
                    self.bridge_script_path().read_bytes()
                ).hexdigest()[:16]
            except OSError:
                bridge_hash = ""
            identity = {
                "certificateId": (
                    existing_certificate.fingerprint[-8:]
                    if existing_certificate
                    else ""
                ),
                "bridgeHash": bridge_hash,
            }
            self._static_health_cache = (now, identity)
            return dict(identity)
