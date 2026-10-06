from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from era.config import AppConfig, load_config
from era.db import utcnow

# Peak-hour list price for deepseek-flash (USD / million tokens), 2026-10-06.
# Used only for a running estimate shown on /debug/llm-calls.
INPUT_USD_PER_M = 0.30
OUTPUT_USD_PER_M = 1.20


class LLMRequestError(Exception):
    """Raised when the model request fails."""


@dataclass
class LLMResult:
    content: str
    reasoning_content: str | None
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    latency_ms: int
    raw: dict[str, Any]
    call_id: int | None = None
    tool_calls: list[dict[str, Any]] | None = None


def extract_error_detail(raw_response: str) -> str:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return raw_response.strip() or "未知错误"

    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message", "")).strip()
            code = str(error_payload.get("code", "")).strip()
            if message and code and code not in message:
                return f"{message} (code: {code})"
            if message:
                return message
            if code:
                return f"错误代码：{code}"

        message = str(payload.get("message", "")).strip()
        if message:
            return message

    return raw_response.strip() or "未知错误"


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * INPUT_USD_PER_M + (output_tokens / 1_000_000) * OUTPUT_USD_PER_M


def log_call(
    conn: sqlite3.Connection,
    *,
    purpose: str,
    model: str,
    prompt_version: str = "",
    thinking: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_hit_tokens: int = 0,
    latency_ms: int = 0,
    ok: bool = True,
    error: str | None = None,
    trace_id: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO llm_calls(purpose, model, prompt_version, thinking, "
        "input_tokens, output_tokens, cache_hit_tokens, latency_ms, cost_usd_est, "
        "ok, error, trace_id, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            purpose,
            model,
            prompt_version,
            1 if thinking else 0,
            input_tokens,
            output_tokens,
            cache_hit_tokens,
            latency_ms,
            estimate_cost_usd(input_tokens, output_tokens),
            1 if ok else 0,
            error,
            trace_id,
            utcnow(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _usage(payload: dict[str, Any]) -> tuple[int, int, int]:
    usage = payload.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0)
    return prompt, completion, cached


class LLMClient:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()

    def chat(
        self,
        conn: sqlite3.Connection,
        *,
        purpose: str,
        messages: list[dict[str, Any]],
        prompt_version: str = "",
        json_mode: bool = False,
        thinking: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        trace_id: str | None = None,
        temperature: float = 0.2,
        retry_empty: bool = True,
    ) -> LLMResult:
        cfg = self.config
        t0 = time.perf_counter()
        if cfg.llm.mock:
            result = self._mock_chat(
                purpose=purpose,
                messages=messages,
                json_mode=json_mode,
                thinking=thinking,
                tools=tools,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            result.latency_ms = latency
            result.call_id = log_call(
                conn,
                purpose=purpose,
                model=cfg.llm.model + ("#mock" if cfg.llm.mock else ""),
                prompt_version=prompt_version,
                thinking=thinking,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency,
                ok=True,
                trace_id=trace_id,
            )
            return result

        if not cfg.llm.api_key.strip():
            latency = int((time.perf_counter() - t0) * 1000)
            log_call(
                conn,
                purpose=purpose,
                model=cfg.llm.model,
                prompt_version=prompt_version,
                thinking=thinking,
                latency_ms=latency,
                ok=False,
                error="missing_api_key",
                trace_id=trace_id,
            )
            raise LLMRequestError("未填写 DeepSeek API Key。请打开 /setup 粘贴密钥后再试。")

        try:
            payload = self._request(
                messages=messages,
                json_mode=json_mode,
                thinking=thinking,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
            )
        except LLMRequestError as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            log_call(
                conn,
                purpose=purpose,
                model=cfg.llm.model,
                prompt_version=prompt_version,
                thinking=thinking,
                latency_ms=latency,
                ok=False,
                error=str(exc)[:500],
                trace_id=trace_id,
            )
            raise

        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        content = message.get("content") or ""
        if json_mode and retry_empty and (not isinstance(content, str) or not content.strip()):
            try:
                payload = self._request(
                    messages=messages,
                    json_mode=json_mode,
                    thinking=thinking,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=temperature,
                )
                message = ((payload.get("choices") or [{}])[0].get("message") or {})
                content = message.get("content") or ""
            except LLMRequestError:
                pass

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        content = (content or "").strip()
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str):
            reasoning = reasoning.strip() or None
        else:
            reasoning = None

        tool_calls_raw = message.get("tool_calls") or []
        tool_calls = []
        for item in tool_calls_raw:
            fn = item.get("function") or {}
            tool_calls.append(
                {
                    "id": item.get("id"),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments") or "{}",
                    "reasoning_content": reasoning,
                }
            )

        prompt_t, completion_t, cached_t = _usage(payload)
        latency = int((time.perf_counter() - t0) * 1000)
        result = LLMResult(
            content=content,
            reasoning_content=reasoning,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            cache_hit_tokens=cached_t,
            latency_ms=latency,
            raw=payload,
            tool_calls=tool_calls or None,
        )
        result.call_id = log_call(
            conn,
            purpose=purpose,
            model=cfg.llm.model,
            prompt_version=prompt_version,
            thinking=thinking,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            cache_hit_tokens=cached_t,
            latency_ms=latency,
            ok=True,
            trace_id=trace_id,
        )
        return result

    def _request(
        self,
        *,
        messages: list[dict[str, Any]],
        json_mode: bool,
        thinking: bool,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
    ) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMRequestError("未安装 openai SDK，请运行 uv sync") from exc

        client = OpenAI(
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.base_url.rstrip("/"),
            timeout=self.config.llm.timeout_seconds,
        )
        kwargs: dict[str, Any] = {
            "model": self.config.llm.model,
            "messages": messages,
        }
        extra_body: dict[str, Any] = {}
        if thinking:
            extra_body["thinking"] = {"type": "enabled"}
        else:
            extra_body["thinking"] = {"type": "disabled"}
            kwargs["temperature"] = temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if extra_body:
            kwargs["extra_body"] = extra_body
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            detail = extract_error_detail(str(exc)) if str(exc).startswith("{") else str(exc)
            raise LLMRequestError(f"模型请求失败：{detail}") from exc
        return resp.model_dump()

    def _mock_chat(
        self,
        *,
        purpose: str,
        messages: list[dict[str, Any]],
        json_mode: bool,
        thinking: bool,
        tools: list[dict[str, Any]] | None,
    ) -> LLMResult:
        from era.llm.mock import mock_response

        payload = mock_response(
            purpose=purpose,
            messages=messages,
            json_mode=json_mode,
            thinking=thinking,
            tools=tools,
        )
        return LLMResult(
            content=payload.get("content") or "",
            reasoning_content=payload.get("reasoning_content"),
            input_tokens=int(payload.get("input_tokens") or 32),
            output_tokens=int(payload.get("output_tokens") or 16),
            cache_hit_tokens=0,
            latency_ms=1,
            raw=payload,
            tool_calls=payload.get("tool_calls"),
        )


def ping(conn: sqlite3.Connection, config: AppConfig | None = None) -> LLMResult:
    client = LLMClient(config)
    return client.chat(
        conn,
        purpose="ping",
        messages=[
            {"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": 'Return {"ok": true, "model": "pong"} and nothing else.'},
        ],
        json_mode=True,
        thinking=False,
        prompt_version="ping.v1",
    )
