from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from era.coach.agent import run_planner
from era.coach.gaps import corpus_gaps
from era.config import load_config
from era.db import connect
from era.dictionary.glossary import draft_term, enqueue_term
from era.ingest.pdf import IngestError
from era.ingest.pipeline import create_corpus, ingest_document
from era.llm.client import LLMClient
from era.llm.schemas import TermClassify
from era.web.deps import page

router = APIRouter()


@router.get("/corpora")
def corpora_list(request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        rows = conn.execute("SELECT * FROM corpora ORDER BY id DESC").fetchall()
        counts = {
            r["corpus_id"]: r["n"]
            for r in conn.execute(
                "SELECT corpus_id, COUNT(*) AS n FROM documents GROUP BY corpus_id"
            )
        }
        return page(request, "corpora.html", {"rows": rows, "counts": counts})
    finally:
        conn.close()


@router.post("/corpora")
def corpora_create(title: str = Form(...), goal: str = Form("")):
    cfg = load_config()
    conn = connect(cfg)
    try:
        cid = create_corpus(conn, title.strip() or "未命名语料", goal.strip())
        return RedirectResponse(f"/corpora/{cid}", status_code=303)
    finally:
        conn.close()


@router.get("/corpora/{corpus_id}")
def corpus_detail(request: Request, corpus_id: int, err: str | None = None):
    cfg = load_config()
    conn = connect(cfg)
    try:
        corpus = conn.execute("SELECT * FROM corpora WHERE id=?", (corpus_id,)).fetchone()
        if not corpus:
            return page(request, "stub.html", {"title": "未找到", "message": "没有这个语料"})
        docs = conn.execute(
            "SELECT * FROM documents WHERE corpus_id=? ORDER BY id", (corpus_id,)
        ).fetchall()
        reports = []
        for d in docs:
            try:
                reports.append(json.loads(d["ingest_report"] or "{}"))
            except json.JSONDecodeError:
                reports.append({})
        gaps = corpus_gaps(conn, corpus_id)
        plan_row = conn.execute(
            "SELECT * FROM plans WHERE corpus_id=? ORDER BY id DESC LIMIT 1", (corpus_id,)
        ).fetchone()
        plan = json.loads(plan_row["plan_json"]) if plan_row else None
        return page(
            request,
            "corpus.html",
            {
                "corpus": corpus,
                "docs": list(zip(docs, reports, gaps, strict=False)),
                "plan": plan,
                "plan_row": plan_row,
                "err": err,
            },
        )
    finally:
        conn.close()


@router.post("/corpora/{corpus_id}/add")
async def corpus_add(
    corpus_id: int,
    source_type: str = Form(...),
    url: str = Form(""),
    title: str = Form(""),
    pasted: str = Form(""),
    file: UploadFile | None = File(None),
):
    cfg = load_config()
    conn = connect(cfg)
    try:
        if source_type == "url":
            ingest_document(conn, corpus_id, source_type="url", source_ref=url.strip(), title=title or None)
        elif source_type == "pdf":
            if not file or not file.filename:
                raise IngestError("请选择 PDF")
            dest = cfg.paths.uploads_dir / file.filename
            dest.write_bytes(await file.read())
            ingest_document(
                conn,
                corpus_id,
                source_type="pdf",
                source_ref=file.filename,
                title=title or file.filename,
                pdf_path=dest,
            )
        else:
            text = pasted
            source_ref = "pasted.md"
            if file and file.filename:
                raw = await file.read()
                text = raw.decode("utf-8", errors="replace")
                source_ref = file.filename
            ingest_document(
                conn,
                corpus_id,
                source_type="md" if source_ref.endswith(".md") else "text",
                source_ref=source_ref,
                title=title or source_ref,
                text=text,
            )
        _maybe_classify_and_draft(conn, cfg, corpus_id)
        return RedirectResponse(f"/corpora/{corpus_id}", status_code=303)
    except IngestError as exc:
        from urllib.parse import quote

        return RedirectResponse(f"/corpora/{corpus_id}?err={quote(str(exc)[:180])}", status_code=303)
    finally:
        conn.close()


@router.post("/corpora/{corpus_id}/plan")
def corpus_plan(corpus_id: int, force_fallback: int = Form(0)):
    cfg = load_config()
    if force_fallback:
        cfg.llm.model = "invalid-model-for-fallback"
        cfg.llm.mock = False
        cfg.llm.api_key = cfg.llm.api_key or "x"
    conn = connect(cfg)
    try:
        run_planner(conn, cfg, corpus_id)
        return RedirectResponse(f"/corpora/{corpus_id}", status_code=303)
    finally:
        conn.close()


def _maybe_classify_and_draft(conn, cfg, corpus_id: int) -> None:
    terms = [
        r["lemma"]
        for r in conn.execute(
            "SELECT lemma, SUM(count) AS n FROM doc_lemmas "
            "WHERE kind='term_candidate' AND doc_id IN (SELECT id FROM documents WHERE corpus_id=?) "
            "GROUP BY lemma ORDER BY n DESC LIMIT 40",
            (corpus_id,),
        )
    ]
    if not terms:
        return
    client = LLMClient(cfg)
    try:
        result = client.chat(
            conn,
            purpose="term_classify",
            messages=[
                {"role": "system", "content": "Classify each item as term, noise, or general. JSON {labels:{word:label}}. Keys must be a subset of the input."},
                {"role": "user", "content": "CANDIDATES: " + json.dumps(terms)},
            ],
            json_mode=True,
            prompt_version="term_classify.v1",
        )
        parsed = TermClassify.model_validate_json(result.content)
        labels = {k.lower(): v for k, v in parsed.labels.items() if k.lower() in {t.lower() for t in terms}}
    except Exception:
        labels = {t: "term" for t in terms}
    for term, label in labels.items():
        if label != "term":
            continue
        tid = enqueue_term(conn, term, lemma=term)
        examples = [
            r["text"]
            for r in conn.execute(
                "SELECT s.text FROM sentences s JOIN doc_lemmas d ON d.first_sentence_id=s.id "
                "WHERE d.lemma=? LIMIT 2",
                (term,),
            )
        ]
        draft_term(conn, cfg, tid, examples)
