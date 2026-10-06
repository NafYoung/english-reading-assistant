from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from era.nlp.lemmatize import DictHit, pick_lemma
from era.nlp.sentences import Sentence, split_sentences
from era.nlp.tokenize import (
    SHORT_ALLOW,
    Token,
    is_probable_proper,
    normalize_text,
    tokenize_sentence,
)


@dataclass
class AnalyzedToken:
    token: Token
    lemma: str | None
    is_proper: bool
    is_short: bool
    hyphen_known: bool | None = None  # filled later with learner model


@dataclass
class DocAnalysis:
    text: str
    sentences: list[Sentence]
    tokens: list[AnalyzedToken]
    lower_seen: set[str]


def dict_lookup_fn(conn: sqlite3.Connection):
    cache: dict[str, DictHit | None] = {}

    def lookup(word: str) -> DictHit | None:
        key = word.lower()
        if key in cache:
            return cache[key]
        if not _has_ecdict(conn):
            cache[key] = None
            return None
        row = conn.execute(
            "SELECT word, frq, bnc FROM ecdict.dict WHERE word = ?",
            (key,),
        ).fetchone()
        if not row:
            cache[key] = None
            return None
        hit = DictHit(word=row["word"], frq=int(row["frq"] or 0), bnc=int(row["bnc"] or 0))
        cache[key] = hit
        return hit

    return lookup


def _has_ecdict(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM pragma_database_list WHERE name = 'ecdict'").fetchone()
    return row is not None


def analyze_text(text: str, lookup) -> DocAnalysis:
    text = normalize_text(text)
    sentences = split_sentences(text)
    all_tokens: list[Token] = []
    for sent in sentences:
        all_tokens.extend(
            tokenize_sentence(sent.text, sentence_index=sent.idx, offset=sent.char_start)
        )
    lower_seen = {t.surface.lower() for t in all_tokens if t.surface[:1].islower()}
    analyzed: list[AnalyzedToken] = []
    for tok in all_tokens:
        stripped = tok.stripped.lower()
        is_short = len(stripped) <= 2 and stripped not in SHORT_ALLOW
        proper = is_probable_proper(tok, lower_seen)
        lemma = None if proper else pick_lemma(tok.stripped, lookup)
        if lemma is None and not proper and not is_short:
            lemma = None
        analyzed.append(
            AnalyzedToken(
                token=tok,
                lemma=lemma,
                is_proper=proper,
                is_short=is_short,
            )
        )
    return DocAnalysis(text=text, sentences=sentences, tokens=analyzed, lower_seen=lower_seen)


def coverage_tokens(analysis: DocAnalysis) -> list[AnalyzedToken]:
    """Tokens that count in the coverage denominator (not proper, not discarded shorts)."""
    out = []
    for item in analysis.tokens:
        if item.is_proper:
            continue
        if item.is_short:
            continue
        out.append(item)
    return out
