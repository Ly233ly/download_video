from __future__ import annotations

import json
import socket
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .constants import DEFAULT_EAGLE_BASE_URL


class EagleUnavailable(RuntimeError):
    pass


class EagleImportError(RuntimeError):
    pass


class EagleEndpointUnavailable(EagleImportError):
    pass


class EagleClient:
    def __init__(self, base_url: str = DEFAULT_EAGLE_BASE_URL, timeout: float = 4) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status in {404, 405}:
                raise EagleEndpointUnavailable(f"Eagle 接口不可用：HTTP {status}") from exc
            raise EagleImportError(f"Eagle 接口返回 HTTP {status}") from exc
        except (URLError, socket.timeout, OSError, HTTPException) as exc:
            raise EagleUnavailable("Eagle 当前不可用") from exc
        except UnicodeDecodeError as exc:
            raise EagleImportError("Eagle 返回了无法识别的文本编码") from exc

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EagleImportError("Eagle 返回了无法识别的结果") from exc
        if not isinstance(result, dict):
            raise EagleImportError("Eagle 返回格式不正确")
        return result

    def app_info(self) -> dict[str, Any]:
        try:
            result = self._request("GET", "/api/v2/app/info")
        except EagleEndpointUnavailable:
            result = self._request("GET", "/api/application/info")
        if result.get("status") not in {"success", True}:
            raise EagleUnavailable("Eagle 本地接口未就绪")
        return result.get("data") or {}

    def is_available(self) -> bool:
        try:
            self.app_info()
            return True
        except (EagleUnavailable, EagleImportError):
            return False

    def add_from_path(self, file_path: str, website: str | None = None) -> str | None:
        path = Path(file_path)
        payload: dict[str, Any] = {
            "path": str(path),
            "name": path.stem,
            "tags": [],
            "annotation": "",
        }
        if website:
            payload["website"] = website
        try:
            result = self._request("POST", "/api/v2/item/add", payload)
        except EagleEndpointUnavailable:
            result = self._request("POST", "/api/item/addFromPath", payload)
        if result.get("status") not in {"success", True}:
            message = result.get("message") or "Eagle 未接受该文件"
            raise EagleImportError(str(message))
        data = result.get("data")
        if isinstance(data, dict):
            item_id = data.get("id") or data.get("itemId")
            return str(item_id) if item_id else None
        return None

    def update_source(self, item_id: str, source_url: str) -> None:
        try:
            result = self._request(
                "POST",
                "/api/v2/item/update",
                {"id": item_id, "url": source_url},
            )
        except EagleEndpointUnavailable:
            result = self._request(
                "POST",
                "/api/item/update",
                {"id": item_id, "url": source_url},
            )
        if result.get("status") not in {"success", True}:
            message = result.get("message") or "Eagle 未能更新来源网址"
            raise EagleImportError(str(message))
