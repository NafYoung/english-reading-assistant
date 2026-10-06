from __future__ import annotations

import re
from dataclasses import dataclass

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Sentence:
    idx: int
    para_idx: int
    text: str
    char_start: int
    char_end: int


def split_paragraphs(text: str) -> list[tuple[int, str]]:
    """Return (para_idx, paragraph_text) keeping original offsets via search."""
    parts = re.split(r"\n\s*\n", text)
    out: list[tuple[int, str]] = []
    cursor = 0
    para_idx = 0
    for part in parts:
        if not part.strip():
            cursor += len(part)
            cursor += 2  # approximate; refined below
            continue
        pos = text.find(part, cursor)
        if pos < 0:
            pos = cursor
        out.append((para_idx, part))
        cursor = pos + len(part)
        para_idx += 1
    return out


def split_sentences(text: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    if not text.strip():
        return sentences
    para_spans: list[tuple[int, int, int]] = []
    cursor = 0
    para_idx = 0
    for chunk in re.split(r"(\n\s*\n)", text):
        if re.fullmatch(r"\n\s*\n", chunk or ""):
            cursor += len(chunk)
            para_idx += 1
            continue
        if chunk.strip():
            para_spans.append((para_idx, cursor, cursor + len(chunk)))
        cursor += len(chunk)

    idx = 0
    for p_i, p_start, p_end in para_spans:
        para = text[p_start:p_end]
        pieces = [p for p in SENT_SPLIT.split(para) if p.strip()]
        search_from = 0
        if not pieces:
            continue
        for piece in pieces:
            rel = para.find(piece, search_from)
            if rel < 0:
                rel = search_from
            start = p_start + rel
            end = start + len(piece)
            sentences.append(
                Sentence(idx=idx, para_idx=p_i, text=piece.strip(), char_start=start, char_end=end)
            )
            search_from = rel + len(piece)
            idx += 1
    if not sentences:
        sentences.append(
            Sentence(idx=0, para_idx=0, text=text.strip(), char_start=0, char_end=len(text))
        )
    return sentences
