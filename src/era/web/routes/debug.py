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


@router.get("/debug/traces")
def traces_index(request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        rows = conn.execute(
            "SELECT trace_id, MAX(ts) AS ts, COUNT(*) AS n FROM agent_traces "
            "GROUP BY trace_id ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        return page(request, "traces.html", {"rows": rows, "steps": None, "trace_id": None})
    finally:
        conn.close()


@router.get("/debug/traces/{trace_id}")
def traces_detail(request: Request, trace_id: str):
    cfg = load_config()
    conn = connect(cfg)
    try:
        steps = conn.execute(
            "SELECT * FROM agent_traces WHERE trace_id=? ORDER BY step, rowid",
            (trace_id,),
        ).fetchall()
        return page(request, "traces.html", {"rows": [], "steps": steps, "trace_id": trace_id})
    finally:
        conn.close()
