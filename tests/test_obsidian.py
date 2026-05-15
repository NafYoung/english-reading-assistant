from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from english_reading_assistant.obsidian import (
    ObsidianSaveError,
    append_to_obsidian_note,
    build_obsidian_note_block,
    resolve_obsidian_note_path,
)


class ObsidianIntegrationTests(unittest.TestCase):
    def _write_config(
        self,
        config_path: Path,
        vault_path: str,
        note_path: str,
    ) -> None:
        config_path.write_text(
            json.dumps(
                {
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "test-key",
                    "model": "deepseek-chat",
                    "system_prompt": "请使用简体中文回答",
                    "obsidian": {
                        "vault_path": vault_path,
                        "note_path": note_path,
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_resolve_obsidian_note_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            vault_path = temp_root / "vault"
            vault_path.mkdir()
            config_path = temp_root / "config.json"
            self._write_config(config_path, str(vault_path), "../outside.md")

            with self.assertRaisesRegex(ObsidianSaveError, "超出 vault 范围"):
                resolve_obsidian_note_path(config_path)

    def test_append_to_obsidian_note_creates_directories_and_appends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            vault_path = temp_root / "vault"
            vault_path.mkdir()
            config_path = temp_root / "config.json"
            self._write_config(config_path, str(vault_path), "Inbox/English Reading.md")

            note_path = append_to_obsidian_note(
                "First sentence.",
                "第一次解析结果",
                config_path=config_path,
                created_at=datetime(2026, 3, 30, 15, 0, 0),
            )
            self.assertEqual(note_path, "Inbox/English Reading.md")

            append_to_obsidian_note(
                "Second sentence.",
                "第二次解析结果",
                config_path=config_path,
                created_at=datetime(2026, 3, 30, 15, 1, 0),
            )

            saved_note = vault_path / "Inbox" / "English Reading.md"
            content = saved_note.read_text(encoding="utf-8")

        self.assertIn("## 2026-03-30 15:00:00", content)
        self.assertIn("## 2026-03-30 15:01:00", content)
        self.assertIn("> First sentence.", content)
        self.assertIn("> Second sentence.", content)
        self.assertIn("第一次解析结果", content)
        self.assertIn("第二次解析结果", content)

    def test_build_obsidian_note_block_uses_markdown_template(self) -> None:
        note_block = build_obsidian_note_block(
            "Line one.\nLine two.",
            "解析结果内容",
            created_at=datetime(2026, 3, 30, 15, 2, 0),
        )

        self.assertIn("## 2026-03-30 15:02:00", note_block)
        self.assertIn("### 原文", note_block)
        self.assertIn("> Line one.", note_block)
        self.assertIn("> Line two.", note_block)
        self.assertIn("### 解析", note_block)
        self.assertIn("解析结果内容", note_block)


if __name__ == "__main__":
    unittest.main()
