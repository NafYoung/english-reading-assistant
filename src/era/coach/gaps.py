from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from era.learner.model import LearnerProfile, is_predicted_unknown, load_profile, p_known

GUIDED = 0.95
INDEPENDENT = 0.98


@dataclass
class DocGap:
    doc_id: int
    title: str
    n_tokens: int
    coverage: float
    band: str  # independent | guided | stretch
    unknown_general: list[tuple[str, int]]
    term_candidates: list[tuple[str, int]]
    difficulty: float


def coverage_band(coverage: float) -> str:
    if coverage >= INDEPENDENT:
        return "independent"
    if coverage >= GUIDED:
        return "guided"
    return "stretch"


def doc_gap(conn: sqlite3.Connection, doc_id: int, profile: LearnerProfile | None = None) -> DocGap:
    profile = profile or load_profile(conn)
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        raise KeyError(doc_id)
    rows = conn.execute("SELECT lemma, count, kind FROM doc_lemmas WHERE doc_id=?", (doc_id,)).fetchall()
    known_tokens = 0
    total = 0
    unknown_general: list[tuple[str, int]] = []
    terms: list[tuple[str, int]] = []
    for row in rows:
        lemma, count, kind = row["lemma"], int(row["count"]), row["kind"]
        p = p_known(conn, lemma, profile)
        total += count
        if kind == "term_candidate":
            terms.append((lemma, count))
            if p >= 0.5:
                known_tokens += count
            continue
        if not is_predicted_unknown(p):
            known_tokens += count
        else:
            unknown_general.append((lemma, count))
    n_tokens = int(doc["n_tokens"] or total)
    coverage = (known_tokens / n_tokens) if n_tokens else 1.0
    term_density = (sum(c for _, c in terms) / n_tokens) if n_tokens else 0.0
    unk_ratio = 1.0 - coverage
    difficulty = unk_ratio + 0.5 * term_density
    unknown_general.sort(key=lambda x: -x[1])
    terms.sort(key=lambda x: -x[1])
    return DocGap(
        doc_id=doc_id,
        title=doc["title"] or "",
        n_tokens=n_tokens,
        coverage=coverage,
        band=coverage_band(coverage),
        unknown_general=unknown_general[:40],
        term_candidates=terms[:40],
        difficulty=difficulty,
    )


def corpus_gaps(conn: sqlite3.Connection, corpus_id: int) -> list[DocGap]:
    profile = load_profile(conn)
    docs = conn.execute(
        "SELECT id FROM documents WHERE corpus_id=? ORDER BY id", (corpus_id,)
    ).fetchall()
    return [doc_gap(conn, d["id"], profile) for d in docs]


def unknown_lemmas_for_doc(conn: sqlite3.Connection, doc_id: int) -> set[str]:
    gap = doc_gap(conn, doc_id)
    return {w for w, _ in gap.unknown_general} | {w for w, _ in gap.term_candidates}
