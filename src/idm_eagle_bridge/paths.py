from __future__ import annotations

import os
import sys
from pathlib import Path

from .constants import DATA_DIR_NAME


def data_dir() -> Path:
    override = os.environ.get("IDM_EAGLE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        portable_root = Path(sys.executable).resolve().parent
    else:
        portable_root = Path(__file__).resolve().parents[2]
    if (portable_root / ".portable").exists():
        return portable_root / "data"

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / DATA_DIR_NAME

    return Path.home() / ".idm-eagle-auto-import"


def ensure_data_dir() -> Path:
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def database_path() -> Path:
    return ensure_data_dir() / "bridge.db"


def bootstrap_pairing_path() -> Path:
    return ensure_data_dir() / "pairing-bootstrap.json"


def download_station_root() -> Path:
    override = os.environ.get("IDM_EAGLE_DOWNLOAD_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
    else:
        profile = Path(os.environ.get("USERPROFILE") or Path.home())
        root = profile.joinpath("Downloads").resolve()
    station = (
        root
        if root.name.casefold() == "下载中转站".casefold()
        else root / "下载中转站"
    )
    station.mkdir(parents=True, exist_ok=True)
    return station
