from __future__ import annotations

APP_NAME = "下载中转站"
APP_VERSION = "1.4.1"
EXTENSION_PROTOCOL_VERSION = 1
DATA_DIR_NAME = "IdmEagleAutoImport"
DEFAULT_EAGLE_BASE_URL = "http://127.0.0.1:41595"
DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = 47652
DEFAULT_HISTORY_DAYS = 90
DEFAULT_HISTORY_LIMIT = 10_000
DEFAULT_PROCESS_INTERVAL = 15.0
DEFAULT_SOURCE_GRACE_PERIOD = 4.0

VIDEO_EXTENSIONS = frozenset(
    {
        ".avi",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ts",
        ".webm",
        ".wmv",
    }
)

TERMINAL_JOB_STATUSES = frozenset(
    {
        "imported",
        "skipped_duplicate",
        "ignored_non_video",
        "ignored_by_user",
        "failed_permanent",
    }
)

TERMINAL_MEDIA_PLAN_STATUSES = frozenset(
    {
        "imported",
        "completed_local",
        "retry",
        "canceled",
    }
)

TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "yclid",
        "_ga",
        "_gl",
    }
)
