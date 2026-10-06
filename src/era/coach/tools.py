from __future__ import annotations

import sqlite3
from collections import Counter

from era.coach.gaps import corpus_gaps, doc_gap, unknown_lemmas_for_doc
from era.dictionary.lookup import candidates
from era.learner.model import load_profile


def get_learner_profile(conn: sqlite3.Connection) -> dict:
    profile = load_profile(conn)
    sessions = conn.execute(
        "SELECT COUNT(*) AS n, AVG(l3_count * 1000.0 / NULLIF(words_read,0)) AS l3_per_k, "
        "AVG(quiz_score) AS quiz FROM sessions WHERE started_at >= datetime('now','-7 days')"
    ).fetchone()
    return {
        "vocab_estimate": profile.vocab_estimate,
        "false_alarm_rate": profile.false_alarm_rate,
        "sessions_7d": int(sessions["n"] or 0),
        "l3_per_thousand": sessions["l3_per_k"],
        "quiz_score": sessions["quiz"],
    }


def get_corpus_overview(conn: sqlite3.Connection, corpus_id: int) -> dict:
    gaps = corpus_gaps(conn, corpus_id)
    suggested = fallback_order(conn, corpus_id, gaps)
    return {
        "docs": [
            {
                "doc_id": g.doc_id,
                "title": g.title,
                "n_tokens": g.n_tokens,
                "coverage": round(g.coverage, 4),
                "band": g.band,
                "n_unknown_general": len(g.unknown_general),
                "n_terms": len(g.term_candidates),
                "difficulty": round(g.difficulty, 4),
            }
            for g in gaps
        ],
        "suggested_order": suggested,
    }


def get_doc_gaps(conn: sqlite3.Connection, doc_id: int, top_k: int = 20) -> dict:
    gap = doc_gap(conn, doc_id)
    corpus_freq: Counter[str] = Counter()
    for lemma, _n in gap.unknown_general + gap.term_candidates:
        row = conn.execute(
            "SELECT SUM(count) AS n FROM doc_lemmas WHERE lemma=?", (lemma,)
        ).fetchone()
        corpus_freq[lemma] = int(row["n"] or 0)
    ranked = sorted(corpus_freq.items(), key=lambda x: -x[1])[:top_k]
    items = []
    for lemma, n in ranked:
        sent = conn.execute(
            "SELECT text FROM sentences WHERE id = "
            "(SELECT first_sentence_id FROM doc_lemmas WHERE doc_id=? AND lemma=?)",
            (doc_id, lemma),
        ).fetchone()
        items.append({"lemma": lemma, "corpus_count": n, "sentence": sent["text"] if sent else ""})
    return {"doc_id": doc_id, "items": items}


def lookup_tool(conn: sqlite3.Connection, lemma: str) -> dict:
    c = candidates(conn, lemma)
    return {
        "lemma": lemma,
        "en": [{"id": s.sid, "text": s.text} for s in c.en],
        "zh": [{"id": s.sid, "text": s.text} for s in c.zh],
        "glossary": [{"id": s.sid, "text": s.text} for s in c.glossary],
    }


def fallback_order(conn: sqlite3.Connection, corpus_id: int, gaps=None) -> list[int]:
    gaps = gaps or corpus_gaps(conn, corpus_id)
    term_home: dict[str, tuple[int, int]] = {}
    for g in gaps:
        for lemma, n in g.term_candidates:
            prev = term_home.get(lemma)
            if prev is None or n > prev[1]:
                term_home[lemma] = (g.doc_id, n)
    intro_score: Counter[int] = Counter()
    for lemma, (doc_id, n) in term_home.items():
        intro_score[doc_id] += n
    ranked = sorted(gaps, key=lambda g: (g.difficulty - 0.02 * intro_score[g.doc_id], g.doc_id))
    return [g.doc_id for g in ranked]


def validate_plan(conn: sqlite3.Connection, corpus_id: int, payload: dict) -> tuple[bool, str, dict]:
    docs = [r["id"] for r in conn.execute("SELECT id FROM documents WHERE corpus_id=?", (corpus_id,))]
    order = payload.get("order") or []
    try:
        order = [int(x) for x in order]
    except (TypeError, ValueError):
        return False, "order 必须是文档 id 列表", payload
    if sorted(order) != sorted(docs) or len(order) != len(set(order)):
        return False, f"order 必须是语料文档的一个排列，当前文档 {docs}", payload
    preteach = payload.get("preteach") or {}
    normalized: dict[int, list[str]] = {}
    for key, words in preteach.items():
        try:
            doc_id = int(key)
        except (TypeError, ValueError):
            return False, f"preteach 的键必须是 doc_id：{key}", payload
        if doc_id not in docs:
            return False, f"preteach 包含语料外文档 {doc_id}", payload
        if len(words) > 15:
            return False, f"文档 {doc_id} 的预习词超过 15 个", payload
        allowed = unknown_lemmas_for_doc(conn, doc_id)
        bad = [w for w in words if w.lower() not in allowed]
        if bad:
            return False, f"预习词不在该篇未知候选中：{bad}", payload
        normalized[doc_id] = [w.lower() for w in words]
    quota = int(payload.get("daily_quota_words") or 0)
    if quota < 300 or quota > 5000:
        return False, "daily_quota_words 必须在 300–5000 之间", payload
    payload = dict(payload)
    payload["order"] = order
    payload["preteach"] = {str(k): v for k, v in normalized.items()}
    payload["daily_quota_words"] = quota
    return True, "", payload


def fallback_plan(conn: sqlite3.Connection, corpus_id: int) -> dict:
    gaps = corpus_gaps(conn, corpus_id)
    order = fallback_order(conn, corpus_id, gaps)
    preteach = {}
    for g in gaps:
        words = [w for w, _ in (g.term_candidates + g.unknown_general)[:8]]
        preteach[str(g.doc_id)] = words
    return {
        "order": order,
        "preteach": preteach,
        "daily_quota_words": 800,
        "rationale_zh": "规则计划：按预测未知比例和术语首次解释文档排序。模型未给出合法计划。",
        "fallback": True,
    }
