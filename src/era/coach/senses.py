from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from era.dictionary.glossary import enqueue_term
from era.dictionary.lookup import SenseCandidates, candidates
from era.llm.client import LLMClient, LLMRequestError
from era.llm.schemas import SensePick

PROMPT_VERSION = "sense_pick.v1"
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "sense_pick.v1.md").read_text(
    encoding="utf-8"
)


def pick_sense(
    conn: sqlite3.Connection,
    cfg,
    *,
    lemma: str,
    surface: str,
    sentence: str,
    sentence_id: int,
) -> dict:
    cached = conn.execute(
        "SELECT result_json FROM sense_cache WHERE lemma=? AND sentence_id=? AND prompt_version=?",
        (lemma, sentence_id, PROMPT_VERSION),
    ).fetchone()
    if cached:
        return json.loads(cached["result_json"])

    cand = candidates(conn, lemma)

    def pack(pick: SensePick | None, invalid: bool = False) -> dict:
        no_fit = bool(pick and pick.fit == "no_fit") or cand.empty
        note = (pick.note_zh if pick else "")[:40]
        data = {
            "lemma": lemma,
            "surface": surface,
            "sentence": sentence,
            "en": [{"id": s.sid, "text": s.text, "source": s.source} for s in cand.en],
            "zh": [{"id": s.sid, "text": s.text, "source": s.source} for s in cand.zh],
            "glossary": [{"id": s.sid, "text": s.text, "source": s.source} for s in cand.glossary],
            "chosen": {
                "en_sense": pick.en_sense if pick else None,
                "zh_sense": pick.zh_sense if pick else None,
                "glossary": pick.glossary if pick else None,
                "fit": pick.fit if pick else "no_fit",
            },
            "note_zh": note,
            "invalid": invalid,
            "no_fit": no_fit,
            "empty": cand.empty,
        }
        if no_fit:
            enqueue_term(conn, surface, lemma=lemma, source="llm_draft", sentence_id=sentence_id)
        return data

    ids = cand.by_id()
    pick_obj: SensePick | None = None
    invalid = False
    try:
        pick_obj = _call(conn, cfg, cand, surface, lemma, sentence)
        if not _valid(pick_obj, ids):
            pick_obj = _call(conn, cfg, cand, surface, lemma, sentence)
            if not _valid(pick_obj, ids):
                invalid = True
                pick_obj = None
    except LLMRequestError:
        invalid = True
        pick_obj = None

    data = pack(pick_obj, invalid=invalid)
    conn.execute(
        "INSERT OR REPLACE INTO sense_cache(lemma, sentence_id, prompt_version, result_json) VALUES (?,?,?,?)",
        (lemma, sentence_id, PROMPT_VERSION, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    return data


def _valid(pick: SensePick, ids: dict) -> bool:
    if pick.fit == "no_fit":
        return pick.en_sense is None and pick.zh_sense is None and pick.glossary is None
    for field_name in ("en_sense", "zh_sense", "glossary"):
        val = getattr(pick, field_name)
        if val and val not in ids:
            return False
    return True


def _call(conn, cfg, cand: SenseCandidates, surface: str, lemma: str, sentence: str) -> SensePick:
    client = LLMClient(cfg)
    listing = []
    for s in cand.en + cand.zh + cand.glossary:
        listing.append(f"{s.sid} [{s.source}] {s.text}")
    user = (
        f"SENTENCE: {sentence}\nWORD: {surface} (lemma {lemma})\nCANDIDATES:\n"
        + "\n".join(listing)
    )
    result = client.chat(
        conn,
        purpose="sense_pick",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        prompt_version=PROMPT_VERSION,
    )
    return SensePick.model_validate_json(result.content)
