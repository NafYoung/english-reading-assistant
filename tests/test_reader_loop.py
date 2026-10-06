from era.coach.quiz import generate_cloze
from era.coach.senses import pick_sense
from era.coach.structure import chunks_ok, explain_structure
from era.config import load_config
from era.db import connect
from era.dictionary.glossary import list_terms
from era.ingest.pipeline import create_corpus, ingest_document


def test_sense_pick_mocked_and_no_fit(isolated):
    cfg = load_config()
    conn = connect(cfg)
    cid = create_corpus(conn, "t", "")
    ingest_document(
        conn,
        cid,
        source_type="text",
        source_ref="a",
        title="a",
        text="The latency of the transformer model is high.",
    )
    sent = conn.execute("SELECT * FROM sentences LIMIT 1").fetchone()
    latency = pick_sense(
        conn, cfg, lemma="latency", surface="latency", sentence=sent["text"], sentence_id=sent["id"]
    )
    assert latency["chosen"]["en_sense"] in {None, "E1"}
    assert latency["en"]
    trans = pick_sense(
        conn,
        cfg,
        lemma="transformer",
        surface="transformer",
        sentence=sent["text"],
        sentence_id=sent["id"],
    )
    assert trans["no_fit"] is True
    drafts = list_terms(conn, "draft")
    assert any(r["lemma"] == "transformer" for r in drafts)


def test_structure_chunks_are_substrings(isolated):
    sentence = "The model can reach the paper."
    assert chunks_ok(sentence, ["The model ", "can reach the paper."])
    assert not chunks_ok(sentence, ["The cat", "sat"])
    cfg = load_config()
    conn = connect(cfg)
    out = explain_structure(conn, cfg, sentence)
    if out["chunks"]:
        assert chunks_ok(sentence, out["chunks"])


def test_cloze_distractors_not_llm(isolated):
    conn = connect(load_config())
    items = generate_cloze(conn, [("reach", "They reach the paper.")], rng=__import__("random").Random(0))
    assert items
    assert items[0]["answer"] == "reach"
    assert "______" in items[0]["sentence"]
    assert items[0]["answer"] in items[0]["options"]


def test_reader_flow_lookup_quiz_writeback(client):
    client.post("/corpora", data={"title": "c", "goal": ""})
    client.post(
        "/corpora/1/add",
        data={
            "source_type": "md",
            "title": "doc",
            "pasted": "The latency of the transformer is high. The model can reach the paper.",
        },
    )
    res = client.get("/read/1", follow_redirects=True)
    assert res.status_code == 200
    assert "结束阅读" in res.text
    # session_id in URL after redirect
    url = str(res.request.url)
    assert "session_id=" in url
    sid = url.split("session_id=")[-1].split("&")[0]
    look = client.get(
        "/api/lookup",
        params={"session_id": sid, "sentence_id": 1, "lemma": "latency", "surface": "latency"},
    )
    assert look.status_code == 200
    assert "ECDICT" in look.text
    hint3 = client.get("/api/hint", params={"session_id": sid, "sentence_id": 1, "level": 3})
    assert "严格模式" in hint3.text or "结构" in hint3.text
    client.get("/api/hint", params={"session_id": sid, "sentence_id": 1, "level": 2})
    hint3b = client.get("/api/hint", params={"session_id": sid, "sentence_id": 1, "level": 3})
    assert hint3b.status_code == 200
    end = client.get(f"/session/{sid}/end")
    assert end.status_code == 200
    client.post(f"/session/{sid}/end", data={}, follow_redirects=True)
    quiz = client.get(f"/session/{sid}/quiz")
    assert quiz.status_code == 200
    vocab = client.get("/vocab?q=latency")
    assert "learning" in vocab.text
    review = client.get("/review")
    assert review.status_code == 200
