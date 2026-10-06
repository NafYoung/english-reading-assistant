from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from era.export.obsidian import (
    ObsidianSaveError,
    append_to_obsidian_note,
    build_obsidian_note_block,
    resolve_obsidian_note_path,
)


def _write_config(config_path: Path, vault_path: str, note_path: str) -> None:
    config_path.write_text(
        json.dumps(
            {
                "llm": {
                    "base_url": "https://api.deepseek.com",
                    "api_key": "test-key",
                    "model": "deepseek-flash",
                },
                "obsidian": {"vault_path": vault_path, "note_path": note_path},
            }
        ),
        encoding="utf-8",
    )


def test_resolve_obsidian_note_path_rejects_escape(isolated):
    vault_path = isolated / "vault"
    vault_path.mkdir()
    _write_config(isolated / "config.json", str(vault_path), "../outside.md")
    try:
        resolve_obsidian_note_path(isolated / "config.json")
        raise AssertionError("should have failed")
    except ObsidianSaveError as exc:
        assert "超出 vault 范围" in str(exc)


def test_append_to_obsidian_note_creates_directories_and_appends(isolated):
    vault_path = isolated / "vault"
    vault_path.mkdir()
    config_path = isolated / "config.json"
    _write_config(config_path, str(vault_path), "Inbox/English Reading.md")

    note_path = append_to_obsidian_note(
        "First sentence.",
        "第一次解析结果",
        config_path=config_path,
        created_at=datetime(2026, 3, 30, 15, 0, 0),
    )
    assert note_path == "Inbox/English Reading.md"
    append_to_obsidian_note(
        "Second sentence.",
        "第二次解析结果",
        config_path=config_path,
        created_at=datetime(2026, 3, 30, 15, 1, 0),
    )
    content = (vault_path / "Inbox" / "English Reading.md").read_text(encoding="utf-8")
    assert "## 2026-03-30 15:00:00" in content
    assert "> First sentence." in content
    assert "第二次解析结果" in content


def test_build_obsidian_note_block_uses_markdown_template():
    note_block = build_obsidian_note_block(
        "Line one.\nLine two.",
        "解析结果内容",
        created_at=datetime(2026, 3, 30, 15, 2, 0),
    )
    assert "## 2026-03-30 15:02:00" in note_block
    assert "> Line one." in note_block
    assert "### 解析" in note_block
