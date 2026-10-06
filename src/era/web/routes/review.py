from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from era.config import load_config
from era.db import connect, utcnow
from era.learner.model import apply_event
from era.web.deps import page

router = APIRouter()


@router.get("/review")
def review_page(request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        now = utcnow()
        due = conn.execute(
            "SELECT * FROM user_words WHERE due_at IS NOT NULL AND due_at <= ? "
            "ORDER BY due_at LIMIT 1",
            (now,),
        ).fetchone()
        context = ""
        if due:
            ev = conn.execute(
                "SELECT sentence_id FROM word_events WHERE lemma=? AND sentence_id IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (due["lemma"],),
            ).fetchone()
            if ev:
                sent = conn.execute(
                    "SELECT text FROM sentences WHERE id=?", (ev["sentence_id"],)
                ).fetchone()
                context = sent["text"] if sent else ""
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM user_words WHERE due_at IS NOT NULL AND due_at <= ?",
            (now,),
        ).fetchone()["n"]
        return page(
            request,
            "review.html",
            {"card": due, "context": context, "remaining": remaining},
        )
    finally:
        conn.close()


@router.post("/review")
def review_post(lemma: str = Form(...), rating: str = Form(...)):
    cfg = load_config()
    conn = connect(cfg)
    try:
        event = {
            "again": "review_again",
            "hard": "review_hard",
            "good": "review_good",
            "easy": "review_easy",
        }[rating]
        apply_event(conn, lemma, event)
        conn.commit()
        return RedirectResponse("/review", status_code=303)
    finally:
        conn.close()
