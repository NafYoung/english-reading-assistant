from __future__ import annotations

import re

MAX_CHUNK_CHARACTERS = 2200


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
            additional_length = (
                len(paragraph_chunk) if not current_parts else len(paragraph_chunk) + 2
            )
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
