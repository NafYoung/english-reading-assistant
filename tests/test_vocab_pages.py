

def test_vocab_search_reach_and_rare(client, isolated):
    res = client.get("/vocab?q=reach")
    assert res.status_code == 200
    assert "预测已知" in res.text
    res = client.get("/vocab?q=embedding")
    assert "预测未知" in res.text


def test_txt_import_shows_eudic_style_status(client, isolated):
    res = client.post(
        "/import/txt",
        data={"pasted": "orchestrator\n", "default_status": "learning"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "导入" in res.text
    page = client.get("/vocab?q=orchestrator")
    assert "learning" in page.text
    assert "csv" in page.text


def test_placement_page_renders(client):
    res = client.get("/placement")
    assert res.status_code == 200
    assert "分级测试" in res.text


def test_finished_placement_shows_result(client):
    from era.config import load_config
    from era.db import connect
    from era.learner.placement import finish_run, start_run

    cfg = load_config()
    conn = connect(cfg)
    run = start_run(conn)
    for i, item in enumerate(run.items):
        run.answers[i] = not item.is_pseudo
    run.cursor_idx = len(run.items)
    run.stage = 2
    finish_run(conn, run)
    rid = run.id
    conn.close()
    res = client.get(f"/placement?run_id={rid}")
    assert res.status_code == 200
    assert "词汇量估计" in res.text
