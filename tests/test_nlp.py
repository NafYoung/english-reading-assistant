from era.config import load_config
from era.db import connect
from era.nlp.analyze import analyze_text, dict_lookup_fn
from era.nlp.lemmatize import lemma_candidates, pick_lemma
from era.nlp.tokenize import normalize_text, tokenize


def _lookup_from_conn(conn):
    return dict_lookup_fn(conn)


def test_acting_goes_to_act(isolated):
    conn = connect(load_config())
    lemma = pick_lemma("acting", _lookup_from_conn(conn))
    assert lemma == "act"


def test_number_does_not_become_numb(isolated):
    conn = connect(load_config())
    lemma = pick_lemma("number", _lookup_from_conn(conn))
    assert lemma == "number"
    assert "numb" not in lemma_candidates("number")


def test_routing_does_not_become_rout(isolated):
    conn = connect(load_config())
    lemma = pick_lemma("routing", _lookup_from_conn(conn))
    assert lemma != "rout"
    assert lemma in {"routing", "route"}


def test_wkh_is_oov(isolated):
    conn = connect(load_config())
    lemma = pick_lemma("wkh", _lookup_from_conn(conn))
    assert lemma is None


def test_contraction_and_hyphen():
    toks = tokenize("They're using in-context learning.")
    surfaces = [t.surface for t in toks]
    assert "They're" in surfaces
    hyphen = next(t for t in toks if t.surface == "in-context")
    assert hyphen.hyphen_parts == ["in", "context"]


def test_nfkc_and_linebreak_hyphen():
    text = normalize_text("ef\ufb01cient trans-\nformer")
    assert "fi" in text or "ﬁ" not in text
    assert "transformer" in text.replace(" ", "")


def test_proper_noun_skipped(isolated):
    conn = connect(load_config())
    text = "The researcher met Alice in the garden. Alice smiled."
    analysis = analyze_text(text, _lookup_from_conn(conn))
    # sentence-internal Alice, never lowercase in the doc
    proper = [t for t in analysis.tokens if t.token.surface == "Alice"]
    assert proper
    assert any(t.is_proper for t in proper)
