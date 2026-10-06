from __future__ import annotations

from fastapi import APIRouter, Request

from era.config import load_config
from era.db import connect
from era.web.deps import page

router = APIRouter()


@router.get("/debug/llm-calls")
def llm_calls(request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        rows = conn.execute(
            "SELECT id, purpose, model, prompt_version, thinking, input_tokens, "
            "output_tokens, cache_hit_tokens, latency_ms, cost_usd_est, ok, error, ts "
            "FROM llm_calls ORDER BY id DESC LIMIT 200"
        ).fetchall()
    finally:
        conn.close()
    return page(request, "debug_llm.html", {"rows": rows})
