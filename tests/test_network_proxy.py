from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from idm_eagle_bridge.database import Database
from idm_eagle_bridge.network_proxy import (
    NetworkProxyManager,
    ProxyConfigurationError,
    normalize_proxy_url,
    proxy_endpoint_label,
)


class NetworkProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "proxy.db")
        self.manager = NetworkProxyManager(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_proxy_address_is_normalized_and_credentials_are_rejected(self) -> None:
        self.assertEqual(
            normalize_proxy_url("127.0.0.1:7890"),
            "http://127.0.0.1:7890",
        )
        self.assertEqual(
            proxy_endpoint_label("http://127.0.0.1:7890"),
            "127.0.0.1:7890",
        )
        with self.assertRaises(ProxyConfigurationError):
            normalize_proxy_url("socks5://127.0.0.1:1080")
        with self.assertRaises(ProxyConfigurationError):
            normalize_proxy_url("http://user:secret@127.0.0.1:7890")

    def test_default_auto_mode_follows_windows_proxy_then_falls_back_once(self) -> None:
        with (
            patch(
                "idm_eagle_bridge.network_proxy._windows_proxies",
                return_value={"http": "127.0.0.1:7890", "https": "127.0.0.1:7890"},
            ),
            patch("idm_eagle_bridge.network_proxy._environment_proxies", return_value={}),
            patch("idm_eagle_bridge.network_proxy.request.proxy_bypass", return_value=False),
        ):
            routes = self.manager.routes_for("https://www.behance.net/gallery/123")
            status = self.manager.status()
        self.assertEqual([route.source for route in routes], ["windows", "direct"])
        self.assertEqual(routes[0].url, "http://127.0.0.1:7890")
        self.assertIsNone(routes[1].url)
        self.assertTrue(status["active"])
        self.assertEqual(status["endpoint"], "127.0.0.1:7890")

    def test_local_service_is_never_sent_through_proxy(self) -> None:
        with patch(
            "idm_eagle_bridge.network_proxy._windows_proxies",
            return_value={"http": "127.0.0.1:7890"},
        ):
            routes = self.manager.routes_for("http://127.0.0.1:41595/api/v2/app/info")
        self.assertEqual(len(routes), 1)
        self.assertFalse(routes[0].enabled)

    def test_manual_and_direct_modes_are_persisted(self) -> None:
        configured = self.manager.configure("manual", "localhost:7890")
        self.assertEqual(configured["manualUrl"], "http://localhost:7890")
        routes = self.manager.routes_for("https://cdn.example/video.mp4")
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].source, "manual")
        self.assertEqual(routes[0].url, "http://localhost:7890")

        self.manager.configure("direct", configured["manualUrl"])
        direct = self.manager.routes_for("https://cdn.example/video.mp4")
        self.assertEqual(len(direct), 1)
        self.assertFalse(direct[0].enabled)
        self.assertEqual(self.manager.configuration()["manualUrl"], "http://localhost:7890")

    def test_proxy_bypass_rule_keeps_target_direct(self) -> None:
        with (
            patch(
                "idm_eagle_bridge.network_proxy._windows_proxies",
                return_value={"http": "127.0.0.1:7890"},
            ),
            patch("idm_eagle_bridge.network_proxy.request.proxy_bypass", return_value=True),
        ):
            routes = self.manager.routes_for("https://intranet.example/video.mp4")
        self.assertEqual([route.source for route in routes], ["direct"])

    def test_status_caches_expensive_system_detection(self) -> None:
        self.manager.configure("auto")
        with (
            patch(
                "idm_eagle_bridge.network_proxy._windows_proxies",
                return_value={"http": "127.0.0.1:7890"},
            ) as windows_proxies,
            patch("idm_eagle_bridge.network_proxy._environment_proxies", return_value={}),
            patch("idm_eagle_bridge.network_proxy.request.proxy_bypass", return_value=False),
        ):
            first = self.manager.status("https://example.com/video")
            second = self.manager.status("https://example.com/video")

        self.assertEqual(first, second)
        self.assertEqual(windows_proxies.call_count, 1)
        self.manager.configure("direct")
        self.assertEqual(
            self.manager.status("https://example.com/video")["source"],
            "direct",
        )


if __name__ == "__main__":
    unittest.main()
