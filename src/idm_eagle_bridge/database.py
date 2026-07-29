from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit

from .paths import database_path
from .constants import (
    DEFAULT_HISTORY_DAYS,
    DEFAULT_HISTORY_LIMIT,
    TERMINAL_JOB_STATUSES,
    TERMINAL_MEDIA_PLAN_STATUSES,
)
from .url_utils import clean_page_url, domain_from_url, normalize_domain


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS site_rules (
    domain TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    include_subdomains INTEGER NOT NULL DEFAULT 1 CHECK (include_subdomains IN (0, 1)),
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS source_events (
    id TEXT PRIMARY KEY,
    page_url TEXT NOT NULL,
    page_title TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL,
    media_hint TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    tab_id INTEGER,
    created_at REAL NOT NULL,
    consumed_by_job_id TEXT,
    consumed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_source_unconsumed
ON source_events(consumed_by_job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    status TEXT NOT NULL,
    source_event_id TEXT,
    source_url TEXT,
    source_title TEXT,
    fingerprint TEXT,
    eagle_item_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at REAL,
    error_code TEXT,
    error_message TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY(source_event_id) REFERENCES source_events(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_retry
ON jobs(status, next_retry_at, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_file_status
ON jobs(file_path, status, created_at DESC);

CREATE TABLE IF NOT EXISTS capture_sessions (
    id TEXT PRIMARY KEY,
    tab_id INTEGER,
    page_url TEXT NOT NULL DEFAULT '',
    page_title TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS media_groups (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    group_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    page_url TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    media_kind TEXT NOT NULL DEFAULT 'direct',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES capture_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_media_groups_session
ON media_groups(session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS media_streams (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    client_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    source_url_redacted TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    extension TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    size INTEGER,
    width INTEGER,
    height INTEGER,
    codec TEXT NOT NULL DEFAULT '',
    duration REAL,
    language TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    drm INTEGER NOT NULL DEFAULT 0 CHECK (drm IN (0, 1)),
    created_at REAL NOT NULL,
    FOREIGN KEY(group_id) REFERENCES media_groups(id)
);

CREATE INDEX IF NOT EXISTS idx_media_streams_group
ON media_streams(group_id, client_index);

CREATE TABLE IF NOT EXISTS download_plans (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    output_container TEXT NOT NULL,
    merge_mode TEXT NOT NULL,
    route TEXT NOT NULL,
    import_to_eagle INTEGER NOT NULL DEFAULT 1 CHECK (import_to_eagle IN (0, 1)),
    delete_after_import INTEGER NOT NULL DEFAULT 0 CHECK (delete_after_import IN (0, 1)),
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER,
    phase_detail TEXT NOT NULL DEFAULT '',
    final_path TEXT,
    preview_path TEXT,
    job_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY(group_id) REFERENCES media_groups(id),
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_download_plans_status
ON download_plans(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS imported_fingerprints (
    fingerprint TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    created_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(source_events)")
            }
            if "media_hint" not in columns:
                connection.execute(
                    "ALTER TABLE source_events ADD COLUMN media_hint TEXT NOT NULL DEFAULT ''"
                )
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if schema_version < 2:
                # 0.2 起来源为可选信息；旧版等待来源任务可直接继续处理。
                connection.execute(
                    "UPDATE jobs SET status = 'queued', updated_at = ? WHERE status = 'waiting_source'",
                    (time.time(),),
                )
                connection.execute("PRAGMA user_version = 2")
            if schema_version < 3:
                # 修复自动重试与手动重试相撞后，同一任务被误标为重复的问题。
                now = time.time()
                connection.execute(
                    """
                    UPDATE jobs SET
                        status = 'imported', error_code = NULL, error_message = NULL,
                        next_retry_at = NULL, completed_at = COALESCE(completed_at, ?),
                        updated_at = ?
                    WHERE status = 'skipped_duplicate'
                      AND eagle_item_id IS NOT NULL
                      AND fingerprint IS NOT NULL
                      AND EXISTS (
                        SELECT 1 FROM imported_fingerprints AS imported
                        WHERE imported.fingerprint = jobs.fingerprint
                          AND imported.job_id = jobs.id
                      )
                    """,
                    (now, now),
                )
                connection.execute("PRAGMA user_version = 3")
            if schema_version < 4:
                # 1.0.0 引入可见媒体候选、下载方案和带归属的组件文件。
                # 表由上面的幂等 SCHEMA 创建；旧任务与配对数据保持原样。
                connection.execute("PRAGMA user_version = 4")
            if schema_version < 5:
                # 1.1.0 起统一由本机软件下载。旧版浏览器组件回传表不再使用，
                # 未完成方案因完整签名地址从未落盘，必须回到来源页重新创建。
                plan_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(download_plans)")
                }
                additions = {
                    "import_to_eagle": "INTEGER NOT NULL DEFAULT 1",
                    "downloaded_bytes": "INTEGER NOT NULL DEFAULT 0",
                    "total_bytes": "INTEGER",
                    "phase_detail": "TEXT NOT NULL DEFAULT ''",
                    "preview_path": "TEXT",
                }
                for name, declaration in additions.items():
                    if name not in plan_columns:
                        connection.execute(
                            f"ALTER TABLE download_plans ADD COLUMN {name} {declaration}"
                        )
                stream_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(media_streams)")
                }
                if "duration" not in stream_columns:
                    connection.execute("ALTER TABLE media_streams ADD COLUMN duration REAL")
                connection.execute(
                    """
                    UPDATE download_plans SET
                        route = 'desktop', status = 'retry', progress = 0,
                        error_code = 'download_context_expired',
                        error_message = '下载方式已升级，请回到来源网页重新创建任务',
                        phase_detail = '需要重新创建任务', updated_at = ?
                    WHERE status IN (
                        'downloading_components', 'ready_to_merge', 'merging',
                        'downloading', 'validating'
                    )
                    """,
                    (time.time(),),
                )
                connection.execute("DROP TABLE IF EXISTS component_files")
                connection.execute("PRAGMA user_version = 5")
            if schema_version < 6:
                # 只有新版界面明确请求时，Eagle 导入成功后才允许清理本机副本。
                # 旧计划默认保留，避免升级后改变已经创建任务的删除语义。
                plan_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(download_plans)"
                    )
                }
                if "delete_after_import" not in plan_columns:
                    connection.execute(
                        """
                        ALTER TABLE download_plans
                        ADD COLUMN delete_after_import INTEGER NOT NULL DEFAULT 0
                        CHECK (delete_after_import IN (0, 1))
                        """
                    )
                connection.execute("PRAGMA user_version = 6")

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.session() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        self.set_settings({key: value})

    def get_settings(self, keys: tuple[str, ...]) -> dict[str, Any]:
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        with self.session() as connection:
            rows = connection.execute(
                f"SELECT key, value FROM settings WHERE key IN ({placeholders})", keys
            ).fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(row["value"])
            except json.JSONDecodeError:
                continue
        return result

    def set_settings(self, values: dict[str, Any]) -> None:
        if not values:
            return
        now = time.time()
        rows = [
            (key, json.dumps(value, ensure_ascii=False), now)
            for key, value in values.items()
        ]
        with self.session() as connection:
            connection.executemany(
                """
                INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """, rows
            )

    def ensure_pairing_code(self) -> str:
        existing = self.get_setting("pairing_code")
        if isinstance(existing, str) and len(existing) == 6 and existing.isdigit():
            return existing
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.set_setting("pairing_code", code)
        return code

    def set_site_rule(
        self, domain: str, enabled: bool, include_subdomains: bool = True
    ) -> None:
        normalized = normalize_domain(domain)
        now = time.time()
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO site_rules(domain, enabled, include_subdomains, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    enabled=excluded.enabled,
                    include_subdomains=excluded.include_subdomains,
                    updated_at=excluded.updated_at
                """,
                (normalized, int(enabled), int(include_subdomains), now),
            )

    def site_enabled(self, domain: str) -> bool:
        normalized = normalize_domain(domain)
        with self.session() as connection:
            rows = connection.execute(
                "SELECT domain, enabled, include_subdomains FROM site_rules"
            ).fetchall()

        exact = next((row for row in rows if row["domain"] == normalized), None)
        if exact is not None:
            return bool(exact["enabled"])

        candidates = [
            row
            for row in rows
            if row["include_subdomains"]
            and normalized.endswith("." + row["domain"])
        ]
        if not candidates:
            return False
        closest = max(candidates, key=lambda row: len(row["domain"]))
        return bool(closest["enabled"])

    def list_site_rules(self) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT domain, enabled, include_subdomains, updated_at FROM site_rules ORDER BY domain"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_site_rule(self, domain: str) -> bool:
        normalized = normalize_domain(domain)
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM site_rules WHERE domain = ?", (normalized,)
            )
        return cursor.rowcount > 0

    def clear_site_rules(self) -> int:
        with self.session() as connection:
            cursor = connection.execute("DELETE FROM site_rules")
        return max(cursor.rowcount, 0)

    def add_source_event(
        self,
        page_url: str,
        page_title: str = "",
        media_url: str = "",
        event_type: str = "download_intent",
        tab_id: int | None = None,
        created_at: float | None = None,
    ) -> str:
        cleaned_url = clean_page_url(page_url)
        domain = domain_from_url(cleaned_url)
        control_event = event_type in {"ignore", "site_disabled"}
        if not control_event and not self.site_enabled(domain):
            raise PermissionError("当前网站未开启自动导入")

        event_id = str(uuid.uuid4())
        captured_at = created_at or time.time()
        media_hint = self._media_hint(media_url)
        with self.session() as connection:
            recent = connection.execute(
                """
                SELECT id FROM source_events
                WHERE consumed_by_job_id IS NULL
                  AND page_url = ? AND media_hint = ?
                  AND created_at BETWEEN ? AND ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (cleaned_url, media_hint, captured_at - 3, captured_at + 3),
            ).fetchone()
            if recent is not None:
                return str(recent["id"])
            connection.execute(
                """
                INSERT INTO source_events(
                    id, page_url, page_title, domain, media_hint,
                    event_type, tab_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    cleaned_url,
                    page_title[:500],
                    domain,
                    media_hint,
                    event_type[:80],
                    tab_id,
                    captured_at,
                ),
            )
        return event_id

    def add_job(self, file_path: str, created_at: float | None = None) -> str:
        path = Path(file_path).expanduser()
        job_id = str(uuid.uuid4())
        now = created_at or time.time()
        with self.transaction() as connection:
            existing = connection.execute(
                """
                SELECT id FROM jobs
                WHERE file_path = ?
                  AND status IN ('queued', 'waiting_source', 'waiting_eagle', 'retry')
                  AND created_at >= ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (str(path), now - 5 * 60),
            ).fetchone()
            if existing is not None:
                return str(existing["id"])
            connection.execute(
                """
                INSERT INTO jobs(
                    id, file_path, file_name, extension, status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, 'queued', ?, ?)
                """,
                (job_id, str(path), path.name, path.suffix.lower(), now, now),
            )
        return job_id

    def attach_best_source(
        self, job_id: str, lookback_seconds: float = 4 * 60 * 60
    ) -> bool:
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT id, created_at FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError(job_id)

            source = connection.execute(
                """
                SELECT id, page_url, page_title, media_hint, event_type, created_at
                FROM source_events
                WHERE consumed_by_job_id IS NULL
                  AND created_at <= ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (job["created_at"], job["created_at"] - lookback_seconds),
            ).fetchall()
            if not source:
                return False

            source = self._choose_source(Path(connection.execute(
                "SELECT file_name FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()["file_name"]), source)
            if source is None:
                return False

            now = time.time()
            connection.execute(
                """
                UPDATE source_events
                SET consumed_by_job_id = ?, consumed_at = ?
                WHERE id = ? AND consumed_by_job_id IS NULL
                """,
                (job_id, now, source["id"]),
            )
            if connection.total_changes != 1:
                return False
            ignored = source["event_type"] in {"ignore", "site_disabled"}
            ignored_message = (
                "该网站已关闭自动导入"
                if source["event_type"] == "site_disabled"
                else "用户选择本次不导入"
            )
            connection.execute(
                """
                UPDATE jobs SET
                    source_event_id = ?, source_url = ?, source_title = ?,
                    status = ?, updated_at = ?, completed_at = ?,
                    error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    source["id"],
                    source["page_url"],
                    source["page_title"],
                    "ignored_by_user" if ignored else "queued",
                    now,
                    now if ignored else None,
                    "ignored_by_user" if ignored else None,
                    ignored_message if ignored else None,
                    job_id,
                ),
            )
            return True

    @staticmethod
    def _media_hint(media_url: str) -> str:
        if not media_url:
            return ""
        try:
            path = unquote(urlsplit(media_url).path)
        except ValueError:
            return ""
        return Path(path).name[:500]

    @staticmethod
    def _normalized_match_text(value: str) -> str:
        return "".join(re.findall(r"[a-z0-9\u3400-\u9fff]+", value.lower()))

    @classmethod
    def _choose_source(
        cls, file_name: Path, candidates: list[sqlite3.Row]
    ) -> sqlite3.Row | None:
        if len(candidates) == 1:
            return candidates[0]

        # A page can request the same video repeatedly while it is playing or
        # while IDM is preparing the download.  Treat those requests as one
        # source candidate so duplicate events from the correct page cannot
        # tie with each other and make an otherwise clear match ambiguous.
        candidates_by_page: dict[str, list[sqlite3.Row]] = {}
        for row in candidates:
            candidates_by_page.setdefault(str(row["page_url"]), []).append(row)

        collapsed: list[sqlite3.Row] = []
        for same_page in candidates_by_page.values():
            explicit_same_page = [
                row for row in same_page if row["event_type"] in {"manual", "ignore"}
            ]
            collapsed.append(
                max(explicit_same_page or same_page, key=lambda row: row["created_at"])
            )
        candidates = sorted(
            collapsed, key=lambda row: row["created_at"], reverse=True
        )

        if len(candidates) == 1:
            return candidates[0]

        explicit = [
            row for row in candidates if row["event_type"] in {"manual", "ignore"}
        ]
        if explicit:
            return max(explicit, key=lambda row: row["created_at"])

        file_text = cls._normalized_match_text(file_name.stem)
        if not file_text:
            return None

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in candidates:
            title_text = cls._normalized_match_text(row["page_title"])
            media_text = cls._normalized_match_text(Path(row["media_hint"]).stem)
            title_score = SequenceMatcher(None, file_text, title_text).ratio() if title_text else 0
            media_score = SequenceMatcher(None, file_text, media_text).ratio() if media_text else 0
            scored.append((max(media_score, title_score * 0.8), row))
        scored.sort(key=lambda entry: (entry[0], entry[1]["created_at"]), reverse=True)
        best_score, best = scored[0]
        second_score = scored[1][0]
        if best_score >= 0.58 and best_score - second_score >= 0.12:
            return best
        return None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_actionable_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        now = time.time()
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('waiting_source', 'queued', 'waiting_eagle', 'retry')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def seconds_until_next_action(self, maximum: float) -> float:
        now = time.time()
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT MIN(COALESCE(next_retry_at, ?)) AS due_at
                FROM jobs
                WHERE status IN ('waiting_source', 'queued', 'waiting_eagle', 'retry')
                """,
                (now,),
            ).fetchone()
        due_at = row["due_at"] if row else None
        if due_at is None:
            return max(0.0, maximum)
        return max(0.0, min(maximum, float(due_at) - now))

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "source_event_id",
            "source_url",
            "source_title",
            "fingerprint",
            "eagle_item_id",
            "attempt_count",
            "next_retry_at",
            "error_code",
            "error_message",
            "completed_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [job_id]
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?", values
            )
            if updates.get("status") == "imported":
                completed_at = updates.get("completed_at") or updates["updated_at"]
                connection.execute(
                    """
                    UPDATE download_plans SET
                        status = 'imported', progress = 100,
                        phase_detail = '已导入 Eagle',
                        error_code = NULL, error_message = NULL,
                        completed_at = COALESCE(completed_at, ?), updated_at = ?
                    WHERE job_id = ?
                    """,
                    (completed_at, updates["updated_at"], job_id),
                )

    def record_plan_output_cleanup(
        self,
        plan_id: str,
        expected_path: str,
        *,
        deleted: bool,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        now = time.time()
        with self.transaction() as connection:
            if deleted:
                cursor = connection.execute(
                    """
                    UPDATE download_plans SET
                        final_path = NULL,
                        phase_detail = '已导入 Eagle，本机下载文件已自动删除',
                        error_code = NULL, error_message = NULL, updated_at = ?
                    WHERE id = ? AND status = 'imported' AND final_path = ?
                    """,
                    (now, plan_id, expected_path),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE download_plans SET
                        phase_detail = '已导入 Eagle，本机文件未删除',
                        error_code = ?, error_message = ?, updated_at = ?
                    WHERE id = ? AND status = 'imported' AND final_path = ?
                    """,
                    (
                        error_code,
                        (error_message or "")[:1000],
                        now,
                        plan_id,
                        expected_path,
                    ),
                )
        return cursor.rowcount == 1

    def expired_retained_plans(self, limit: int = 10) -> list[dict[str, Any]]:
        retention_days = self.get_setting("file_retention_days", 7)
        retention_days = max(0, min(365, int(retention_days)))
        if retention_days == 0:
            return []
        cutoff = time.time() - retention_days * 24 * 60 * 60
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT plan.id AS plan_id, plan.final_path, plan.completed_at, jobs.id AS job_id
                FROM download_plans AS plan
                JOIN jobs ON jobs.id = plan.job_id
                WHERE plan.status = 'imported'
                  AND plan.delete_after_import = 1
                  AND plan.final_path IS NOT NULL
                  AND plan.error_code IS NULL
                  AND plan.completed_at IS NOT NULL
                  AND plan.completed_at <= ?
                ORDER BY plan.completed_at ASC
                LIMIT ?
                """,
                (cutoff, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def fingerprint_owner(self, fingerprint: str) -> str | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT job_id FROM imported_fingerprints WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return str(row["job_id"]) if row else None

    def remember_fingerprint(
        self, fingerprint: str, job_id: str, file_size: int
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO imported_fingerprints(
                    fingerprint, job_id, file_size, created_at
                ) VALUES(?, ?, ?, ?)
                """,
                (fingerprint, job_id, file_size, time.time()),
            )

    def list_jobs(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def jobs_revision(self) -> tuple[int, float]:
        with self.session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(MAX(updated_at), 0) AS revision FROM jobs"
            ).fetchone()
        return int(row["count"]), float(row["revision"])

    def ui_snapshot(self) -> dict[str, Any]:
        """Read the small dashboard projection through one database session."""
        with self.session() as connection:
            status_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
            revision_row = connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(MAX(updated_at), 0) AS revision FROM jobs"
            ).fetchone()
            enabled_site_count = connection.execute(
                "SELECT COUNT(*) FROM site_rules WHERE enabled = 1"
            ).fetchone()[0]
        return {
            "status_counts": {
                str(row["status"]): int(row["count"]) for row in status_rows
            },
            "jobs_revision": (
                int(revision_row["count"]),
                float(revision_row["revision"]),
            ),
            "enabled_site_count": int(enabled_site_count),
        }

    def retry_job(self, job_id: str) -> bool:
        with self.session() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET
                    status = 'queued', attempt_count = 0, next_retry_at = NULL,
                    error_code = NULL, error_message = NULL,
                    completed_at = NULL, updated_at = ?
                WHERE id = ?
                  AND status IN (
                    'waiting_source', 'queued', 'waiting_eagle', 'retry', 'failed_permanent'
                  )
                """,
                (time.time(), job_id),
            )
        return cursor.rowcount == 1

    def remove_job(self, job_id: str) -> bool:
        """Remove one import queue row without deleting the source file or Eagle item."""
        now = time.time()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT id FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            unsupported = connection.execute(
                """
                SELECT 1 FROM download_plans
                WHERE job_id = ?
                  AND status NOT IN (
                    'ready_to_import', 'imported', 'completed_local', 'retry', 'canceled'
                  )
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if unsupported is not None:
                raise ValueError("这条导入记录仍由媒体任务使用，请先清理对应媒体任务")
            connection.execute(
                """
                UPDATE download_plans SET
                    status = CASE
                        WHEN status = 'ready_to_import' THEN 'completed_local'
                        ELSE status
                    END,
                    progress = CASE
                        WHEN status = 'ready_to_import' THEN 100
                        ELSE progress
                    END,
                    import_to_eagle = CASE
                        WHEN status = 'ready_to_import' THEN 0
                        ELSE import_to_eagle
                    END,
                    delete_after_import = CASE
                        WHEN status = 'ready_to_import' THEN 0
                        ELSE delete_after_import
                    END,
                    phase_detail = CASE
                        WHEN status = 'ready_to_import'
                            THEN '已移出 Eagle 导入队列，本机文件已保留'
                        ELSE phase_detail
                    END,
                    error_code = CASE
                        WHEN status = 'ready_to_import' THEN NULL
                        ELSE error_code
                    END,
                    error_message = CASE
                        WHEN status = 'ready_to_import' THEN NULL
                        ELSE error_message
                    END,
                    completed_at = CASE
                        WHEN status = 'ready_to_import' THEN COALESCE(completed_at, ?)
                        ELSE completed_at
                    END,
                    job_id = NULL,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (now, now, job_id),
            )
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            connection.execute(
                """
                DELETE FROM source_events
                WHERE consumed_by_job_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs
                      WHERE jobs.source_event_id = source_events.id
                  )
                """,
                (job_id,),
            )
        return cursor.rowcount == 1

    def assign_source(self, job_id: str, source_url: str, source_title: str = "") -> bool:
        cleaned_url = clean_page_url(source_url)
        with self.session() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET
                    source_url = ?, source_title = ?, status = 'queued',
                    attempt_count = 0, next_retry_at = NULL,
                    error_code = NULL, error_message = NULL,
                    completed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (cleaned_url, source_title[:500], time.time(), job_id),
            )
        return cursor.rowcount == 1

    def record_imported_source(
        self, job_id: str, source_url: str, source_title: str = ""
    ) -> bool:
        cleaned_url = clean_page_url(source_url)
        with self.session() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET source_url = ?, source_title = ?, updated_at = ?
                WHERE id = ? AND status = 'imported' AND eagle_item_id IS NOT NULL
                """,
                (cleaned_url, source_title[:500], time.time(), job_id),
            )
        return cursor.rowcount == 1

    def clear_terminal_history(self) -> int:
        statuses = tuple(TERMINAL_JOB_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        plan_statuses = tuple(TERMINAL_MEDIA_PLAN_STATUSES)
        plan_placeholders = ",".join("?" for _ in plan_statuses)
        with self.transaction() as connection:
            # A terminal media plan no longer needs its IDM/Eagle queue row.
            # Unlink it first so clearing the queue history keeps the plan
            # visible and never touches its downloaded output.
            connection.execute(
                f"""
                UPDATE download_plans SET job_id = NULL, updated_at = ?
                WHERE status IN ({plan_placeholders})
                  AND job_id IN (
                      SELECT id FROM jobs WHERE status IN ({placeholders})
                  )
                """,
                (time.time(), *plan_statuses, *statuses),
            )
            cursor = connection.execute(
                f"""
                DELETE FROM jobs
                WHERE status IN ({placeholders})
                  AND NOT EXISTS (
                      SELECT 1 FROM download_plans
                      WHERE download_plans.job_id = jobs.id
                  )
                """,
                statuses,
            )
            connection.execute(
                """
                DELETE FROM source_events
                WHERE consumed_by_job_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs
                      WHERE jobs.id = source_events.consumed_by_job_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs
                      WHERE jobs.source_event_id = source_events.id
                  )
                """
            )
        return max(cursor.rowcount, 0)

    def cleanup_history(
        self,
        history_days: int = DEFAULT_HISTORY_DAYS,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> dict[str, int]:
        cutoff = time.time() - max(history_days, 1) * 86400
        statuses = tuple(TERMINAL_JOB_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        plan_statuses = tuple(TERMINAL_MEDIA_PLAN_STATUSES)
        plan_placeholders = ",".join("?" for _ in plan_statuses)
        with self.transaction() as connection:
            before_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            before_sources = connection.execute(
                "SELECT COUNT(*) FROM source_events"
            ).fetchone()[0]
            connection.execute(
                f"""
                UPDATE download_plans SET job_id = NULL, updated_at = ?
                WHERE status IN ({plan_placeholders})
                  AND job_id IN (
                      SELECT id FROM jobs
                      WHERE status IN ({placeholders})
                        AND COALESCE(completed_at, updated_at) < ?
                  )
                """,
                (time.time(), *plan_statuses, *statuses, cutoff),
            )
            connection.execute(
                f"""
                DELETE FROM jobs
                WHERE status IN ({placeholders})
                  AND COALESCE(completed_at, updated_at) < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM download_plans
                      WHERE download_plans.job_id = jobs.id
                  )
                """,
                (*statuses, cutoff),
            )
            connection.execute(
                f"""
                UPDATE download_plans SET job_id = NULL, updated_at = ?
                WHERE status IN ({plan_placeholders})
                  AND job_id IN (
                      SELECT id FROM jobs
                      WHERE status IN ({placeholders})
                      ORDER BY created_at DESC
                      LIMIT -1 OFFSET ?
                  )
                """,
                (
                    time.time(),
                    *plan_statuses,
                    *statuses,
                    max(history_limit, 1),
                ),
            )
            connection.execute(
                f"""
                DELETE FROM jobs WHERE id IN (
                    SELECT id FROM jobs
                    WHERE status IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                )
                  AND NOT EXISTS (
                      SELECT 1 FROM download_plans
                      WHERE download_plans.job_id = jobs.id
                  )
                """,
                (*statuses, max(history_limit, 1)),
            )
            connection.execute(
                """
                DELETE FROM source_events
                WHERE (
                    (consumed_by_job_id IS NOT NULL AND created_at < ?)
                    OR (consumed_by_job_id IS NULL AND created_at < ?)
                )
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs
                      WHERE jobs.source_event_id = source_events.id
                  )
                """,
                (cutoff, time.time() - 7 * 86400),
            )
            after_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            after_sources = connection.execute(
                "SELECT COUNT(*) FROM source_events"
            ).fetchone()[0]
        return {
            "jobs": before_jobs - after_jobs,
            "source_events": before_sources - after_sources,
        }
