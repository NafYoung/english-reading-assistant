from __future__ import annotations

import json
from pathlib import Path

from era.config import ConfigError, load_config, load_obsidian_config, save_config


def test_load_config_allows_missing_key(isolated):
    cfg = load_config()
    assert cfg.llm.api_key == ""
    assert cfg.llm.model == "deepseek-flash"
    assert cfg.has_llm_key  # mock env is on in isolated fixture


def test_env_key_wins(isolated, monkeypatch):
    monkeypatch.setenv("ERA_MOCK_LLM", "0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    path = Path("config.json")
    path.write_text(
        json.dumps({"llm": {"api_key": "sk-from-file", "model": "deepseek-flash"}}),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.llm.api_key == "sk-from-env"


def test_save_and_reload_roundtrip(isolated, monkeypatch):
    monkeypatch.setenv("ERA_MOCK_LLM", "0")
    cfg = load_config()
    cfg.llm.api_key = "sk-saved"
    cfg.eudic_api_key = "eu-1"
    cfg.strict_hints = False
    save_config(cfg)
    loaded = load_config()
    assert loaded.llm.api_key == "sk-saved"
    assert loaded.eudic_api_key == "eu-1"
    assert loaded.strict_hints is False


def test_obsidian_rejects_absolute_note_path(isolated):
    Path("config.json").write_text(
        json.dumps(
            {
                "llm": {"api_key": "x"},
                "obsidian": {"vault_path": str(Path("vault").resolve()), "note_path": "/abs.md"},
            }
        ),
        encoding="utf-8",
    )
    Path("vault").mkdir()
    try:
        load_obsidian_config()
        raise AssertionError("should have failed")
    except ConfigError as exc:
        assert "相对路径" in str(exc)
