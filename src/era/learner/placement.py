from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass

from era.db import utcnow
from era.learner.model import LearnerProfile, import_lemmas, save_profile

# Hand-picked nonce words. None of these is a real high-frequency English word;
# each is ≥2 edits from the obvious neighbors (hourry/theand/uping were rejected).
PSEUDOWORDS = [
    "blimpet",
    "gornack",
    "trellup",
    "vandor",
    "snellic",
    "quomper",
    "farnile",
    "drosket",
    "hampel",
    "worbing",
    "splect",
    "nurmish",
    "calletor",
    "brimdex",
    "jorvine",
    "taspin",
    "mellock",
    "prindle",
    "gessary",
    "lorbane",
    "twessit",
    "nackle",
    "vorbelt",
    "shenmar",
    "crindle",
    "yopper",
    "falmick",
    "sturnel",
    "bexham",
    "plinter",
    "gorvish",
    "blornet",
    "kessil",
    "pranvet",
    "wimsol",
    "darfect",
    "nelbost",
    "crovane",
    "harple",
    "torvess",
]

N_BANDS = 20
BAND_WIDTH = 1000
STAGE1_PER_BAND = 2
STAGE1_PSEUDO = 8
STAGE2_ITEMS = 30
STAGE2_PSEUDO = 4
BATCH_SIZE = 10


@dataclass
class PlacementItem:
    word: str
    is_pseudo: bool
    band: int | None

    def to_json(self) -> dict:
        return {"word": self.word, "is_pseudo": self.is_pseudo, "band": self.band}

    @classmethod
    def from_json(cls, raw: dict) -> PlacementItem:
        return cls(word=raw["word"], is_pseudo=bool(raw["is_pseudo"]), band=raw.get("band"))


@dataclass
class PlacementRun:
    id: int
    stage: int
    items: list[PlacementItem]
    answers: dict[int, bool]  # item index -> recognized
    cursor_idx: int
    finished: bool = False


def _has_ecdict(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM pragma_database_list WHERE name='ecdict'").fetchone() is not None


def band_of_rank(rank: int) -> int:
    return min(N_BANDS - 1, max(0, (int(rank) - 1) // BAND_WIDTH))


def load_band_words(conn: sqlite3.Connection) -> dict[int, list[str]]:
    bands: dict[int, list[str]] = {i: [] for i in range(N_BANDS)}
    if not _has_ecdict(conn):
        return bands
    rows = conn.execute(
        "SELECT word, frq FROM ecdict.dict "
        "WHERE frq > 0 AND length(word) > 2 "
        "AND (exchange IS NULL OR exchange NOT LIKE '0:%') "
        "AND frq <= ?",
        (N_BANDS * BAND_WIDTH,),
    )
    for word, frq in rows:
        bands[band_of_rank(int(frq))].append(word)
    return bands


def band_sizes(conn: sqlite3.Connection) -> list[int]:
    sizes = [0] * N_BANDS
    if not _has_ecdict(conn):
        return sizes
    rows = conn.execute(
        "SELECT frq FROM ecdict.dict "
        "WHERE frq > 0 AND length(word) > 2 "
        "AND (exchange IS NULL OR exchange NOT LIKE '0:%') "
        "AND frq <= ?",
        (N_BANDS * BAND_WIDTH,),
    )
    for (frq,) in rows:
        sizes[band_of_rank(int(frq))] += 1
    return sizes


def _sample(words: list[str], k: int, rng: random.Random, used: set[str]) -> list[str]:
    pool = [w for w in words if w not in used]
    rng.shuffle(pool)
    picked = pool[:k]
    used.update(picked)
    return picked


def build_stage1(conn: sqlite3.Connection, rng: random.Random | None = None) -> list[PlacementItem]:
    rng = rng or random.Random()
    bands = load_band_words(conn)
    used: set[str] = set()
    items: list[PlacementItem] = []
    for b in range(N_BANDS):
        for w in _sample(bands[b], STAGE1_PER_BAND, rng, used):
            items.append(PlacementItem(w, False, b))
    for w in _sample(list(PSEUDOWORDS), STAGE1_PSEUDO, rng, used):
        items.append(PlacementItem(w, True, None))
    rng.shuffle(items)
    return items


def build_stage2(
    conn: sqlite3.Connection,
    center_band: int,
    rng: random.Random | None = None,
    used: set[str] | None = None,
) -> list[PlacementItem]:
    rng = rng or random.Random()
    used = used or set()
    bands = load_band_words(conn)
    lo = max(0, center_band - 3)
    hi = min(N_BANDS - 1, center_band + 3)
    pool: list[tuple[int, str]] = []
    for b in range(lo, hi + 1):
        pool.extend((b, w) for w in bands[b] if w not in used)
    rng.shuffle(pool)
    items: list[PlacementItem] = []
    for b, w in pool[:STAGE2_ITEMS]:
        items.append(PlacementItem(w, False, b))
        used.add(w)
    for w in _sample(list(PSEUDOWORDS), STAGE2_PSEUDO, rng, used):
        items.append(PlacementItem(w, True, None))
    rng.shuffle(items)
    return items


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS placement_runs ("
        "id INTEGER PRIMARY KEY, stage INTEGER NOT NULL, items_json TEXT NOT NULL, "
        "answers_json TEXT NOT NULL, cursor_idx INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT, finished_at TEXT)"
    )
    conn.commit()


def start_run(conn: sqlite3.Connection, rng: random.Random | None = None) -> PlacementRun:
    ensure_schema(conn)
    items = build_stage1(conn, rng)
    cur = conn.execute(
        "INSERT INTO placement_runs(stage, items_json, answers_json, cursor_idx, created_at) "
        "VALUES (1,?,?,0,?)",
        (json.dumps([i.to_json() for i in items]), "{}", utcnow()),
    )
    conn.commit()
    return PlacementRun(id=int(cur.lastrowid), stage=1, items=items, answers={}, cursor_idx=0)


def load_run(conn: sqlite3.Connection, run_id: int) -> PlacementRun | None:
    ensure_schema(conn)
    row = conn.execute("SELECT * FROM placement_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    items = [PlacementItem.from_json(x) for x in json.loads(row["items_json"])]
    answers = {int(k): bool(v) for k, v in json.loads(row["answers_json"] or "{}").items()}
    return PlacementRun(
        id=row["id"],
        stage=row["stage"],
        items=items,
        answers=answers,
        cursor_idx=row["cursor_idx"],
        finished=bool(row["finished_at"]),
    )


def save_run(conn: sqlite3.Connection, run: PlacementRun) -> None:
    conn.execute(
        "UPDATE placement_runs SET stage=?, items_json=?, answers_json=?, cursor_idx=?, "
        "finished_at=? WHERE id=?",
        (
            run.stage,
            json.dumps([i.to_json() for i in run.items]),
            json.dumps({str(k): v for k, v in run.answers.items()}),
            run.cursor_idx,
            utcnow() if run.finished else None,
            run.id,
        ),
    )
    conn.commit()


def estimate(run: PlacementRun, sizes: list[int]) -> tuple[int, list[float], float]:
    """Return V, p_b per band, false-alarm rate f."""
    pseudo_n = 0
    pseudo_yes = 0
    band_yes: dict[int, int] = {i: 0 for i in range(N_BANDS)}
    band_n: dict[int, int] = {i: 0 for i in range(N_BANDS)}
    for idx, item in enumerate(run.items):
        if idx not in run.answers:
            continue
        yes = run.answers[idx]
        if item.is_pseudo:
            pseudo_n += 1
            if yes:
                pseudo_yes += 1
            continue
        if item.band is None:
            continue
        band_n[item.band] += 1
        if yes:
            band_yes[item.band] += 1
    f = (pseudo_yes / pseudo_n) if pseudo_n else 0.0
    p_b: list[float] = []
    for b in range(N_BANDS):
        if band_n[b] == 0:
            p_b.append(0.0)
            continue
        h = band_yes[b] / band_n[b]
        if f >= 1:
            p = 0.0
        else:
            p = max(0.0, (h - f) / (1 - f))
        p_b.append(p)
    v = int(round(sum(p * n for p, n in zip(p_b, sizes, strict=False))))
    return max(v, 0), p_b, f


def apply_answers_to_lexicon(conn: sqlite3.Connection, run: PlacementRun) -> None:
    yes_words = []
    no_words = []
    for idx, item in enumerate(run.items):
        if item.is_pseudo or idx not in run.answers:
            continue
        if run.answers[idx]:
            yes_words.append(item.word)
        else:
            no_words.append(item.word)
    import_lemmas(conn, yes_words, status="known", source="placement", confidence=0.8)
    import_lemmas(conn, no_words, status="unknown", source="placement", confidence=0.2)


def finish_run(conn: sqlite3.Connection, run: PlacementRun) -> LearnerProfile:
    sizes = band_sizes(conn)
    v, curve, f = estimate(run, sizes)
    profile = LearnerProfile(
        vocab_estimate=v or 3000,
        band_curve=curve,
        false_alarm_rate=f,
        placement_at=utcnow(),
    )
    save_profile(conn, profile)
    apply_answers_to_lexicon(conn, run)
    run.finished = True
    save_run(conn, run)
    return profile


def maybe_advance_stage(conn: sqlite3.Connection, run: PlacementRun, rng: random.Random | None = None) -> PlacementRun:
    if run.stage == 1 and len(run.answers) >= len(run.items):
        sizes = band_sizes(conn)
        v, curve, _f = estimate(run, sizes)
        center = band_of_rank(max(v, 1))
        used = {it.word for it in run.items}
        extra = build_stage2(conn, center, rng=rng, used=used)
        run.items.extend(extra)
        run.stage = 2
        save_run(conn, run)
    return run
