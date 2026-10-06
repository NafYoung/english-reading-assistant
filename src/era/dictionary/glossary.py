from __future__ import annotations

import sqlite3

from era.db import utcnow
from era.llm.client import LLMClient, LLMRequestError
from era.llm.schemas import GlossaryDraft


def enqueue_term(
    conn: sqlite3.Connection,
    term: str,
    *,
    lemma: str | None = None,
    source: str = "llm_draft",
    sentence_id: int | None = None,
) -> int:
    lemma = (lemma or term).lower()
    existing = conn.execute(
        "SELECT id FROM glossary_terms WHERE lemma=? AND status IN ('draft','approved')",
        (lemma,),
    ).fetchone()
    if existing:
        return int(existing["id"])
    cur = conn.execute(
        "INSERT INTO glossary_terms(term, lemma, pos, en_def, zh_def, domain, status, source, "
        "example_sentence_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (term, lemma, "", "", "", "ai", "draft", source, sentence_id, utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def draft_term(conn: sqlite3.Connection, cfg, term_id: int, examples: list[str]) -> None:
    row = conn.execute("SELECT * FROM glossary_terms WHERE id=?", (term_id,)).fetchone()
    if not row:
        return
    client = LLMClient(cfg)
    prompt = (
        f"TERM: {row['term']}\nEXAMPLES:\n"
        + "\n".join(f"- {e}" for e in examples[:2])
        + "\nDraft an AI-domain glossary entry. JSON: {en_def, zh_def, pos}."
    )
    try:
        result = client.chat(
            conn,
            purpose="glossary_draft",
            messages=[
                {"role": "system", "content": "Return JSON only. Do not invent senses outside AI/agent usage."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
            prompt_version="glossary_draft.v1",
        )
        draft = GlossaryDraft.model_validate_json(result.content)
        conn.execute(
            "UPDATE glossary_terms SET en_def=?, zh_def=?, pos=? WHERE id=?",
            (draft.en_def, draft.zh_def, draft.pos, term_id),
        )
        conn.commit()
    except (LLMRequestError, Exception):
        conn.execute(
            "UPDATE glossary_terms SET en_def=?, zh_def=? WHERE id=?",
            ("(draft pending)", "（待起草）", term_id),
        )
        conn.commit()


def set_status(
    conn: sqlite3.Connection,
    term_id: int,
    status: str,
    *,
    en_def: str | None = None,
    zh_def: str | None = None,
) -> None:
    row = conn.execute("SELECT * FROM glossary_terms WHERE id=?", (term_id,)).fetchone()
    if not row:
        return
    conn.execute(
        "UPDATE glossary_terms SET status=?, en_def=?, zh_def=?, reviewed_at=? WHERE id=?",
        (
            status,
            en_def if en_def is not None else row["en_def"],
            zh_def if zh_def is not None else row["zh_def"],
            utcnow(),
            term_id,
        ),
    )
    conn.commit()


def list_terms(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM glossary_terms WHERE status=? ORDER BY id DESC", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM glossary_terms ORDER BY id DESC").fetchall()
