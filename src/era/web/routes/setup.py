from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from era.config import load_config, save_config
from era.db import connect
from era.llm.client import LLMRequestError, ping
from era.web.deps import page

router = APIRouter()


@router.get("/setup")
def setup_page(request: Request, saved: int = 0, ping_ok: str | None = None, ping_err: str | None = None):
    cfg = load_config()
    return page(
        request,
        "setup.html",
        {
            "cfg": cfg,
            "saved": bool(saved),
            "ping_ok": ping_ok,
            "ping_err": ping_err,
        },
    )


@router.post("/setup")
def setup_save(
    api_key: str = Form(""),
    base_url: str = Form("https://api.deepseek.com"),
    model: str = Form("deepseek-flash"),
    eudic_api_key: str = Form(""),
    maimemo_token: str = Form(""),
    vault_path: str = Form(""),
    note_path: str = Form("Inbox/Reading Coach.md"),
    strict_hints: str = Form(""),
):
    cfg = load_config()
    cfg.llm.api_key = api_key.strip()
    cfg.llm.base_url = base_url.strip() or cfg.llm.base_url
    cfg.llm.model = model.strip() or cfg.llm.model
    cfg.eudic_api_key = eudic_api_key.strip()
    cfg.maimemo_token = maimemo_token.strip()
    cfg.obsidian.vault_path = vault_path.strip()
    cfg.obsidian.note_path = note_path.strip() or "Inbox/Reading Coach.md"
    cfg.strict_hints = strict_hints == "on"
    save_config(cfg)
    return RedirectResponse("/setup?saved=1", status_code=303)


@router.post("/setup/ping")
def setup_ping():
    cfg = load_config()
    conn = connect(cfg)
    try:
        ping(conn, cfg)
        return RedirectResponse("/setup?ping_ok=1", status_code=303)
    except LLMRequestError as exc:
        from urllib.parse import quote

        return RedirectResponse(f"/setup?ping_err={quote(str(exc)[:180])}", status_code=303)
    finally:
        conn.close()
