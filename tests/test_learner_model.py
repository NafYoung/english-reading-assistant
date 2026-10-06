from era.config import load_config
from era.db import connect
from era.learner.model import (
    apply_event,
    get_word,
    is_predicted_unknown,
    p_known,
    upsert_word,
)
from era.learner.srs import review, serialize_new_card


def test_explicit_status_overrides_prior(isolated):
    cfg = load_config()
    conn = connect(cfg)
    upsert_word(conn, "reach", status="learning", source="eudic", confidence=0.3)
    conn.commit()
    assert p_known(conn, "reach") == 0.3
    upsert_word(conn, "reach", status="known", source="manual", confidence=0.95)
    conn.commit()
    assert p_known(conn, "reach") == 0.95


def test_band_prior_common_vs_rare(isolated):
    conn = connect(load_config())
    p_reach = p_known(conn, "reach")
    p_embed = p_known(conn, "embedding")
    assert p_reach >= 0.5
    assert p_embed < 0.5
    assert not is_predicted_unknown(p_reach)
    assert is_predicted_unknown(p_embed)


def test_oov_is_unknown(isolated):
    conn = connect(load_config())
    assert p_known(conn, "agentic") == 0.0


def test_lookup_l1_writeback(isolated):
    conn = connect(load_config())
    apply_event(conn, "latency", "lookup_l1")
    conn.commit()
    row = get_word(conn, "latency")
    assert row["status"] == "learning"
    assert row["source"] == "reading"
    assert row["lookups"] >= 1
    assert row["fsrs_card"]


def test_quiz_and_review_writeback(isolated):
    conn = connect(load_config())
    apply_event(conn, "model", "lookup_l1")
    apply_event(conn, "model", "quiz_right")
    conn.commit()
    row = get_word(conn, "model")
    assert row["due_at"]
    apply_event(conn, "model", "review_good")
    conn.commit()
    events = [r["event"] for r in conn.execute("SELECT event FROM word_events WHERE lemma='model'")]
    assert "quiz_right" in events
    assert "review_good" in events


def test_confirm_known(isolated):
    conn = connect(load_config())
    apply_event(conn, "workflow", "confirm_known")
    conn.commit()
    row = get_word(conn, "workflow")
    assert row["status"] == "known"
    assert row["source"] == "reading"


def test_fsrs_roundtrip():
    raw = serialize_new_card()
    new_json, due = review(raw, "good")
    assert due
    assert "stability" in new_json
