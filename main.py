from __future__ import annotations

import sys

from english_reading_assistant.ui import launch_app


def main() -> int:
    try:
        launch_app()
    except Exception as exc:
        print(f"应用启动失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
