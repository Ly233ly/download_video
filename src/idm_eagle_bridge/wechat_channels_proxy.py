from __future__ import annotations

import ctypes
import base64
import fnmatch
import ipaddress
import json
import os
import re
import select
import socket
import socketserver
import ssl
import threading
import time
import uuid
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .wechat_channels_certificate import CertificateFiles


MAX_HEADER_BYTES = 64 * 1024
MAX_CONTROL_BODY = 512 * 1024
MAX_BUFFERED_RESPONSE = 16 * 1024 * 1024
MAX_CONNECTIONS = 32
CAPTURE_PATH = "/__download_station_wechat__"
INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
INTERNET_CONNECTIONS = INTERNET_SETTINGS + r"\Connections"
PROXY_VALUE_NAMES = (
    "ProxyEnable",
    "ProxyServer",
    "ProxyOverride",
    "AutoConfigURL",
    "AutoDetect",
    "Connections/DefaultConnectionSettings",
    "Connections/SavedLegacySettings",
)


class CaptureProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegistryValue:
    exists: bool
    value: Any = None
    kind: int = 0


@dataclass(frozen=True)
class ProxySnapshot:
    values: dict[str, RegistryValue]

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in self.values.items():
            item = asdict(value)
            if isinstance(value.value, bytes):
                item["value"] = {"base64": base64.b64encode(value.value).decode("ascii")}
            result[name] = item
        return result

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProxySnapshot":
        values: dict[str, RegistryValue] = {}
        for name in PROXY_VALUE_NAMES:
            raw = payload.get(name, {})
            if isinstance(raw, dict):
                value = raw.get("value")
                if isinstance(value, dict) and isinstance(value.get("base64"), str):
                    try:
                        value = base64.b64decode(value["base64"], validate=True)
                    except (ValueError, TypeError):
                        value = None
                values[name] = RegistryValue(
                    bool(raw.get("exists")), value, int(raw.get("kind", 0))
                )
        return cls(values)


class WinInetRegistryBackend:
    def snapshot(self) -> ProxySnapshot:
        if os.name != "nt":
            return ProxySnapshot({name: RegistryValue(False) for name in PROXY_VALUE_NAMES})
        import winreg

        values: dict[str, RegistryValue] = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as key:
            for name in PROXY_VALUE_NAMES[:5]:
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    values[name] = RegistryValue(False)
                else:
                    values[name] = RegistryValue(True, value, kind)
        try:
            connections = winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_CONNECTIONS)
        except FileNotFoundError:
            connections = None
        try:
            for name in PROXY_VALUE_NAMES[5:]:
                value_name = name.split("/", 1)[1]
                if connections is None:
                    values[name] = RegistryValue(False)
                    continue
                try:
                    value, kind = winreg.QueryValueEx(connections, value_name)
                except FileNotFoundError:
                    values[name] = RegistryValue(False)
                else:
                    values[name] = RegistryValue(True, value, kind)
        finally:
            if connections is not None:
                connections.Close()
        return ProxySnapshot(values)

    def apply_local(self, endpoint: str, bypass: str) -> None:
        if os.name != "nt":
            return
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, endpoint)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, bypass)
            for name in ("AutoConfigURL", "AutoDetect"):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        self.notify()

    def disable_manual_proxy(self) -> None:
        if os.name != "nt":
            return
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        self.notify()

    def restore(self, snapshot: ProxySnapshot) -> None:
        if os.name != "nt":
            return
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
        ) as key:
            for name in PROXY_VALUE_NAMES[:5]:
                value = snapshot.values.get(name, RegistryValue(False))
                if value.exists:
                    winreg.SetValueEx(key, name, 0, value.kind, value.value)
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        connections = winreg.CreateKey(winreg.HKEY_CURRENT_USER, INTERNET_CONNECTIONS)
        try:
            for name in PROXY_VALUE_NAMES[5:]:
                value_name = name.split("/", 1)[1]
                value = snapshot.values.get(name, RegistryValue(False))
                if value.exists:
                    winreg.SetValueEx(connections, value_name, 0, value.kind, value.value)
                else:
                    try:
                        winreg.DeleteValue(connections, value_name)
                    except FileNotFoundError:
                        pass
        finally:
            connections.Close()
        self.notify()

    @staticmethod
    def notify() -> None:
        if os.name != "nt":
            return
        internet_set_option = ctypes.windll.wininet.InternetSetOptionW
        internet_set_option(None, 39, None, 0)
        internet_set_option(None, 37, None, 0)


class WinInetProxyLease:
    def __init__(self, path: str | Path, backend: WinInetRegistryBackend | None = None) -> None:
        self.path = Path(path)
        self.backend = backend or WinInetRegistryBackend()
        self.instance_id = uuid.uuid4().hex
        self.snapshot: ProxySnapshot | None = None
        self.endpoint = ""

    def acquire(self, endpoint: str) -> ProxySnapshot:
        if self.snapshot is not None:
            return self.snapshot
        snapshot = self.backend.snapshot()
        payload = {
            "instanceId": self.instance_id,
            "endpoint": endpoint,
            "createdAt": time.time(),
            "snapshot": snapshot.to_json(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
        self.snapshot = snapshot
        self.endpoint = endpoint
        try:
            self.backend.apply_local(endpoint, "<local>;127.*;localhost")
        except Exception as apply_error:
            try:
                self.backend.restore(snapshot)
            except Exception as restore_error:
                # Keep the durable lease and in-memory ownership so a later
                # stop or process restart can retry exact recovery.
                raise CaptureProxyError(
                    "设置本机代理失败，且原代理暂未恢复；恢复记录已保留"
                ) from restore_error
            self.snapshot = None
            self.endpoint = ""
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            raise apply_error
        return snapshot

    def reacquire(self, endpoint: str) -> bool:
        """Reclaim the proxy after another app changed it, restoring that app on stop."""
        current = self.backend.snapshot()
        if self._is_owned(current, endpoint):
            return False
        payload = {
            "instanceId": self.instance_id,
            "endpoint": endpoint,
            "createdAt": time.time(),
            "snapshot": current.to_json(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
        self.snapshot = current
        self.endpoint = endpoint
        try:
            self.backend.apply_local(endpoint, "<local>;127.*;localhost")
        except Exception as apply_error:
            try:
                self.backend.restore(current)
            except Exception as restore_error:
                raise CaptureProxyError(
                    "重新接管代理失败，且接管前的代理暂未恢复；恢复记录已保留"
                ) from restore_error
            self.snapshot = None
            self.endpoint = ""
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            raise apply_error
        return True

    def release(self) -> bool:
        if self.snapshot is None:
            return False
        current = self.backend.snapshot()
        if not self._is_owned(current, self.endpoint):
            self.snapshot = None
            self.endpoint = ""
            return False
        self.backend.restore(self.snapshot)
        self.snapshot = None
        self.endpoint = ""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return True

    def recover_orphan(self) -> bool:
        if not self.path.exists():
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            endpoint = str(payload["endpoint"])
            snapshot = ProxySnapshot.from_json(payload["snapshot"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False
        if not self._is_owned(self.backend.snapshot(), endpoint):
            return False
        self.backend.restore(snapshot)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return True

    @staticmethod
    def _is_owned(snapshot: ProxySnapshot, endpoint: str) -> bool:
        enabled = snapshot.values.get("ProxyEnable", RegistryValue(False))
        server = snapshot.values.get("ProxyServer", RegistryValue(False))
        return bool(enabled.exists and int(enabled.value or 0) == 1 and server.exists and str(server.value) == endpoint)


def upstream_http_proxy(snapshot: ProxySnapshot) -> tuple[str, int] | None:
    enabled = snapshot.values.get("ProxyEnable", RegistryValue(False))
    server = snapshot.values.get("ProxyServer", RegistryValue(False))
    if not enabled.exists or int(enabled.value or 0) != 1 or not server.exists:
        return None
    raw = str(server.value or "").strip()
    if not raw:
        return None
    selected = raw
    if ";" in raw or "=" in raw:
        entries: dict[str, str] = {}
        for item in raw.split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                entries[key.strip().lower()] = value.strip()
        selected = entries.get("https") or entries.get("http") or ""
    if "://" not in selected:
        selected = "http://" + selected
    try:
        parsed = urlsplit(selected)
        if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
            return None
        if parsed.username or parsed.password:
            return None
        return parsed.hostname, parsed.port
    except ValueError:
        return None


def proxy_endpoint_is_loopback(endpoint: tuple[str, int] | None) -> bool:
    if not endpoint:
        return False
    host = endpoint[0].lower().strip("[]").rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def proxy_endpoint_reachable(
    endpoint: tuple[str, int] | None,
    timeout: float = 0.35,
) -> bool:
    if not endpoint:
        return False
    try:
        connection = socket.create_connection(endpoint, timeout=timeout)
    except OSError:
        return False
    connection.close()
    return True


def upstream_proxy_bypass(snapshot: ProxySnapshot) -> tuple[str, ...]:
    value = snapshot.values.get("ProxyOverride", RegistryValue(False))
    if not value.exists:
        return ()
    return tuple(
        item.strip().lower()
        for item in str(value.value or "").split(";")
        if item.strip()
    )


def _read_head(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(min(4096, MAX_HEADER_BYTES + 4 - len(data)))
        if not chunk:
            raise EOFError
        data.extend(chunk)
        if len(data) > MAX_HEADER_BYTES:
            raise CaptureProxyError("请求头过大")
    marker = data.index(b"\r\n\r\n") + 4
    return bytes(data[:marker]), bytes(data[marker:])


def _parse_head(data: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    try:
        lines = data.decode("iso-8859-1").split("\r\n")
        method, target, version = lines[0].split(" ", 2)
        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if not line:
                continue
            name, value = line.split(":", 1)
            headers.append((name.strip(), value.strip()))
        return method.upper(), target, version, headers
    except (UnicodeDecodeError, ValueError) as exc:
        raise CaptureProxyError("请求头无效") from exc


def _parse_response_head(data: bytes) -> tuple[int, list[tuple[str, str]]]:
    try:
        lines = data.decode("iso-8859-1").split("\r\n")
        version, status, _reason = lines[0].split(" ", 2)
        if not version.startswith("HTTP/"):
            raise ValueError
        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if not line:
                continue
            name, value = line.split(":", 1)
            headers.append((name.strip(), value.strip()))
        return int(status), headers
    except (UnicodeDecodeError, ValueError) as exc:
        raise CaptureProxyError("响应头无效") from exc


def _header(headers: list[tuple[str, str]], name: str) -> str:
    lowered = name.lower()
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return ""


def _read_exact(sock: socket.socket, initial: bytes, length: int) -> bytes:
    data = bytearray(initial[:length])
    while len(data) < length:
        chunk = sock.recv(min(65_536, length - len(data)))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def _read_chunked(sock: socket.socket, initial: bytes) -> bytes:
    buffer = bytearray(initial)
    output = bytearray()

    def line() -> bytes:
        while b"\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                raise EOFError
            buffer.extend(chunk)
            if len(buffer) > MAX_HEADER_BYTES:
                raise CaptureProxyError("分块响应头过大")
        marker = buffer.index(b"\r\n")
        result = bytes(buffer[:marker])
        del buffer[: marker + 2]
        return result

    while True:
        size_line = line().split(b";", 1)[0]
        try:
            size = int(size_line, 16)
        except ValueError as exc:
            raise CaptureProxyError("分块响应长度无效") from exc
        if size == 0:
            while line():
                pass
            return bytes(output)
        if len(output) + size > MAX_BUFFERED_RESPONSE:
            raise CaptureProxyError("页面响应过大")
        while len(buffer) < size + 2:
            chunk = sock.recv(min(65_536, size + 2 - len(buffer)))
            if not chunk:
                raise EOFError
            buffer.extend(chunk)
        output.extend(buffer[:size])
        if buffer[size : size + 2] != b"\r\n":
            raise CaptureProxyError("分块响应结尾无效")
        del buffer[: size + 2]


def _decompress_limited(data: bytes, encoding: str) -> bytes:
    window = 16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
    decompressor = zlib.decompressobj(window)
    output = decompressor.decompress(data, MAX_BUFFERED_RESPONSE + 1)
    if len(output) > MAX_BUFFERED_RESPONSE or decompressor.unconsumed_tail:
        raise CaptureProxyError("解压后的页面响应过大")
    remaining = MAX_BUFFERED_RESPONSE + 1 - len(output)
    output += decompressor.flush(remaining)
    if len(output) > MAX_BUFFERED_RESPONSE:
        raise CaptureProxyError("解压后的页面响应过大")
    return output


def _tunnel(client: socket.socket, remote: socket.socket) -> None:
    sockets = [client, remote]
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, 30)
        if exceptional or not readable:
            return
        for source in readable:
            data = source.recv(65_536)
            if not data:
                return
            (remote if source is client else client).sendall(data)


class _ProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], owner: "WechatLoopbackProxy") -> None:
        self.owner = owner
        self.connection_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(address, _ProxyHandler)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self.connection_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


class _ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(20)
        try:
            head, initial = _read_head(self.request)
            method, target, version, headers = _parse_head(head)
            if method != "CONNECT":
                self.server.owner.handle_plain_http(
                    self.request, method, target, version, headers, initial
                )
                return
            host, port = self.server.owner.parse_authority(target)
            if not self.server.owner.should_intercept(host):
                remote = self.server.owner.connect_remote(host, port, tls=False)
                try:
                    self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    if initial:
                        remote.sendall(initial)
                    _tunnel(self.request, remote)
                finally:
                    remote.close()
                return
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client = self.server.owner.server_context.wrap_socket(self.request, server_side=True)
            try:
                self.server.owner.handle_intercepted(client, host, port)
            finally:
                client.close()
        except (OSError, EOFError, ssl.SSLError, CaptureProxyError):
            return


class WechatLoopbackProxy:
    _FINDER_METHODS = (
        b"finderInit",
        b"finderPcFlow",
        b"finderGetRecommend",
        b"finderGetCommentDetail",
        b"finderGetCommentList",
        b"finderUserPage",
        b"finderGetInteractionedFeedList",
        b"finderSearch",
        b"finderGetLiveInfo",
        b"joinLive",
        b"goToNextFlowFeed",
        b"goToPrevFlowFeed",
        b"loadLocalPlaylist",
        b"finderGetFeedH5Url",
        b"finderGetFollowList",
    )

    def __init__(
        self,
        certificate: CertificateFiles,
        bridge_script: bytes,
        candidate_callback: Callable[
            [dict[str, Any], dict[str, str]], dict[str, Any] | None
        ],
        allowed_hosts: tuple[str, ...] = ("channels.weixin.qq.com", "res.wx.qq.com"),
        host: str = "127.0.0.1",
        port: int = 0,
        upstream_proxy: tuple[str, int] | None = None,
        upstream_bypass: tuple[str, ...] = (),
    ) -> None:
        self.bridge_script = bridge_script
        self.candidate_callback = candidate_callback
        self.allowed_hosts = tuple(item.lower().lstrip(".") for item in allowed_hosts)
        self.session_token = uuid.uuid4().hex
        self.upstream_proxy = upstream_proxy
        self.upstream_bypass = upstream_bypass
        self._diagnostic_lock = threading.Lock()
        self._diagnostic_counts = {
            "resourceScriptsSeen": 0,
            "resourceScriptsInstrumented": 0,
            "finderHooksInstalled": 0,
        }
        self.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.server_context.set_alpn_protocols(["http/1.1"])
        self.server_context.load_cert_chain(certificate.leaf_pem, certificate.leaf_key)
        self.server = _ProxyServer((host, port), self)
        self.thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.server.serve_forever, name="wechat-capture-proxy", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=3)
        self.thread = None

    @staticmethod
    def parse_authority(value: str) -> tuple[str, int]:
        if value.startswith("["):
            host, separator, port = value[1:].partition("]:")
        else:
            host, separator, port = value.rpartition(":")
        if not separator or not host:
            raise CaptureProxyError("CONNECT 地址无效")
        try:
            number = int(port)
        except ValueError as exc:
            raise CaptureProxyError("CONNECT 端口无效") from exc
        if not 1 <= number <= 65535:
            raise CaptureProxyError("CONNECT 端口无效")
        return host.lower(), number

    def should_intercept(self, host: str) -> bool:
        lowered = host.lower().rstrip(".")
        return any(lowered == item or lowered.endswith("." + item) for item in self.allowed_hosts)

    def diagnostics(self) -> dict[str, int]:
        with self._diagnostic_lock:
            return dict(self._diagnostic_counts)

    def connect_remote(self, host: str, port: int, *, tls: bool) -> socket.socket:
        use_upstream = bool(self.upstream_proxy) and not self._bypass_upstream(host)
        if use_upstream and self.upstream_proxy:
            remote = socket.create_connection(self.upstream_proxy, timeout=15)
            remote.sendall(
                f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode("ascii")
            )
            head, remaining = _read_head(remote)
            if not head.startswith(b"HTTP/1.1 200") and not head.startswith(b"HTTP/1.0 200"):
                remote.close()
                raise CaptureProxyError("上游代理连接失败")
            if remaining:
                remote.close()
                raise CaptureProxyError("上游代理返回意外数据")
        else:
            remote = socket.create_connection((host, port), timeout=15)
        if not tls:
            return remote
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
        return context.wrap_socket(remote, server_hostname=host)

    def _bypass_upstream(self, host: str) -> bool:
        lowered = host.lower().strip("[]").rstrip(".")
        for pattern in self.upstream_bypass:
            if pattern == "<local>" and "." not in lowered:
                return True
            if fnmatch.fnmatchcase(lowered, pattern):
                return True
        return False

    @staticmethod
    def _request_context(headers: list[tuple[str, str]]) -> dict[str, str]:
        allowed = {"user-agent", "referer", "origin", "cookie", "accept-language"}
        result: dict[str, str] = {}
        for name, value in headers:
            lowered = name.lower()
            if lowered not in allowed or "\r" in value or "\n" in value:
                continue
            limit = 16_384 if lowered == "cookie" else 4_096
            result[name.title()] = value[:limit]
        return result

    @staticmethod
    def _plain_target(
        target: str, headers: list[tuple[str, str]]
    ) -> tuple[str, int, str, str]:
        parsed = urlsplit(target)
        if parsed.scheme:
            if parsed.scheme.lower() != "http" or not parsed.hostname:
                raise CaptureProxyError("仅支持转发 HTTP 代理请求")
            host = parsed.hostname.lower()
            try:
                port = parsed.port or 80
            except ValueError as exc:
                raise CaptureProxyError("HTTP 目标端口无效") from exc
            origin_target = parsed.path or "/"
            if parsed.query:
                origin_target += "?" + parsed.query
            absolute_target = target
        else:
            host_value = _header(headers, "Host")
            if not host_value:
                raise CaptureProxyError("HTTP 请求缺少 Host")
            if host_value.startswith("["):
                host, separator, port_text = host_value[1:].partition("]:")
            else:
                host, separator, port_text = host_value.rpartition(":")
                if not separator:
                    host, port_text = host_value, "80"
            try:
                port = int(port_text)
            except ValueError as exc:
                raise CaptureProxyError("HTTP 目标端口无效") from exc
            origin_target = target if target.startswith("/") else "/" + target
            default_port = "" if port == 80 else f":{port}"
            absolute_target = f"http://{host}{default_port}{origin_target}"
        if not host or not 1 <= port <= 65535:
            raise CaptureProxyError("HTTP 目标地址无效")
        return host, port, origin_target, absolute_target

    def handle_plain_http(
        self,
        client: socket.socket,
        method: str,
        target: str,
        version: str,
        headers: list[tuple[str, str]],
        initial: bytes,
    ) -> None:
        host, port, origin_target, absolute_target = self._plain_target(target, headers)
        use_upstream = bool(self.upstream_proxy) and not self._bypass_upstream(host)
        address = self.upstream_proxy if use_upstream else (host, port)
        if not address:
            raise CaptureProxyError("HTTP 目标地址无效")
        remote = socket.create_connection(address, timeout=15)
        try:
            request_target = absolute_target if use_upstream else origin_target
            forwarded = [
                (name, value)
                for name, value in headers
                if name.lower() not in {"proxy-connection", "connection"}
            ]
            request_head = f"{method} {request_target} {version}\r\n".encode("iso-8859-1")
            request_head += b"".join(
                f"{name}: {value}\r\n".encode("iso-8859-1") for name, value in forwarded
            )
            remote.sendall(request_head + b"Connection: close\r\n\r\n" + initial)
            _tunnel(client, remote)
        finally:
            remote.close()

    def handle_intercepted(self, client: ssl.SSLSocket, host: str, port: int) -> None:
        while True:
            try:
                head, initial = _read_head(client)
            except EOFError:
                return
            method, target, version, headers = _parse_head(head)
            content_length = int(_header(headers, "Content-Length") or "0")
            if content_length < 0 or content_length > MAX_CONTROL_BODY:
                raise CaptureProxyError("请求正文过大")
            body = _read_exact(client, initial, content_length) if content_length else b""
            path = urlsplit(target).path
            if path.startswith(CAPTURE_PATH + "/bridge.js"):
                self._send_bridge(client)
                return
            if path.startswith(CAPTURE_PATH + "/candidate"):
                self._accept_candidate(client, target, body, headers)
                return
            self._forward(client, host, port, method, target, version, headers, body)
            return

    def _send_bridge(self, client: socket.socket) -> None:
        body = self.bridge_script.replace(b"__DOWNLOAD_STATION_SESSION__", self.session_token.encode("ascii"))
        client.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/javascript; charset=utf-8\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: "
            + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        )

    def _accept_candidate(
        self,
        client: socket.socket,
        target: str,
        body: bytes,
        headers: list[tuple[str, str]],
    ) -> None:
        query = urlsplit(target).query
        if f"token={self.session_token}" not in query.split("&"):
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, CaptureProxyError):
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            return
        try:
            result = self.candidate_callback(payload, self._request_context(headers))
        except Exception:
            client.sendall(b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            return
        response_body = json.dumps(
            result if isinstance(result, dict) else {},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        client.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
            b"Cache-Control: no-store\r\nConnection: close\r\nContent-Length: "
            + str(len(response_body)).encode("ascii")
            + b"\r\n\r\n"
            + response_body
        )

    def _forward(
        self,
        client: socket.socket,
        host: str,
        port: int,
        method: str,
        target: str,
        version: str,
        headers: list[tuple[str, str]],
        body: bytes,
    ) -> None:
        remote = self.connect_remote(host, port, tls=True)
        try:
            output_headers: list[tuple[str, str]] = []
            for name, value in headers:
                lowered = name.lower()
                if lowered in {"proxy-connection", "connection", "accept-encoding", "content-length"}:
                    continue
                output_headers.append((name, value))
            output_headers.extend((("Accept-Encoding", "identity"), ("Connection", "close")))
            if body:
                output_headers.append(("Content-Length", str(len(body))))
            request_target = target if target.startswith("/") else urlsplit(target).path or "/"
            query = urlsplit(target).query
            if query and "?" not in request_target:
                request_target += "?" + query
            request_head = f"{method} {request_target} {version}\r\n".encode("iso-8859-1")
            request_head += b"".join(f"{name}: {value}\r\n".encode("iso-8859-1") for name, value in output_headers) + b"\r\n"
            remote.sendall(request_head + body)
            response_head, initial = _read_head(remote)
            status, response_headers = _parse_response_head(response_head)
            status_line = response_head.split(b"\r\n", 1)[0]
            length_text = _header(response_headers, "Content-Length")
            transfer_encoding = _header(response_headers, "Transfer-Encoding").lower()
            content_type = _header(response_headers, "Content-Type").lower()
            content_encoding = _header(response_headers, "Content-Encoding").lower()
            if method == "HEAD" or status in {204, 304} or 100 <= status < 200:
                response_body = b""
            elif "chunked" in transfer_encoding:
                response_body = _read_chunked(remote, initial)
            elif length_text:
                length = int(length_text)
                if length > MAX_BUFFERED_RESPONSE:
                    client.sendall(response_head + initial)
                    while True:
                        chunk = remote.recv(65_536)
                        if not chunk:
                            return
                        client.sendall(chunk)
                response_body = _read_exact(remote, initial, length)
            else:
                chunks = [initial]
                total = len(initial)
                while True:
                    chunk = remote.recv(65_536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BUFFERED_RESPONSE:
                        client.sendall(response_head + b"".join(chunks) + chunk)
                        while True:
                            chunk = remote.recv(65_536)
                            if not chunk:
                                return
                            client.sendall(chunk)
                    chunks.append(chunk)
                response_body = b"".join(chunks)
            path = urlsplit(target).path
            is_html = "text/html" in content_type
            is_resource_script = host == "res.wx.qq.com" and (
                "javascript" in content_type or path.lower().endswith(".js")
            )
            decoded_body = False
            if is_html or is_resource_script:
                if content_encoding == "gzip":
                    response_body = _decompress_limited(response_body, "gzip")
                    decoded_body = True
                elif content_encoding == "deflate":
                    response_body = _decompress_limited(response_body, "deflate")
                    decoded_body = True
                elif not content_encoding or content_encoding == "identity":
                    decoded_body = True
                if decoded_body:
                    if is_html:
                        response_body = self._inject_html(response_body)
                    elif is_resource_script:
                        response_body = self._instrument_javascript(response_body, path)
            cleaned = [
                (name, value) for name, value in response_headers
                if name.lower() not in {"content-length", "transfer-encoding", "connection"}
                and not (decoded_body and name.lower() == "content-encoding")
            ]
            final_head = status_line + b"\r\n" + b"".join(
                f"{name}: {value}\r\n".encode("iso-8859-1") for name, value in cleaned
            )
            final_head += b"Content-Length: " + str(len(response_body)).encode("ascii") + b"\r\nConnection: close\r\n\r\n"
            client.sendall(final_head + response_body)
        finally:
            remote.close()

    def _inject_html(self, body: bytes) -> bytes:
        nonce_match = re.search(br"\bnonce=[\"']([^\"']{1,256})[\"']", body, re.IGNORECASE)
        nonce = b""
        if nonce_match:
            nonce = b' nonce="' + nonce_match.group(1).replace(b'"', b"") + b'"'
        script = (
            f'<script src="{CAPTURE_PATH}/bridge.js?token={self.session_token}" data-download-station="wechat"'.encode("utf-8")
            + nonce
            + b"></script>"
        )
        cache_key = b"__download_station_session=" + self.session_token.encode("ascii")

        def bust_script_url(match: re.Match[bytes]) -> bytes:
            prefix, quote, url = match.group(1), match.group(2), match.group(3)
            if cache_key in url:
                return match.group(0)
            fragment = b""
            if b"#" in url:
                url, fragment = url.split(b"#", 1)
                fragment = b"#" + fragment
            separator = b"&" if b"?" in url else b"?"
            return prefix + quote + url + separator + cache_key + fragment + quote

        body = re.sub(
            br"(?i)(\b(?:src|href)\s*=\s*)([\"'])([^\"'<>]+\.js(?:\?[^\"'<>#]*)?(?:#[^\"'<>]*)?)\2",
            bust_script_url,
            body,
        )
        lowered = body.lower()
        index = lowered.find(b"<head")
        if index >= 0:
            end = body.find(b">", index)
            if end >= 0:
                return body[: end + 1] + script + body[end + 1 :]
        index = lowered.find(b"<html")
        if index >= 0:
            end = body.find(b">", index)
            if end >= 0:
                return body[: end + 1] + b"<head>" + script + b"</head>" + body[end + 1 :]
        return script + body

    @staticmethod
    def _find_matching_delim(body: bytes, start: int, open_ch: int, close_ch: int) -> int:
        """返回匹配闭合定界符之后的位置。定界符不匹配时抛出 ValueError。"""
        depth = 1
        cursor = start + 1
        while cursor < len(body) and depth > 0:
            ch = body[cursor]
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
            cursor += 1
        if depth != 0:
            raise ValueError("定界符不匹配")
        return cursor

    @staticmethod
    def _async_keyword_start(body: bytes, method_start: int) -> int:
        """回扫 method_start 查找 async 关键字起始位置。未找到返回 method_start。"""
        scan = method_start - 1
        while scan >= 0 and body[scan:scan + 1] in (b" ", b"\t"):
            scan -= 1
        if scan >= 4 and body[scan - 4:scan + 1] == b"async":
            return scan - 4
        return method_start

    def _instrument_javascript(self, body: bytes, _path: str = "") -> bytes:
        with self._diagnostic_lock:
            self._diagnostic_counts["resourceScriptsSeen"] += 1
        cache_key = b"__download_station_session=" + self.session_token.encode("ascii")

        def bust_module_url(match: re.Match[bytes]) -> bytes:
            quote, url = match.group(1), match.group(2)
            if cache_key in url:
                return match.group(0)
            separator = b"&" if b"?" in url else b"?"
            return quote + url + separator + cache_key + quote

        body = re.sub(
            br"([\"'])([^\"'\r\n]{1,1024}\.js(?:\?[^\"'\r\n#]*)?)\1",
            bust_module_url,
            body,
        )
        if b"__DOWNLOAD_STATION_WECHAT_OBSERVE__" in body:
            return body

        method_names = b"|".join(re.escape(name) for name in self._FINDER_METHODS)
        finder_re = re.compile(rb"(?:" + method_names + rb")\s*\(")

        parts: list[bytes] = []
        cursor = 0
        count = 0

        for match in finder_re.finditer(body):
            method_start = match.start()
            method_end = match.end()  # 指向 methodName( 之后

            async_start = self._async_keyword_start(body, method_start)
            is_async = async_start != method_start

            try:
                # 找到 (...) 参数列表边界
                paren_end = self._find_matching_delim(body, method_end - 1, 0x28, 0x29)
                arguments = body[method_end:paren_end - 1]

                # 跳过空白找到 {
                brace_pos = paren_end
                while brace_pos < len(body) and body[brace_pos:brace_pos + 1] in (b" ", b"\t", b"\n", b"\r"):
                    brace_pos += 1
                if brace_pos >= len(body) or body[brace_pos] != 0x7B:
                    continue

                # 找到 { ... } 方法体边界
                body_end_pos = self._find_matching_delim(body, brace_pos, 0x7B, 0x7D)
                original_body = body[brace_pos + 1:body_end_pos - 1]

            except ValueError:
                continue

            # 输出此方法之前的部分（async 关键字由插桩部分输出）
            parts.append(body[cursor:async_start])

            # 输出插桩后的方法
            name_only = body[method_start:method_end - 1]  # methodName 不含 (
            method_literal = json.dumps(name_only.decode("ascii")).encode("ascii")
            if is_async:
                parts.append(
                    b"async " + name_only + b"(" + arguments + b"){"
                    b"var __download_station_finder_result__="
                    b"await(async()=>{" + original_body + b"})();"
                    b"try{if(typeof globalThis!==\"undefined\"&&"
                    b"typeof globalThis.__DOWNLOAD_STATION_WECHAT_OBSERVE__===\"function\"){"
                    b"globalThis.__DOWNLOAD_STATION_WECHAT_OBSERVE__(__download_station_finder_result__,"
                    + method_literal
                    + b")"
                    b"}}catch(_download_station_observe_error__){}"
                    b"return __download_station_finder_result__}"
                )
            else:
                parts.append(
                    name_only + b"(" + arguments + b"){"
                    b"var __download_station_finder_result__="
                    b"(()=>{" + original_body + b"})();"
                    b"try{if(typeof globalThis!==\"undefined\"&&"
                    b"typeof globalThis.__DOWNLOAD_STATION_WECHAT_OBSERVE__===\"function\"){"
                    b"globalThis.__DOWNLOAD_STATION_WECHAT_OBSERVE__(__download_station_finder_result__,"
                    + method_literal
                    + b")"
                    b"}}catch(_download_station_observe_error__){}"
                    b"return __download_station_finder_result__}"
                )

            cursor = body_end_pos
            count += 1

        # 追加剩余部分
        parts.append(body[cursor:])

        if count:
            with self._diagnostic_lock:
                self._diagnostic_counts["resourceScriptsInstrumented"] += 1
                self._diagnostic_counts["finderHooksInstalled"] += count

        return b"".join(parts)
