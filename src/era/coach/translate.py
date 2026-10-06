from __future__ import annotations

import sqlite3
from pathlib import Path

from era.llm.client import LLMClient, LLMRequestError
from era.llm.schemas import TranslateOut

PROMPT_VERSION = "translate.v1"
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "translate.v1.md").read_text(
    encoding="utf-8"
)


def translate_sentence(
    conn: sqlite3.Connection,
    cfg,
    sentence: str,
    prev_s: str = "",
    next_s: str = "",
) -> dict:
    client = LLMClient(cfg)
    try:
        result = client.chat(
            conn,
            purpose="translate",
            messages=[
                {"role": "system", "content": PROMPT},
                {
                    "role": "user",
                    "content": f"PREV: {prev_s}\nTARGET: {sentence}\nNEXT: {next_s}",
                },
            ],
            json_mode=True,
            prompt_version=PROMPT_VERSION,
        )
        parsed = TranslateOut.model_validate_json(result.content)
        return {"zh": parsed.zh, "ok": True}
    except (LLMRequestError, Exception) as exc:
        return {"zh": "", "ok": False, "error": str(exc)}
