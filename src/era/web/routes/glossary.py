from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from era.config import load_config
from era.db import connect
from era.dictionary.glossary import list_terms, set_status
from era.web.deps import page

router = APIRouter()


@router.get("/glossary")
def glossary_page(request: Request, status: str = "draft"):
    cfg = load_config()
    conn = connect(cfg)
    try:
        rows = list_terms(conn, status if status != "all" else None)
        return page(request, "glossary.html", {"rows": rows, "status": status})
    finally:
        conn.close()


@router.post("/glossary/{term_id}")
def glossary_update(
    term_id: int,
    action: str = Form(...),
    en_def: str = Form(""),
    zh_def: str = Form(""),
):
    cfg = load_config()
    conn = connect(cfg)
    try:
        if action == "approve":
            set_status(conn, term_id, "approved", en_def=en_def, zh_def=zh_def)
        elif action == "reject":
            set_status(conn, term_id, "rejected")
        elif action == "edit":
            set_status(conn, term_id, "draft", en_def=en_def, zh_def=zh_def)
        return RedirectResponse("/glossary", status_code=303)
    finally:
        conn.close()
