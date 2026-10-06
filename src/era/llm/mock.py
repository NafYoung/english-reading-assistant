"""Deterministic mock used when ERA_MOCK_LLM=1 or config.llm.mock is true."""

from __future__ import annotations

import json
import re
from typing import Any


def _last_user(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content") or ""
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            return str(content)
    return ""


def mock_response(
    *,
    purpose: str,
    messages: list[dict[str, Any]],
    json_mode: bool,
    thinking: bool,
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    user = _last_user(messages)
    if purpose == "ping":
        return {"content": json.dumps({"ok": True, "model": "pong"}), "input_tokens": 8, "output_tokens": 6}

    if purpose == "sense_pick":
        return _sense_pick(user)
    if purpose == "structure":
        return _structure(user)
    if purpose == "translate":
        return {"content": json.dumps({"zh": "（模拟翻译）系统在没有 API Key 时用这条占位译文。"}, ensure_ascii=False)}
    if purpose == "quiz":
        return _quiz()
    if purpose == "quiz_verify":
        return json.dumps({"choice": "A"}) if not user.startswith("{") else _quiz_verify(user)
    if purpose == "glossary_draft":
        return _glossary(user)
    if purpose == "term_classify":
        return _term_classify(user)
    if purpose == "planner" and tools:
        return _planner(user, messages, tools)

    if json_mode:
        return {"content": json.dumps({"ok": True, "note": "mock"})}
    return {"content": "mock"}


def _sense_pick(user: str) -> dict[str, Any]:
    no_fit_hint = "transformer" in user.lower() or "NO_FIT_TRIGGER" in user
    if no_fit_hint and "G1" not in user:
        return {
            "content": json.dumps(
                {
                    "en_sense": None,
                    "zh_sense": None,
                    "glossary": None,
                    "fit": "no_fit",
                    "note_zh": "词典义项均不适合本句中的用法。",
                },
                ensure_ascii=False,
            )
        }
    en = "E1" if "E1" in user else None
    zh = "Z1" if "Z1" in user else None
    gl = "G1" if "G1" in user else None
    return {
        "content": json.dumps(
            {
                "en_sense": en,
                "zh_sense": zh,
                "glossary": gl,
                "fit": "good" if (en or zh or gl) else "no_fit",
                "note_zh": "模拟选择：取候选列表中的第一项。",
            },
            ensure_ascii=False,
        )
    }


def _structure(user: str) -> dict[str, Any]:
    m = re.search(r"SENTENCE:\s*(.+)", user, re.S)
    sentence = (m.group(1).strip().splitlines()[0] if m else user.strip().splitlines()[-1]).strip()
    words = sentence.split()
    mid = max(1, len(words) // 2)
    c1 = " ".join(words[:mid]) or sentence
    c2 = " ".join(words[mid:])
    chunks = [c1] + ([c2] if c2 else [])
    return {
        "content": json.dumps(
            {
                "main_clause": {
                    "subject": words[0] if words else "",
                    "verb": words[1] if len(words) > 1 else "",
                    "object": " ".join(words[2:]) if len(words) > 2 else "",
                },
                "chunks": chunks,
                "note_zh": "模拟结构：按词数对半切开。",
            },
            ensure_ascii=False,
        )
    }


def _quiz() -> dict[str, Any]:
    return {
        "content": json.dumps(
            {
                "items": [
                    {
                        "question": "What is the main claim of the passage?",
                        "options": {
                            "A": "Agents should start simple.",
                            "B": "Agents must always use tools.",
                            "C": "Translation is required.",
                            "D": "Coverage must be 100%.",
                        },
                        "answer": "A",
                        "evidence_sentence_ids": [1],
                    },
                    {
                        "question": "Which technique is mentioned?",
                        "options": {
                            "A": "OCR",
                            "B": "Tool use",
                            "C": "TTS",
                            "D": "EPUB split",
                        },
                        "answer": "B",
                        "evidence_sentence_ids": [2],
                    },
                    {
                        "question": "What should happen after reading?",
                        "options": {
                            "A": "Ignore the text",
                            "B": "Only translate",
                            "C": "Take a short quiz",
                            "D": "Delete the corpus",
                        },
                        "answer": "C",
                        "evidence_sentence_ids": [3],
                    },
                ]
            }
        )
    }


def _quiz_verify(user: str) -> dict[str, Any]:
    return {"content": json.dumps({"choice": "A"})}


def _glossary(user: str) -> dict[str, Any]:
    m = re.search(r"TERM:\s*(\S+)", user)
    term = m.group(1) if m else "term"
    return {
        "content": json.dumps(
            {
                "en_def": f"(draft) A domain-specific use of '{term}' in AI/agent systems.",
                "zh_def": f"（草稿）AI/Agent 语境中「{term}」的专门用法。",
                "pos": "n",
            },
            ensure_ascii=False,
        )
    }


def _term_classify(user: str) -> dict[str, Any]:
    m = re.search(r"CANDIDATES:\s*(\[.*\])", user, re.S)
    items = []
    if m:
        try:
            items = json.loads(m.group(1))
        except json.JSONDecodeError:
            items = []
    labels = {}
    for w in items:
        wl = str(w).lower()
        if wl in {"wkh", "dqg", "fw", "rx"}:
            labels[wl] = "noise"
        elif any(k in wl for k in ("agent", "workflow", "embed", "transform", "hallucin", "orchestr")):
            labels[wl] = "term"
        else:
            labels[wl] = "general"
    return {"content": json.dumps({"labels": labels})}


def _planner(
    user: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    names = [(t.get("function") or {}).get("name") for t in tools]
    n_tool_results = sum(1 for m in messages if m.get("role") == "tool")
    if n_tool_results == 0 and "get_corpus_overview" in names:
        return {
            "content": "",
            "reasoning_content": "先看语料概览。",
            "tool_calls": [
                {
                    "id": "call_overview",
                    "name": "get_corpus_overview",
                    "arguments": "{}",
                }
            ],
        }
    if n_tool_results < 2 and "propose_plan" in names:
        return {
            "content": "",
            "reasoning_content": "提出一个阅读计划。",
            "tool_calls": [
                {
                    "id": "call_plan",
                    "name": "propose_plan",
                    "arguments": json.dumps(
                        {
                            "order": [],
                            "preteach": {},
                            "daily_quota_words": 800,
                            "rationale_zh": "模拟规划：按难度从易到难。",
                        }
                    ),
                }
            ],
        }
    return {
        "content": "",
        "reasoning_content": "结束。",
        "tool_calls": [
            {
                "id": "call_finish",
                "name": "finish",
                "arguments": json.dumps({"summary_zh": "模拟规划完成。"}),
            }
        ],
    }
