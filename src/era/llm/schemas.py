from __future__ import annotations

from pydantic import BaseModel, Field


class SensePick(BaseModel):
    en_sense: str | None = None
    zh_sense: str | None = None
    glossary: str | None = None
    fit: str = "good"
    note_zh: str = ""


class StructureOut(BaseModel):
    main_clause: dict[str, str] = Field(default_factory=dict)
    chunks: list[str] = Field(default_factory=list)
    note_zh: str = ""


class TranslateOut(BaseModel):
    zh: str


class QuizItem(BaseModel):
    question: str
    options: dict[str, str]
    answer: str
    evidence_sentence_ids: list[int] = Field(default_factory=list)


class QuizOut(BaseModel):
    items: list[QuizItem]


class QuizVerify(BaseModel):
    choice: str


class GlossaryDraft(BaseModel):
    en_def: str
    zh_def: str
    pos: str = "n"


class TermClassify(BaseModel):
    labels: dict[str, str]


class ProposePlan(BaseModel):
    order: list[int]
    preteach: dict[int, list[str]] | dict[str, list[str]] = Field(default_factory=dict)
    daily_quota_words: int = 800
    rationale_zh: str = ""
