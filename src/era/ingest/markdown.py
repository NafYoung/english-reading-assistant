from __future__ import annotations

from pathlib import Path


def read_text_file(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    return title, text
