from __future__ import annotations

import ipaddress
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import request
from urllib.parse import urlsplit, urlunsplit

from .database import Database


PROXY_MODES = frozenset({"auto", "direct", "manual"})
PROXY_MODE_KEY = "network_proxy_mode"
PROXY_URL_KEY = "network_proxy_url"
SUPPORTED_PROXY_SCHEMES = frozenset({"http"})


class ProxyConfigurationError(ValueError):
    """Raised when a user supplied proxy cannot be used safely."""


@dataclass(frozen=True)
class ProxyRoute:
    url: str | None
    source: str
    mode: str
    label: str

    @property
    def enabled(self) -> bool:
        return bool(self.url)


def normalize_proxy_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ProxyConfigurationError("请输入代理地址，例如 127.0.0.1:7890")
    if any(character in raw for character in "\r\n\t\x00"):
        raise ProxyConfigurationError("代理地址包含无效字符")
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ProxyConfigurationError("代理地址或端口无效") from exc
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        raise ProxyConfigurationError("请使用代理软件的 HTTP 或混合端口")
    if not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise ProxyConfigurationError("代理地址必须包含有效的主机和端口")
    if parsed.username is not None or parsed.password is not None:
        raise ProxyConfigurationError("当前版本不保存带账号密码的代理地址")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ProxyConfigurationError("代理地址只需要填写主机和端口")
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
            raise ProxyConfigurationError("代理主机名无效")
        display_host = host.lower()
    else:
        display_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return urlunsplit((scheme, f"{display_host}:{port}", "", "", ""))


def proxy_endpoint_label(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.port is None:
            return ""
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        return f"{host}:{parsed.port}"
    except ValueError:
        return ""


def _environment_proxies() -> dict[str, str]:
    try:
        values = request.getproxies_environment()
    except (AttributeError, OSError):
        return {}
    return {str(key).lower(): str(value) for key, value in values.items() if value}


def _windows_proxies() -> dict[str, str]:
    if os.name != "nt":
        return {}
    try:
        values = request.getproxies_registry()
    except (AttributeError, OSError):
        return {}
    return {str(key).lower(): str(value) for key, value in values.items() if value}


def _is_local_target(target_url: str) -> bool:
    try:
        host = (urlsplit(target_url).hostname or "").strip("[]").lower()
    except ValueError:
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _is_tencent_cdn_host(host: str) -> bool:
    """腾讯媒体 CDN（微信视频号等）经代理/VPN 中转会降级清晰度，需直连。"""
    if not host:
        return False
    lowered = host.strip("[]").lower()
    for base in (".qq.com", ".weixin.qq.com", ".wx.qq.com"):
        if lowered == base[1:] or lowered.endswith(base):
            return True
    return False


def _proxy_for_target(
    target_url: str,
    proxies: Mapping[str, str],
) -> str | None:
    try:
        parsed = urlsplit(target_url)
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    raw = proxies.get(scheme) or proxies.get("https") or proxies.get("http") or proxies.get("all")
    if not raw:
        return None
    try:
        return normalize_proxy_url(raw)
    except ProxyConfigurationError:
        return None


class NetworkProxyManager:
    """Resolve one safe, task-scoped proxy route without touching local APIs."""

    _STATUS_CACHE_SECONDS = 30.0

    def __init__(self, database: Database) -> None:
        self.database = database
        self._status_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._status_cache_lock = threading.Lock()

    def configuration(self) -> dict[str, str]:
        values = self.database.get_settings((PROXY_MODE_KEY, PROXY_URL_KEY))
        mode = str(values.get(PROXY_MODE_KEY) or "auto").lower()
        if mode not in PROXY_MODES:
            mode = "auto"
        manual = str(values.get(PROXY_URL_KEY) or "")
        return {"mode": mode, "manualUrl": manual}

    def configure(self, mode: str, manual_url: Any = "") -> dict[str, str]:
        selected = str(mode or "").lower()
        if selected not in PROXY_MODES:
            raise ProxyConfigurationError("代理模式无效")
        normalized = str(manual_url or "").strip()
        if selected == "manual":
            normalized = normalize_proxy_url(manual_url)
        elif normalized:
            try:
                # Preserve a previously entered valid endpoint for later use,
                # but never block switching back to automatic/direct mode.
                normalized = normalize_proxy_url(normalized)
            except ProxyConfigurationError:
                normalized = ""
        self.database.set_settings(
            {PROXY_MODE_KEY: selected, PROXY_URL_KEY: normalized}
        )
        with self._status_cache_lock:
            self._status_cache.clear()
        return self.configuration()

    def _detected_system_route(self, target_url: str) -> ProxyRoute | None:
        if _is_local_target(target_url):
            return None
        hostname = (urlsplit(target_url).hostname or "").strip("[]").lower()
        if _is_tencent_cdn_host(hostname):
            # 腾讯媒体 CDN 经代理/VPN 中转会降级清晰度，始终直连。
            return None
        try:
            if request.proxy_bypass(hostname):
                return None
        except (OSError, ValueError):
            pass
        for source, proxies in (
            ("windows", _windows_proxies()),
            ("environment", _environment_proxies()),
        ):
            selected = _proxy_for_target(target_url, proxies)
            if selected:
                endpoint = proxy_endpoint_label(selected)
                label = f"系统代理 {endpoint}" if source == "windows" else f"环境代理 {endpoint}"
                return ProxyRoute(selected, source, "auto", label)
        return None

    def routes_for(self, target_url: str) -> list[ProxyRoute]:
        configuration = self.configuration()
        mode = configuration["mode"]
        direct = ProxyRoute(None, "direct", mode, "直连")
        if mode == "direct" or _is_local_target(target_url):
            return [direct]
        if mode == "manual":
            proxy_url = normalize_proxy_url(configuration["manualUrl"])
            endpoint = proxy_endpoint_label(proxy_url)
            return [ProxyRoute(proxy_url, "manual", mode, f"手动代理 {endpoint}")]
        detected = self._detected_system_route(target_url)
        # Automatic mode follows the same system proxy as Chrome. A single
        # direct fallback keeps temporary proxy failures from stranding tasks.
        return [detected, direct] if detected else [direct]

    def status(self, target_url: str = "https://www.behance.net/") -> dict[str, Any]:
        now = time.monotonic()
        with self._status_cache_lock:
            cached = self._status_cache.get(target_url)
            if cached and now - cached[0] < self._STATUS_CACHE_SECONDS:
                return dict(cached[1])
        status = self._uncached_status(target_url)
        with self._status_cache_lock:
            self._status_cache[target_url] = (now, status)
        return dict(status)

    def _uncached_status(self, target_url: str) -> dict[str, Any]:
        configuration = self.configuration()
        mode = configuration["mode"]
        if mode == "manual":
            try:
                proxy_url = normalize_proxy_url(configuration["manualUrl"])
            except ProxyConfigurationError as exc:
                return {
                    "mode": mode,
                    "active": False,
                    "source": "manual",
                    "endpoint": "",
                    "summary": f"手动代理无效：{exc}",
                }
            endpoint = proxy_endpoint_label(proxy_url)
            return {
                "mode": mode,
                "active": True,
                "source": "manual",
                "endpoint": endpoint,
                "summary": f"手动代理 {endpoint}",
            }
        if mode == "direct":
            return {
                "mode": mode,
                "active": False,
                "source": "direct",
                "endpoint": "",
                "summary": "始终直连",
            }
        detected = self._detected_system_route(target_url)
        if not detected:
            return {
                "mode": mode,
                "active": False,
                "source": "none",
                "endpoint": "",
                "summary": "自动（当前未检测到系统代理）",
            }
        return {
            "mode": mode,
            "active": True,
            "source": detected.source,
            "endpoint": proxy_endpoint_label(detected.url),
            "summary": f"自动（{detected.label}）",
        }
