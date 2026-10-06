from era.config import load_config
from era.db import connect
from era.evals.runners import load_samples, run_eval


def test_eval_samples_are_loadable():
    for task in ("e1", "e2", "e3", "e4", "e6"):
        rows = load_samples(task)
        assert rows, task


def test_run_eval_e1_to_e6(isolated, monkeypatch):
    monkeypatch.setenv("ERA_EVAL_REPORTS", str(isolated / "eval_reports"))
    names = []
    for task in ("e1", "e2", "e3", "e4", "e5", "e6"):
        path = run_eval(task)
        names.append(path.name)
        text = path.read_text(encoding="utf-8")
        assert "基线对比" in text
        assert path.exists()
    assert any(n.endswith("-e1.md") for n in names)
    e3 = (isolated / "eval_reports").glob("*-e3.md")
    body = next(e3).read_text(encoding="utf-8")
    assert "transformer" in body
    assert "no_fit" in body or "True" in body


def test_evals_page_and_label(client):
    res = client.get("/evals?task=e3")
    assert res.status_code == 200
    assert "逐条标注" in res.text
    assert "transformer" in res.text or "latency" in res.text
    item = '{"lemma":"latency","sentence":"The latency of the system is high."}'
    post = client.post(
        "/evals/label",
        data={"task": "e3", "item_json": item, "fit": "good", "en_sense": "E1"},
        follow_redirects=True,
    )
    assert post.status_code == 200
    assert "labeled" in str(post.request.url) or "已标" in post.text or "latency" in post.text
    run = client.post("/evals/run", data={"task": "e1"}, follow_redirects=True)
    assert run.status_code == 200
    assert "E1" in run.text or "词形" in run.text


def test_evals_e4_structured_label(client):
    item = '{"lemma":"orchestrator","sentence":"An orchestrator coordinates tools."}'
    res = client.post(
        "/evals/label",
        data={"task": "e4", "item_json": item, "unknown": "1"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    cfg = load_config()
    conn = connect(cfg)
    row = conn.execute("SELECT * FROM eval_labels WHERE task='e4'").fetchone()
    assert row is not None
    assert "true" in row["label_json"].lower()


def test_dashboard_empty_and_with_sessions(client):
    empty = client.get("/dashboard")
    assert empty.status_code == 200
    assert "仪表盘" in empty.text
    cfg = load_config()
    conn = connect(cfg)
    for i in range(5):
        conn.execute(
            "INSERT INTO sessions(doc_id, started_at, ended_at, words_read, "
            "l1_count, l2_count, l3_count, quiz_score) VALUES (0,?,?,120,?,?,?,0.75)",
            (
                f"2026-10-0{i + 1}T10:00:00Z",
                f"2026-10-0{i + 1}T11:00:00Z",
                10 - i,
                3,
                8 - i,
            ),
        )
    conn.commit()
    conn.close()
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "L3/千词" in res.text
    assert "每千词 L3" in res.text
    for i in range(1, 6):
        assert f"2026-10-0{i}" in res.text
