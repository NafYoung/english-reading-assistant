from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from era.config import load_config
from era.db import connect
from era.learner.placement import (
    BATCH_SIZE,
    finish_run,
    load_run,
    maybe_advance_stage,
    save_run,
    start_run,
)
from era.web.deps import page

router = APIRouter()


@router.get("/placement")
def placement_get(request: Request, run_id: int | None = None, done: int = 0):
    cfg = load_config()
    conn = connect(cfg)
    try:
        if done and run_id:
            run = load_run(conn, run_id)
            profile = None
            if run and run.finished:
                row = conn.execute("SELECT * FROM learner_profile WHERE id=1").fetchone()
                profile = row
            return page(
                request,
                "placement_result.html",
                {"run": run, "profile": profile},
            )
        run = load_run(conn, run_id) if run_id else None
        if run is None or run.finished:
            run = start_run(conn)
        batch = []
        start = run.cursor_idx
        end = min(len(run.items), start + BATCH_SIZE)
        for i in range(start, end):
            if i not in run.answers:
                batch.append((i, run.items[i]))
        if not batch and run.cursor_idx >= len(run.items):
            if run.stage == 1:
                run = maybe_advance_stage(conn, run)
                return RedirectResponse(f"/placement?run_id={run.id}", status_code=303)
            profile = finish_run(conn, run)
            return RedirectResponse(f"/placement?run_id={run.id}&done=1", status_code=303)
        total = 80
        answered = len(run.answers)
        return page(
            request,
            "placement.html",
            {
                "run": run,
                "batch": batch,
                "answered": answered,
                "total": total,
                "start": start + 1,
                "end": end,
            },
        )
    finally:
        conn.close()


@router.post("/placement")
def placement_post(
    run_id: int = Form(...),
    answers: str = Form(""),
):
    """answers is a compact 'idx:0/1,idx:0/1' string from the form."""
    cfg = load_config()
    conn = connect(cfg)
    try:
        run = load_run(conn, run_id)
        if run is None:
            return RedirectResponse("/placement", status_code=303)
        for part in answers.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            idx_s, val_s = part.split(":", 1)
            run.answers[int(idx_s)] = val_s in {"1", "true", "yes", "on"}
        # advance cursor past answered prefix
        while run.cursor_idx < len(run.items) and run.cursor_idx in run.answers:
            run.cursor_idx += 1
        save_run(conn, run)
        if run.cursor_idx >= len(run.items):
            run = maybe_advance_stage(conn, run)
            if run.stage == 2 and run.cursor_idx >= len(run.items):
                finish_run(conn, run)
                return RedirectResponse(f"/placement?run_id={run.id}&done=1", status_code=303)
        return RedirectResponse(f"/placement?run_id={run.id}", status_code=303)
    finally:
        conn.close()
