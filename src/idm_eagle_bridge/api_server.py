from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from .constants import (
    APP_VERSION,
    DEFAULT_LOCAL_HOST,
    DEFAULT_LOCAL_PORT,
    EXTENSION_PROTOCOL_VERSION,
)
from .database import Database
from .eagle import EagleClient
from .media import MediaCoordinator, MediaPlanError
from .security import CHROME_EXTENSION_ORIGIN, PairingError, PairingManager
from .url_utils import InvalidPageUrl, normalize_domain
from .wechat_channels import WechatChannelsCaptureService


MAX_BODY_SIZE = 256 * 1024


class LocalThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalApi:
    def __init__(
        self,
        database: Database,
        media_ready_callback: Callable[[], None] | None = None,
    ) -> None:
        self.database = database
        self.pairing = PairingManager(database)
        # Eagle is optional. Keep a short cached probe so popup and video-page
        # actions can choose a safe local-download route without turning every
        # UI refresh into a four-second connection wait.
        self.eagle = EagleClient(timeout=0.5)
        self._eagle_available = False
        self._eagle_checked_at = 0.0
        self._eagle_probe_lock = threading.Lock()
        self.media = MediaCoordinator(database, ready_callback=media_ready_callback)
        self.wechat_channels = WechatChannelsCaptureService(
            self.media,
            root=database.path.parent / "wechat-channels",
            eagle_available=self.eagle_available,
        )

    def eagle_available(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        with self._eagle_probe_lock:
            if not force and now - self._eagle_checked_at < 3.0:
                return self._eagle_available
            try:
                self._eagle_available = bool(self.eagle.is_available())
            except Exception:
                # Eagle is an optional integration.  A broken or changing local
                # API must degrade to local download rather than fail /health or
                # an old extension's download request.
                self._eagle_available = False
            self._eagle_checked_at = time.monotonic()
            return self._eagle_available

    def media_health(self) -> dict[str, Any]:
        health = dict(self.media.health())
        health["eagleAvailable"] = self.eagle_available()
        return health

    def create_media_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        fell_back_to_local = bool(request.get("importToEagle", True)) and not self.eagle_available()
        if fell_back_to_local:
            request["importToEagle"] = False
            request["deleteAfterImport"] = False
        plan = self.media.create_plan(request)
        if fell_back_to_local:
            plan = dict(plan)
            plan["deliveryFallback"] = "local"
        return plan

    def import_media_plan(self, plan_id: str) -> dict[str, Any]:
        if not self.eagle_available(force=True):
            raise MediaPlanError(
                "Eagle 未安装或未启动；本机下载文件仍会保留，启动 Eagle 后再导入",
                "eagle_unavailable",
            )
        return self.media.import_completed_plan(plan_id)

    def pair(self, origin: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = self.pairing.pair(origin, str(payload.get("code", "")))
        return {"token": token}

    def pair_automatically(
        self, origin: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        token = self.pairing.pair_with_bootstrap(
            origin,
            str(payload.get("secret", "")),
        )
        return {"token": token}

    def recover_pairing(self, origin: str) -> dict[str, Any]:
        return {"token": self.pairing.recover(origin)}

    def site_status(self, domain: str) -> dict[str, Any]:
        normalized = normalize_domain(domain)
        return {"domain": normalized, "enabled": self.database.site_enabled(normalized)}

    def set_site(self, payload: dict[str, Any]) -> dict[str, Any]:
        domain = normalize_domain(str(payload.get("domain", "")))
        enabled = bool(payload.get("enabled", False))
        include_subdomains = bool(payload.get("includeSubdomains", True))
        self.database.set_site_rule(domain, enabled, include_subdomains)
        return {
            "domain": domain,
            "enabled": enabled,
            "includeSubdomains": include_subdomains,
        }

    def add_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        captured_at_ms = payload.get("capturedAt")
        captured_at = time.time()
        if isinstance(captured_at_ms, (int, float)):
            candidate = float(captured_at_ms) / 1000
            if time.time() - 7 * 86400 <= candidate <= time.time() + 300:
                captured_at = candidate

        event_id = self.database.add_source_event(
            page_url=str(payload.get("pageUrl", "")),
            page_title=str(payload.get("pageTitle", "")),
            media_url=str(payload.get("mediaUrl", "")),
            event_type=str(payload.get("eventType", "download_intent")),
            tab_id=payload.get("tabId") if isinstance(payload.get("tabId"), int) else None,
            created_at=captured_at,
        )
        return {"eventId": event_id}


def build_handler(api: LocalApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "IdmEagleLocal/0.1"

        def log_message(self, _format: str, *args: object) -> None:
            return

        def _origin(self) -> str:
            return self.headers.get("Origin", "")

        def _cors(self) -> None:
            origin = self._origin()
            if CHROME_EXTENSION_ORIGIN.fullmatch(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("请求长度无效") from exc
            if length <= 0 or length > MAX_BODY_SIZE:
                raise ValueError("请求内容为空或过大")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("请求内容不是有效 JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("请求内容格式不正确")
            return payload

        def _token(self) -> str:
            value = self.headers.get("Authorization", "")
            prefix = "Bearer "
            return value[len(prefix) :] if value.startswith(prefix) else ""

        def _authenticated(self, payload: dict[str, Any] | None = None) -> bool:
            token = self._token()
            if not token and payload is not None:
                candidate = payload.get("authToken", "")
                token = candidate if isinstance(candidate, str) else ""
            return api.pairing.authenticate(self._origin(), token)

        def do_OPTIONS(self) -> None:
            if not CHROME_EXTENSION_ORIGIN.fullmatch(self._origin()):
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "来源不受信任"})
                return
            self.send_response(HTTPStatus.NO_CONTENT.value)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/health":
                try:
                    media_health = api.media_health()
                    wechat_health = api.wechat_channels.health()
                    self._json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "service": "idm-eagle",
                            "version": APP_VERSION,
                            "extensionProtocol": EXTENSION_PROTOCOL_VERSION,
                            "databaseSchema": media_health.get("databaseSchema"),
                            "downloadEngine": media_health.get("downloadEngine"),
                            "mediaReady": bool(media_health.get("ok")),
                            "eagleAvailable": bool(media_health.get("eagleAvailable")),
                            "youtubeResolverReady": bool(media_health.get("youtubeResolver")),
                            "wechatChannels": {
                                "state": wechat_health.get("state"),
                                "running": bool(wechat_health.get("running")),
                                "candidateCount": int(wechat_health.get("candidateCount", 0)),
                                "rejectedCount": int(wechat_health.get("rejectedCount", 0)),
                                "internalApiObserved": int(wechat_health.get("internalApiObserved", 0)),
                                "proxyDiagnostics": dict(wechat_health.get("proxyDiagnostics") or {}),
                                "bridgeHash": str(wechat_health.get("bridgeHash") or ""),
                                "certificateId": str(wechat_health.get("certificateId") or ""),
                                "errorCode": str(wechat_health.get("errorCode") or ""),
                            },
                        },
                    )
                except Exception:
                    self._json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"ok": False, "error": "本机助手处理失败"},
                    )
                return
            if not self._authenticated():
                self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "尚未配对或配对已失效"})
                return

            try:
                if parsed.path == "/api/site":
                    query = parse_qs(parsed.query)
                    data = api.site_status(query.get("domain", [""])[0])
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                elif parsed.path == "/api/jobs":
                    query = parse_qs(parsed.query)
                    limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
                    self._json(
                        HTTPStatus.OK,
                        {"ok": True, "data": api.database.list_jobs(limit)},
                    )
                elif parsed.path == "/api/media/plan":
                    query = parse_qs(parsed.query)
                    data = api.media.get_plan(query.get("id", [""])[0])
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                elif parsed.path == "/api/media/plans":
                    query = parse_qs(parsed.query)
                    limit = min(max(int(query.get("limit", ["50"])[0]), 1), 200)
                    self._json(
                        HTTPStatus.OK,
                        {"ok": True, "data": api.media.list_plans(limit)},
                    )
                elif parsed.path == "/api/media/preview":
                    query = parse_qs(parsed.query)
                    data = api.media.get_plan_preview(query.get("id", [""])[0])
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                elif parsed.path == "/api/media/health":
                    self._json(
                        HTTPStatus.OK,
                        {"ok": True, "data": api.media_health()},
                    )
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "接口不存在"})
            except (InvalidPageUrl, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            except MediaPlanError as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(exc), "errorCode": exc.code},
                )
            except Exception:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": "本机助手处理失败"},
                )

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            try:
                payload = self._read_json()
                if parsed.path == "/api/pair":
                    data = api.pair(self._origin(), payload)
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                    return
                if parsed.path == "/api/pair/auto":
                    data = api.pair_automatically(self._origin(), payload)
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                    return
                if parsed.path == "/api/pair/recover":
                    data = api.recover_pairing(self._origin())
                    self._json(HTTPStatus.OK, {"ok": True, "data": data})
                    return
                if not self._authenticated(payload):
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "尚未配对或配对已失效"})
                    return
                if parsed.path == "/api/site/status":
                    data = api.site_status(str(payload.get("domain", "")))
                elif parsed.path == "/api/site":
                    data = api.set_site(payload)
                elif parsed.path == "/api/source":
                    data = api.add_source(payload)
                elif parsed.path == "/api/media/health":
                    data = api.media_health()
                elif parsed.path == "/api/media/plans":
                    limit = min(max(int(payload.get("limit", 50)), 1), 200)
                    data = api.media.list_plans(limit)
                elif parsed.path == "/api/media/plan/get":
                    data = api.media.get_plan(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/preview":
                    data = api.media.get_plan_preview(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/plan":
                    data = api.create_media_plan(payload)
                elif parsed.path == "/api/media/retry":
                    data = api.media.retry_plan(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/stop":
                    data = api.media.stop_plan(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/open":
                    data = api.media.open_plan_output(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/import":
                    data = api.import_media_plan(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/remove":
                    data = api.media.remove_plan(str(payload.get("planId", "")))
                elif parsed.path == "/api/media/clear":
                    data = {"removed": api.media.clear_terminal_history()}
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "接口不存在"})
                    return
                self._json(HTTPStatus.OK, {"ok": True, "data": data})
            except PairingError as exc:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
            except PermissionError as exc:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
            except (InvalidPageUrl, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            except MediaPlanError as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(exc), "errorCode": exc.code},
                )
            except Exception:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "本机助手处理失败"})

    return Handler


class LocalApiServer:
    def __init__(
        self,
        database: Database,
        host: str = DEFAULT_LOCAL_HOST,
        port: int = DEFAULT_LOCAL_PORT,
        media_ready_callback: Callable[[], None] | None = None,
    ) -> None:
        self.api = LocalApi(database, media_ready_callback=media_ready_callback)
        self.server = LocalThreadingHTTPServer((host, port), build_handler(self.api))
        self.thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        thread = threading.Thread(
            target=self.server.serve_forever,
            name="local-api",
            daemon=True,
        )
        self.thread = thread
        try:
            thread.start()
        except Exception:
            # Keep stop() on the non-started path; BaseServer.shutdown() cannot
            # be called until serve_forever() has actually begun.
            self.thread = None
            raise

    def stop(self) -> None:
        # Restore the user's system proxy before waiting for HTTP/media workers.
        # The native launcher has a bounded shutdown timeout, so this ordering is
        # a safety property rather than merely a performance preference.
        self.api.wechat_channels.close()
        # BaseServer.shutdown() waits for serve_forever() and deadlocks when a
        # startup failure occurs before the worker thread is created.
        if self.thread is not None:
            self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=3)
        self.api.media.close()
