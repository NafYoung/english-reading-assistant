from __future__ import annotations

import json
import sqlite3
import uuid

from era.coach import tools as T
from era.config import AppConfig
from era.db import utcnow
from era.llm.client import LLMClient, LLMRequestError

TOOL_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_learner_profile",
            "description": "Learner vocab estimate and recent session stats.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_corpus_overview",
            "description": "Per-document coverage and suggested order.",
            "parameters": {
                "type": "object",
                "properties": {"corpus_id": {"type": "integer"}},
                "required": ["corpus_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_doc_gaps",
            "description": "Unknown lemmas in a document, ranked by corpus frequency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "integer"},
                    "top_k": {"type": "integer"},
                },
                "required": ["doc_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "ECDICT + approved glossary candidates for a lemma.",
            "parameters": {
                "type": "object",
                "properties": {"lemma": {"type": "string"}},
                "required": ["lemma"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "Submit a reading plan for validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order": {"type": "array", "items": {"type": "integer"}},
                    "preteach": {"type": "object"},
                    "daily_quota_words": {"type": "integer"},
                    "rationale_zh": {"type": "string"},
                },
                "required": ["order", "preteach", "daily_quota_words", "rationale_zh"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the planning loop.",
            "parameters": {
                "type": "object",
                "properties": {"summary_zh": {"type": "string"}},
                "required": ["summary_zh"],
            },
        },
    },
]


def _trace(conn: sqlite3.Connection, trace_id: str, step: int, kind: str, content) -> None:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    conn.execute(
        "INSERT INTO agent_traces(trace_id, step, kind, content, ts) VALUES (?,?,?,?,?)",
        (trace_id, step, kind, content, utcnow()),
    )
    conn.commit()


def _run_tool(conn: sqlite3.Connection, corpus_id: int, name: str, args: dict) -> tuple[str, dict | str]:
    if name == "get_learner_profile":
        return "ok", T.get_learner_profile(conn)
    if name == "get_corpus_overview":
        return "ok", T.get_corpus_overview(conn, int(args.get("corpus_id", corpus_id)))
    if name == "get_doc_gaps":
        return "ok", T.get_doc_gaps(conn, int(args["doc_id"]), int(args.get("top_k") or 20))
    if name == "lookup":
        return "ok", T.lookup_tool(conn, str(args.get("lemma") or ""))
    if name == "propose_plan":
        ok, err, payload = T.validate_plan(conn, corpus_id, args)
        if not ok:
            return "validation_error", {"error": err}
        return "ok", payload
    if name == "finish":
        return "ok", {"summary_zh": args.get("summary_zh") or ""}
    return "error", {"error": f"unknown tool {name}"}


def run_planner(conn: sqlite3.Connection, cfg: AppConfig, corpus_id: int) -> tuple[dict, str, bool]:
    """Return (plan, trace_id, used_fallback)."""
    trace_id = uuid.uuid4().hex[:12]
    client = LLMClient(cfg)
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You plan reading order for one learner. Use tools. "
                "propose_plan must pass code validation. Chinese rationale."
            ),
        },
        {"role": "user", "content": f"Plan corpus_id={corpus_id}. Call get_corpus_overview first."},
    ]
    accepted: dict | None = None
    max_steps = 8
    try:
        for step in range(max_steps):
            result = client.chat(
                conn,
                purpose="planner",
                messages=messages,
                tools=TOOL_SPEC,
                thinking=True,
                json_mode=False,
                prompt_version="planner.v1",
                trace_id=trace_id,
            )
            if result.reasoning_content:
                _trace(conn, trace_id, step, "thought", result.reasoning_content)
            assistant_msg: dict = {"role": "assistant", "content": result.content or ""}
            if result.reasoning_content:
                assistant_msg["reasoning_content"] = result.reasoning_content
            if result.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.get("id") or f"call_{step}_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                            if isinstance(tc["arguments"], str)
                            else json.dumps(tc["arguments"]),
                        },
                    }
                    for i, tc in enumerate(result.tool_calls)
                ]
            messages.append(assistant_msg)
            if not result.tool_calls:
                break
            finished = False
            for tc in result.tool_calls:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                _trace(conn, trace_id, step, "tool_call", {"name": name, "arguments": args})
                status, payload = _run_tool(conn, corpus_id, name, args)
                kind = "tool_result" if status == "ok" else "validation_error"
                _trace(conn, trace_id, step, kind, payload)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id") or "",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                )
                if name == "propose_plan" and status == "ok" and isinstance(payload, dict):
                    accepted = payload
                if name == "finish":
                    finished = True
            if finished:
                break
        if accepted is None:
            raise LLMRequestError("planner produced no valid plan")
        used_fallback = False
        plan = accepted
    except (LLMRequestError, Exception):
        plan = T.fallback_plan(conn, corpus_id)
        used_fallback = True
        _trace(conn, trace_id, 99, "final", {"fallback": True, "plan": plan})

    conn.execute(
        "INSERT INTO plans(corpus_id, created_at, plan_json, trace_id) VALUES (?,?,?,?)",
        (corpus_id, utcnow(), json.dumps(plan, ensure_ascii=False), trace_id),
    )
    conn.commit()
    return plan, trace_id, used_fallback
