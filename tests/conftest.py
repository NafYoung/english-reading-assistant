from __future__ import annotations

import pytest

from tests.fixtures import write_slim_dict


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ERA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ERA_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setenv("ERA_MOCK_LLM", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    write_slim_dict(data / "ecdict_slim.db")
    return tmp_path


@pytest.fixture
def client(isolated):
    from fastapi.testclient import TestClient

    from era.web.app import create_app

    return TestClient(create_app())
