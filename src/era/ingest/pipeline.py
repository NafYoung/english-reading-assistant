from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from era.db import utcnow
from era.ingest.markdown import read_text_file
from era.ingest.pdf import IngestError, extract_pdf
from era.ingest.url import fetch_url
from era.learner.model import load_profile, p_known
from era.nlp.analyze import analyze_text, coverage_tokens, dict_lookup_fn
from era.nlp.lemmatize import pick_lemma

TERM_RANK = 20000


def ingest_document(
    conn: sqlite3.Connection,
    corpus_id: int,
    *,
    source_type: str,
    source_ref: str,
    title: str | None = None,
    text: str | None = None,
    pdf_path: Path | None = None,
) -> int:
    lookup = dict_lookup_fn(conn)
    report: dict = {}
    if source_type == "url":
        title_f, text = fetch_url(source_ref)
        title = title or title_f
    elif source_type == "pdf":
        if pdf_path is None:
            raise IngestError("缺少 PDF 文件")
        text, report = extract_pdf(pdf_path, lookup)
        title = title or Path(source_ref).name
    elif source_type in {"md", "text"}:
        if text is None and source_ref:
            p = Path(source_ref)
            if p.exists():
                title_f, text = read_text_file(p)
                title = title or title_f
        title = title or source_ref or "untitled"
        text = text or ""
    else:
        raise IngestError(f"未知来源 {source_type}")

    text = text or ""
    analysis = analyze_text(text, lookup)
    profile = load_profile(conn)
    cov_toks = coverage_tokens(analysis)
    lemma_counts: Counter[str] = Counter()
    lemma_first: dict[str, int] = {}
    lemma_kind: dict[str, str] = {}
    oov: Counter[str] = Counter()
    hyphen_terms: Counter[str] = Counter()

    skipped_hyphen = 0
    for item in analysis.tokens:
        if item.is_proper or item.is_short:
            continue
        tok = item.token
        if tok.hyphen_parts and item.lemma is None:
            parts_known = True
            for part in tok.hyphen_parts:
                pl = pick_lemma(part, lookup) or part.lower()
                if p_known(conn, pl, profile) < 0.5:
                    parts_known = False
                    break
            if parts_known:
                skipped_hyphen += 1
                continue
            hyphen_terms[tok.lower] += 1
            continue
        if item.lemma is None:
            oov[tok.lower] += 1
            continue
        lemma_counts[item.lemma] += 1
        lemma_first.setdefault(item.lemma, item.token.sentence_index)

    for lemma, n in lemma_counts.items():
        rank_row = conn.execute(
            "SELECT frq, bnc FROM ecdict.dict WHERE word=?", (lemma,)
        ).fetchone() if _has_dict(conn) else None
        rank = None
        if rank_row:
            vals = [int(v) for v in (rank_row["frq"], rank_row["bnc"]) if v and int(v) > 0]
            rank = min(vals) if vals else None
        if rank is None or rank > TERM_RANK:
            lemma_kind[lemma] = "term_candidate"
        else:
            lemma_kind[lemma] = "dict"

    oov_terms = {w: n for w, n in oov.items() if n >= 2}
    for w, n in oov_terms.items():
        lemma_counts[w] += n
        lemma_kind[w] = "term_candidate"
    for w, n in hyphen_terms.items():
        if n >= 1:
            lemma_counts[w] += n
            lemma_kind[w] = "term_candidate"

    n_tokens = max(len(cov_toks) - skipped_hyphen, 0)
    cur = conn.execute(
        "INSERT INTO documents(corpus_id, source_type, source_ref, title, text, n_tokens, ingest_report, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            corpus_id,
            source_type,
            source_ref,
            title,
            text,
            n_tokens,
            json.dumps(
                {
                    **report,
                    "n_tokens": n_tokens,
                    "n_sentences": len(analysis.sentences),
                    "oov_types": sorted(oov_terms, key=lambda w: -oov_terms[w])[:40],
                    "proper_sample": sorted(
                        {t.token.surface for t in analysis.tokens if t.is_proper}
                    )[:20],
                },
                ensure_ascii=False,
            ),
            utcnow(),
        ),
    )
    doc_id = int(cur.lastrowid)
    sent_ids: list[int] = []
    for sent in analysis.sentences:
        sc = conn.execute(
            "INSERT INTO sentences(doc_id, idx, para_idx, text, char_start, char_end) VALUES (?,?,?,?,?,?)",
            (doc_id, sent.idx, sent.para_idx, sent.text, sent.char_start, sent.char_end),
        )
        sent_ids.append(int(sc.lastrowid))
    for lemma, n in lemma_counts.items():
        first_idx = lemma_first.get(lemma, 0)
        first_sid = sent_ids[first_idx] if sent_ids and first_idx < len(sent_ids) else None
        conn.execute(
            "INSERT OR REPLACE INTO doc_lemmas(doc_id, lemma, count, first_sentence_id, kind) VALUES (?,?,?,?,?)",
            (doc_id, lemma, n, first_sid, lemma_kind.get(lemma, "dict")),
        )
    conn.commit()
    return doc_id


def create_corpus(conn: sqlite3.Connection, title: str, goal: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO corpora(title, goal, created_at) VALUES (?,?,?)",
        (title, goal, utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def _has_dict(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM pragma_database_list WHERE name='ecdict'").fetchone() is not None
