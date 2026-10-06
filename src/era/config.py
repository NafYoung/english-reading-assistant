from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE_NAME = "config.json"


class ConfigError(Exception):
    """Raised when the local configuration is missing or invalid."""


@dataclass
class LLMConfig:
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-flash"
    timeout_seconds: float = 90.0
    mock: bool = False


@dataclass
class PathsConfig:
    data_dir: Path
    db_path: Path
    dict_path: Path
    uploads_dir: Path

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class ObsidianConfig:
    vault_path: str = ""
    note_path: str = "Inbox/Reading Coach.md"

    @property
    def configured(self) -> bool:
        return bool(self.vault_path.strip() and self.note_path.strip())


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    paths: PathsConfig = field(default_factory=lambda: default_paths())
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    eudic_api_key: str = ""
    maimemo_token: str = ""
    strict_hints: bool = True

    @property
    def has_llm_key(self) -> bool:
        return bool(self.llm.api_key.strip()) or self.llm.mock


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def default_paths(data_dir: Path | None = None) -> PathsConfig:
    root = Path(os.environ.get("ERA_DATA_DIR", "")).expanduser() if os.environ.get("ERA_DATA_DIR") else None
    data = data_dir or root or (Path.cwd() / "data")
    data = data.resolve()
    return PathsConfig(
        data_dir=data,
        db_path=data / "era.db",
        dict_path=data / "ecdict_slim.db",
        uploads_dir=data / "uploads",
    )


def get_default_config_path() -> Path:
    env = os.environ.get("ERA_CONFIG_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / CONFIG_FILE_NAME


def _load_raw(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or get_default_config_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"配置文件无法解析：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("配置文件格式错误：根节点必须是对象")
    return raw


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or get_default_config_path()
    raw = _load_raw(path)
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    # Accept a flat legacy file (old Tk config) by mapping top-level keys.
    if not llm_raw and raw.get("base_url"):
        llm_raw = {
            "base_url": raw.get("base_url"),
            "api_key": raw.get("api_key"),
            "model": raw.get("model"),
            "timeout_seconds": raw.get("timeout_seconds", 90),
        }

    timeout_value = llm_raw.get("timeout_seconds", 90)
    try:
        timeout_seconds = float(timeout_value)
    except (TypeError, ValueError):
        timeout_seconds = 90.0

    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    file_key = str(llm_raw.get("api_key", "")).strip()
    mock_env = os.environ.get("ERA_MOCK_LLM", "").strip() in {"1", "true", "TRUE", "yes"}
    mock = bool(llm_raw.get("mock", False)) or mock_env

    llm = LLMConfig(
        base_url=str(llm_raw.get("base_url") or "https://api.deepseek.com").strip(),
        api_key=env_key or file_key,
        model=str(llm_raw.get("model") or "deepseek-flash").strip(),
        timeout_seconds=timeout_seconds,
        mock=mock,
    )

    obsidian_raw = raw.get("obsidian") if isinstance(raw.get("obsidian"), dict) else {}
    obsidian = ObsidianConfig(
        vault_path=str(obsidian_raw.get("vault_path") or "").strip(),
        note_path=str(obsidian_raw.get("note_path") or "Inbox/Reading Coach.md").strip(),
    )

    eudic = str(raw.get("eudic_api_key") or os.environ.get("EUDIC_API_KEY") or "").strip()
    maimemo = str(raw.get("maimemo_token") or os.environ.get("MAIMEMO_TOKEN") or "").strip()
    strict = raw.get("strict_hints", True)
    if isinstance(strict, str):
        strict = strict.lower() not in {"0", "false", "no"}

    cfg = AppConfig(
        llm=llm,
        paths=default_paths(),
        obsidian=obsidian,
        eudic_api_key=eudic,
        maimemo_token=maimemo,
        strict_hints=bool(strict),
    )
    cfg.paths.ensure()
    return cfg


def load_obsidian_config(config_path: Path | None = None) -> ObsidianConfig:
    cfg = load_config(config_path)
    if not cfg.obsidian.vault_path:
        raise ConfigError("未找到 Obsidian 配置，请检查本地配置文件")
    vault_path = cfg.obsidian.vault_path
    note_path = cfg.obsidian.note_path
    if not Path(vault_path).expanduser().is_absolute():
        raise ConfigError("Obsidian vault_path 必须是绝对路径")
    if Path(note_path).is_absolute():
        raise ConfigError("Obsidian note_path 必须是相对路径")
    return cfg.obsidian


def save_config(cfg: AppConfig, config_path: Path | None = None) -> Path:
    path = config_path or get_default_config_path()
    payload = {
        "llm": {
            "base_url": cfg.llm.base_url,
            "api_key": cfg.llm.api_key,
            "model": cfg.llm.model,
            "timeout_seconds": cfg.llm.timeout_seconds,
        },
        "eudic_api_key": cfg.eudic_api_key,
        "maimemo_token": cfg.maimemo_token,
        "strict_hints": cfg.strict_hints,
        "obsidian": asdict(cfg.obsidian),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def missing_llm_key_message() -> str:
    return "未填写 DeepSeek API Key。请在设置页粘贴，或设置环境变量 DEEPSEEK_API_KEY。"
