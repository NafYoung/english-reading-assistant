from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_FILE_NAME = "config.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """Raised when the local configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    api_key: str
    model: str
    system_prompt: str
    timeout_seconds: float = 90.0


@dataclass(frozen=True)
class ObsidianConfig:
    vault_path: str
    note_path: str


def get_default_config_path() -> Path:
    return PROJECT_ROOT / CONFIG_FILE_NAME


def _load_raw_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or get_default_config_path()

    if not path.exists():
        raise ConfigError("未找到 API 密钥，请检查本地配置文件")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"未找到 API 密钥，请检查本地配置文件：{exc}") from exc


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    raw_data = _load_raw_config(config_path)

    required_fields = ("base_url", "api_key", "model", "system_prompt")
    missing_fields = [
        field for field in required_fields if not str(raw_data.get(field, "")).strip()
    ]
    if missing_fields:
        raise ConfigError("未找到 API 密钥，请检查本地配置文件")

    timeout_value = raw_data.get("timeout_seconds", 90)
    try:
        timeout_seconds = float(timeout_value)
    except (TypeError, ValueError):
        timeout_seconds = 90.0

    return AppConfig(
        base_url=str(raw_data["base_url"]).strip(),
        api_key=str(raw_data["api_key"]).strip(),
        model=str(raw_data["model"]).strip(),
        system_prompt=str(raw_data["system_prompt"]).strip(),
        timeout_seconds=timeout_seconds,
    )


def load_obsidian_config(config_path: Optional[Path] = None) -> ObsidianConfig:
    raw_data = _load_raw_config(config_path)
    obsidian_data = raw_data.get("obsidian")

    if not isinstance(obsidian_data, dict):
        raise ConfigError("未找到 Obsidian 配置，请检查本地配置文件")

    required_fields = ("vault_path", "note_path")
    missing_fields = [
        field for field in required_fields if not str(obsidian_data.get(field, "")).strip()
    ]
    if missing_fields:
        raise ConfigError("未找到 Obsidian 配置，请检查本地配置文件")

    vault_path = str(obsidian_data["vault_path"]).strip()
    note_path = str(obsidian_data["note_path"]).strip()

    if not Path(vault_path).expanduser().is_absolute():
        raise ConfigError("Obsidian vault_path 必须是绝对路径")

    if Path(note_path).is_absolute():
        raise ConfigError("Obsidian note_path 必须是相对路径")

    return ObsidianConfig(vault_path=vault_path, note_path=note_path)
