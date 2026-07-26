from __future__ import annotations

import argparse
import time

from .api_server import LocalApiServer
from .constants import DEFAULT_PROCESS_INTERVAL
from .database import Database
from .processor import JobProcessor
from .service import ProcessingService
from .single_instance import SingleInstance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载中转站：IDM 视频自动导入 Eagle")
    parser.add_argument("--once", action="store_true", help="只处理一轮任务后退出")
    parser.add_argument(
        "--cleanup-wechat-capture",
        action="store_true",
        help="恢复视频号捕获代理并移除本程序证书后退出",
    )
    parser.add_argument("--headless", action="store_true", help="不显示窗口，只运行后台服务")
    parser.add_argument(
        "--start-hidden",
        action="store_true",
        help="启动后直接在右下角运行，不弹出主窗口",
    )
    parser.add_argument(
        "--external-tray",
        action="store_true",
        help="由 Windows 原生启动器管理右下角图标",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_PROCESS_INTERVAL,
        help="后台保底检查间隔（秒）；新下载会立即唤醒",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cleanup_wechat_capture:
        from .wechat_channels import cleanup_wechat_capture

        cleanup_wechat_capture()
        return 0
    database = Database()
    if args.once:
        JobProcessor(database).process_once()
        return 0

    instance = SingleInstance()
    if instance.already_running:
        instance.close()
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "下载中转站已经在右下角运行。",
            "下载中转站",
            0x40,
        )
        return 0

    processing = ProcessingService(database, args.interval)
    api_server = LocalApiServer(database, media_ready_callback=processing.wake)
    api_server.start()
    processing.start()
    try:
        if args.headless:
            while True:
                time.sleep(60)
        else:
            from .ui import MainWindow

            MainWindow(
                database,
                api_server,
                processing,
                external_tray=args.external_tray,
                start_hidden=args.start_hidden,
            ).run()
    except KeyboardInterrupt:
        pass
    finally:
        # LocalApiServer.stop() restores any owned WeChat capture proxy first.
        # Do that before the legacy processor can spend up to five seconds
        # waiting for its worker thread during application shutdown.
        api_server.stop()
        processing.stop()
        instance.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
