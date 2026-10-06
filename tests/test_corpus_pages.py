def test_corpora_import_markdown_and_glossary(client):
    res = client.post("/corpora", data={"title": "Agent 入门", "goal": "demo"}, follow_redirects=True)
    assert res.status_code == 200
    assert "Agent 入门" in res.text
    # corpus id 1 in isolated db
    res = client.post(
        "/corpora/1/add",
        data={
            "source_type": "md",
            "title": "notes",
            "pasted": "An agentic workflow uses an orchestrator. The orchestrator coordinates the workflow.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "差距报告" in res.text
    gl = client.get("/glossary")
    assert gl.status_code == 200


def test_generate_plan_page(client):
    client.post("/corpora", data={"title": "c", "goal": ""})
    client.post(
        "/corpora/1/add",
        data={"source_type": "md", "title": "a", "pasted": "The model can reach the paper."},
    )
    res = client.post("/corpora/1/plan", follow_redirects=True)
    assert res.status_code == 200
    assert "阅读计划" in res.text
