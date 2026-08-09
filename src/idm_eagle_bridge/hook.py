from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .database import Database
from .constants import APP_NAME, LEGACY_APP_NAME
from .wake_signal import notify_processing_service


def start_assistant_hidden() -> bool:
    """下载触发器发现助手未运行时，静默启动完整助手。"""
    if os.environ.get("IDM_EAGLE_DISABLE_AUTO_START") == "1":
        return False

    project_directory = _project_directory()
    candidates = (
        project_directory / f"{APP_NAME}.exe",
        project_directory / f"{LEGACY_APP_NAME}.exe",
        project_directory / "IDM-Eagle助手.exe",
        project_directory / "launcher" / "IdmEagleAssistant.exe",
    )
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        return False

    try:
        subprocess.Popen(
            [str(executable), "--start-hidden"],
            cwd=str(project_directory),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except OSError:
        return False
    return True


def _project_directory() -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        executable_directory = Path(sys.executable).resolve().parent
        candidates.extend((executable_directory, *executable_directory.parents))
    candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        if (candidate / f"{APP_NAME}.exe").is_file() or (
            candidate / f"{LEGACY_APP_NAME}.exe"
        ).is_file() or (
            candidate / "IDM-Eagle助手.exe"
        ).is_file():
            return candidate
    return candidates[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="接收 IDM 下载完成的文件路径")
    parser.add_argument("file", help="IDM 下载完成后的完整文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.file).expanduser()
    if not path.is_absolute():
        print("必须提供完整文件路径", file=sys.stderr)
        return 2
    Database().add_job(str(path))
    if not notify_processing_service():
        start_assistant_hidden()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
