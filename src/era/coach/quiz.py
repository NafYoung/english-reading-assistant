from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from era.llm.client import LLMClient, LLMRequestError
from era.llm.schemas import QuizItem, QuizOut, QuizVerify
from era.nlp.chunking import split_text_into_chunks

PROMPT_VERSION = "quiz.v1"
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "quiz.v1.md").read_text(encoding="utf-8")
VERIFY_PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "quiz_verify.v1.md").read_text(
    encoding="utf-8"
)


def _sentences_for_session(conn: sqlite3.Connection, doc_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, idx, text FROM sentences WHERE doc_id=? ORDER BY idx", (doc_id,)
    ).fetchall()


def _verify(conn, cfg, item: QuizItem, evidence_text: str, bare: bool) -> str:
    client = LLMClient(cfg)
    if bare:
        user = f"QUESTION: {item.question}\nOPTIONS: {json.dumps(item.options)}\nNo passage."
    else:
        user = f"EVIDENCE:\n{evidence_text}\nQUESTION: {item.question}\nOPTIONS: {json.dumps(item.options)}"
    result = client.chat(
        conn,
        purpose="quiz_verify",
        messages=[
            {"role": "system", "content": VERIFY_PROMPT},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        prompt_version="quiz_verify.v1",
    )
    return QuizVerify.model_validate_json(result.content).choice.upper()


def _filter_items(conn, cfg, items: list[QuizItem], sent_by_id: dict[int, str]) -> tuple[list[QuizItem], dict]:
    if getattr(cfg, "llm", None) is not None and cfg.llm.mock:
        return items[:3], {"mock": True}
    kept = []
    report = {"dropped": []}
    for item in items[:3]:
        evidence = "\n".join(sent_by_id.get(i, "") for i in item.evidence_sentence_ids)
        try:
            a = _verify(conn, cfg, item, evidence, bare=False)
            b = _verify(conn, cfg, item, evidence, bare=True)
        except (LLMRequestError, Exception) as exc:
            report["dropped"].append({"q": item.question, "reason": str(exc)})
            continue
        if a != item.answer.upper():
            report["dropped"].append({"q": item.question, "reason": "evidence_fail"})
            continue
        if b == item.answer.upper():
            report["dropped"].append({"q": item.question, "reason": "guessable"})
            continue
        kept.append(item)
    return kept, report


def generate_cloze(
    conn: sqlite3.Connection,
    lookups: list[tuple[str, str]],
    rng: random.Random | None = None,
) -> list[dict]:
    """lookups: (lemma, sentence). Distractors from ECDICT, same-ish rank, different lemma."""
    rng = rng or random.Random()
    items = []
    for lemma, sentence in lookups[:5]:
        if lemma.lower() not in sentence.lower():
            blank = sentence
        else:
            blank = re_blank(sentence, lemma)
        distractors = _distractors(conn, lemma, rng)
        options = [lemma, *distractors][:4]
        rng.shuffle(options)
        if lemma not in options:
            options[0] = lemma
        items.append(
            {
                "type": "cloze",
                "lemma": lemma,
                "sentence": blank,
                "options": options,
                "answer": lemma,
            }
        )
    return items


def re_blank(sentence: str, lemma: str) -> str:
    import re

    return re.sub(re.escape(lemma), "______", sentence, count=1, flags=re.I)


def _distractors(conn: sqlite3.Connection, lemma: str, rng: random.Random) -> list[str]:
    try:
        row = conn.execute("SELECT frq, pos FROM ecdict.dict WHERE word=?", (lemma,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row or not row["frq"]:
        pool = conn.execute(
            "SELECT word FROM ecdict.dict WHERE length(word)>3 LIMIT 30"
        ).fetchall() if _has(conn) else []
        words = [r["word"] for r in pool if r["word"] != lemma]
        rng.shuffle(words)
        return words[:3]
    frq = int(row["frq"])
    rows = conn.execute(
        "SELECT word FROM ecdict.dict WHERE word != ? AND frq BETWEEN ? AND ? AND length(word)>3 LIMIT 20",
        (lemma, max(frq - 1000, 1), frq + 1000),
    ).fetchall()
    words = [r["word"] for r in rows]
    rng.shuffle(words)
    return words[:3]


def _has(conn) -> bool:
    return conn.execute("SELECT 1 FROM pragma_database_list WHERE name='ecdict'").fetchone() is not None


def generate_quiz(
    conn: sqlite3.Connection,
    cfg,
    *,
    doc_id: int,
    session_id: int,
    lookup_lemmas: list[tuple[str, str]],
) -> int:
    sents = _sentences_for_session(conn, doc_id)
    sent_by_id = {int(s["id"]): s["text"] for s in sents}
    passage = "\n".join(f"[{s['id']}] {s['text']}" for s in sents)
    chunks = split_text_into_chunks(passage, max_chars=4000)
    client = LLMClient(cfg)
    items: list[QuizItem] = []
    verify_report: dict = {}
    try:
        result = client.chat(
            conn,
            purpose="quiz",
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": chunks[0] if chunks else passage},
            ],
            json_mode=True,
            prompt_version=PROMPT_VERSION,
        )
        parsed = QuizOut.model_validate_json(result.content)
        items, verify_report = _filter_items(conn, cfg, parsed.items, sent_by_id)
        if len(items) < 3:
            result = client.chat(
                conn,
                purpose="quiz",
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": (chunks[0] if chunks else passage) + "\nRegenerate weaker items."},
                ],
                json_mode=True,
                prompt_version=PROMPT_VERSION,
            )
            parsed = QuizOut.model_validate_json(result.content)
            extra, extra_rep = _filter_items(conn, cfg, parsed.items, sent_by_id)
            verify_report["retry"] = extra_rep
            for it in extra:
                if len(items) >= 3:
                    break
                items.append(it)
    except (LLMRequestError, Exception) as exc:
        verify_report["error"] = str(exc)

    cloze = generate_cloze(conn, lookup_lemmas)
    payload = {
        "comprehension": [it.model_dump() for it in items[:3]],
        "cloze": cloze,
    }
    cur = conn.execute(
        "INSERT INTO quizzes(session_id, items_json, verify_json) VALUES (?,?,?)",
        (session_id, json.dumps(payload, ensure_ascii=False), json.dumps(verify_report, ensure_ascii=False)),
    )
    conn.commit()
    return int(cur.lastrowid)
