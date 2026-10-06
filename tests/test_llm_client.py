from era.config import load_config
from era.db import connect
from era.llm.client import extract_error_detail, ping


def test_extract_error_detail_prefers_api_message():
    raw_error = '{"error": {"message": "Insufficient Balance", "code": "insufficient_balance"}}'
    assert extract_error_detail(raw_error) == "Insufficient Balance (code: insufficient_balance)"


def test_mock_ping_writes_llm_call(isolated):
    cfg = load_config()
    conn = connect(cfg)
    result = ping(conn, cfg)
    assert "pong" in result.content
    row = conn.execute("SELECT purpose, ok, model FROM llm_calls").fetchone()
    assert row["purpose"] == "ping"
    assert row["ok"] == 1
    conn.close()
