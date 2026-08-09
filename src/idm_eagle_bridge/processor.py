from __future__ import annotations

import time
from pathlib import Path

from .constants import DEFAULT_SOURCE_GRACE_PERIOD, VIDEO_EXTENSIONS
from .database import Database
from .eagle import EagleClient, EagleImportError, EagleUnavailable
from .fingerprint import sha256_file
from .paths import download_station_root


class JobProcessor:
    def __init__(
        self,
        database: Database,
        eagle: EagleClient | None = None,
        minimum_file_age: float = 2.0,
        source_grace_period: float = DEFAULT_SOURCE_GRACE_PERIOD,
    ) -> None:
        self.database = database
        self.eagle = eagle or EagleClient()
        self.minimum_file_age = minimum_file_age
        self.source_grace_period = max(0.0, source_grace_period)
        self._eagle_unavailable_until = 0.0

    def process_once(self, limit: int = 20) -> int:
        processed = 0
        for job in self.database.list_actionable_jobs(limit):
            self.process_job(job["id"])
            processed += 1
        # Retention is independent of the IDM import batch.  In particular, a
        # machine without Eagle may keep refilling the import batch with due
        # waiting_eagle rows; that must not starve already-approved cleanup.
        self.cleanup_retained_files(max(1, min(10, limit)))
        return processed

    def cleanup_retained_files(self, limit: int = 10) -> None:
        for plan in self.database.expired_retained_plans(limit):
            plan_id = str(plan["plan_id"])
            path = Path(str(plan["final_path"]))
            try:
                resolved = path.resolve(strict=True)
                job_path = Path(str(plan["job_file_path"])).resolve(strict=True)
                completed_root = (download_station_root() / "已完成").resolve(strict=True)
            except OSError:
                self.database.record_plan_output_cleanup(
                    plan_id, str(path),
                    deleted=False,
                    error_code="local_file_delete_not_owned",
                    error_message="本机下载文件不存在或无法访问",
                )
                continue
            if (
                not resolved.is_file()
                or resolved != job_path
                or not resolved.is_relative_to(completed_root)
            ):
                self.database.record_plan_output_cleanup(
                    plan_id, str(path),
                    deleted=False,
                    error_code="local_file_delete_not_owned",
                    error_message="本机下载文件不属于本程序已完成目录或与导入任务不一致",
                )
                continue
            last_error = ""
            for attempt in range(4):
                try:
                    resolved.unlink()
                    self.database.record_plan_output_cleanup(plan_id, str(path), deleted=True)
                    break
                except OSError as exc:
                    last_error = type(exc).__name__
                    if attempt < 3:
                        time.sleep(0.2)
            else:
                self.database.record_plan_output_cleanup(
                    plan_id, str(path),
                    deleted=False,
                    error_code="local_file_delete_failed",
                    error_message=f"保留期已过，但无法删除本机下载文件（{last_error or 'OSError'}）",
                )

    def process_job(self, job_id: str) -> None:
        job = self.database.get_job(job_id)
        if job is None:
            return

        path = Path(job["file_path"])
        if (
            path.suffix.lower() not in VIDEO_EXTENSIONS
            and not self.database.job_has_download_plan(job_id)
        ):
            self.database.update_job(
                job_id,
                status="ignored_non_video",
                completed_at=time.time(),
                error_code="non_video",
                error_message="该文件格式未启用视频自动导入",
            )
            return

        if not job.get("source_event_id") and not job.get("source_url"):
            attached = self.database.attach_best_source(job_id)
            job = self.database.get_job(job_id)
            if job is None:
                return
            if job["status"] == "waiting_source":
                self.database.update_job(job_id, status="queued")
                job["status"] = "queued"
            if job["status"] == "ignored_by_user":
                return
            if not attached and not job.get("source_url"):
                source_due_at = float(job["created_at"]) + self.source_grace_period
                if time.time() < source_due_at:
                    self.database.update_job(
                        job_id,
                        next_retry_at=source_due_at,
                        error_code="source_grace",
                        error_message="正在短暂等待浏览器来源，无来源时仍会自动导入",
                    )
                    return

        # One unavailable local Eagle endpoint can otherwise consume its full
        # socket timeout once per queued IDM file.  A short in-memory circuit is
        # enough to collapse the current batch while still detecting a newly
        # started Eagle on the next scheduled retry.
        if time.monotonic() < self._eagle_unavailable_until:
            self._wait_for_eagle(job)
            return

        try:
            stat = path.stat()
        except FileNotFoundError:
            self._retry(job, "file_missing", "下载文件暂时不存在")
            return

        age = time.time() - stat.st_mtime
        if stat.st_size <= 0:
            self._retry(
                job,
                "file_not_stable",
                "下载文件暂时为空，将在几秒内自动重试",
                delay_override=3.0,
                maximum_attempts=20,
                terminal_message="下载文件持续为空，已停止自动重试；确认下载完成后可手动重试",
            )
            return
        if age < self.minimum_file_age:
            delay = max(0.5, min(3.0, self.minimum_file_age - age + 0.25))
            self._retry(
                job,
                "file_not_stable",
                "下载文件刚完成，将在几秒内自动重试",
                delay_override=delay,
                maximum_attempts=20,
                terminal_message="下载文件持续未稳定，已停止自动重试；确认下载完成后可手动重试",
            )
            return

        try:
            fingerprint = job.get("fingerprint") or sha256_file(path)
        except OSError as exc:
            self._retry(job, "file_read_error", f"无法读取下载文件：{exc}")
            return

        fingerprint_owner = self.database.fingerprint_owner(fingerprint)
        if fingerprint_owner == job_id and job.get("eagle_item_id"):
            self.database.update_job(
                job_id,
                status="imported",
                next_retry_at=None,
                error_code=None,
                error_message=None,
                completed_at=time.time(),
            )
            return
        if fingerprint_owner is not None:
            self.database.update_job(
                job_id,
                status="skipped_duplicate",
                fingerprint=fingerprint,
                completed_at=time.time(),
                error_code="duplicate",
                error_message="相同内容的视频已经导入过",
            )
            return

        self.database.update_job(job_id, fingerprint=fingerprint)
        latest_job = self.database.get_job(job_id)
        if latest_job is None or latest_job.get("status") == "ignored_by_user":
            return
        try:
            item_id = self.eagle.add_from_path(str(path), job.get("source_url"))
        except EagleUnavailable:
            self._eagle_unavailable_until = time.monotonic() + 5.0
            self._wait_for_eagle(job)
            return
        except EagleImportError as exc:
            self._retry(job, "eagle_import_error", str(exc))
            return

        self._eagle_unavailable_until = 0.0
        self.database.remember_fingerprint(fingerprint, job_id, stat.st_size)
        self.database.update_job(
            job_id,
            status="imported",
            eagle_item_id=item_id,
            attempt_count=0,
            next_retry_at=None,
            error_code=None,
            error_message=None,
            completed_at=time.time(),
        )

    def _retry(
        self,
        job: dict,
        code: str,
        message: str,
        delay_override: float | None = None,
        maximum_attempts: int = 12,
        terminal_message: str | None = None,
    ) -> None:
        attempts = int(job.get("attempt_count") or 0) + 1
        delay = (
            max(0.5, float(delay_override))
            if delay_override is not None
            else min(15 * (2 ** min(attempts - 1, 6)), 15 * 60)
        )
        status = "failed_permanent" if attempts >= maximum_attempts else "retry"
        self.database.update_job(
            job["id"],
            status=status,
            attempt_count=attempts,
            next_retry_at=None if status == "failed_permanent" else time.time() + delay,
            error_code=code,
            error_message=(terminal_message if status == "failed_permanent" and terminal_message else message)[:1000],
            completed_at=time.time() if status == "failed_permanent" else None,
        )

    def _wait_for_eagle(self, job: dict) -> None:
        attempts = int(job.get("attempt_count") or 0) + 1
        stopped = attempts >= 120
        self.database.update_job(
            job["id"],
            status="failed_permanent" if stopped else "waiting_eagle",
            attempt_count=attempts,
            next_retry_at=None if stopped else time.time() + 30,
            error_code="eagle_unavailable",
            error_message=(
                "等待 Eagle 超过约 1 小时，已停止自动重试；打开 Eagle 后可手动重试"
                if stopped
                else "正在等待 Eagle 启动，将自动重试"
            ),
            completed_at=time.time() if stopped else None,
        )
