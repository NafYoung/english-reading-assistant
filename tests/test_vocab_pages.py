

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
