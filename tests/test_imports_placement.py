
from era.config import load_config
from era.db import connect
from era.learner.imports.csvtxt import parse_word_list
from era.learner.imports.eudic import fetch_eudic_words
from era.learner.imports.maimemo import map_record
from era.learner.model import get_word, import_lemmas
from era.learner.placement import PlacementItem, PlacementRun, estimate, finish_run


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return FakeResp(self.payload)

    def close(self):
        pass


def test_parse_word_list():
    text = "reach\nlatency,learning\n# comment\n"
    pairs = parse_word_list(text)
    assert ("reach", "known") in pairs
    assert ("latency", "learning") in pairs


def test_csv_import_sets_source(isolated):
    conn = connect(load_config())
    n = import_lemmas(conn, ["reach", "latency"], status="learning", source="eudic", confidence=0.3)
    assert n == 2
    row = get_word(conn, "reach")
    assert row["status"] == "learning"
    assert row["source"] == "eudic"


def test_eudic_fixture_shape():
    payload = {"data": [{"word": "orchestrator", "add_time": "2026-01-01"}]}
    words = fetch_eudic_words("dummy-key", client=FakeClient(payload))
    assert words[0]["word"] == "orchestrator"


def test_maimemo_mapping():
    lemma, status, conf = map_record(
        {"voc_spelling": "agent", "last_response": "WELL_FAMILIAR", "study_count": 1}
    )
    assert (lemma, status) == ("agent", "known")
    lemma, status, _ = map_record(
        {"voc_spelling": "latency", "last_response": "FAMILIAR", "study_count": 3}
    )
    assert status == "known"
    lemma, status, _ = map_record(
        {"voc_spelling": "workflow", "last_response": "FORGET", "study_count": 1}
    )
    assert status == "learning"


def test_placement_estimate_false_alarm():
    items = [
        PlacementItem("the", False, 0),
        PlacementItem("the", False, 0),
        PlacementItem("blimpet", True, None),
        PlacementItem("gornack", True, None),
    ]
    run = PlacementRun(id=1, stage=1, items=items, answers={0: True, 1: True, 2: True, 3: False}, cursor_idx=4)
    sizes = [1000] + [0] * 19
    v, curve, f = estimate(run, sizes)
    assert f == 0.5
    # h=1, p = (1-0.5)/(1-0.5) = 1
    assert curve[0] == 1.0
    assert v == 1000


def test_finish_run_writes_profile(isolated):
    conn = connect(load_config())
    items = [PlacementItem("reach", False, 0), PlacementItem("blimpet", True, None)]
    conn.execute(
        "CREATE TABLE IF NOT EXISTS placement_runs ("
        "id INTEGER PRIMARY KEY, stage INTEGER, items_json TEXT, answers_json TEXT, "
        "cursor_idx INTEGER, created_at TEXT, finished_at TEXT)"
    )
    conn.execute(
        "INSERT INTO placement_runs(stage, items_json, answers_json, cursor_idx) VALUES (2,'[]','{}',0)"
    )
    conn.commit()
    run = PlacementRun(
        id=1,
        stage=2,
        items=items,
        answers={0: True, 1: False},
        cursor_idx=2,
    )
    profile = finish_run(conn, run)
    assert profile.vocab_estimate >= 0
    assert get_word(conn, "reach")["status"] == "known"
