from __future__ import annotations

import argparse
from pathlib import Path
import sys

from english_reading_assistant.desktop_launcher import (
    DesktopLauncherError,
    install_desktop_launcher,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为项目创建 macOS 桌面启动按钮。")
    parser.add_argument(
        "--output",
        type=Path,
        help="自定义输出路径，默认是 ~/Desktop/英语阅读助手.app",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(__file__).resolve().parent
    output_path = args.output.expanduser() if args.output else None

    try:
        created_path = install_desktop_launcher(
            project_dir,
            output_path,
            overwrite_existing=True,
        )
    except DesktopLauncherError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"已更新桌面启动器：{created_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
