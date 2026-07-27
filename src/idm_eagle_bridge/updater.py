from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from urllib.error import HTTPError

from .constants import APP_VERSION
from .paths import ensure_data_dir


UPDATE_MANIFEST_URL = (
    "https://github.com/Ly233ly/download-for-eagle/"
    "releases/latest/download/update.json"
)
UPDATE_CHECK_INTERVAL = 24 * 60 * 60
MAX_MANIFEST_BYTES = 128 * 1024
MAX_PACKAGE_BYTES = 250 * 1024 * 1024

# 私钥仅由维护者离线保存；软件和公开仓库只包含这个验证公钥。
PUBLIC_KEY_MODULUS_B64 = (
    "p/m7gobd8P39ZunYAWI9wuTeK5uhQenj6fIh96fi33keyr8N7sebAJyFGWZd1SMy"
    "lbc0nFmGw1bcch/v9MqRaYtR3oqc3bg0rAgG4upzdOAxUkQWHhb5J3sVKEeVkq8"
    "Juy2aJJDrfQlaqQXy/J6tCZVC0/LxTVJy8WEFolNTe/vQRBinAIhlYHIVGXmrxL/"
    "lrEMeK8DduUN1yicBUw/Apx4JkiMfz4Dv8WPMwDvRmYLbzuyhYXQjeHpVWCVsaE"
    "jdIjoSzV5CMxiBLN9RNCHcHPgm8cTnxkGzfVA4ARLqf0RcZfzKTmdq6LzTebq/d"
    "8dF7zd/oTZg+D46xS96F2ghVQ=="
)
PUBLIC_KEY_EXPONENT_B64 = "AQAB"


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    sha256: str
    size: int
    notes: str


def _version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = cleaned.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise UpdateError("更新版本号格式无效")
    return tuple(int(part) for part in parts)


def _canonical_manifest(data: dict) -> bytes:
    unsigned = dict(data)
    unsigned.pop("signature", None)
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _verify_rsa_signature(message: bytes, signature_b64: str) -> bool:
    try:
        modulus_bytes = base64.b64decode(PUBLIC_KEY_MODULUS_B64, validate=True)
        exponent_bytes = base64.b64decode(PUBLIC_KEY_EXPONENT_B64, validate=True)
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    if len(signature) != len(modulus_bytes):
        return False

    modulus = int.from_bytes(modulus_bytes, "big")
    exponent = int.from_bytes(exponent_bytes, "big")
    decoded = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes(
        len(modulus_bytes), "big"
    )
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420")
    digest_info += hashlib.sha256(message).digest()
    padding_length = len(modulus_bytes) - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    return hmac.compare_digest(decoded, expected)


def parse_manifest(payload: bytes, current_version: str = APP_VERSION) -> UpdateInfo | None:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise UpdateError("更新信息文件过大")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("更新信息格式无效") from exc
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise UpdateError("不支持的更新信息版本")

    signature = data.get("signature")
    if not isinstance(signature, str) or not _verify_rsa_signature(
        _canonical_manifest(data), signature
    ):
        raise UpdateError("更新信息签名校验失败，已停止更新")

    version = data.get("version")
    download_url = data.get("downloadUrl")
    checksum = data.get("sha256")
    size = data.get("size")
    notes = data.get("notes", "")
    if not isinstance(version, str):
        raise UpdateError("更新版本号缺失")
    if not isinstance(download_url, str):
        raise UpdateError("更新下载地址缺失")
    parsed_url = urlsplit(download_url)
    expected_prefix = "/Ly233ly/download-for-eagle/releases/download/"
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or not parsed_url.path.startswith(expected_prefix)
    ):
        raise UpdateError("更新下载地址不在受信任的 GitHub 仓库中")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise UpdateError("更新包校验值无效")
    try:
        int(checksum, 16)
    except ValueError as exc:
        raise UpdateError("更新包校验值无效") from exc
    if not isinstance(size, int) or size <= 0 or size > MAX_PACKAGE_BYTES:
        raise UpdateError("更新包大小无效")
    if not isinstance(notes, str):
        raise UpdateError("更新说明格式无效")

    if _version_tuple(version) <= _version_tuple(current_version):
        return None
    return UpdateInfo(version, download_url, checksum.lower(), size, notes.strip())


def check_for_update(current_version: str = APP_VERSION) -> UpdateInfo | None:
    request = Request(
        UPDATE_MANIFEST_URL,
        headers={"User-Agent": f"DownloadTransferStation/{current_version}"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read(MAX_MANIFEST_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError("暂时无法连接更新服务器") from exc
    except OSError as exc:
        raise UpdateError("暂时无法连接更新服务器") from exc
    return parse_manifest(payload, current_version)


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for entry in archive.infolist():
        target = (destination / entry.filename).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise UpdateError("更新包包含不安全的文件路径") from exc
    archive.extractall(destination)


def prepare_update(
    update: UpdateInfo,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    updates_root = ensure_data_dir() / "updates"
    updates_root.mkdir(parents=True, exist_ok=True)
    for previous in updates_root.iterdir():
        if previous.is_dir():
            shutil.rmtree(previous, ignore_errors=True)
        elif previous.is_file():
            try:
                previous.unlink()
            except OSError:
                pass
    work = updates_root / f"v{update.version}-{uuid.uuid4().hex}"
    package = work / "update.zip"
    extracted = work / "extracted"
    work.mkdir(parents=True)
    digest = hashlib.sha256()
    downloaded = 0
    request = Request(
        update.download_url,
        headers={"User-Agent": f"DownloadTransferStation/{APP_VERSION}"},
    )
    try:
        with urlopen(request, timeout=30) as response, package.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_PACKAGE_BYTES or downloaded > update.size:
                    raise UpdateError("下载的更新包大小异常")
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(downloaded, update.size)
        if downloaded != update.size:
            raise UpdateError("更新包下载不完整")
        if not hmac.compare_digest(digest.hexdigest(), update.sha256):
            raise UpdateError("更新包完整性校验失败，已停止安装")

        extracted.mkdir()
        try:
            with zipfile.ZipFile(package) as archive:
                _safe_extract(archive, extracted)
        except zipfile.BadZipFile as exc:
            raise UpdateError("更新包不是有效的 ZIP 文件") from exc
        installers = list(extracted.rglob("一键安装.exe"))
        if len(installers) != 1:
            raise UpdateError("更新包中没有找到唯一的一键安装程序")
        return installers[0]
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def launch_installer(installer: Path) -> None:
    if os.name != "nt" or not installer.is_file():
        raise UpdateError("无法启动更新安装程序")
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(
            [str(installer), "--update"],
            cwd=str(installer.parent),
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise UpdateError("无法启动更新安装程序") from exc


def _state_path() -> Path:
    return ensure_data_dir() / "update-state.json"


def automatic_check_due(now: float | None = None) -> bool:
    current = time.time() if now is None else now
    try:
        state = json.loads(_state_path().read_text(encoding="utf-8"))
        last_check = float(state.get("lastSuccessfulCheck", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return True
    return current - last_check >= UPDATE_CHECK_INTERVAL


def record_successful_check(now: float | None = None) -> None:
    state = {"lastSuccessfulCheck": time.time() if now is None else now}
    path = _state_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)
