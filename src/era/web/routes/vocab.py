from __future__ import annotations

from fastapi import APIRouter, Request

from era.config import load_config
from era.db import connect
from era.learner.model import is_predicted_unknown, load_profile, p_known
from era.web.deps import page

router = APIRouter()


@router.get("/vocab")
def vocab_page(request: Request, q: str = ""):
    cfg = load_config()
    conn = connect(cfg)
    try:
        profile = load_profile(conn)
        rows = []
        result = None
        if q.strip():
            lemma = q.strip().lower()
            explicit = conn.execute("SELECT * FROM user_words WHERE lemma = ?", (lemma,)).fetchone()
            p = p_known(conn, lemma, profile)
            result = {
                "lemma": lemma,
                "explicit": explicit,
                "p": p,
                "predicted_unknown": is_predicted_unknown(p),
                "label": _label(explicit, p),
            }
        rows = conn.execute(
            "SELECT lemma, status, source, confidence, lookups, encounters, updated_at "
            "FROM user_words ORDER BY updated_at DESC LIMIT 80"
        ).fetchall()
        return page(
            request,
            "vocab.html",
            {"q": q, "result": result, "rows": rows, "profile": profile},
        )
    finally:
        conn.close()


def _label(explicit, p: float) -> str:
    if explicit:
        return f"{explicit['status']} · {explicit['source']}"
    if p >= 0.5:
        return f"预测已知 · p={p:.2f}"
    return f"预测未知 · p={p:.2f}"
