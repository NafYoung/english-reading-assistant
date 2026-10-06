from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from era.config import load_config
from era.db import connect, utcnow
from era.dictionary.lookup import candidates
from era.evals.runners import item_key, load_samples, reports_dir, run_eval
from era.web.deps import page

router = APIRouter()


def _labeled_keys(conn, task: str) -> set[str]:
    keys: set[str] = set()
    for row in conn.execute("SELECT item_json FROM eval_labels WHERE task=?", (task,)):
        try:
            keys.add(item_key(json.loads(row["item_json"])))
        except json.JSONDecodeError:
            continue
    return keys


def _next_sample(conn, task: str) -> dict | None:
    seen = _labeled_keys(conn, task)
    for item in load_samples(task):
        if item_key(item) not in seen:
            return item
    return None


@router.get("/evals")
def evals_page(request: Request, task: str = "e3", msg: str | None = None):
    cfg = load_config()
    conn = connect(cfg)
    try:
        if task not in {"e1", "e2", "e3", "e4", "e5", "e6"}:
            task = "e3"
        labels = conn.execute(
            "SELECT * FROM eval_labels WHERE task=? ORDER BY id DESC LIMIT 30", (task,)
        ).fetchall()
        rdir = reports_dir()
        reports = sorted(rdir.glob("*.md"), reverse=True)[:20] if rdir.exists() else []
        contents = [(p.name, p.read_text(encoding="utf-8")[:6000]) for p in reports]
        nxt = _next_sample(conn, task)
        cand = None
        if nxt and nxt.get("lemma"):
            cand = candidates(conn, nxt["lemma"])
        n_samples = len(load_samples(task))
        n_done = len(_labeled_keys(conn, task))
        return page(
            request,
            "evals.html",
            {
                "labels": labels,
                "reports": contents,
                "msg": msg,
                "task": task,
                "next_item": nxt,
                "next_item_json": json.dumps(nxt, ensure_ascii=False) if nxt else "",
                "cand": cand,
                "n_samples": n_samples,
                "n_done": n_done,
            },
        )
    finally:
        conn.close()


@router.post("/evals/label")
def evals_label(
    task: str = Form(...),
    item_json: str = Form(...),
    label_json: str = Form(""),
    lemma: str = Form(""),
    fit: str = Form(""),
    en_sense: str = Form(""),
    zh_sense: str = Form(""),
    glossary: str = Form(""),
    unknown: str = Form(""),
    kind: str = Form(""),
    useful: str = Form(""),
    labeler: str = Form("owner"),
):
    cfg = load_config()
    conn = connect(cfg)
    try:
        json.loads(item_json)
        if label_json.strip():
            payload = json.loads(label_json)
        elif task == "e1":
            payload = {"lemma": lemma.strip()}
        elif task == "e2":
            payload = {"kind": kind or "body"}
        elif task == "e3":
            payload = {
                "fit": fit or "good",
                "en_sense": en_sense or None,
                "zh_sense": zh_sense or None,
                "glossary": glossary or None,
            }
        elif task == "e4":
            payload = {"unknown": unknown in {"1", "true", "yes", "on"}}
        elif task == "e6":
            payload = {"useful": int(useful or 0)}
        else:
            payload = {}
        conn.execute(
            "INSERT INTO eval_labels(task, item_json, label_json, labeler, ts) VALUES (?,?,?,?,?)",
            (task, item_json, json.dumps(payload, ensure_ascii=False), labeler, utcnow()),
        )
        conn.commit()
        return RedirectResponse(f"/evals?task={task}&msg=labeled", status_code=303)
    finally:
        conn.close()


@router.post("/evals/run")
def evals_run(task: str = Form(...)):
    path = run_eval(task)
    return RedirectResponse(f"/evals?task={task}&msg={path.name}", status_code=303)
