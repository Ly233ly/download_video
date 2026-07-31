from __future__ import annotations

import json
import http.server
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import zlib
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from unittest.mock import Mock, patch

from idm_eagle_bridge.wechat_channels import (
    WechatCandidateRegistry,
    WechatChannelsCaptureService,
    WechatChannelsError,
    cleanup_wechat_capture,
)
from idm_eagle_bridge.database import Database
from idm_eagle_bridge.media import MediaCoordinator, resolve_media_tool
from idm_eagle_bridge.wechat_channels_certificate import WechatCertificateAuthority
from idm_eagle_bridge.wechat_channels_crypto import Isaac64, WechatVideoDecryptor
from idm_eagle_bridge.wechat_channels_proxy import (
    CaptureProxyError,
    ProxySnapshot,
    RegistryValue,
    WechatLoopbackProxy,
    WinInetProxyLease,
    proxy_endpoint_is_loopback,
    upstream_http_proxy,
    upstream_proxy_bypass,
    _decompress_limited,
)


def sample_candidate(object_id: str = "1234567890123456789") -> dict:
    return {
        "action": "candidate",
        "current": True,
        "objectId": object_id,
        "title": "同一条视频自己的标题",
        "author": "视频号作者",
        "sourceUrl": "https://channels.weixin.qq.com/web/pages/feed?objectId=123",
        "media": [
            {
                "url": "https://finder.video.qq.com/media/video.mp4?token=one",
                "urlToken": "&extra=two",
                "decodeKey": "123456789",
                "width": 1920,
                "height": 1080,
                "durationMs": 91234,
                "fileSize": 5_000_000,
                "coverUrl": "https://finder.video.qq.com/cover.jpg",
                "specs": [{
                    "fileFormat": "hd",
                    "width": 1920,
                    "height": 1080,
                    "durationMs": 91_234,
                    "bitrate": 4_000_000,
                }],
            }
        ],
    }


class CaptureServiceLifecycleTests(unittest.TestCase):
    def test_legacy_remote_command_channel_is_not_exposed(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        proxy_source = (
            project_root
            / "src"
            / "idm_eagle_bridge"
            / "wechat_channels_proxy.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn('CAPTURE_PATH + "/poll"', proxy_source)
        self.assertNotIn("enqueue_command", proxy_source)

    def test_health_caches_static_file_identity_and_counts_without_rendering_candidates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
            )
            bridge_path = Mock()
            bridge_path.read_bytes.return_value = b"bridge"
            try:
                service.registry.ingest(sample_candidate())
                with (
                    patch.object(
                        service.certificate,
                        "existing",
                        wraps=service.certificate.existing,
                    ) as existing,
                    patch.object(
                        service,
                        "bridge_script_path",
                        return_value=bridge_path,
                    ),
                    patch.object(
                        service.registry,
                        "list",
                        side_effect=AssertionError("health should use the O(1) count"),
                    ),
                ):
                    first = service.health()
                    second = service.health()

                self.assertEqual(first["candidateCount"], 1)
                self.assertEqual(second["candidateCount"], 1)
                self.assertEqual(existing.call_count, 1)
                self.assertEqual(bridge_path.read_bytes.call_count, 1)
            finally:
                service.close()
                coordinator.close()

    def test_candidates_can_be_cleared_without_stopping_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
            )
            try:
                service.state = "capturing"
                service.registry.ingest(sample_candidate())
                service._preview_cache["1234567890123456789"] = b"preview"
                service._preview_order.append("1234567890123456789")

                self.assertEqual(service.clear_candidates(), 1)
                self.assertEqual(service.candidates(), [])
                self.assertEqual(service.state, "capturing")
                self.assertEqual(service._preview_cache, {})
                self.assertEqual(service._preview_order, [])
            finally:
                service.close()
                coordinator.close()

    def test_trusted_certificate_is_reused_without_reinstalling_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            proxy = Mock()
            proxy.address = ("127.0.0.1", 20230)
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
                proxy_factory=Mock(return_value=proxy),
            )
            try:
                service.certificate.ensure()
                with (
                    patch.object(
                        service.certificate,
                        "is_trusted",
                        return_value=True,
                    ),
                    patch.object(service.certificate, "install") as install,
                ):
                    health = service.start(
                        configure_system_proxy=False,
                        trust_certificate=True,
                    )
                install.assert_not_called()
                self.assertTrue(health["certificateTrusted"])
            finally:
                service.close()
                coordinator.close()

    def test_start_reports_an_unreachable_loopback_proxy_as_repairable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
            )
            service.proxy_lease.backend = FakeRegistryBackend(
                ProxySnapshot(
                    {
                        "ProxyEnable": RegistryValue(True, 1, 4),
                        "ProxyServer": RegistryValue(True, "127.0.0.1:6553", 1),
                    }
                )
            )
            try:
                with patch(
                    "idm_eagle_bridge.wechat_channels.proxy_endpoint_reachable",
                    return_value=False,
                ):
                    with self.assertRaisesRegex(
                        WechatChannelsError,
                        "修复代理冲突",
                    ):
                        service.start(
                            configure_system_proxy=False,
                            trust_certificate=False,
                        )
                self.assertEqual(service.health()["state"], "failed")
            finally:
                service.close()
                coordinator.close()

    def test_proxy_repair_clears_only_an_unreachable_loopback_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            backend = FakeRegistryBackend(
                ProxySnapshot(
                    {
                        "ProxyEnable": RegistryValue(True, 1, 4),
                        "ProxyServer": RegistryValue(True, "127.0.0.1:6553", 1),
                    }
                )
            )
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
            )
            service.proxy_lease.backend = backend
            try:
                with patch(
                    "idm_eagle_bridge.wechat_channels.proxy_endpoint_reachable",
                    return_value=False,
                ):
                    result = service.repair_proxy_conflict()
                self.assertTrue(result["changed"])
                self.assertEqual(
                    backend.current.values["ProxyEnable"].value,
                    0,
                )
                self.assertEqual(
                    backend.current.values["ProxyServer"].value,
                    "127.0.0.1:6553",
                )
            finally:
                service.close()
                coordinator.close()

    def test_running_capture_reclaims_proxy_and_restores_latest_external_proxy(self) -> None:
        class FakeProxy:
            address = ("127.0.0.1", 20230)

            def start(self) -> None:
                return None

            def stop(self) -> None:
                return None

        direct = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 0, 4),
                "ProxyServer": RegistryValue(False),
            }
        )
        external = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "10.0.0.2:7890", 1),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            backend = FakeRegistryBackend(direct)
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
                proxy_factory=lambda *_args, **_kwargs: FakeProxy(),  # type: ignore[arg-type]
            )
            service.proxy_lease.backend = backend
            try:
                service.start(trust_certificate=False)
                backend.current = external

                result = service.repair_proxy_conflict()

                self.assertTrue(result["changed"])
                self.assertEqual(
                    backend.current.values["ProxyServer"].value,
                    "127.0.0.1:20230",
                )
                self.assertEqual(
                    service.proxy.upstream_proxy,
                    ("10.0.0.2", 7890),
                )
                service.stop()
                self.assertEqual(backend.current, external)
            finally:
                service.close()
                coordinator.close()

    def test_explicit_start_candidate_submit_and_stop_share_one_media_coordinator(self) -> None:
        proxies = []

        class FakeProxy:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.address = ("127.0.0.1", 20230)
                self.started = False
                self.stopped = False
                proxies.append(self)

            def start(self) -> None:
                self.started = True

            def stop(self) -> None:
                self.stopped = True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            coordinator.schedule = lambda _plan_id: None  # type: ignore[method-assign]
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
                proxy_factory=FakeProxy,  # type: ignore[arg-type]
            )
            try:
                health = service.start(configure_system_proxy=False, trust_certificate=False)
                self.assertEqual(health["state"], "waiting_wechat")
                self.assertTrue(health["running"])
                self.assertTrue(proxies[0].started)

                service._handle_page_message(
                    sample_candidate(),
                    {
                        "User-Agent": "WechatDesktop/1.0",
                        "Referer": "https://finder.video.qq.com/media/video.mp4",
                    },
                )
                self.assertEqual(service.health()["state"], "capturing")
                self.assertEqual(service.health()["candidateCount"], 1)
                plan = service.submit("1234567890123456789", import_to_eagle=False)
                self.assertEqual(plan["route"], "desktop")
                stored = coordinator.get_plan(str(plan["id"]))
                self.assertFalse(stored["import_to_eagle"])
                runtime_stream = coordinator._remote_inputs[str(plan["id"])]["streams"][0]
                self.assertEqual(runtime_stream["wechat_decode_key"], 123456789)

                stopped = service.stop()
                self.assertEqual(stopped["state"], "off")
                self.assertEqual(stopped["candidateCount"], 0)
                self.assertTrue(proxies[0].stopped)
                self.assertFalse(service.stop()["running"])
            finally:
                service.close()
                coordinator.close()

    def test_page_download_action_creates_the_selected_variant_and_imports_to_eagle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = MediaCoordinator(Database(root / "bridge.db"))
            coordinator.schedule = lambda _plan_id: None  # type: ignore[method-assign]
            service = WechatChannelsCaptureService(
                coordinator,
                root=root / "wechat-channels",
            )
            try:
                captured = service._handle_page_message(
                    sample_candidate(),
                    {
                        "User-Agent": "WechatDesktop/1.0",
                        "Referer": "https://finder.video.qq.com/media/video.mp4",
                    },
                )
                candidate = captured["candidate"]
                selected = next(
                    variant
                    for variant in candidate["variants"]
                    if variant["deliverySpec"] == "hd"
                )
                created = service._handle_page_message(
                    {
                        "action": "download",
                        "objectId": candidate["objectId"],
                        "variantId": selected["id"],
                    },
                    {},
                )
                plan = coordinator.get_plan(created["plan"]["id"])
                self.assertTrue(plan["import_to_eagle"])
                self.assertTrue(plan["delete_after_import"])
                self.assertIn(
                    "X-snsvideoflag=hd",
                    coordinator._remote_inputs[str(plan["id"])]["streams"][0]["url"],
                )
                with self.assertRaisesRegex(WechatChannelsError, "质量已过期"):
                    service._handle_page_message(
                        {
                            "action": "download",
                            "objectId": candidate["objectId"],
                            "variantId": "not-a-server-variant",
                        },
                        {},
                    )
            finally:
                service.close()
                coordinator.close()

    def test_external_proxy_change_blocks_restart_and_preserves_recovery_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = ProxySnapshot({
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
            })
            backend = FakeRegistryBackend(original)
            path = root / "capture" / "proxy-lease.json"
            lease = WinInetProxyLease(path, backend)  # type: ignore[arg-type]
            lease.acquire("127.0.0.1:20230")
            backend.current = ProxySnapshot({
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:10809", 1),
            })
            database = Database(root / "bridge.db")
            coordinator = MediaCoordinator(database)
            # Use a different root so __init__ doesn't encounter the stale lease
            # and clean it up before we can test the recovery path.
            service = WechatChannelsCaptureService(
                coordinator,
                root / "service",
                proxy_factory=lambda *_args, **_kwargs: self.fail("proxy must not start"),
            )
            service.proxy_lease = lease
            service.state = "needs_recovery"
            service.error = "外部代理已经改变"
            try:
                with self.assertRaisesRegex(WechatChannelsError, "外部代理"):
                    service.start(trust_certificate=False)
                self.assertTrue(path.exists())
                service._system_proxy_configured = True
                health = service.stop()
                self.assertEqual(health["state"], "needs_recovery")
                self.assertTrue(path.exists())
            finally:
                coordinator.close()

    def test_stop_attempts_system_proxy_restore_before_closing_listener(self) -> None:
        events: list[str] = []

        class FakeProxy:
            address = ("127.0.0.1", 20230)

            def stop(self) -> None:
                events.append("proxy.stop")

        class FakeLease:
            snapshot = object()
            path = Path("unused-proxy-lease.json")

            def release(self) -> bool:
                events.append("lease.release")
                self.snapshot = None
                return True

        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            service = WechatChannelsCaptureService(
                coordinator,
                root=Path(directory) / "capture",
            )
            service.proxy = FakeProxy()  # type: ignore[assignment]
            service.proxy_lease = FakeLease()  # type: ignore[assignment]
            service._system_proxy_configured = True
            try:
                health = service.stop()
                self.assertEqual(events, ["lease.release", "proxy.stop"])
                self.assertEqual(health["state"], "off")
            finally:
                coordinator.close()

    def test_start_failure_restores_lease_before_closing_listener(self) -> None:
        events: list[str] = []
        original = ProxySnapshot({
            "ProxyEnable": RegistryValue(True, 1, 4),
            "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
        })

        class FakeProxy:
            address = ("127.0.0.1", 20230)

            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def start(self) -> None:
                events.append("proxy.start")

            def stop(self) -> None:
                events.append("proxy.stop")

        class FakeBackend:
            def snapshot(self) -> ProxySnapshot:
                return original

        class FakeLease:
            backend = FakeBackend()
            snapshot: object | None = None
            path = Path("unused-start-failure-lease.json")

            def acquire(self, endpoint: str) -> ProxySnapshot:
                events.append("lease.acquire")
                self.snapshot = object()
                raise CaptureProxyError("设置本机代理失败")

            def release(self) -> bool:
                events.append("lease.release")
                self.snapshot = None
                return True

        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            service = WechatChannelsCaptureService(
                coordinator,
                root=Path(directory) / "capture",
                proxy_factory=FakeProxy,  # type: ignore[arg-type]
            )
            service.proxy_lease = FakeLease()  # type: ignore[assignment]
            try:
                # The fake snapshot points at 127.0.0.1:7890; treat it as
                # reachable so the start failure happens at lease.acquire and
                # not at the stale-proxy preflight (which depends on the local
                # port state and would make this test environment-sensitive).
                with patch(
                    "idm_eagle_bridge.wechat_channels.proxy_endpoint_reachable",
                    return_value=True,
                ):
                    with self.assertRaisesRegex(
                        WechatChannelsError, "设置本机代理失败"
                    ):
                        service.start(trust_certificate=False)
                self.assertEqual(
                    events,
                    ["proxy.start", "lease.acquire", "lease.release", "proxy.stop"],
                )
                self.assertEqual(service.health()["state"], "failed")
            finally:
                coordinator.close()

    def test_start_resets_needs_recovery_when_system_proxy_is_disabled(self) -> None:
        events: list[str] = []
        disabled = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 0, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:20230", 1),
            }
        )

        class FakeProxy:
            address = ("127.0.0.1", 20230)

            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def start(self) -> None:
                events.append("proxy.start")

            def stop(self) -> None:
                events.append("proxy.stop")

        class FakeBackend:
            def snapshot(self) -> ProxySnapshot:
                return disabled

        class FakeLease:
            backend = FakeBackend()
            snapshot: object | None = None
            path = Path("unused-needs-recovery.json")

            def recover_orphan(self) -> bool:
                return False

            def acquire(self, endpoint: str) -> ProxySnapshot:
                self.snapshot = disabled
                return disabled

        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            service = WechatChannelsCaptureService(
                coordinator,
                root=Path(directory) / "capture",
                proxy_factory=FakeProxy,  # type: ignore[arg-type]
            )
            service.proxy_lease = FakeLease()  # type: ignore[assignment]
            service.state = "needs_recovery"
            service.error = "系统代理已被其他程序修改，未覆盖当前设置"
            try:
                health = service.start(trust_certificate=False)
                self.assertEqual(health["state"], "waiting_wechat")
                self.assertEqual(service.error, "")
                self.assertEqual(service.error_code, "")
            finally:
                coordinator.close()

    def test_proxy_repair_clears_stale_loopback_when_disabled(self) -> None:
        stale = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 0, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:20230", 1),
                "ProxyOverride": RegistryValue(True, "<local>;127.*;localhost", 1),
            }
        )

        class FakeBackend:
            def __init__(self) -> None:
                self.current = stale
                self.restored: ProxySnapshot | None = None

            def snapshot(self) -> ProxySnapshot:
                return self.current

            def restore(self, snapshot: ProxySnapshot) -> None:
                self.restored = snapshot
                self.current = snapshot

            def disable_manual_proxy(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            service = WechatChannelsCaptureService(
                coordinator,
                root=Path(directory) / "capture",
            )
            service.proxy_lease.backend = FakeBackend()  # type: ignore[assignment]
            service.state = "needs_recovery"
            try:
                with patch(
                    "idm_eagle_bridge.wechat_channels.proxy_endpoint_reachable",
                    return_value=False,
                ):
                    result = service.repair_proxy_conflict()
                self.assertTrue(result["changed"])
                self.assertEqual(service.state, "off")
                self.assertEqual(service.error, "")
                self.assertEqual(service.error_code, "")
                self.assertFalse(
                    service.proxy_lease.backend.current.values["ProxyServer"].exists
                )
            finally:
                coordinator.close()


class Isaac64Tests(unittest.TestCase):
    def test_public_domain_isaac64_seed_vector(self) -> None:
        generator = Isaac64(1)
        self.assertEqual(
            [generator.next_u64() for _ in range(3)],
            [0xE19ED5D2CA98AF2D, 0xA7A18D07CAB39B52, 0xA0AB0232D180AF14],
        )

    def test_stream_decrypt_is_chunk_boundary_independent_and_preserves_tail(self) -> None:
        plaintext = bytes(range(256)) * 1024
        encrypted = WechatVideoDecryptor(987654321, 131_072).transform(plaintext)
        decryptor = WechatVideoDecryptor(987654321, 131_072)
        restored = b"".join(
            decryptor.transform(encrypted[index : index + size])
            for index, size in ((0, 3), (3, 4093), (4096, 70_000), (74_096, len(encrypted)))
        )
        self.assertEqual(restored, plaintext)
        self.assertEqual(encrypted[131_072:], plaintext[131_072:])

    def test_wrong_key_does_not_produce_the_plaintext(self) -> None:
        plaintext = b"video-header" * 20_000
        encrypted = WechatVideoDecryptor(12345).transform(plaintext)
        self.assertNotEqual(WechatVideoDecryptor(54321).transform(encrypted), plaintext)


class CertificateTests(unittest.TestCase):
    def test_generated_chain_loads_in_python_tls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            files = WechatCertificateAuthority(directory).ensure()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(files.leaf_pem, files.leaf_key)
            self.assertEqual(len(files.fingerprint), 40)
            self.assertNotEqual(files.root_key.read_bytes(), files.leaf_key.read_bytes())
            metadata = json.loads((Path(directory) / "certificate.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["fingerprint"], files.fingerprint)
            self.assertIn("res.wx.qq.com", metadata["dnsNames"])

            context = ssl.create_default_context(cafile=str(files.root_pem))
            context.set_alpn_protocols(["http/1.1"])
            self.assertIn("res.wx.qq.com", WechatCertificateAuthority.DNS_NAMES)

    def test_uninstall_without_existing_certificate_does_not_generate_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "missing"
            authority = WechatCertificateAuthority(root)
            self.assertFalse(authority.uninstall())
            self.assertFalse(root.exists())

    def test_legacy_leaf_is_rotated_without_replacing_the_trusted_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            authority = WechatCertificateAuthority(directory)
            first = authority.ensure()
            root_before = first.root_der.read_bytes()
            leaf_before = first.leaf_pem.read_bytes()
            metadata_path = Path(directory) / "certificate.json"
            metadata_path.write_text(
                json.dumps({"fingerprint": first.fingerprint, "subject": authority.ROOT_NAME}, ensure_ascii=False),
                encoding="utf-8",
            )

            migrated = authority.ensure()

            self.assertEqual(migrated.fingerprint, first.fingerprint)
            self.assertEqual(migrated.root_der.read_bytes(), root_before)
            self.assertNotEqual(migrated.leaf_pem.read_bytes(), leaf_before)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["leafProfile"], authority.LEAF_PROFILE)
            self.assertIn("res.wx.qq.com", metadata["dnsNames"])


class CandidateRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = WechatCandidateRegistry()

    def test_candidate_view_groups_rotating_urls_without_leaking_context(self) -> None:
        first = sample_candidate()
        self.registry.ingest(first)
        second = sample_candidate()
        second["title"] = "更新后的同一内容标题"
        second["media"][0]["urlToken"] = "&extra=rotated"
        self.registry.ingest(second)
        view = self.registry.list()
        self.assertEqual(len(view), 1)
        self.assertEqual(view[0]["groupKey"], "wechat-channel:1234567890123456789")
        self.assertEqual(view[0]["title"], "更新后的同一内容标题")
        serialized = json.dumps(view, ensure_ascii=False)
        self.assertNotIn("decodeKey", serialized)
        self.assertNotIn("token=one", serialized)

    def test_candidate_list_only_exposes_the_current_video(self) -> None:
        with patch(
            "idm_eagle_bridge.wechat_channels.time.time",
            side_effect=[1.0, 2.0, 3.0],
        ):
            self.registry.ingest(sample_candidate("first"))
            self.registry.ingest(sample_candidate("second"))
            self.assertEqual(
                [item["objectId"] for item in self.registry.list()],
                ["second"],
            )
            self.registry.ingest(sample_candidate("first"))

        self.assertEqual(
            [item["objectId"] for item in self.registry.list()],
            ["first"],
        )

    def test_preloads_stay_hidden_and_stale_activation_cannot_replace_current(self) -> None:
        first = sample_candidate("first")
        second = sample_candidate("second")
        self.registry.ingest(first, make_current=False)
        self.registry.ingest(second, make_current=False)
        self.assertEqual(self.registry.list(), [])

        current, activated = self.registry.activate("second", 300)
        self.assertTrue(activated)
        self.assertEqual(current["objectId"], "second")

        current, activated = self.registry.activate("first", 250)
        self.assertFalse(activated)
        self.assertEqual(current["objectId"], "second")
        self.assertEqual(self.registry.list()[0]["objectId"], "second")

    def test_candidate_registry_evicts_oldest_at_session_limit(self) -> None:
        with patch(
            "idm_eagle_bridge.wechat_channels.time.time",
            side_effect=[float(index) for index in range(WechatCandidateRegistry.MAX_CANDIDATES + 1)],
        ):
            for index in range(WechatCandidateRegistry.MAX_CANDIDATES + 1):
                self.registry.ingest(sample_candidate(f"bounded-{index}"))

        self.assertEqual(
            self.registry.retained_count(),
            WechatCandidateRegistry.MAX_CANDIDATES,
        )
        evicted, activated = self.registry.activate("bounded-0")
        self.assertIsNone(evicted)
        self.assertFalse(activated)
        self.assertEqual(
            self.registry.list()[0]["objectId"],
            f"bounded-{WechatCandidateRegistry.MAX_CANDIDATES}",
        )

    def test_plan_uses_selected_variant_and_keeps_secret_only_in_runtime_payload(self) -> None:
        candidate = self.registry.ingest(
            sample_candidate(),
            {
                "User-Agent": "WechatDesktop/1.0",
                "Referer": "https://channels.weixin.qq.com/web/pages/feed?secret=memory-only",
                "Cookie": "session=must-not-cross-domains",
            },
        )
        variant_id = next(iter(candidate.variants))
        payload = self.registry.plan_payload(
            candidate.object_id,
            variant_id,
            import_to_eagle=True,
            delete_after_import=True,
        )
        self.assertEqual(payload["sourceType"], "wechat_channels")
        self.assertEqual(payload["streams"][0]["wechatDecodeKey"], "123456789")
        self.assertTrue(payload["importToEagle"])
        self.assertTrue(payload["deleteAfterImport"])
        self.assertEqual(payload["mergeMode"], "direct")
        self.assertEqual(payload["streams"][0]["headers"]["User-Agent"], "WechatDesktop/1.0")
        self.assertNotIn("Cookie", payload["streams"][0]["headers"])

    def test_quality_spec_becomes_a_selectable_delivery_variant(self) -> None:
        candidate = self.registry.ingest(sample_candidate())
        self.assertEqual(len(candidate.variants), 2)
        spec_variant = next(
            variant for variant in candidate.variants.values() if variant.delivery_spec == "hd"
        )
        view = spec_variant.view()
        self.assertEqual(view["deliverySpec"], "hd")
        self.assertIn("1080p", view["quality"])
        self.assertEqual(view["fileSize"], 0)
        payload = self.registry.plan_payload(candidate.object_id, spec_variant.variant_id)
        selected_url = urlsplit(payload["streams"][0]["url"])
        self.assertEqual(
            selected_url.query,
            "token=one&extra=two&X-snsvideoflag=hd",
        )
        self.assertIn(("X-snsvideoflag", "hd"), parse_qsl(selected_url.query))

    def test_private_or_untrusted_media_url_is_rejected(self) -> None:
        payload = sample_candidate()
        payload["media"][0]["url"] = "https://127.0.0.1/private.mp4"
        with self.assertRaisesRegex(WechatChannelsError, "可用"):
            self.registry.ingest(payload)

    def test_zero_key_is_clear_and_portrait_quality_uses_short_edge(self) -> None:
        payload = sample_candidate()
        payload["media"][0].update(
            {"decodeKey": "0", "width": 1080, "height": 1440, "coverUrl": "http://example.com/cover.jpg"}
        )
        candidate = self.registry.ingest(payload)
        view = candidate.view()
        self.assertEqual(view["variants"][0]["quality"], "1080p · 原始/最高")
        self.assertFalse(view["variants"][0]["encrypted"])
        self.assertTrue(view["coverUrl"].startswith("http://"))


class WechatBridgeSelectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for bridge validation")
    def test_preloads_are_bounded_and_only_active_video_is_published(self) -> None:
        bridge_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "idm_eagle_bridge"
            / "assets"
            / "wechat_channels_bridge.js"
        )
        script = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1], "utf8");
const requests = [];
globalThis.__DOWNLOAD_STATION_TEST__ = true;
globalThis.location = { href: "https://channels.weixin.qq.com/web/pages/feed" };
globalThis.document = {
  readyState: "loading",
  documentElement: null,
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  getElementById: function (id) {
    return id === "download-station-wechat-control" ? { style: {} } : null;
  },
};
globalThis.window = globalThis;
window.addEventListener = function () {};
globalThis.MutationObserver = undefined;
globalThis.Response = undefined;
globalThis.XMLHttpRequest = function () {};
XMLHttpRequest.prototype.open = function () {};
window.fetch = function (_url, options) {
  const payload = JSON.parse(options.body);
  requests.push(payload);
  if (payload.action === "candidate") {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          action: "candidate",
          candidate: { objectId: payload.objectId, variants: [{ id: "auto" }] },
        });
      },
    });
  }
  return Promise.resolve({
    ok: true,
    json: function () {
      return Promise.resolve({
        action: "active",
        accepted: true,
        candidate: { objectId: payload.objectId },
      });
    },
  });
};
eval(source);

function feed(id) {
  return {
    id: id,
    objectDesc: {
      description: "视频 " + id,
      media: [{ url: "https://finder.video.qq.com/" + id + ".mp4" }],
    },
  };
}
function waitForRequests() {
  return new Promise(function (resolve) { setTimeout(resolve, 25); });
}

(async function () {
  const test = globalThis.__DOWNLOAD_STATION_WECHAT_TEST__;
  const preload = [];
  for (let index = 0; index < 100; index += 1) {
    preload.push(feed("preload-" + index));
  }
  test.scan({ items: preload }, "finderGetRecommend");
  await waitForRequests();
  if (requests.some(function (item) { return item.action === "candidate"; })) process.exit(2);
  if (test.seenCount() > 64) process.exit(3);

  test.scan(feed("current-a"), "finderGetCommentDetail");
  await waitForRequests();
  test.scan(feed("current-b"), "goToNextFlowFeed");
  await waitForRequests();

  const candidates = requests.filter(function (item) { return item.action === "candidate"; });
  const active = requests.filter(function (item) { return item.action === "active"; });
  if (candidates.map(function (item) { return item.objectId; }).join(",") !== "current-a,current-b") {
    process.exit(4);
  }
  if (candidates.some(function (item) { return item.current !== false; })) process.exit(5);
  if (active.map(function (item) { return item.objectId; }).join(",") !== "current-a,current-b") {
    process.exit(6);
  }
})().catch(function () { process.exit(7); });
"""
        result = subprocess.run(
            ["node", "-e", script, str(bridge_path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class WechatMediaDownloadTests(unittest.TestCase):
    def test_complete_encrypted_video_reaches_completed_local_and_ffprobe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plain = root / "plain.mp4"
            subprocess.run(
                [
                    str(resolve_media_tool("ffmpeg")), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(plain),
                ],
                check=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            key = 99887766
            encrypted = WechatVideoDecryptor(key).transform(plain.read_bytes())

            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, _format: str, *args: object) -> None:
                    return

                def do_GET(self) -> None:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(encrypted)))
                    self.end_headers()
                    self.wfile.write(encrypted)

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            database = Database(root / "bridge.db")
            coordinator = MediaCoordinator(database)
            try:
                payload = {
                    "sourceType": "wechat_channels",
                    "groupKey": "wechat-channel:integration-test",
                    "pageTitle": "加密视频号集成测试",
                    "pageUrl": "",
                    "thumbnailUrl": "",
                    "outputName": "加密视频号集成测试.mp4",
                    "outputContainer": "mp4",
                    "mergeMode": "direct",
                    "importToEagle": False,
                    "runtimeHeaders": [{}],
                    "streams": [{
                        "role": "video",
                        "url": f"http://127.0.0.1:{server.server_port}/video.mp4",
                        "extension": "mp4",
                        "mimeType": "video/mp4",
                        "width": 320,
                        "height": 240,
                        "duration": 1,
                        "size": len(encrypted),
                        "wechatDecodeKey": str(key),
                        "wechatEncryptedBytes": 131_072,
                    }],
                }
                with patch.dict(os.environ, {"IDM_EAGLE_DOWNLOAD_ROOT": str(root / "downloads")}):
                    plan = coordinator.create_plan(payload)
                    deadline = time.time() + 30
                    result = coordinator.get_plan(plan["id"])
                    while time.time() < deadline and result["status"] in {
                        "queued", "downloading", "merging", "validating"
                    }:
                        time.sleep(0.1)
                        result = coordinator.get_plan(plan["id"])
                self.assertEqual(result["status"], "completed_local", result.get("error_message"))
                final_path = Path(result["final_path"])
                self.assertTrue(final_path.is_file())
                probe = subprocess.run(
                    [
                        str(resolve_media_tool("ffprobe")), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "json", str(final_path),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                    timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                stream = json.loads(probe.stdout)["streams"][0]
                self.assertEqual((stream["width"], stream["height"]), (320, 240))
            finally:
                coordinator.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_secret_url_headers_and_key_are_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            coordinator.schedule = lambda _plan_id: None  # type: ignore[method-assign]
            registry = WechatCandidateRegistry()
            candidate = registry.ingest(
                sample_candidate(),
                {
                    "User-Agent": "WechatDesktop/1.0",
                    "Referer": "https://finder.video.qq.com/watch",
                    "Cookie": "session=database-must-not-contain-this",
                },
            )
            payload = registry.plan_payload(candidate.object_id)
            plan = coordinator.create_plan(payload)
            try:
                with database.session() as connection:
                    persisted = json.dumps(
                        {
                            table: [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
                            for table in ("capture_sessions", "media_groups", "media_streams", "download_plans")
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                self.assertNotIn("token=one", persisted)
                self.assertNotIn("extra=two", persisted)
                self.assertNotIn("database-must-not-contain-this", persisted)
                self.assertNotIn("123456789", persisted)
                self.assertEqual(
                    coordinator._remote_inputs[plan["id"]]["streams"][0]["wechat_decode_key"],
                    123456789,
                )
            finally:
                coordinator.close()

    def test_encrypted_prefix_is_streamed_to_plain_local_input(self) -> None:
        plaintext = b"plain-mp4-test" * 30_000
        encrypted = WechatVideoDecryptor(778899, 131_072).transform(plaintext)

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", str(len(encrypted)))
                self.end_headers()
                self.wfile.write(encrypted)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "bridge.db")
            coordinator = MediaCoordinator(database)
            target = Path(directory) / "decrypted.mp4"
            try:
                context = {
                    "url": f"http://127.0.0.1:{server.server_port}/video",
                    "headers": {},
                    "size": len(encrypted),
                    "wechat_decode_key": 778899,
                    "wechat_encrypted_bytes": 131_072,
                    "role": "video",
                }
                result = coordinator._download_and_decrypt_wechat_stream(
                    "missing-plan-is-safe", context, target
                )
                self.assertEqual(target.read_bytes(), plaintext)
                self.assertTrue(result["local_input"])
                self.assertIsNone(result["wechat_decode_key"])
            finally:
                coordinator.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class FakeRegistryBackend:
    def __init__(self, snapshot: ProxySnapshot) -> None:
        self.current = snapshot
        self.restored: ProxySnapshot | None = None

    def snapshot(self) -> ProxySnapshot:
        return self.current

    def apply_local(self, endpoint: str, bypass: str) -> None:
        self.current = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, endpoint, 1),
                "ProxyOverride": RegistryValue(True, bypass, 1),
            }
        )

    def restore(self, snapshot: ProxySnapshot) -> None:
        self.restored = snapshot
        self.current = snapshot

    def disable_manual_proxy(self) -> None:
        values = dict(self.current.values)
        values["ProxyEnable"] = RegistryValue(True, 0, 4)
        self.current = ProxySnapshot(values)


class FailingApplyRegistryBackend(FakeRegistryBackend):
    def __init__(self, snapshot: ProxySnapshot, *, fail_restore: bool = False) -> None:
        super().__init__(snapshot)
        self.fail_restore = fail_restore

    def apply_local(self, endpoint: str, bypass: str) -> None:
        super().apply_local(endpoint, bypass)
        raise OSError("simulated proxy notification failure")

    def restore(self, snapshot: ProxySnapshot) -> None:
        if self.fail_restore:
            raise OSError("simulated restore failure")
        super().restore(snapshot)


class ProxyLeaseTests(unittest.TestCase):
    def test_snapshot_round_trips_binary_connection_settings(self) -> None:
        snapshot = ProxySnapshot(
            {
                "Connections/DefaultConnectionSettings": RegistryValue(True, b"\x01\x02\xff", 3),
            }
        )
        restored = ProxySnapshot.from_json(snapshot.to_json())
        self.assertEqual(
            restored.values["Connections/DefaultConnectionSettings"],
            RegistryValue(True, b"\x01\x02\xff", 3),
        )

    def test_existing_proxy_and_bypass_rules_are_parsed(self) -> None:
        snapshot = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "http=127.0.0.1:8080;https=127.0.0.1:7890", 1),
                "ProxyOverride": RegistryValue(True, "<local>;*.internal.example", 1),
            }
        )
        self.assertEqual(upstream_http_proxy(snapshot), ("127.0.0.1", 7890))
        self.assertEqual(upstream_proxy_bypass(snapshot), ("<local>", "*.internal.example"))
        self.assertTrue(proxy_endpoint_is_loopback(("127.0.0.1", 7890)))
        self.assertFalse(proxy_endpoint_is_loopback(("10.0.0.2", 7890)))

    def test_exact_restore_and_external_change_protection(self) -> None:
        original = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
                "ProxyOverride": RegistryValue(False),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeRegistryBackend(original)
            lease = WinInetProxyLease(Path(directory) / "lease.json", backend)  # type: ignore[arg-type]
            lease.acquire("127.0.0.1:20230")
            self.assertTrue(lease.release())
            self.assertEqual(backend.restored, original)

            lease.acquire("127.0.0.1:20230")
            backend.current = ProxySnapshot(
                {
                    "ProxyEnable": RegistryValue(True, 1, 4),
                    "ProxyServer": RegistryValue(True, "127.0.0.1:10809", 1),
                }
            )
            self.assertFalse(lease.release())
            self.assertNotEqual(backend.current, original)

    def test_release_recovers_when_own_proxy_was_disabled_externally(self) -> None:
        original = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 0, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeRegistryBackend(original)
            lease = WinInetProxyLease(Path(directory) / "lease.json", backend)  # type: ignore[arg-type]
            lease.acquire("127.0.0.1:20230")
            # 外部把本实例设置的代理禁用，但 ProxyServer 仍残留本实例 endpoint
            backend.current = ProxySnapshot(
                {
                    "ProxyEnable": RegistryValue(True, 0, 4),
                    "ProxyServer": RegistryValue(True, "127.0.0.1:20230", 1),
                }
            )
            self.assertTrue(lease.release())
            self.assertEqual(backend.restored, original)
            self.assertFalse(lease.path.exists())

    def test_recover_orphan_recovers_when_own_proxy_was_disabled_externally(self) -> None:
        original = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 0, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeRegistryBackend(original)
            path = Path(directory) / "lease.json"
            WinInetProxyLease(path, backend).acquire("127.0.0.1:20230")  # type: ignore[arg-type]
            backend.current = ProxySnapshot(
                {
                    "ProxyEnable": RegistryValue(True, 0, 4),
                    "ProxyServer": RegistryValue(True, "127.0.0.1:20230", 1),
                }
            )
            recovery = WinInetProxyLease(path, backend)  # type: ignore[arg-type]
            self.assertTrue(recovery.recover_orphan())
            self.assertEqual(
                backend.restored.values["ProxyEnable"], original.values["ProxyEnable"]
            )
            self.assertEqual(
                backend.restored.values["ProxyServer"], original.values["ProxyServer"]
            )
            self.assertFalse(path.exists())

    def test_partial_apply_failure_restores_original_before_removing_lease(self) -> None:
        original = ProxySnapshot({
            "ProxyEnable": RegistryValue(True, 1, 4),
            "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lease.json"
            backend = FailingApplyRegistryBackend(original)
            lease = WinInetProxyLease(path, backend)  # type: ignore[arg-type]
            with self.assertRaisesRegex(OSError, "notification"):
                lease.acquire("127.0.0.1:20230")
            self.assertEqual(backend.current, original)
            self.assertFalse(path.exists())
            self.assertIsNone(lease.snapshot)

    def test_failed_apply_and_restore_preserve_recoverable_lease(self) -> None:
        original = ProxySnapshot({
            "ProxyEnable": RegistryValue(True, 1, 4),
            "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lease.json"
            backend = FailingApplyRegistryBackend(original, fail_restore=True)
            lease = WinInetProxyLease(path, backend)  # type: ignore[arg-type]
            with self.assertRaisesRegex(CaptureProxyError, "恢复记录已保留"):
                lease.acquire("127.0.0.1:20230")
            self.assertTrue(path.exists())
            self.assertEqual(lease.snapshot, original)

    def test_cleanup_deletes_stale_lease_even_when_ownership_was_lost(self) -> None:
        original = ProxySnapshot({
            "ProxyEnable": RegistryValue(True, 1, 4),
            "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "capture"
            path = root / "proxy-lease.json"
            backend = FakeRegistryBackend(original)
            lease = WinInetProxyLease(path, backend)  # type: ignore[arg-type]
            lease.acquire("127.0.0.1:20230")
            backend.current = ProxySnapshot({
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:10809", 1),
            })
            with patch(
                "idm_eagle_bridge.wechat_channels.WinInetProxyLease",
                return_value=WinInetProxyLease(path, backend),  # type: ignore[arg-type]
            ):
                result = cleanup_wechat_capture(root)
            self.assertFalse(path.exists())
            self.assertFalse(result["proxyRestored"])

    def test_orphan_lease_restores_only_owned_proxy(self) -> None:
        original = ProxySnapshot(
            {
                "ProxyEnable": RegistryValue(True, 1, 4),
                "ProxyServer": RegistryValue(True, "127.0.0.1:7890", 1),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeRegistryBackend(original)
            path = Path(directory) / "lease.json"
            WinInetProxyLease(path, backend).acquire("127.0.0.1:20230")
            recovery = WinInetProxyLease(path, backend)
            self.assertTrue(recovery.recover_orphan())
            self.assertEqual(backend.current.values["ProxyEnable"], original.values["ProxyEnable"])
            self.assertEqual(backend.current.values["ProxyServer"], original.values["ProxyServer"])
            self.assertFalse(path.exists())


class LoopbackProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.files = WechatCertificateAuthority(Path(self.temporary.name) / "certificate").ensure()
        self.payloads: list[dict] = []
        self.contexts: list[dict[str, str]] = []

        def capture(payload: dict, headers: dict[str, str]) -> dict:
            self.payloads.append(payload)
            self.contexts.append(headers)
            return {"action": "candidate", "candidate": {"objectId": payload.get("objectId")}}

        self.proxy = WechatLoopbackProxy(
            self.files,
            b"window.__session='__DOWNLOAD_STATION_SESSION__';",
            capture,
        )
        self.proxy.start()

    def tearDown(self) -> None:
        self.proxy.stop()
        self.temporary.cleanup()

    def tls_connection(self) -> ssl.SSLSocket:
        sock = socket.create_connection(self.proxy.address, timeout=5)
        sock.sendall(b"CONNECT channels.weixin.qq.com:443 HTTP/1.1\r\nHost: channels.weixin.qq.com:443\r\n\r\n")
        response = sock.recv(4096)
        self.assertIn(b"200 Connection Established", response)
        context = ssl.create_default_context(cafile=str(self.files.root_pem))
        context.set_alpn_protocols(["http/1.1"])
        return context.wrap_socket(sock, server_hostname="channels.weixin.qq.com")

    @staticmethod
    def read_all(sock: socket.socket) -> bytes:
        chunks = []
        while True:
            chunk = sock.recv(65_536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def test_internal_bridge_and_candidate_endpoint(self) -> None:
        client = self.tls_connection()
        client.sendall(b"GET /__download_station_wechat__/bridge.js HTTP/1.1\r\nHost: channels.weixin.qq.com\r\nConnection: close\r\n\r\n")
        response = self.read_all(client)
        client.close()
        self.assertIn(self.proxy.session_token.encode("ascii"), response)

        body = json.dumps(sample_candidate()).encode("utf-8")
        client = self.tls_connection()
        request = (
            f"POST /__download_station_wechat__/candidate?token={self.proxy.session_token} HTTP/1.1\r\n"
            f"Host: channels.weixin.qq.com\r\nContent-Type: application/json\r\n"
            f"User-Agent: WechatDesktop/1.0\r\nReferer: https://channels.weixin.qq.com/web/pages/feed\r\n"
            f"Cookie: session=memory-only\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + body
        client.sendall(request)
        response = self.read_all(client)
        client.close()
        self.assertIn(b"200 OK", response)
        self.assertIn(b'"action":"candidate"', response)
        self.assertEqual(self.payloads[0]["objectId"], "1234567890123456789")
        self.assertEqual(self.contexts[0]["User-Agent"], "WechatDesktop/1.0")
        self.assertEqual(self.contexts[0]["Cookie"], "session=memory-only")

    def test_html_injection_reuses_nonce_and_compression_is_bounded(self) -> None:
        result = self.proxy._inject_html(
            b'<html><head><script nonce="safe-nonce" src="https://res.wx.qq.com/app.js"></script></head></html>'
        )
        self.assertIn(b"data-download-station=\"wechat\"", result)
        self.assertIn(b'nonce="safe-nonce"', result)
        self.assertIn(b"__download_station_session=", result)
        compressed = zlib.compress(b"x" * (16 * 1024 * 1024 + 1))
        with self.assertRaises(CaptureProxyError):
            _decompress_limited(compressed, "deflate")

    def test_resource_host_and_internal_finder_results_are_instrumented(self) -> None:
        self.assertTrue(self.proxy.should_intercept("res.wx.qq.com"))
        source = (
            b'import"./chunks/flow.js";const lazy=import("./chunks/lazy.js");'
            b"async finderPcFlow(e){const t=await load(e);return t}async "
            b"finderGetRecommend(e){const t=await recommend(e);return t}async next(e){return e}"
        )
        result = self.proxy._instrument_javascript(source, "/t/wx_fed/finder/web/index.publish.js")
        self.assertIn(b"__DOWNLOAD_STATION_WECHAT_OBSERVE__", result)
        self.assertIn(b'"finderPcFlow"', result)
        self.assertIn(b'"finderGetRecommend"', result)
        self.assertEqual(result.count(b"__DOWNLOAD_STATION_WECHAT_OBSERVE__"), 4)
        self.assertEqual(result.count(b"__download_station_session="), 2)
        diagnostics = self.proxy.diagnostics()
        self.assertEqual(diagnostics["resourceScriptsSeen"], 1)
        self.assertEqual(diagnostics["resourceScriptsInstrumented"], 1)
        self.assertEqual(diagnostics["finderHooksInstalled"], 2)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for transformed module validation")
    def test_internal_finder_instrumentation_preserves_method_result(self) -> None:
        source = b"async finderPcFlow(e){if(!e)return null;return {data:{object:[e]}}}async next(e){return e}"
        transformed = self.proxy._instrument_javascript(source, "/finder.publish.js").decode("utf-8")
        script = (
            "const observed=[];globalThis.__DOWNLOAD_STATION_WECHAT_OBSERVE__=(v,m)=>observed.push([v,m]);"
            f"class Api{{{transformed}}}"
            "(async()=>{const input={id:'feed-1'};const result=await new Api().finderPcFlow(input);"
            "if(result.data.object[0]!==input||observed[0][0]!==result||observed[0][1]!=='finderPcFlow')process.exit(3)})().catch(()=>process.exit(4));"
        )
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plain_http_requests_are_forwarded_instead_of_rejected(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                body = b"plain-http-ok"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = socket.create_connection(self.proxy.address, timeout=5)
            client.sendall(
                f"GET http://127.0.0.1:{server.server_port}/health HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{server.server_port}\r\nConnection: close\r\n\r\n".encode("ascii")
            )
            response = self.read_all(client)
            client.close()
            self.assertIn(b"200 OK", response)
            self.assertIn(b"plain-http-ok", response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_non_target_connect_is_a_plain_tunnel(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        address = listener.getsockname()

        def echo() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.sendall(connection.recv(16))

        thread = threading.Thread(target=echo, daemon=True)
        thread.start()
        client = socket.create_connection(self.proxy.address, timeout=5)
        client.sendall(f"CONNECT 127.0.0.1:{address[1]} HTTP/1.1\r\nHost: test\r\n\r\n".encode("ascii"))
        response = client.recv(4096)
        self.assertIn(b"200 Connection Established", response)
        client.sendall(b"plain-tunnel")
        self.assertEqual(client.recv(16), b"plain-tunnel")
        client.close()
        listener.close()
        thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
