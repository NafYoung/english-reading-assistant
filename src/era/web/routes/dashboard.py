from __future__ import annotations

from fastapi import APIRouter, Request

from era.config import load_config
from era.db import connect
from era.learner.model import load_profile
from era.web.deps import page

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request):
    cfg = load_config()
    conn = connect(cfg)
    try:
        profile = load_profile(conn)
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE ended_at IS NOT NULL ORDER BY id DESC LIMIT 20"
        ).fetchall()
        rows = []
        for s in sessions:
            wr = s["words_read"] or 0
            l3k = (1000.0 * (s["l3_count"] or 0) / wr) if wr else None
            l1k = (1000.0 * (s["l1_count"] or 0) / wr) if wr else None
            cost = conn.execute(
                "SELECT SUM(cost_usd_est) AS c FROM llm_calls WHERE ts >= ? AND ts <= ?",
                (s["started_at"], s["ended_at"] or s["started_at"]),
            ).fetchone()
            rows.append(
                {
                    "id": s["id"],
                    "started": s["started_at"],
                    "l1": s["l1_count"],
                    "l2": s["l2_count"],
                    "l3": s["l3_count"],
                    "l1k": l1k,
                    "l3k": l3k,
                    "quiz": s["quiz_score"],
                    "cost": cost["c"] if cost else 0,
                }
            )
        totals = conn.execute(
            "SELECT COUNT(*) AS n, SUM(cost_usd_est) AS cost FROM llm_calls WHERE ok=1"
        ).fetchone()
        l3_vals = [r["l3k"] for r in rows if r["l3k"] is not None]
        trend = None
        if len(l3_vals) >= 2:
            older = l3_vals[-min(5, len(l3_vals)) :]
            newer = l3_vals[: min(5, len(l3_vals))]
            trend = {
                "older": sum(older) / len(older),
                "newer": sum(newer) / len(newer),
            }
        return page(
            request,
            "dashboard.html",
            {"profile": profile, "rows": rows, "totals": totals, "trend": trend},
        )
    finally:
        conn.close()
