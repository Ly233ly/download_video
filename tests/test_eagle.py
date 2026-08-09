from __future__ import annotations

from http.client import RemoteDisconnected
from io import BytesIO
import unittest
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from idm_eagle_bridge.eagle import (
    EagleClient,
    EagleEndpointUnavailable,
    EagleImportError,
    EagleUnavailable,
)


class RecordingEagle(EagleClient):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[str, str, dict | None]] = []

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        self.requests.append((method, path, data))
        if path == "/api/v2/item/add":
            return {"status": "success", "data": {"id": "item-1"}}
        return {"status": "success"}


class LegacyFallbackEagle(RecordingEagle):
    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        self.requests.append((method, path, data))
        if path.startswith("/api/v2/item/"):
            raise EagleEndpointUnavailable("not supported")
        return {"status": "success"}


class EagleFourBeforeV2WebApi(EagleClient):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[str, str, dict | None]] = []

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        self.requests.append((method, path, data))
        if path == "/api/v2/app/info":
            raise EagleEndpointUnavailable("V2 Web API requires a newer Eagle 4 build")
        if path == "/api/application/info":
            return {
                "status": "success",
                "data": {"version": "4.0.0", "buildVersion": "20250917"},
            }
        raise AssertionError(f"unexpected endpoint: {path}")


class EagleClientTests(unittest.TestCase):
    def test_remote_disconnect_is_reported_as_eagle_unavailable(self) -> None:
        eagle = EagleClient(timeout=0.01)
        with patch(
            "idm_eagle_bridge.eagle.urlopen",
            side_effect=RemoteDisconnected("Eagle closed the connection"),
        ):
            with self.assertRaises(EagleUnavailable):
                eagle.app_info()
            self.assertFalse(eagle.is_available())

    def test_invalid_response_encoding_is_reported_as_import_error(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"\xff\xfe"
        eagle = EagleClient(timeout=0.01)
        with patch("idm_eagle_bridge.eagle.urlopen", return_value=response):
            with self.assertRaises(EagleImportError):
                eagle.app_info()
            self.assertFalse(eagle.is_available())

    def test_http_error_response_is_closed_before_endpoint_fallback(self) -> None:
        error = HTTPError(
            "http://127.0.0.1:41595/api/v2/app/info",
            404,
            "Not Found",
            hdrs=None,
            fp=BytesIO(b"not found"),
        )
        eagle = EagleClient(timeout=0.01)
        with (
            patch("idm_eagle_bridge.eagle.urlopen", side_effect=error),
            patch.object(error, "close", wraps=error.close) as close,
            self.assertRaises(EagleEndpointUnavailable),
        ):
            eagle._request("GET", "/api/v2/app/info")
        close.assert_called_once_with()

    def test_health_falls_back_to_eagle_four_legacy_application_endpoint(self) -> None:
        eagle = EagleFourBeforeV2WebApi()
        self.assertEqual(eagle.app_info()["version"], "4.0.0")
        self.assertTrue(eagle.is_available())
        self.assertEqual(
            [request[1] for request in eagle.requests],
            [
                "/api/v2/app/info",
                "/api/application/info",
                "/api/v2/app/info",
                "/api/application/info",
            ],
        )

    def test_import_without_source_omits_website_field(self) -> None:
        eagle = RecordingEagle()
        item_id = eagle.add_from_path("C:/Downloads/video.mp4")
        self.assertEqual(item_id, "item-1")
        self.assertNotIn("website", eagle.requests[0][2])

    def test_import_with_source_keeps_website_field(self) -> None:
        eagle = RecordingEagle()
        eagle.add_from_path("C:/Downloads/video.mp4", "https://example.com/watch")
        self.assertEqual(eagle.requests[0][2]["website"], "https://example.com/watch")

    def test_update_source_uses_existing_eagle_item(self) -> None:
        eagle = RecordingEagle()
        eagle.update_source("item-1", "https://example.com/watch")
        self.assertEqual(
            eagle.requests,
            [
                (
                    "POST",
                    "/api/v2/item/update",
                    {"id": "item-1", "url": "https://example.com/watch"},
                )
            ],
        )

    def test_import_falls_back_to_legacy_endpoint(self) -> None:
        eagle = LegacyFallbackEagle()
        eagle.add_from_path("C:/Downloads/video.mp4")
        self.assertEqual(
            [request[1] for request in eagle.requests],
            ["/api/v2/item/add", "/api/item/addFromPath"],
        )

    def test_update_falls_back_to_legacy_endpoint(self) -> None:
        eagle = LegacyFallbackEagle()
        eagle.update_source("item-1", "https://example.com/watch")
        self.assertEqual(
            [request[1] for request in eagle.requests],
            ["/api/v2/item/update", "/api/item/update"],
        )


if __name__ == "__main__":
    unittest.main()
