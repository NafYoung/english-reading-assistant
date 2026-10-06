from era.coach.gaps import coverage_band, doc_gap
from era.coach.tools import fallback_plan, validate_plan
from era.config import load_config
from era.db import connect
from era.ingest.pdf import is_garbage_block
from era.ingest.pipeline import create_corpus, ingest_document
from era.nlp.analyze import dict_lookup_fn


def _seed_docs(conn):
    cid = create_corpus(conn, "Agent 入门", "test")
    ingest_document(
        conn,
        cid,
        source_type="text",
        source_ref="a.md",
        title="Easy",
        text="The model and the language can reach the paper. Read the paper in context.",
    )
    ingest_document(
        conn,
        cid,
        source_type="text",
        source_ref="b.md",
        title="Harder",
        text=(
            "An agentic workflow uses an orchestrator. "
            "Transformer latency and embedding attention appear twice: "
            "transformer embedding, transformer embedding."
        ),
    )
    return cid


def test_garbage_block_drops_shifted_words(isolated):
    conn = connect(load_config())
    lookup = dict_lookup_fn(conn)
    garbage = "wkh dqg fw rx wkh"
    clean = "The paper describes the model and the language."
    assert is_garbage_block(garbage, lookup) is True
    assert is_garbage_block(clean, lookup) is False


def test_gap_coverage_and_hyphen(isolated):
    conn = connect(load_config())
    cid = create_corpus(conn, "t", "")
    ingest_document(
        conn,
        cid,
        source_type="text",
        source_ref="c.md",
        title="hyphen",
        text="We study in-context learning in the paper. in-context examples help.",
    )
    docs = conn.execute("SELECT id FROM documents").fetchall()
    gap = doc_gap(conn, docs[0]["id"])
    assert 0 <= gap.coverage <= 1
    assert coverage_band(0.99) == "independent"
    assert coverage_band(0.96) == "guided"
    assert coverage_band(0.5) == "stretch"


def test_unknown_top_has_no_pdf_garbage(isolated):
    conn = connect(load_config())
    cid = create_corpus(conn, "t", "")
    ingest_document(
        conn,
        cid,
        source_type="text",
        source_ref="g.md",
        title="g",
        text="The workflow uses an orchestrator. The workflow needs an orchestrator.",
    )
    lemmas = [r["lemma"] for r in conn.execute("SELECT lemma FROM doc_lemmas")]
    for junk in ("wkh", "dqg", "fw", "rx"):
        assert junk not in lemmas


def test_validate_plan_and_fallback(isolated):
    conn = connect(load_config())
    cid = _seed_docs(conn)
    docs = [r["id"] for r in conn.execute("SELECT id FROM documents WHERE corpus_id=?", (cid,))]
    ok, err, payload = validate_plan(
        conn,
        cid,
        {"order": docs, "preteach": {}, "daily_quota_words": 800, "rationale_zh": "x"},
    )
    assert ok, err
    ok, err, _ = validate_plan(
        conn,
        cid,
        {"order": docs, "preteach": {str(docs[0]): ["not-in-gap-zzzz"]}, "daily_quota_words": 800},
    )
    assert not ok
    plan = fallback_plan(conn, cid)
    assert sorted(plan["order"]) == sorted(docs)
    assert plan["fallback"] is True
    assert 300 <= plan["daily_quota_words"] <= 5000


def test_planner_fallback_on_invalid_model(isolated, monkeypatch):
    from era.coach.agent import run_planner
    from era.config import load_config

    conn = connect(load_config())
    cid = _seed_docs(conn)
    cfg = load_config()
    cfg.llm.mock = False
    cfg.llm.api_key = "sk-fake"
    cfg.llm.model = "no-such-model"
    plan, trace_id, used_fallback = run_planner(conn, cfg, cid)
    assert used_fallback is True
    assert plan.get("fallback") is True
    steps = conn.execute("SELECT kind FROM agent_traces WHERE trace_id=?", (trace_id,)).fetchall()
    assert steps
