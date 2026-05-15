from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request

from english_reading_assistant.config import load_config


class LLMRequestError(Exception):
    """Raised when the model request fails."""


MIN_RETRY_TIMEOUT_SECONDS = 90.0
MAX_CHUNK_CHARACTERS = 2200


def build_api_endpoint(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/chat/completions"):
        return normalized_base_url
    return f"{normalized_base_url}/chat/completions"


def build_user_prompt(
    source_text: str,
    part_index: int | None = None,
    total_parts: int | None = None,
) -> str:
    instructions = (
        "请针对以下英文内容，使用简体中文提供阅读辅助。\n"
        "请按照下列格式输出：\n"
        "1. 中文意思：用自然中文翻译全文。\n"
        "2. 重点单词与短语：列出 3 到 8 个关键单词或短语，标注词性并给出中文解释。\n"
        "3. 句型与语法解析：说明重要句型、从句、时态、短语或修辞用法。\n"
        "如果输入内容只有单词或短语，请改为重点解释词性、常见用法与在原句中的意思。\n\n"
    )

    if part_index is not None and total_parts is not None:
        instructions += (
            f"这是同一篇长文的第 {part_index} / {total_parts} 部分。\n"
            "请只解析当前这一部分，不要补写未提供的上下文。\n\n"
        )

    return instructions + "英文内容：\n" + source_text.strip()


def build_overview_prompt(part_results: list[str]) -> str:
    overview_parts = []
    for index, result in enumerate(part_results, start=1):
        overview_parts.append(f"第 {index} 部分解析：\n{result}")

    return (
        "以下是同一篇英文长文的分段解析结果，请整合出一版整篇总览。\n"
        "请使用简体中文，只基于提供的分段解析结果总结，不要补写未提供的事实。\n"
        "请按照下列格式输出：\n"
        "1. 整篇主旨：概括全文的核心内容、脉络和作者重点。\n"
        "2. 重点单词与短语：整合全文最关键的 5 到 10 个词或短语，给出简洁中文解释。\n"
        "3. 句型与语法重点：整合全文最值得注意的句型、语法或表达方式。\n\n"
        "分段解析结果：\n"
        + "\n\n".join(overview_parts)
    )


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


def parse_response_content(payload: Dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMRequestError("API 返回格式错误：缺少可解析内容") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMRequestError("API 未返回有效内容")

    return content.strip()


def format_timeout_seconds(seconds: float) -> str:
    return str(int(seconds)) if float(seconds).is_integer() else str(seconds)


def get_retry_timeout_seconds(timeout_seconds: float) -> float:
    return max(timeout_seconds * 2, timeout_seconds + 30, MIN_RETRY_TIMEOUT_SECONDS)


def is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, socket.timeout):
        return True
    if isinstance(exc, error.URLError):
        return isinstance(exc.reason, socket.timeout)
    return False


def raise_http_request_error(exc: error.HTTPError) -> None:
    error_text = exc.read().decode("utf-8", errors="ignore")
    detail = extract_error_detail(error_text)
    raise LLMRequestError(f"请求失败（HTTP {exc.code}）：{detail}") from exc


def raise_network_request_error(exc: Exception, timeout_seconds: float) -> None:
    if is_timeout_error(exc):
        timeout_text = format_timeout_seconds(timeout_seconds)
        raise LLMRequestError(
            "网络请求失败：连接超时"
            f"（当前超时设置：{timeout_text} 秒；已自动重试一次，"
            "如仍频繁出现，可在 config.json 中调大 timeout_seconds）"
        ) from exc

    if isinstance(exc, error.URLError):
        detail = str(exc.reason)
    else:
        detail = str(exc)
    raise LLMRequestError(f"网络请求失败：{detail}") from exc


def execute_request(req: request.Request, timeout_seconds: float) -> str:
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8")


def split_oversized_text(text: str, max_chars: int) -> list[str]:
    stripped_text = text.strip()
    if not stripped_text:
        return []
    if len(stripped_text) <= max_chars:
        return [stripped_text]

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", stripped_text)
        if sentence.strip()
    ]
    if len(sentences) <= 1:
        return [
            stripped_text[index : index + max_chars].strip()
            for index in range(0, len(stripped_text), max_chars)
            if stripped_text[index : index + max_chars].strip()
        ]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current_parts:
                chunks.append(" ".join(current_parts))
                current_parts = []
                current_length = 0
            chunks.extend(split_oversized_text(sentence, max_chars))
            continue

        additional_length = len(sentence) if not current_parts else len(sentence) + 1
        if current_parts and current_length + additional_length > max_chars:
            chunks.append(" ".join(current_parts))
            current_parts = [sentence]
            current_length = len(sentence)
            continue

        current_parts.append(sentence)
        current_length += additional_length

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def split_text_into_chunks(source_text: str, max_chars: int = MAX_CHUNK_CHARACTERS) -> list[str]:
    text = source_text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if len(paragraphs) <= 1:
        return split_oversized_text(text, max_chars)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        paragraph_chunks = split_oversized_text(paragraph, max_chars)
        for paragraph_chunk in paragraph_chunks:
            additional_length = len(paragraph_chunk) if not current_parts else len(paragraph_chunk) + 2
            if current_parts and current_length + additional_length > max_chars:
                chunks.append("\n\n".join(current_parts))
                current_parts = [paragraph_chunk]
                current_length = len(paragraph_chunk)
                continue

            current_parts.append(paragraph_chunk)
            current_length += additional_length

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def build_request(
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    source_text: str = "",
    part_index: int | None = None,
    total_parts: int | None = None,
    user_prompt: str | None = None,
) -> request.Request:
    user_content = user_prompt or build_user_prompt(source_text, part_index, total_parts)
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    return request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def perform_model_request(req: request.Request, timeout_seconds: float) -> str:
    retry_timeout_seconds = get_retry_timeout_seconds(timeout_seconds)
    try:
        response_text = execute_request(req, timeout_seconds)
    except error.HTTPError as exc:
        raise_http_request_error(exc)
    except (error.URLError, socket.timeout) as exc:
        if not is_timeout_error(exc):
            raise_network_request_error(exc, timeout_seconds)

        try:
            response_text = execute_request(req, retry_timeout_seconds)
        except error.HTTPError as retry_exc:
            raise_http_request_error(retry_exc)
        except (error.URLError, socket.timeout) as retry_exc:
            raise_network_request_error(retry_exc, timeout_seconds)

    try:
        response_payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise LLMRequestError("API 返回格式错误：无法解析 JSON") from exc

    return parse_response_content(response_payload)


def format_chunked_result(
    results: list[str],
    overview: str | None = None,
    overview_error: str | None = None,
) -> str:
    if len(results) == 1:
        return results[0]

    sections = [f"这篇文章较长，已自动分成 {len(results)} 部分解析。"]
    if overview:
        sections.append(f"【整篇总览】\n{overview}")
    elif overview_error:
        sections.append(f"【整篇总览】\n生成失败：{overview_error}\n已保留分段解析结果。")

    for index, result in enumerate(results, start=1):
        sections.append(f"【第 {index} 部分】\n{result}")
    return "\n\n".join(sections)


def analyze_text(source_text: str, config_path: Optional[Path] = None) -> str:
    config = load_config(config_path)
    endpoint = build_api_endpoint(config.base_url)
    chunks = split_text_into_chunks(source_text)
    results: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        req = build_request(
            endpoint=endpoint,
            api_key=config.api_key,
            model=config.model,
            system_prompt=config.system_prompt,
            source_text=chunk,
            part_index=index if len(chunks) > 1 else None,
            total_parts=len(chunks) if len(chunks) > 1 else None,
        )
        results.append(perform_model_request(req, config.timeout_seconds))

    overview: str | None = None
    overview_error: str | None = None
    if len(results) > 1:
        overview_req = build_request(
            endpoint=endpoint,
            api_key=config.api_key,
            model=config.model,
            system_prompt=config.system_prompt,
            user_prompt=build_overview_prompt(results),
        )
        try:
            overview = perform_model_request(overview_req, config.timeout_seconds)
        except LLMRequestError as exc:
            overview_error = str(exc)

    return format_chunked_result(results, overview, overview_error)
