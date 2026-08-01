from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from idm_eagle_bridge.updater import (
    UpdateError,
    UpdateInfo,
    automatic_check_due,
    check_for_update,
    parse_manifest,
    prepare_update,
    record_successful_check,
)


VALID_MANIFEST = {
    "schemaVersion": 1,
    "version": "9.9.9",
    "downloadUrl": (
        "https://github.com/Ly233ly/download-for-eagle/"
        "releases/download/v9.9.9/test.zip"
    ),
    "sha256": "0" * 64,
    "size": 123,
    "notes": "测试更新",
    "signature": (
        "FM/mvGYEigMIRts3sseD9qK30FE/uLLC6OC12htX6CsnlrDYEFnP75SoqAqVHszne"
        "FxRgh5YzZD6+qncesJqCygQtH/7cI9vK/sYRzjlR5N3IaJRGiO//QfPeNgAO8jW9"
        "LXE7EkuD6N1P+8oaXVl81v17Gxv+xYPjZL1dbFB0/xQwXDsuqLi6bemjfq5Osn6Q"
        "ZiLv94fxxVDabeRfC1brta0zthLGPm7tEwyoQ6QQmXXQS/71OY3Y8O2GNNMSEFC+"
        "AwcvJZYFrzsS1UqVUQZIJTp9ThF40Q8J1pv2p28TcRAOqIigti74XPb9tlqrX+Tn"
        "/u2uis8egA7OLV79nLo5w=="
    ),
}


class UpdaterTests(unittest.TestCase):
    def test_signed_manifest_is_accepted(self) -> None:
        payload = json.dumps(VALID_MANIFEST, ensure_ascii=False).encode("utf-8")

        update = parse_manifest(payload, "0.6.0")

        self.assertIsNotNone(update)
        self.assertEqual(update.version, "9.9.9")

    def test_manifest_tampering_is_rejected(self) -> None:
        changed = dict(VALID_MANIFEST)
        changed["downloadUrl"] = changed["downloadUrl"].replace("test.zip", "other.zip")

        with self.assertRaisesRegex(UpdateError, "签名校验失败"):
            parse_manifest(json.dumps(changed, ensure_ascii=False).encode("utf-8"))

    def test_older_or_equal_version_does_not_offer_update(self) -> None:
        payload = json.dumps(VALID_MANIFEST, ensure_ascii=False).encode("utf-8")

        self.assertIsNone(parse_manifest(payload, "9.9.9"))
        self.assertIsNone(parse_manifest(payload, "10.0.0"))

    def test_missing_manifest_is_treated_as_no_published_update(self) -> None:
        missing = HTTPError(
            "https://example.invalid/update.json",
            404,
            "Not Found",
            None,
            None,
        )
        with patch("idm_eagle_bridge.updater.urlopen", side_effect=missing):
            self.assertIsNone(check_for_update("1.5.0"))

    def test_download_verifies_and_extracts_unique_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("下载中转站-9.9.9/一键安装.exe", b"test-installer")
            package = archive_path.read_bytes()
            update = UpdateInfo(
                version="9.9.9",
                download_url=archive_path.as_uri(),
                sha256=hashlib.sha256(package).hexdigest(),
                size=len(package),
                notes="",
            )
            with patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": str(root / "data")}):
                installer = prepare_update(update)

            self.assertEqual(installer.name, "一键安装.exe")
            self.assertEqual(installer.read_bytes(), b"test-installer")

    def test_automatic_check_is_limited_to_once_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": temporary}):
                self.assertTrue(automatic_check_due(now=1_000_000))
                record_successful_check(now=1_000_000)
                self.assertFalse(automatic_check_due(now=1_000_100))
                self.assertTrue(automatic_check_due(now=1_000_000 + 86_400))


if __name__ == "__main__":
    unittest.main()
