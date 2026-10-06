from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")
CONTRACTIONS = ("n't", "'s", "'re", "'ll", "'ve", "'d", "'m")
# ≤2 letter tokens are dropped from the unknown list, except these (go to glossary path).
SHORT_ALLOW = {"ai", "ml", "ir", "ui", "id", "ok", "us", "uk", "eu"}
HYPHEN_RE = re.compile(r"-")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def strip_contraction(word: str) -> str:
    lower = word.lower()
    for suffix in CONTRACTIONS:
        if lower.endswith(suffix) and len(lower) > len(suffix):
            return word[: -len(suffix)] or word
    return word


@dataclass(frozen=True)
class Token:
    surface: str
    start: int
    end: int
    sentence_index: int
    index_in_sentence: int

    @property
    def lower(self) -> str:
        return self.surface.lower()

    @property
    def stripped(self) -> str:
        return strip_contraction(self.surface)

    @property
    def hyphen_parts(self) -> list[str]:
        if "-" not in self.surface:
            return []
        return [p for p in self.surface.split("-") if p]


def tokenize_sentence(sentence: str, *, sentence_index: int = 0, offset: int = 0) -> list[Token]:
    tokens: list[Token] = []
    for i, match in enumerate(TOKEN_RE.finditer(sentence)):
        tokens.append(
            Token(
                surface=match.group(),
                start=offset + match.start(),
                end=offset + match.end(),
                sentence_index=sentence_index,
                index_in_sentence=i,
            )
        )
    return tokens


def tokenize(text: str) -> list[Token]:
    return tokenize_sentence(text, sentence_index=0, offset=0)


def is_probable_proper(token: Token, lower_seen: set[str]) -> bool:
    surface = token.surface
    if not surface or not surface[0].isupper():
        return False
    if token.index_in_sentence == 0:
        return False
    if surface.isupper() and len(surface) <= 5:
        return False  # acronym, keep as a candidate term / dict lookup
    return surface.lower() not in lower_seen
