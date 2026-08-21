from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from urllib.error import HTTPError

from .constants import APP_VERSION
from .paths import ensure_data_dir


GITHUB_REPOSITORY = "Ly233ly/download_video"
LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
)
UPDATE_CHECK_INTERVAL = 24 * 60 * 60
MAX_RELEASE_BYTES = 512 * 1024
MAX_PACKAGE_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4096
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_EXTRACTED_FILE_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_VERSION_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _open_without_redirects(request: Request, timeout: int):
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


def _response_status(response: object) -> int:
    status = getattr(response, "status", None)
    if status is None:
        getter = getattr(response, "getcode", None)
        status = getter() if callable(getter) else None
    try:
        return int(status)
    except (TypeError, ValueError) as exc:
        raise UpdateError("GitHub 响应状态无效") from exc


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


def parse_release(payload: bytes, current_version: str = APP_VERSION) -> UpdateInfo | None:
    if len(payload) > MAX_RELEASE_BYTES:
        raise UpdateError("更新信息文件过大")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("更新信息格式无效") from exc
    if not isinstance(data, dict):
        raise UpdateError("更新信息格式无效")
    if data.get("draft") is not False or data.get("prerelease") is not False:
        raise UpdateError("GitHub 最新版本不是正式发布版本")

    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateError("更新版本号缺失")
    if _VERSION_TAG.fullmatch(tag) is None:
        raise UpdateError("更新版本号格式无效")
    version = tag[1:]
    _version_tuple(version)
    if _version_tuple(version) <= _version_tuple(current_version):
        return None

    expected_release_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/releases/tag/{tag}"
    )
    if data.get("html_url") != expected_release_url:
        raise UpdateError("GitHub 更新来源不是受信任的项目仓库")

    expected_asset_name = f"liudi-downloader-{version}-windows-x64.zip"
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("GitHub 发布资产列表无效")
    matches = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name") == expected_asset_name
    ]
    if len(matches) != 1:
        raise UpdateError("GitHub 发布中没有唯一的 Windows 更新包")
    asset = matches[0]
    if asset.get("state") != "uploaded":
        raise UpdateError("GitHub Windows 更新包尚未上传完成")

    asset_id = asset.get("id")
    asset_api_url = asset.get("url")
    expected_asset_api_url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/assets/"
        f"{asset_id}"
    )
    if (
        type(asset_id) is not int
        or asset_id <= 0
        or asset_api_url != expected_asset_api_url
    ):
        raise UpdateError("GitHub Windows 更新包身份无效")

    download_url = asset.get("browser_download_url")
    expected_download_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/releases/download/"
        f"{tag}/{expected_asset_name}"
    )
    if download_url != expected_download_url:
        raise UpdateError("更新下载地址不在受信任的 GitHub 仓库中")
    parsed_url = urlsplit(download_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.port is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise UpdateError("更新下载地址不在受信任的 GitHub 仓库中")

    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise UpdateError("更新包校验值无效")
    checksum = digest.removeprefix("sha256:")
    if len(checksum) != 64 or checksum != checksum.lower():
        raise UpdateError("更新包校验值无效")
    try:
        int(checksum, 16)
    except ValueError as exc:
        raise UpdateError("更新包校验值无效") from exc

    size = asset.get("size")
    if type(size) is not int or size <= 0 or size > MAX_PACKAGE_BYTES:
        raise UpdateError("更新包大小无效")
    notes = data.get("body")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise UpdateError("更新说明格式无效")
    return UpdateInfo(version, asset_api_url, checksum, size, notes.strip())


def check_for_update(current_version: str = APP_VERSION) -> UpdateInfo | None:
    request = Request(
        LATEST_RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LiudiDownloader/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with _open_without_redirects(request, timeout=10) as response:
            if _response_status(response) != 200:
                raise UpdateError("GitHub 更新信息响应状态异常")
            payload = response.read(MAX_RELEASE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            exc.close()
            return None
        if 300 <= exc.code < 400:
            exc.close()
            raise UpdateError("GitHub 更新信息发生了不可信跳转") from exc
        if exc.code in (403, 429):
            exc.close()
            raise UpdateError("GitHub 更新检查次数受限，请稍后重试") from exc
        exc.close()
        raise UpdateError("暂时无法连接更新服务器") from exc
    except OSError as exc:
        raise UpdateError("暂时无法连接更新服务器") from exc
    return parse_release(payload, current_version)


def _normalized_archive_parts(entry: zipfile.ZipInfo) -> tuple[str, ...]:
    raw = entry.filename
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise UpdateError("更新包包含无效的文件路径")
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise UpdateError("更新包包含不安全的文件路径")
    is_directory = entry.is_dir() or normalized.endswith("/")
    if is_directory:
        normalized = normalized.rstrip("/")
    raw_parts = normalized.split("/")
    if not raw_parts or any(part in ("", ".", "..") for part in raw_parts):
        raise UpdateError("更新包包含不安全的文件路径")
    for part in raw_parts:
        if ":" in part or part.rstrip(" .") != part:
            raise UpdateError("更新包包含 Windows 不安全文件名")
        device_name = part.split(".", 1)[0].upper()
        if device_name in _WINDOWS_DEVICE_NAMES:
            raise UpdateError("更新包包含 Windows 保留文件名")
    return tuple(raw_parts)


def _safe_extract(
    archive: zipfile.ZipFile,
    destination: Path,
    expected_root: str,
) -> set[str]:
    root = destination.resolve()
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise UpdateError("更新包文件数量异常")
    seen: dict[str, bool] = {}
    total_size = 0
    normalized_names: set[str] = set()
    prepared: list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]] = []
    for entry in entries:
        parts = _normalized_archive_parts(entry)
        if parts[0] != expected_root:
            raise UpdateError("更新包根目录与版本不一致")
        is_directory = entry.is_dir() or entry.filename.endswith(("/", "\\"))
        mode = (entry.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise UpdateError("更新包不得包含符号链接")
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UpdateError("更新包包含不支持的文件类型")
        key = "/".join(parts).casefold()
        if key in seen:
            raise UpdateError("更新包包含重复或大小写冲突路径")
        if not is_directory and any(
            existing.startswith(key + "/") for existing in seen
        ):
            raise UpdateError("更新包文件与目录路径冲突")
        for index in range(1, len(parts)):
            parent_key = "/".join(parts[:index]).casefold()
            if seen.get(parent_key) is False:
                raise UpdateError("更新包文件与目录路径冲突")
        seen[key] = is_directory
        normalized_names.add("/".join(parts))
        if not is_directory:
            if entry.file_size < 0 or entry.file_size > MAX_EXTRACTED_FILE_BYTES:
                raise UpdateError("更新包包含异常大小的文件")
            total_size += entry.file_size
            if total_size > MAX_EXTRACTED_BYTES:
                raise UpdateError("更新包解压总大小异常")
            if entry.file_size and entry.compress_size <= 0:
                raise UpdateError("更新包压缩信息无效")
            if (
                entry.file_size >= 1024 * 1024
                and entry.file_size > entry.compress_size * MAX_COMPRESSION_RATIO
            ):
                raise UpdateError("更新包包含异常压缩比文件")
        prepared.append((entry, parts, is_directory))

    for entry, parts, is_directory in prepared:
        target = destination.joinpath(*parts).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise UpdateError("更新包包含不安全的文件路径") from exc
        if is_directory:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry, "r") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
    return normalized_names


def _validate_asset_redirect(location: str) -> str:
    if not isinstance(location, str) or not location:
        raise UpdateError("GitHub 更新包跳转地址缺失")
    parsed = urlsplit(location)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "release-assets.githubusercontent.com"
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path in ("", "/")
    ):
        raise UpdateError("GitHub 更新包跳转到不受信任的地址")
    return location


def _asset_request(url: str, version: str, *, api: bool) -> Request:
    headers = {"User-Agent": f"LiudiDownloader/{version}"}
    if api:
        headers.update(
            {
                "Accept": "application/octet-stream",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
    return Request(url, headers=headers)


def _open_release_asset(update: UpdateInfo):
    expected_api_prefix = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/assets/"
    )
    if not update.download_url.startswith(expected_api_prefix):
        raise UpdateError("GitHub Windows 更新包身份无效")
    asset_id = update.download_url.removeprefix(expected_api_prefix)
    if not asset_id.isdigit() or int(asset_id) <= 0:
        raise UpdateError("GitHub Windows 更新包身份无效")
    request = _asset_request(update.download_url, APP_VERSION, api=True)
    try:
        response = _open_without_redirects(request, timeout=30)
    except HTTPError as exc:
        if exc.code != 302:
            if exc.code in (403, 429):
                exc.close()
                raise UpdateError("GitHub 更新下载次数受限，请稍后重试") from exc
            exc.close()
            raise UpdateError("暂时无法下载 GitHub 更新包") from exc
        try:
            location = _validate_asset_redirect(exc.headers.get("Location", ""))
        finally:
            exc.close()
    else:
        if _response_status(response) != 200:
            response.close()
            raise UpdateError("GitHub 更新包响应状态异常")
        return response
    redirected = _asset_request(location, APP_VERSION, api=False)
    try:
        response = _open_without_redirects(redirected, timeout=30)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            exc.close()
            raise UpdateError("GitHub 更新包跳转次数超过限制") from exc
        exc.close()
        raise UpdateError("暂时无法下载 GitHub 更新包") from exc
    status = _response_status(response)
    if status != 200:
        response.close()
        raise UpdateError("GitHub 更新包响应状态异常")
    return response


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
    try:
        with _open_release_asset(update) as response, package.open("wb") as output:
            content_length = response.headers.get("Content-Length")
            try:
                response_size = int(content_length)
            except (TypeError, ValueError) as exc:
                raise UpdateError("GitHub 更新包缺少有效的文件大小") from exc
            if response_size != update.size:
                raise UpdateError("GitHub 更新包响应大小与发布信息不一致")
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
        expected_root = f"留底下载器-{update.version}"
        try:
            with zipfile.ZipFile(package) as archive:
                names = _safe_extract(archive, extracted, expected_root)
        except zipfile.BadZipFile as exc:
            raise UpdateError("更新包不是有效的 ZIP 文件") from exc
        expected_installer = f"{expected_root}/留底安装器.exe"
        installer_names = {
            name
            for name in names
            if name.rsplit("/", 1)[-1].casefold()
            in {"留底安装器.exe".casefold(), "一键安装.exe".casefold()}
        }
        if installer_names != {expected_installer}:
            raise UpdateError("更新包中没有找到唯一的一键安装程序")
        installer = extracted / expected_root / "留底安装器.exe"
        if not installer.is_file():
            raise UpdateError("更新包中没有找到唯一的一键安装程序")
        return installer
    except BaseException:
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
