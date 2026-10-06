from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from era.learner.srs import RatingName, serialize_new_card
from era.learner.srs import review as srs_review

STATUSES = ("unknown", "learning", "known", "ignored")
P_BY_STATUS = {"known": 0.95, "learning": 0.3, "ignored": 1.0, "unknown": 0.05}


@dataclass
class LearnerProfile:
    vocab_estimate: int = 5000
    band_curve: list[float] | None = None
    false_alarm_rate: float = 0.0
    placement_at: str | None = None


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_profile(conn: sqlite3.Connection) -> LearnerProfile:
    row = conn.execute("SELECT * FROM learner_profile WHERE id = 1").fetchone()
    if not row:
        return LearnerProfile()
    curve = []
    if row["band_curve"]:
        try:
            curve = json.loads(row["band_curve"])
        except json.JSONDecodeError:
            curve = []
    return LearnerProfile(
        vocab_estimate=int(row["vocab_estimate"] or 5000),
        band_curve=curve,
        false_alarm_rate=float(row["false_alarm_rate"] or 0),
        placement_at=row["placement_at"],
    )


def save_profile(conn: sqlite3.Connection, profile: LearnerProfile) -> None:
    conn.execute(
        "INSERT INTO learner_profile(id, vocab_estimate, band_curve, false_alarm_rate, placement_at) "
        "VALUES (1,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET vocab_estimate=excluded.vocab_estimate, "
        "band_curve=excluded.band_curve, false_alarm_rate=excluded.false_alarm_rate, "
        "placement_at=excluded.placement_at",
        (
            profile.vocab_estimate,
            json.dumps(profile.band_curve or []),
            profile.false_alarm_rate,
            profile.placement_at,
        ),
    )
    conn.commit()


def get_word(conn: sqlite3.Connection, lemma: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user_words WHERE lemma = ?", (lemma,)).fetchone()


def dict_rank(conn: sqlite3.Connection, lemma: str) -> int | None:
    try:
        row = conn.execute(
            "SELECT frq, bnc FROM ecdict.dict WHERE word = ?", (lemma.lower(),)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    vals = [int(v) for v in (row["frq"], row["bnc"]) if v and int(v) > 0]
    return min(vals) if vals else None


def in_dictionary(conn: sqlite3.Connection, lemma: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM ecdict.dict WHERE word = ?", (lemma.lower(),)
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


def approved_glossary_known(conn: sqlite3.Connection, lemma: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM glossary_terms WHERE lemma = ? AND status = 'approved'",
        (lemma.lower(),),
    ).fetchone()
    return row is not None


def logistic_p(rank: int, vocab_estimate: int) -> float:
    v = max(int(vocab_estimate), 200)
    s = 0.15 * v
    return 1.0 / (1.0 + math.exp((rank - v) / s))


def p_known(conn: sqlite3.Connection, lemma: str, profile: LearnerProfile | None = None) -> float:
    lemma = lemma.lower()
    row = get_word(conn, lemma)
    if row:
        return P_BY_STATUS.get(row["status"], 0.05)
    if not in_dictionary(conn, lemma):
        if approved_glossary_known(conn, lemma):
            return 0.0
        return 0.0
    profile = profile or load_profile(conn)
    rank = dict_rank(conn, lemma)
    if rank is None:
        return 0.0
    return logistic_p(rank, profile.vocab_estimate)


def is_predicted_unknown(p: float) -> bool:
    return p < 0.5


def log_event(
    conn: sqlite3.Connection,
    lemma: str,
    event: str,
    *,
    session_id: int | None = None,
    doc_id: int | None = None,
    sentence_id: int | None = None,
    payload: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO word_events(lemma, event, session_id, doc_id, sentence_id, payload, ts) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            lemma,
            event,
            session_id,
            doc_id,
            sentence_id,
            json.dumps(payload, ensure_ascii=False) if payload else None,
            utcnow(),
        ),
    )


def upsert_word(
    conn: sqlite3.Connection,
    lemma: str,
    *,
    status: str,
    source: str,
    confidence: float,
    encounters_delta: int = 0,
    lookups_delta: int = 0,
    ensure_card: bool = False,
    card_json: str | None = None,
    due_at: str | None = None,
) -> None:
    lemma = lemma.lower()
    now = utcnow()
    existing = get_word(conn, lemma)
    if existing is None:
        fsrs = card_json or (serialize_new_card() if ensure_card else None)
        conn.execute(
            "INSERT INTO user_words(lemma, status, source, confidence, encounters, lookups, "
            "first_seen, last_seen, fsrs_card, due_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                lemma,
                status,
                source,
                confidence,
                max(encounters_delta, 0),
                max(lookups_delta, 0),
                now,
                now,
                fsrs,
                due_at,
                now,
            ),
        )
        log_event(conn, lemma, "status_change", payload={"to": status, "source": source})
        return
    new_enc = int(existing["encounters"] or 0) + encounters_delta
    new_look = int(existing["lookups"] or 0) + lookups_delta
    fsrs = card_json if card_json is not None else existing["fsrs_card"]
    if ensure_card and not fsrs:
        fsrs = serialize_new_card()
    due = due_at if due_at is not None else existing["due_at"]
    old_status = existing["status"]
    conn.execute(
        "UPDATE user_words SET status=?, source=?, confidence=?, encounters=?, lookups=?, "
        "last_seen=?, fsrs_card=?, due_at=?, updated_at=? WHERE lemma=?",
        (status, source, confidence, new_enc, new_look, now, fsrs, due, now, lemma),
    )
    if old_status != status:
        log_event(
            conn,
            lemma,
            "status_change",
            payload={"from": old_status, "to": status, "source": source},
        )


def apply_event(
    conn: sqlite3.Connection,
    lemma: str,
    event: str,
    *,
    session_id: int | None = None,
    doc_id: int | None = None,
    sentence_id: int | None = None,
    payload: dict | None = None,
) -> None:
    lemma = lemma.lower()
    log_event(
        conn,
        lemma,
        event,
        session_id=session_id,
        doc_id=doc_id,
        sentence_id=sentence_id,
        payload=payload,
    )
    row = get_word(conn, lemma)
    predicted_known = p_known(conn, lemma) >= 0.5

    if event == "lookup_l1":
        if predicted_known:
            log_event(conn, lemma, "prediction_miss", session_id=session_id, doc_id=doc_id)
        upsert_word(
            conn,
            lemma,
            status="learning",
            source="reading",
            confidence=0.3,
            lookups_delta=1,
            ensure_card=True,
        )
        card_json, due = srs_review(get_word(conn, lemma)["fsrs_card"], "again")
        upsert_word(
            conn,
            lemma,
            status="learning",
            source="reading",
            confidence=0.3,
            card_json=card_json,
            due_at=due,
        )
        return

    if event == "confirm_known":
        upsert_word(conn, lemma, status="known", source="reading", confidence=0.85)
        return

    if event == "confirm_unknown":
        upsert_word(
            conn, lemma, status="learning", source="reading", confidence=0.3, ensure_card=True
        )
        return

    if event == "encounter_known":
        if not row:
            return
        conf = min(0.95, float(row["confidence"] or 0.5) + 0.02)
        status = row["status"] if row else "known"
        source = row["source"] if row else "reading"
        upsert_word(
            conn,
            lemma,
            status=status if row else "known",
            source=source,
            confidence=conf,
            encounters_delta=1,
        )
        return

    if event in {"quiz_right", "quiz_wrong"}:
        rating: RatingName = "good" if event == "quiz_right" else "again"
        fsrs = row["fsrs_card"] if row else serialize_new_card()
        card_json, due = srs_review(fsrs, rating)
        status = row["status"] if row else "learning"
        upsert_word(
            conn,
            lemma,
            status=status if status != "unknown" else "learning",
            source=row["source"] if row else "quiz",
            confidence=row["confidence"] if row else 0.3,
            card_json=card_json,
            due_at=due,
            ensure_card=True,
        )
        return

    if event.startswith("review_"):
        mapping = {
            "review_again": "again",
            "review_hard": "hard",
            "review_good": "good",
            "review_easy": "easy",
        }
        rating = mapping[event]
        fsrs = row["fsrs_card"] if row else serialize_new_card()
        card_json, due = srs_review(fsrs, rating)
        status = row["status"] if row else "learning"
        source = row["source"] if row else "reading"
        conf = row["confidence"] if row else 0.3
        # consecutive 2x Good+ with interval ≥7 days → known
        if rating in {"good", "easy"}:
            hist = conn.execute(
                "SELECT event, ts FROM word_events WHERE lemma=? AND event LIKE 'review_%' "
                "ORDER BY id DESC LIMIT 2",
                (lemma,),
            ).fetchall()
            goodish = {"review_good", "review_easy"}
            if len(hist) >= 2 and all(h["event"] in goodish for h in hist):
                # interval between last two reviews
                try:
                    t0 = datetime.fromisoformat(hist[1]["ts"].replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(hist[0]["ts"].replace("Z", "+00:00"))
                    if abs((t1 - t0).days) >= 7:
                        status = "known"
                        conf = 0.9
                        source = "reading"
                except Exception:
                    pass
        upsert_word(
            conn,
            lemma,
            status=status,
            source=source,
            confidence=conf,
            card_json=card_json,
            due_at=due,
        )
        return

    if event in {"imported", "placement_yes", "placement_no"}:
        return


def import_lemmas(
    conn: sqlite3.Connection,
    lemmas: list[str],
    *,
    status: str,
    source: str,
    confidence: float,
) -> int:
    n = 0
    for raw in lemmas:
        lemma = raw.strip().lower()
        if not lemma:
            continue
        upsert_word(conn, lemma, status=status, source=source, confidence=confidence)
        log_event(conn, lemma, "imported", payload={"source": source})
        n += 1
    conn.commit()
    return n
