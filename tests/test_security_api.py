from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from idm_eagle_bridge.api_server import LocalApiServer
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.security import PairingManager


ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
FIREFOX_ORIGIN = "moz-extension://12345678-1234-4abc-8def-1234567890ab"


class SecurityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pairing_rejects_wrong_code_and_accepts_token(self) -> None:
        pairing = PairingManager(self.database)
        with self.assertRaises(ValueError):
            pairing.pair(ORIGIN, "000000" if pairing.pairing_code != "000000" else "999999")

        code = pairing.pairing_code
        token = pairing.pair(ORIGIN, code)
        self.assertTrue(pairing.authenticate(ORIGIN, token))
        self.assertFalse(pairing.authenticate(ORIGIN, "wrong"))

    def test_firefox_extension_origin_can_pair(self) -> None:
        pairing = PairingManager(self.database)
        token = pairing.pair(FIREFOX_ORIGIN, pairing.pairing_code)
        self.assertTrue(pairing.authenticate(FIREFOX_ORIGIN, token))

    def test_health_reports_release_compatibility_gate(self) -> None:
        server = LocalApiServer(self.database, port=0)
        server.start()
        host, port = server.address
        try:
            with urlopen(f"http://{host}:{port}/health", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["version"], "1.4.4")
            self.assertEqual(payload["extensionProtocol"], 1)
            self.assertEqual(payload["databaseSchema"], 6)
            self.assertEqual(payload["downloadEngine"], "desktop_ffmpeg")
            self.assertIsInstance(payload["youtubeResolverReady"], bool)
            self.assertTrue(payload["mediaReady"])
            self.assertEqual(payload["wechatChannels"]["state"], "off")
            self.assertFalse(payload["wechatChannels"]["running"])
            self.assertEqual(len(payload["wechatChannels"]["bridgeHash"]), 16)
        finally:
            server.stop()

    def test_http_pair_site_and_source_flow(self) -> None:
        server = LocalApiServer(self.database, port=0)
        server.start()
        host, port = server.address
        base = f"http://{host}:{port}"
        try:
            code = PairingManager(self.database).pairing_code
            paired = self._json_request(
                f"{base}/api/pair", {"code": code}, origin=ORIGIN
            )
            token = paired["data"]["token"]

            self._json_request(
                f"{base}/api/site",
                {"domain": "example.com", "enabled": True, "includeSubdomains": True},
                origin=ORIGIN,
                token=token,
            )
            source = self._json_request(
                f"{base}/api/source",
                {
                    "pageUrl": "https://video.example.com/watch?id=1&utm_source=test",
                    "pageTitle": "测试页面",
                    "eventType": "manual",
                },
                origin=ORIGIN,
                token=token,
            )
            self.assertTrue(source["data"]["eventId"])
        finally:
            server.stop()

    def test_installer_bootstrap_pairs_once_and_is_consumed(self) -> None:
        secret = "installer-secret-for-test"
        bootstrap = Path(self.temp_dir.name) / "pairing-bootstrap.json"
        bootstrap.write_text(
            json.dumps(
                {
                    "secretHash": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
                    "expiresAt": time.time() + 60,
                }
            ),
            encoding="utf-8",
        )
        server = LocalApiServer(self.database, port=0)
        server.api.pairing.bootstrap_path = bootstrap
        server.start()
        host, port = server.address
        try:
            paired = self._json_request(
                f"http://{host}:{port}/api/pair/auto",
                {"secret": secret},
                origin=ORIGIN,
            )
            token = paired["data"]["token"]
            self.assertTrue(server.api.pairing.authenticate(ORIGIN, token))
            self.assertFalse(bootstrap.exists())
        finally:
            server.stop()

    def test_web_page_origin_is_rejected(self) -> None:
        server = LocalApiServer(self.database, port=0)
        server.start()
        host, port = server.address
        try:
            with self.assertRaises(HTTPError) as caught:
                self._json_request(
                    f"http://{host}:{port}/api/pair",
                    {"code": PairingManager(self.database).pairing_code},
                    origin="https://example.com",
                )
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
        finally:
            server.stop()

    def test_post_body_token_authentication(self) -> None:
        server = LocalApiServer(self.database, host="127.0.0.1", port=0)
        server.start()
        host, port = server.address
        try:
            code = PairingManager(self.database).pairing_code
            paired = self._json_request(
                f"http://{host}:{port}/api/pair",
                {"code": code},
                origin=ORIGIN,
            )
            token = paired["data"]["token"]
            site = self._json_request(
                f"http://{host}:{port}/api/site/status",
                {"domain": "example.com", "authToken": token},
                origin=ORIGIN,
            )
            self.assertEqual(site["data"], {"domain": "example.com", "enabled": False})
        finally:
            server.stop()

    def test_post_body_token_authenticates_media_read_endpoints(self) -> None:
        server = LocalApiServer(self.database, host="127.0.0.1", port=0)
        server.start()
        host, port = server.address
        base = f"http://{host}:{port}"
        try:
            code = PairingManager(self.database).pairing_code
            paired = self._json_request(
                f"{base}/api/pair",
                {"code": code},
                origin=ORIGIN,
            )
            token = paired["data"]["token"]
            health = self._json_request(
                f"{base}/api/media/health",
                {"authToken": token},
                origin=ORIGIN,
            )
            plans = self._json_request(
                f"{base}/api/media/plans",
                {"authToken": token},
                origin=ORIGIN,
            )
            self.assertTrue(health["data"]["ok"])
            self.assertEqual(plans["data"], [])
        finally:
            server.stop()

    def test_authenticated_media_clear_endpoint_uses_safe_terminal_cleanup(self) -> None:
        server = LocalApiServer(self.database, host="127.0.0.1", port=0)
        server.start()
        host, port = server.address
        base = f"http://{host}:{port}"
        try:
            code = PairingManager(self.database).pairing_code
            paired = self._json_request(
                f"{base}/api/pair",
                {"code": code},
                origin=ORIGIN,
            )
            token = paired["data"]["token"]
            with patch.object(
                server.api.media,
                "clear_terminal_history",
                return_value=7,
            ) as clear_history:
                response = self._json_request(
                    f"{base}/api/media/clear",
                    {"authToken": token},
                    origin=ORIGIN,
                )

            self.assertEqual(response["data"], {"removed": 7})
            clear_history.assert_called_once_with()
        finally:
            server.stop()

    def test_authenticated_preview_and_open_folder_endpoints(self) -> None:
        server = LocalApiServer(self.database, host="127.0.0.1", port=0)
        server.start()
        host, port = server.address
        base = f"http://{host}:{port}"
        station_parent = Path(self.temp_dir.name) / "downloads"
        station = station_parent / "下载中转站"
        completed = station / "已完成"
        previews = station / "预览"
        completed.mkdir(parents=True)
        previews.mkdir(parents=True)
        output = completed / "finished.mp4"
        preview = previews / "plan.png"
        output.write_bytes(b"media")
        preview.write_bytes(b"\x89PNG\r\n\x1a\npreview")
        try:
            code = PairingManager(self.database).pairing_code
            paired = self._json_request(
                f"{base}/api/pair", {"code": code}, origin=ORIGIN
            )
            token = paired["data"]["token"]
            with (
                patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(station_parent)}),
                patch.object(server.api.media, "schedule"),
            ):
                created = self._json_request(
                    f"{base}/api/media/plan",
                    {
                        "pageUrl": "https://example.com/watch/1",
                        "pageTitle": "Generic video",
                        "outputName": "finished.mp4",
                        "outputContainer": "mp4",
                        "mergeMode": "direct",
                        "route": "desktop",
                        "importToEagle": False,
                        "streams": [{
                            "clientIndex": 0,
                            "url": "https://cdn.example.com/video.mp4",
                            "role": "video",
                            "name": "video.mp4",
                            "extension": "mp4",
                            "mimeType": "video/mp4",
                        }],
                        "runtimeHeaders": [{}],
                    },
                    origin=ORIGIN,
                    token=token,
                )
                plan_id = created["data"]["id"]
                with self.database.session() as connection:
                    connection.execute(
                        "UPDATE download_plans SET status = 'completed_local', progress = 100, final_path = ?, preview_path = ? WHERE id = ?",
                        (str(output), str(preview), plan_id),
                    )
                preview_result = self._get_json_request(
                    f"{base}/api/media/preview?id={plan_id}", origin=ORIGIN, token=token
                )
                with patch.object(os, "startfile", create=True) as startfile:
                    opened = self._json_request(
                        f"{base}/api/media/open", {"planId": plan_id}, origin=ORIGIN, token=token
                    )
                queued_import = self._json_request(
                    f"{base}/api/media/import", {"planId": plan_id}, origin=ORIGIN, token=token
                )

            self.assertTrue(preview_result["data"]["dataUrl"].startswith("data:image/png;base64,"))
            self.assertTrue(opened["data"]["opened"])
            self.assertEqual(queued_import["data"]["status"], "ready_to_import")
            self.assertIsNotNone(queued_import["data"]["job_id"])
            startfile.assert_called_once_with(str(completed.resolve()))
        finally:
            server.stop()

    @staticmethod
    def _json_request(
        url: str,
        payload: dict,
        *,
        origin: str,
        token: str | None = None,
    ) -> dict:
        headers = {"Content-Type": "application/json", "Origin": origin}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _get_json_request(url: str, *, origin: str, token: str) -> dict:
        request = Request(
            url,
            headers={"Origin": origin, "Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
