from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from era.llm.client import LLMClient, LLMRequestError
from era.llm.schemas import StructureOut

PROMPT_VERSION = "structure.v1"
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "structure.v1.md").read_text(
    encoding="utf-8"
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def chunks_ok(sentence: str, chunks: list[str]) -> bool:
    if not chunks:
        return False
    pos = 0
    for chunk in chunks:
        idx = sentence.find(chunk, pos)
        if idx < 0:
            return False
        pos = idx + len(chunk)
    return _norm("".join(chunks)) == _norm(sentence)


def explain_structure(conn: sqlite3.Connection, cfg, sentence: str) -> dict:
    client = LLMClient(cfg)
    parsed: StructureOut | None = None
    for _ in range(2):
        try:
            result = client.chat(
                conn,
                purpose="structure",
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": f"SENTENCE: {sentence}"},
                ],
                json_mode=True,
                prompt_version=PROMPT_VERSION,
            )
            parsed = StructureOut.model_validate_json(result.content)
            if chunks_ok(sentence, parsed.chunks):
                break
            parsed = parsed.model_copy(update={"chunks": []})
        except (LLMRequestError, Exception):
            parsed = None
            break
    if parsed is None:
        return {"main_clause": {}, "chunks": [], "note_zh": "结构解析失败。", "ok": False}
    ok = chunks_ok(sentence, parsed.chunks)
    return {
        "main_clause": parsed.main_clause,
        "chunks": parsed.chunks if ok else [],
        "note_zh": parsed.note_zh,
        "ok": ok or bool(parsed.main_clause),
    }
