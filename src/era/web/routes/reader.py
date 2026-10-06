from __future__ import annotations

import html
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from era.coach.quiz import generate_quiz
from era.coach.senses import pick_sense
from era.coach.structure import explain_structure
from era.coach.translate import translate_sentence
from era.config import load_config
from era.db import connect, utcnow
from era.export.obsidian import ObsidianSaveError, append_session_summary
from era.learner.model import apply_event, is_predicted_unknown, load_profile, p_known
from era.nlp.analyze import analyze_text, dict_lookup_fn
from era.web.deps import page

router = APIRouter()


def _start_session(conn, doc_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO sessions(doc_id, started_at, words_read, l1_count, l2_count, l3_count) "
        "VALUES (?,?,0,0,0,0)",
        (doc_id, utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


@router.get("/read/{doc_id}")
def read_doc(request: Request, doc_id: int, session_id: int | None = None):
    cfg = load_config()
    conn = connect(cfg)
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return page(request, "stub.html", {"title": "未找到文档", "message": "没有这篇文章。"})
        if session_id is None:
            session_id = _start_session(conn, doc_id)
            return RedirectResponse(f"/read/{doc_id}?session_id={session_id}", status_code=303)
        sents = conn.execute(
            "SELECT * FROM sentences WHERE doc_id=? ORDER BY idx", (doc_id,)
        ).fetchall()
        lookup = dict_lookup_fn(conn)
        profile = load_profile(conn)
        analysis = analyze_text(doc["text"] or "", lookup)
        rendered = []
        for sent in sents:
            pieces = _render_sentence(conn, profile, analysis, sent)
            rendered.append((sent, pieces))
        l2_seen = {
            r["sentence_id"]
            for r in conn.execute(
                "SELECT sentence_id FROM hint_events WHERE session_id=? AND level=2",
                (session_id,),
            )
        }
        return page(
            request,
            "read.html",
            {
                "doc": doc,
                "session_id": session_id,
                "rendered": rendered,
                "strict": cfg.strict_hints,
                "l2_seen": l2_seen,
            },
        )
    finally:
        conn.close()


def _render_sentence(conn, profile, analysis, sent) -> str:
    toks = [t for t in analysis.tokens if t.token.sentence_index == sent["idx"]]
    text = sent["text"]
    # map using relative offsets inside sentence
    rel_base = sent["char_start"]
    parts = []
    cursor = 0
    local = text
    for item in toks:
        start = item.token.start - rel_base
        end = item.token.end - rel_base
        if start < 0 or end > len(local) or start < cursor:
            continue
        parts.append(html.escape(local[cursor:start]))
        surface = local[start:end]
        lemma = item.lemma
        if lemma and not item.is_proper:
            unknown = (not item.is_short) and is_predicted_unknown(p_known(conn, lemma, profile))
            cls = "word unknown" if unknown else "word"
            parts.append(
                f'<button type="button" class="{cls}" data-lemma="{html.escape(lemma)}" '
                f'data-surface="{html.escape(surface)}" data-sentence-id="{sent["id"]}">{html.escape(surface)}</button>'
            )
        else:
            parts.append(html.escape(surface))
        cursor = end
    parts.append(html.escape(local[cursor:]))
    return "".join(parts)


@router.get("/api/lookup", response_class=HTMLResponse)
def lookup_fragment(
    request: Request,
    session_id: int,
    sentence_id: int,
    lemma: str,
    surface: str,
):
    cfg = load_config()
    conn = connect(cfg)
    try:
        sent = conn.execute("SELECT * FROM sentences WHERE id=?", (sentence_id,)).fetchone()
        data = pick_sense(
            conn,
            cfg,
            lemma=lemma.lower(),
            surface=surface,
            sentence=sent["text"] if sent else "",
            sentence_id=sentence_id,
        )
        apply_event(conn, lemma, "lookup_l1", session_id=session_id, sentence_id=sentence_id)
        conn.execute(
            "INSERT INTO hint_events(session_id, sentence_id, level, target, ts) VALUES (?,?,?,?,?)",
            (session_id, sentence_id, 1, lemma, utcnow()),
        )
        conn.execute(
            "UPDATE sessions SET l1_count = l1_count + 1 WHERE id=?", (session_id,)
        )
        conn.commit()
        return page(request, "popup_sense.html", {"data": data})
    finally:
        conn.close()


@router.get("/api/hint", response_class=HTMLResponse)
def hint_fragment(
    request: Request,
    session_id: int,
    sentence_id: int,
    level: int,
):
    cfg = load_config()
    conn = connect(cfg)
    try:
        sent = conn.execute("SELECT * FROM sentences WHERE id=?", (sentence_id,)).fetchone()
        if not sent:
            return HTMLResponse("没有这句话。")
        if level == 3 and cfg.strict_hints:
            seen = conn.execute(
                "SELECT 1 FROM hint_events WHERE session_id=? AND sentence_id=? AND level=2",
                (session_id, sentence_id),
            ).fetchone()
            if not seen:
                return HTMLResponse(
                    "<p class='flash err'>严格模式：请先看本句的「结构」，再打开中文。</p>"
                )
        if level == 2:
            data = explain_structure(conn, cfg, sent["text"])
            conn.execute(
                "UPDATE sessions SET l2_count = l2_count + 1 WHERE id=?", (session_id,)
            )
        else:
            prev = conn.execute(
                "SELECT text FROM sentences WHERE doc_id=? AND idx=?",
                (sent["doc_id"], sent["idx"] - 1),
            ).fetchone()
            nxt = conn.execute(
                "SELECT text FROM sentences WHERE doc_id=? AND idx=?",
                (sent["doc_id"], sent["idx"] + 1),
            ).fetchone()
            data = translate_sentence(
                conn,
                cfg,
                sent["text"],
                prev["text"] if prev else "",
                nxt["text"] if nxt else "",
            )
            conn.execute(
                "UPDATE sessions SET l3_count = l3_count + 1 WHERE id=?", (session_id,)
            )
        conn.execute(
            "INSERT INTO hint_events(session_id, sentence_id, level, target, ts) VALUES (?,?,?,?,?)",
            (session_id, sentence_id, level, "", utcnow()),
        )
        conn.commit()
        return page(request, "popup_hint.html", {"level": level, "data": data})
    finally:
        conn.close()


@router.get("/session/{session_id}/end")
def session_end(request: Request, session_id: int):
    cfg = load_config()
    conn = connect(cfg)
    try:
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (session["doc_id"],)).fetchone()
        profile = load_profile(conn)
        clicked = {
            r["target"]
            for r in conn.execute(
                "SELECT target FROM hint_events WHERE session_id=? AND level=1", (session_id,)
            )
        }
        lemmas = conn.execute(
            "SELECT lemma, count FROM doc_lemmas WHERE doc_id=?", (session["doc_id"],)
        ).fetchall()
        pending = []
        for row in lemmas:
            if row["lemma"] in clicked:
                continue
            if is_predicted_unknown(p_known(conn, row["lemma"], profile)):
                pending.append(row["lemma"])
        return page(
            request,
            "session_end.html",
            {"session": session, "doc": doc, "pending": pending[:40]},
        )
    finally:
        conn.close()


@router.post("/session/{session_id}/end")
async def session_end_post(session_id: int, request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        form = await request.form()
        known_set = {str(v) for v in form.getlist("known")}
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        profile = load_profile(conn)
        clicked = {
            r["target"]
            for r in conn.execute(
                "SELECT target FROM hint_events WHERE session_id=? AND level=1", (session_id,)
            )
        }
        pending = []
        for row in conn.execute(
            "SELECT lemma FROM doc_lemmas WHERE doc_id=?", (session["doc_id"],)
        ):
            lemma = row["lemma"]
            p = p_known(conn, lemma, profile)
            if lemma in clicked:
                continue
            if is_predicted_unknown(p):
                pending.append(lemma)
            else:
                apply_event(conn, lemma, "encounter_known", session_id=session_id)
        for lemma in pending:
            if lemma in known_set:
                apply_event(conn, lemma, "confirm_known", session_id=session_id)
            else:
                apply_event(conn, lemma, "confirm_unknown", session_id=session_id)
        conn.commit()
        lookups = []
        for row in conn.execute(
            "SELECT h.target, s.text FROM hint_events h JOIN sentences s ON s.id=h.sentence_id "
            "WHERE h.session_id=? AND h.level=1",
            (session_id,),
        ):
            lookups.append((row["target"], row["text"]))
        generate_quiz(conn, cfg, doc_id=session["doc_id"], session_id=session_id, lookup_lemmas=lookups)
        return RedirectResponse(f"/session/{session_id}/quiz", status_code=303)
    finally:
        conn.close()


@router.get("/session/{session_id}/quiz")
def quiz_page(request: Request, session_id: int, done: int = 0, score: int = 0, total: int = 0):
    cfg = load_config()
    conn = connect(cfg)
    try:
        quiz = conn.execute(
            "SELECT * FROM quizzes WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)
        ).fetchone()
        items = json.loads(quiz["items_json"]) if quiz else {"comprehension": [], "cloze": []}
        return page(
            request,
            "quiz.html",
            {
                "quiz": quiz,
                "items": items,
                "session_id": session_id,
                "done": bool(done),
                "score": score,
                "total": total,
            },
        )
    finally:
        conn.close()


@router.post("/session/{session_id}/quiz")
async def quiz_submit(session_id: int, request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        quiz = conn.execute(
            "SELECT * FROM quizzes WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)
        ).fetchone()
        items = json.loads(quiz["items_json"]) if quiz else {"comprehension": [], "cloze": []}
        form = await request.form()
        correct_n = 0
        total = 0
        idx = 0
        for i, it in enumerate(items.get("comprehension") or []):
            ans = str(form.get(f"c{i}") or "")
            ok = ans.upper() == str(it.get("answer") or "").upper()
            total += 1
            correct_n += int(ok)
            conn.execute(
                "INSERT INTO quiz_answers(quiz_id, item_idx, answer, correct, ts) VALUES (?,?,?,?,?)",
                (quiz["id"], idx, ans, int(ok), utcnow()),
            )
            idx += 1
        for i, it in enumerate(items.get("cloze") or []):
            ans = str(form.get(f"z{i}") or "")
            ok = ans.lower() == str(it.get("answer") or "").lower()
            total += 1
            correct_n += int(ok)
            apply_event(conn, it["lemma"], "quiz_right" if ok else "quiz_wrong", session_id=session_id)
            conn.execute(
                "INSERT INTO quiz_answers(quiz_id, item_idx, answer, correct, ts) VALUES (?,?,?,?,?)",
                (quiz["id"], idx, ans, int(ok), utcnow()),
            )
            idx += 1
        score = (correct_n / total) if total else 1.0
        conn.execute(
            "UPDATE sessions SET ended_at=?, quiz_score=? WHERE id=?",
            (utcnow(), score, session_id),
        )
        conn.commit()
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (session["doc_id"],)).fetchone()
        if cfg.obsidian.configured:
            try:
                summary = (
                    f"**{doc['title']}**\n\n"
                    f"- L1 {session['l1_count']} / L2 {session['l2_count']} / L3 {session['l3_count']}\n"
                    f"- 测验 {correct_n}/{total}（{score:.0%}）\n"
                )
                append_session_summary(doc["title"] or "阅读", summary)
            except ObsidianSaveError:
                pass
        return RedirectResponse(
            f"/session/{session_id}/quiz?done=1&score={correct_n}&total={total}",
            status_code=303,
        )
    finally:
        conn.close()
