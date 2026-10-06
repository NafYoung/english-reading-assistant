from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fsrs import Card, Rating, Scheduler

RatingName = Literal["again", "hard", "good", "easy"]
_RATING = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}

_scheduler = Scheduler()


def serialize_new_card() -> str:
    return json.dumps(Card().to_dict())


def review(card_json: str | None, rating: RatingName, now: datetime | None = None) -> tuple[str, str]:
    card = Card.from_dict(json.loads(card_json)) if card_json else Card()
    reviewed, _log = _scheduler.review_card(card, _RATING[rating], now or datetime.now(timezone.utc))
    due = reviewed.due
    if due.tzinfo is None:
        due_s = due.isoformat() + "Z"
    else:
        due_s = due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps(reviewed.to_dict()), due_s
