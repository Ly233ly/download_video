from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from email.message import Message
from unittest.mock import patch

from idm_eagle_bridge.updater import (
    LATEST_RELEASE_API_URL,
    UpdateError,
    UpdateInfo,
    automatic_check_due,
    check_for_update,
    parse_release,
    prepare_update,
    record_successful_check,
    _open_release_asset,
    _safe_extract,
    _validate_asset_redirect,
)


VALID_RELEASE = {
    "tag_name": "v9.9.9",
    "html_url": "https://github.com/Ly233ly/download_video/releases/tag/v9.9.9",
    "draft": False,
    "prerelease": False,
    "body": "测试更新",
    "assets": [
        {
            "id": 123456,
            "url": (
                "https://api.github.com/repos/Ly233ly/download_video/"
                "releases/assets/123456"
            ),
            "name": "liudi-downloader-9.9.9-windows-x64.zip",
            "state": "uploaded",
            "size": 123,
            "digest": f"sha256:{'0' * 64}",
            "browser_download_url": (
                "https://github.com/Ly233ly/download_video/releases/download/"
                "v9.9.9/liudi-downloader-9.9.9-windows-x64.zip"
            ),
        }
    ],
}


class MemoryResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        status: int = 200,
        content_length: int | None = None,
    ) -> None:
        self._stream = BytesIO(payload)
        self.status = status
        self.headers = Message()
        if content_length is not None or payload:
            self.headers["Content-Length"] = str(
                len(payload) if content_length is None else content_length
            )
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self.closed = True
        self._stream.close()


class UpdaterTests(unittest.TestCase):
    def test_official_github_release_asset_is_accepted(self) -> None:
        payload = json.dumps(VALID_RELEASE, ensure_ascii=False).encode("utf-8")

        update = parse_release(payload, "0.6.0")

        self.assertIsNotNone(update)
        self.assertEqual(update.version, "9.9.9")
        self.assertEqual(update.sha256, "0" * 64)
        self.assertEqual(update.size, 123)

    def test_release_from_another_repository_is_rejected(self) -> None:
        changed = dict(VALID_RELEASE)
        changed["html_url"] = changed["html_url"].replace(
            "Ly233ly/download_video", "attacker/download_video"
        )

        with self.assertRaisesRegex(UpdateError, "不是受信任"):
            parse_release(json.dumps(changed, ensure_ascii=False).encode("utf-8"))

    def test_missing_github_digest_is_rejected(self) -> None:
        changed = json.loads(json.dumps(VALID_RELEASE))
        changed["assets"][0]["digest"] = None

        with self.assertRaisesRegex(UpdateError, "校验值无效"):
            parse_release(json.dumps(changed).encode("utf-8"))

    def test_invalid_asset_identity_is_rejected(self) -> None:
        for asset_id, url in (
            (True, "https://api.github.com/repos/Ly233ly/download_video/releases/assets/1"),
            (0, "https://api.github.com/repos/Ly233ly/download_video/releases/assets/0"),
            (123456, "https://api.github.com/repos/attacker/download_video/releases/assets/123456"),
        ):
            with self.subTest(asset_id=asset_id, url=url):
                changed = json.loads(json.dumps(VALID_RELEASE))
                changed["assets"][0]["id"] = asset_id
                changed["assets"][0]["url"] = url
                with self.assertRaisesRegex(UpdateError, "身份无效"):
                    parse_release(json.dumps(changed).encode("utf-8"))

    def test_malformed_version_tag_is_rejected(self) -> None:
        for tag in ("9.9.9", "v09.9.9", "v9.9", "v9.9.9-beta"):
            with self.subTest(tag=tag):
                changed = json.loads(json.dumps(VALID_RELEASE))
                changed["tag_name"] = tag
                with self.assertRaisesRegex(UpdateError, "版本号格式无效"):
                    parse_release(json.dumps(changed).encode("utf-8"))

    def test_tampered_asset_url_is_rejected(self) -> None:
        changed = json.loads(json.dumps(VALID_RELEASE))
        changed["assets"][0]["browser_download_url"] = (
            "https://github.com/attacker/download_video/releases/download/"
            "v9.9.9/liudi-downloader-9.9.9-windows-x64.zip"
        )

        with self.assertRaisesRegex(UpdateError, "不在受信任"):
            parse_release(json.dumps(changed).encode("utf-8"))

    def test_non_sha256_or_uppercase_digest_is_rejected(self) -> None:
        for digest in (f"sha512:{'0' * 64}", f"sha256:{'A' * 64}"):
            with self.subTest(digest=digest[:12]):
                changed = json.loads(json.dumps(VALID_RELEASE))
                changed["assets"][0]["digest"] = digest
                with self.assertRaisesRegex(UpdateError, "校验值无效"):
                    parse_release(json.dumps(changed).encode("utf-8"))

    def test_duplicate_windows_assets_are_rejected(self) -> None:
        changed = json.loads(json.dumps(VALID_RELEASE))
        changed["assets"].append(dict(changed["assets"][0]))

        with self.assertRaisesRegex(UpdateError, "没有唯一"):
            parse_release(json.dumps(changed).encode("utf-8"))

    def test_draft_or_prerelease_is_rejected(self) -> None:
        for field in ("draft", "prerelease"):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(VALID_RELEASE))
                changed[field] = True
                with self.assertRaisesRegex(UpdateError, "不是正式发布"):
                    parse_release(json.dumps(changed).encode("utf-8"))

    def test_older_or_equal_version_does_not_offer_update(self) -> None:
        payload = json.dumps(VALID_RELEASE, ensure_ascii=False).encode("utf-8")

        self.assertIsNone(parse_release(payload, "9.9.9"))
        self.assertIsNone(parse_release(payload, "10.0.0"))

    def test_missing_latest_release_is_treated_as_no_published_update(self) -> None:
        missing = HTTPError(
            "https://api.github.com/repos/Ly233ly/download_video/releases/latest",
            404,
            "Not Found",
            None,
            None,
        )
        with patch(
            "idm_eagle_bridge.updater._open_without_redirects",
            side_effect=missing,
        ):
            self.assertIsNone(check_for_update("1.6.3"))

    def test_check_uses_the_fixed_github_api_and_versioned_headers(self) -> None:
        payload = json.dumps(VALID_RELEASE).encode("utf-8")
        observed = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, limit):
                return payload[:limit]

            def close(self):
                pass

        def open_request(request, timeout):
            observed["url"] = request.full_url
            observed["accept"] = request.get_header("Accept")
            observed["api_version"] = request.get_header("X-github-api-version")
            observed["user_agent"] = request.get_header("User-agent")
            observed["timeout"] = timeout
            return Response()

        with patch(
            "idm_eagle_bridge.updater._open_without_redirects",
            side_effect=open_request,
        ):
            update = check_for_update("1.6.3")

        self.assertIsNotNone(update)
        self.assertEqual(observed["url"], LATEST_RELEASE_API_URL)
        self.assertEqual(observed["accept"], "application/vnd.github+json")
        self.assertEqual(observed["api_version"], "2022-11-28")
        self.assertEqual(observed["user_agent"], "LiudiDownloader/1.6.3")
        self.assertEqual(observed["timeout"], 10)

    def test_check_rejects_metadata_redirects_and_reports_rate_limit(self) -> None:
        for code, expected in ((302, "不可信跳转"), (403, "次数受限"), (429, "次数受限")):
            with self.subTest(code=code):
                error = HTTPError(LATEST_RELEASE_API_URL, code, "error", Message(), None)
                with (
                    patch(
                        "idm_eagle_bridge.updater._open_without_redirects",
                        side_effect=error,
                    ),
                    self.assertRaisesRegex(UpdateError, expected),
                ):
                    check_for_update("1.6.3")

    def test_asset_download_allows_one_exact_github_cdn_redirect(self) -> None:
        update = UpdateInfo(
            "9.9.9",
            "https://api.github.com/repos/Ly233ly/download_video/releases/assets/123456",
            "0" * 64,
            3,
            "",
        )
        redirect_headers = Message()
        redirect_headers["Location"] = (
            "https://release-assets.githubusercontent.com/github-production-release-asset/"
            "123/example.zip?token=short-lived"
        )
        redirect = HTTPError(update.download_url, 302, "Found", redirect_headers, None)
        response = MemoryResponse(b"zip")
        with patch(
            "idm_eagle_bridge.updater._open_without_redirects",
            side_effect=[redirect, response],
        ) as opener:
            actual = _open_release_asset(update)
        self.assertIs(actual, response)
        self.assertEqual(opener.call_count, 2)
        second_request = opener.call_args_list[1].args[0]
        self.assertEqual(second_request.full_url, redirect_headers["Location"])
        self.assertIsNone(second_request.get_header("Authorization"))

    def test_asset_download_rejects_untrusted_or_repeated_redirect(self) -> None:
        update = UpdateInfo(
            "9.9.9",
            "https://api.github.com/repos/Ly233ly/download_video/releases/assets/123456",
            "0" * 64,
            3,
            "",
        )
        for location in (
            "http://release-assets.githubusercontent.com/file.zip",
            "https://evil.example/file.zip",
            "https://user@release-assets.githubusercontent.com/file.zip",
        ):
            with self.subTest(location=location):
                headers = Message()
                headers["Location"] = location
                error = HTTPError(update.download_url, 302, "Found", headers, None)
                with (
                    patch(
                        "idm_eagle_bridge.updater._open_without_redirects",
                        side_effect=error,
                    ),
                    self.assertRaisesRegex(UpdateError, "不受信任"),
                ):
                    _open_release_asset(update)

        valid = Message()
        valid["Location"] = "https://release-assets.githubusercontent.com/file.zip?t=1"
        first = HTTPError(update.download_url, 302, "Found", valid, None)
        second = HTTPError(valid["Location"], 302, "Found", valid, None)
        with (
            patch(
                "idm_eagle_bridge.updater._open_without_redirects",
                side_effect=[first, second],
            ),
            self.assertRaisesRegex(UpdateError, "跳转次数超过限制"),
        ):
            _open_release_asset(update)

        for code in (301, 303, 307, 308):
            with self.subTest(code=code):
                error = HTTPError(update.download_url, code, "redirect", valid, None)
                with (
                    patch(
                        "idm_eagle_bridge.updater._open_without_redirects",
                        side_effect=error,
                    ),
                    self.assertRaisesRegex(UpdateError, "暂时无法下载"),
                ):
                    _open_release_asset(update)

    def test_download_verifies_and_extracts_unique_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("留底下载器-9.9.9/留底安装器.exe", b"test-installer")
            package = archive_path.read_bytes()
            update = UpdateInfo(
                version="9.9.9",
                download_url=(
                    "https://api.github.com/repos/Ly233ly/download_video/"
                    "releases/assets/123456"
                ),
                sha256=hashlib.sha256(package).hexdigest(),
                size=len(package),
                notes="",
            )
            response = MemoryResponse(package)
            with (
                patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": str(root / "data")}),
                patch(
                    "idm_eagle_bridge.updater._open_release_asset",
                    return_value=response,
                ),
            ):
                installer = prepare_update(update)

            self.assertEqual(installer.name, "留底安装器.exe")
            self.assertEqual(installer.read_bytes(), b"test-installer")

    def test_download_size_hash_and_failures_remove_partial_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            update = UpdateInfo(
                "9.9.9",
                "https://api.github.com/repos/Ly233ly/download_video/releases/assets/123456",
                hashlib.sha256(b"expected").hexdigest(),
                8,
                "",
            )
            cases = (
                (MemoryResponse(b"short", content_length=5), "响应大小"),
                (MemoryResponse(b"short", content_length=8), "下载不完整"),
                (MemoryResponse(b"tampered", content_length=8), "完整性校验失败"),
            )
            for response, expected in cases:
                with self.subTest(expected=expected):
                    data_root = root / expected
                    with (
                        patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": str(data_root)}),
                        patch(
                            "idm_eagle_bridge.updater._open_release_asset",
                            return_value=response,
                        ),
                        self.assertRaisesRegex(UpdateError, expected),
                    ):
                        prepare_update(update)
                    updates = data_root / "updates"
                    self.assertEqual(list(updates.iterdir()), [])

    def test_safe_extract_rejects_dangerous_archive_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {
                "traversal": [("留底下载器-9.9.9/../evil.exe", b"x", None)],
                "absolute": [("C:/evil.exe", b"x", None)],
                "wrong-root": [("other/留底安装器.exe", b"x", None)],
                "case-collision": [
                    ("留底下载器-9.9.9/App.dll", b"a", None),
                    ("留底下载器-9.9.9/app.dll", b"b", None),
                ],
                "symlink": [
                    ("留底下载器-9.9.9/link", b"target", (0o120777 << 16)),
                ],
                "child-before-file-parent": [
                    ("留底下载器-9.9.9/app/child.dll", b"x", None),
                    ("留底下载器-9.9.9/app", b"not-a-directory", None),
                ],
            }
            for name, entries in cases.items():
                with self.subTest(name=name):
                    archive_path = root / f"{name}.zip"
                    with zipfile.ZipFile(archive_path, "w") as archive:
                        for entry_name, payload, external_attr in entries:
                            info = zipfile.ZipInfo(entry_name)
                            if external_attr is not None:
                                info.create_system = 3
                                info.external_attr = external_attr
                            archive.writestr(info, payload)
                    destination = root / f"out-{name}"
                    destination.mkdir()
                    with zipfile.ZipFile(archive_path) as archive:
                        with self.assertRaises(UpdateError):
                            _safe_extract(archive, destination, "留底下载器-9.9.9")

    def test_archive_limits_and_unique_root_installer_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "too-many.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("留底下载器-9.9.9/留底安装器.exe", b"one")
                archive.writestr("留底下载器-9.9.9/extra.txt", b"two")
            destination = root / "out"
            destination.mkdir()
            with (
                zipfile.ZipFile(archive_path) as archive,
                patch("idm_eagle_bridge.updater.MAX_ARCHIVE_ENTRIES", 1),
                self.assertRaisesRegex(UpdateError, "文件数量异常"),
            ):
                _safe_extract(archive, destination, "留底下载器-9.9.9")

            multiple_path = root / "multiple.zip"
            with zipfile.ZipFile(multiple_path, "w") as archive:
                archive.writestr("留底下载器-9.9.9/留底安装器.exe", b"one")
                archive.writestr("留底下载器-9.9.9/deep/一键安装.exe", b"two")
            package = multiple_path.read_bytes()
            update = UpdateInfo(
                "9.9.9",
                "https://api.github.com/repos/Ly233ly/download_video/releases/assets/123456",
                hashlib.sha256(package).hexdigest(),
                len(package),
                "",
            )
            data_root = root / "data"
            with (
                patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": str(data_root)}),
                patch(
                    "idm_eagle_bridge.updater._open_release_asset",
                    return_value=MemoryResponse(package),
                ),
                self.assertRaisesRegex(UpdateError, "唯一的一键安装程序"),
            ):
                prepare_update(update)
            self.assertEqual(list((data_root / "updates").iterdir()), [])

    def test_redirect_validator_accepts_only_exact_github_asset_host(self) -> None:
        valid = "https://release-assets.githubusercontent.com/file.zip?token=abc"
        self.assertEqual(_validate_asset_redirect(valid), valid)
        for invalid in (
            "https://release-assets.githubusercontent.com.evil.test/file.zip",
            "https://release-assets.githubusercontent.com:444/file.zip",
            "https://release-assets.githubusercontent.com/",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                _validate_asset_redirect(invalid)

    def test_automatic_check_is_limited_to_once_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"IDM_EAGLE_DATA_DIR": temporary}):
                self.assertTrue(automatic_check_due(now=1_000_000))
                record_successful_check(now=1_000_000)
                self.assertFalse(automatic_check_due(now=1_000_100))
                self.assertTrue(automatic_check_due(now=1_000_000 + 86_400))


if __name__ == "__main__":
    unittest.main()
