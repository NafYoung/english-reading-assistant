
from era.config import load_config
from era.db import connect, dict_count
from era.dictionary.setup import build_slim_ecdict
from tests.fixtures import write_stardict


def test_build_slim_from_fixture(isolated):
    src = isolated / "stardict.db"
    dest = isolated / "data" / "ecdict_slim.db"
    write_stardict(src)
    n = build_slim_ecdict(src, dest)
    assert n >= 10
    cfg = load_config()
    conn = connect(cfg)
    assert dict_count(conn) == n
    conn.close()


def test_setup_page_reports_dict(client):
    res = client.get("/setup")
    assert res.status_code == 200
    assert "词典已就绪" in res.text
    assert "deepseek-flash" in res.text
    assert "DeepSeek API Key" in res.text


def test_ping_and_debug_log(client):
    res = client.post("/setup/ping", follow_redirects=True)
    assert res.status_code == 200
    assert "测试连接成功" in res.text
    log = client.get("/debug/llm-calls")
    assert log.status_code == 200
    assert "ping" in log.text
