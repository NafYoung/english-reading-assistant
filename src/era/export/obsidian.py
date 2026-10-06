from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from era.config import ConfigError, load_obsidian_config


class ObsidianSaveError(Exception):
    """Raised when saving a note to Obsidian fails."""


def _quote_markdown(text: str) -> str:
    lines = text.strip().splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def build_obsidian_note_block(
    source_text: str,
    analysis_result: str,
    created_at: Optional[datetime] = None,
) -> str:
    timestamp = (created_at or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M:%S")
    quoted_source = _quote_markdown(source_text)
    clean_result = analysis_result.strip()

    return (
        f"## {timestamp}\n\n"
        "### 原文\n"
        f"{quoted_source}\n\n"
        "### 解析\n"
        f"{clean_result}\n\n"
        "---\n"
    )


def build_session_summary_block(
    title: str,
    summary: str,
    created_at: Optional[datetime] = None,
) -> str:
    timestamp = (created_at or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"## {timestamp} · {title}\n\n"
        f"{summary.strip()}\n\n"
        "---\n"
    )


def resolve_obsidian_note_path(config_path: Optional[Path] = None) -> Path:
    try:
        obsidian_config = load_obsidian_config(config_path)
    except ConfigError as exc:
        raise ObsidianSaveError(str(exc)) from exc

    vault_root = Path(obsidian_config.vault_path).expanduser()
    if not vault_root.exists() or not vault_root.is_dir():
        raise ObsidianSaveError("Obsidian vault 路径无效，请检查 vault_path")

    vault_root = vault_root.resolve()
    target_path = (vault_root / obsidian_config.note_path).resolve()

    try:
        target_path.relative_to(vault_root)
    except ValueError as exc:
        raise ObsidianSaveError("Obsidian note_path 超出 vault 范围，请检查配置") from exc

    return target_path


def append_to_obsidian_note(
    source_text: str,
    analysis_result: str,
    config_path: Optional[Path] = None,
    created_at: Optional[datetime] = None,
) -> str:
    target_path = resolve_obsidian_note_path(config_path)
    note_block = build_obsidian_note_block(source_text, analysis_result, created_at)
    _append_block(target_path, note_block)

    try:
        obsidian_config = load_obsidian_config(config_path)
    except ConfigError as exc:
        raise ObsidianSaveError(str(exc)) from exc

    return Path(obsidian_config.note_path).as_posix()


def append_session_summary(
    title: str,
    summary: str,
    config_path: Optional[Path] = None,
    created_at: Optional[datetime] = None,
) -> str:
    target_path = resolve_obsidian_note_path(config_path)
    note_block = build_session_summary_block(title, summary, created_at)
    _append_block(target_path, note_block)
    obsidian_config = load_obsidian_config(config_path)
    return Path(obsidian_config.note_path).as_posix()


def _append_block(target_path: Path, note_block: str) -> None:
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("a", encoding="utf-8") as note_file:
            if target_path.exists() and target_path.stat().st_size > 0:
                note_file.write("\n")
            note_file.write(note_block)
    except OSError as exc:
        raise ObsidianSaveError(f"写入 Obsidian 笔记失败：{exc}") from exc
