from __future__ import annotations

import re
from pathlib import Path

from era.nlp.lemmatize import pick_lemma
from era.nlp.tokenize import normalize_text, tokenize

REF = re.compile(r"^\s*(\d+\s+)?(References|REFERENCES|Bibliography)\s*$")


class IngestError(Exception):
    pass


def is_garbage_block(text: str, lookup, threshold: float = 0.35) -> bool:
    toks = tokenize(text)
    if len(toks) < 3:
        return False
    bad = 0
    for tok in toks:
        w = tok.stripped.lower()
        lemma = pick_lemma(w, lookup)
        if lemma is None or len(w) <= 2:
            bad += 1
    return (bad / len(toks)) > threshold


def extract_pdf(path: Path, lookup) -> tuple[str, dict]:
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
    except ImportError as exc:  # pragma: no cover
        raise IngestError("未安装 pdfminer.six") from exc

    kept: list[str] = []
    dropped = 0
    stop = False
    for page in extract_pages(str(path)):
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            block = normalize_text(el.get_text())
            if REF.match(block.strip()):
                stop = True
                break
            toks = tokenize(block)
            if len(toks) < 3:
                continue
            if is_garbage_block(block, lookup):
                dropped += 1
                continue
            kept.append(block.strip())
        if stop:
            break
    report = {"kept_blocks": len(kept), "dropped_blocks": dropped, "cut_references": stop}
    return "\n\n".join(kept), report
