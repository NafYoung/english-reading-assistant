from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Sense:
    sid: str
    text: str
    kind: str  # en | zh | glossary
    source: str  # ECDICT | 术语表(已审核)


@dataclass
class SenseCandidates:
    lemma: str
    en: list[Sense] = field(default_factory=list)
    zh: list[Sense] = field(default_factory=list)
    glossary: list[Sense] = field(default_factory=list)
    phonetic: str = ""
    pos: str = ""
    frq: int = 0
    bnc: int = 0
    in_dict: bool = False

    def by_id(self) -> dict[str, Sense]:
        out: dict[str, Sense] = {}
        for seq in (self.en, self.zh, self.glossary):
            for s in seq:
                out[s.sid] = s
        return out

    @property
    def empty(self) -> bool:
        return not (self.en or self.zh or self.glossary)


def _lines(blob: str | None) -> list[str]:
    if not blob:
        return []
    return [ln.strip() for ln in str(blob).replace("\r", "\n").split("\n") if ln.strip()]


def get_dict_row(conn: sqlite3.Connection, lemma: str) -> sqlite3.Row | None:
    if not lemma:
        return None
    try:
        return conn.execute("SELECT * FROM ecdict.dict WHERE word = ?", (lemma.lower(),)).fetchone()
    except sqlite3.OperationalError:
        return None


def rank_of_row(row: sqlite3.Row | None) -> int | None:
    if row is None:
        return None
    vals = [int(v) for v in (row["frq"], row["bnc"]) if v and int(v) > 0]
    return min(vals) if vals else None


def approved_glossary(conn: sqlite3.Connection, lemma: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM glossary_terms WHERE lemma = ? AND status = 'approved' ORDER BY id",
        (lemma.lower(),),
    ).fetchall()


def candidates(conn: sqlite3.Connection, lemma: str) -> SenseCandidates:
    lemma = (lemma or "").lower()
    out = SenseCandidates(lemma=lemma)
    row = get_dict_row(conn, lemma)
    if row:
        out.in_dict = True
        out.phonetic = row["phonetic"] or ""
        out.pos = row["pos"] or ""
        out.frq = int(row["frq"] or 0)
        out.bnc = int(row["bnc"] or 0)
        for i, line in enumerate(_lines(row["definition"]), start=1):
            out.en.append(Sense(sid=f"E{i}", text=line, kind="en", source="ECDICT"))
        for i, line in enumerate(_lines(row["translation"]), start=1):
            out.zh.append(Sense(sid=f"Z{i}", text=line, kind="zh", source="ECDICT"))
    for i, g in enumerate(approved_glossary(conn, lemma), start=1):
        text = f"{g['en_def']} / {g['zh_def']}"
        out.glossary.append(
            Sense(sid=f"G{i}", text=text, kind="glossary", source="术语表(已审核)")
        )
    return out
