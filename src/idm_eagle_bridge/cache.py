from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from .database import Database
from .paths import download_station_root


ACTIVE_CACHE_STATUSES = {
    "queued",
    "downloading",
    "merging",
    "validating",
    "ready_to_import",
}


def _path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _measure(path: Path) -> tuple[int, int, int]:
    """Return bytes, regular-file count and directory count without following links."""
    try:
        if not path.exists() or _is_link(path):
            return 0, 0, 0
        if path.is_file():
            return max(0, int(path.stat().st_size)), 1, 0
    except OSError:
        return 0, 0, 0

    total = 0
    files = 0
    directories = 1
    try:
        entries = tuple(path.rglob("*"))
    except OSError:
        return 0, 0, 0
    for entry in entries:
        try:
            if _is_link(entry):
                continue
            if entry.is_file():
                total += max(0, int(entry.stat().st_size))
                files += 1
            elif entry.is_dir():
                directories += 1
        except OSError:
            continue
    return total, files, directories


def _latest_mtime(path: Path) -> float | None:
    """Return None for unsafe/inaccessible trees so cleanup skips them."""
    try:
        if not path.exists() or _is_link(path):
            return None
        latest = float(path.stat().st_mtime)
        if path.is_file():
            return latest
        entries = tuple(path.rglob("*"))
    except OSError:
        return None
    for entry in entries:
        try:
            if _is_link(entry):
                return None
            latest = max(latest, float(entry.stat().st_mtime))
        except OSError:
            return None
    return latest


class ProgramCacheManager:
    """Owns only temporary downloads, generated previews and the legacy media log."""

    def __init__(
        self,
        database: Database,
        station_root: str | Path | None = None,
    ) -> None:
        self.database = database
        self._station_root = Path(station_root) if station_root is not None else None

    @property
    def station_root(self) -> Path:
        return self._station_root if self._station_root is not None else download_station_root()

    @property
    def temporary_root(self) -> Path:
        return self.station_root / "临时"

    @property
    def preview_root(self) -> Path:
        return self.station_root / "预览"

    @property
    def legacy_log(self) -> Path:
        return self.station_root / "media-download.log"

    def status(self) -> dict[str, Any]:
        temporary = _measure(self.temporary_root)
        previews = _measure(self.preview_root)
        log = _measure(self.legacy_log)
        categories = {
            "temporary": {"bytes": temporary[0], "files": temporary[1]},
            "previews": {"bytes": previews[0], "files": previews[1]},
            "log": {"bytes": log[0], "files": log[1]},
        }
        return {
            "totalBytes": sum(item["bytes"] for item in categories.values()),
            "fileCount": sum(item["files"] for item in categories.values()),
            "categories": categories,
        }

    def _active_cache_owners(self) -> tuple[set[str], set[str]]:
        placeholders = ",".join("?" for _ in ACTIVE_CACHE_STATUSES)
        with self.database.session() as connection:
            rows = connection.execute(
                f"""
                SELECT id, preview_path
                FROM download_plans
                WHERE status IN ({placeholders})
                """,
                tuple(sorted(ACTIVE_CACHE_STATUSES)),
            ).fetchall()
        plan_ids = {str(row["id"]) for row in rows}
        previews = {
            _path_key(str(row["preview_path"]))
            for row in rows
            if row["preview_path"]
        }
        return plan_ids, previews

    @staticmethod
    def _eligible(path: Path, cutoff: float | None) -> bool:
        latest = _latest_mtime(path)
        if latest is None:
            return False
        return cutoff is None or latest <= cutoff

    def cleanup(
        self,
        *,
        retention_days: int | None = None,
        now: float | None = None,
        protected_plan_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        days = None if retention_days is None else max(0, min(365, int(retention_days)))
        before = self.status()
        result: dict[str, Any] = {
            "beforeBytes": before["totalBytes"],
            "remainingBytes": before["totalBytes"],
            "freedBytes": 0,
            "removedFiles": 0,
            "removedDirectories": 0,
            "skippedActive": 0,
            "skippedUnsafe": 0,
            "errorCount": 0,
            "retentionDays": days,
        }
        if days == 0:
            return result
        cutoff = None if days is None else current - days * 86400
        active_ids, active_previews = self._active_cache_owners()
        active_ids.update(str(value) for value in protected_plan_ids)
        deleted_preview_paths: list[str] = []

        try:
            temporary_children = tuple(self.temporary_root.iterdir())
        except (FileNotFoundError, OSError):
            temporary_children = ()
        for child in temporary_children:
            if child.name in active_ids:
                result["skippedActive"] += 1
                continue
            if not self._eligible(child, cutoff):
                continue
            if _is_link(child):
                result["skippedUnsafe"] += 1
                continue
            measured = _measure(child)
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError:
                result["errorCount"] += 1
                continue
            result["removedFiles"] += measured[1]
            result["removedDirectories"] += measured[2]

        try:
            preview_files = tuple(
                path for path in self.preview_root.rglob("*") if path.is_file()
            )
        except (FileNotFoundError, OSError):
            preview_files = ()
        for preview in preview_files:
            if _path_key(preview) in active_previews:
                result["skippedActive"] += 1
                continue
            if not self._eligible(preview, cutoff):
                continue
            if _is_link(preview):
                result["skippedUnsafe"] += 1
                continue
            try:
                preview.unlink()
            except OSError:
                result["errorCount"] += 1
                continue
            result["removedFiles"] += 1
            deleted_preview_paths.append(str(preview))
        if deleted_preview_paths:
            with self.database.session() as connection:
                connection.executemany(
                    "UPDATE download_plans SET preview_path = NULL WHERE preview_path = ?",
                    ((path,) for path in deleted_preview_paths),
                )
        if self.preview_root.is_dir():
            try:
                preview_directories = sorted(
                    (path for path in self.preview_root.rglob("*") if path.is_dir()),
                    key=lambda path: len(path.parts),
                    reverse=True,
                )
            except OSError:
                preview_directories = []
            for directory in preview_directories:
                try:
                    directory.rmdir()
                except OSError:
                    continue
                result["removedDirectories"] += 1

        if self.legacy_log.is_file() and self._eligible(self.legacy_log, cutoff):
            if _is_link(self.legacy_log):
                result["skippedUnsafe"] += 1
            else:
                try:
                    self.legacy_log.unlink()
                except OSError:
                    result["errorCount"] += 1
                else:
                    result["removedFiles"] += 1

        after = self.status()
        result["remainingBytes"] = after["totalBytes"]
        result["freedBytes"] = max(0, before["totalBytes"] - after["totalBytes"])
        return result
