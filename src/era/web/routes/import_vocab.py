from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from era.config import load_config, save_config
from era.db import connect
from era.learner.imports.csvtxt import parse_word_list
from era.learner.imports.eudic import EudicError, fetch_eudic_words
from era.learner.imports.maimemo import MaimemoError, fetch_maimemo_records, map_record
from era.learner.model import import_lemmas, load_profile, upsert_word
from era.learner.placement import load_band_words
from era.web.deps import page

router = APIRouter()


@router.get("/import")
def import_page(request: Request, msg: str | None = None, err: str | None = None, n: int = 0):
    return page(request, "import_vocab.html", {"msg": msg, "err": err, "n": n})


@router.post("/import/txt")
async def import_txt(
    default_status: str = Form("known"),
    file: UploadFile | None = File(None),
    pasted: str = Form(""),
):
    text = pasted
    if file and file.filename:
        raw = await file.read()
        text = raw.decode("utf-8", errors="replace")
    pairs = parse_word_list(text, default_status=default_status)
    cfg = load_config()
    conn = connect(cfg)
    try:
        n = 0
        for word, status in pairs:
            conf = {"known": 0.9, "learning": 0.3, "unknown": 0.1, "ignored": 1.0}[status]
            upsert_word(conn, word, status=status, source="csv", confidence=conf)
            n += 1
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(f"/import?msg=txt&n={n}", status_code=303)


@router.post("/import/eudic")
def import_eudic(eudic_api_key: str = Form(""), category_id: int = Form(0)):
    cfg = load_config()
    if eudic_api_key.strip():
        cfg.eudic_api_key = eudic_api_key.strip()
        save_config(cfg)
    conn = connect(cfg)
    try:
        rows = fetch_eudic_words(cfg.eudic_api_key, category_id=category_id)
        words = [r["word"] for r in rows]
        n = import_lemmas(conn, words, status="learning", source="eudic", confidence=0.3)
        return RedirectResponse(f"/import?msg=eudic&n={n}", status_code=303)
    except EudicError as exc:
        from urllib.parse import quote

        return RedirectResponse(f"/import?err={quote(str(exc)[:200])}", status_code=303)
    finally:
        conn.close()


@router.post("/import/maimemo")
def import_maimemo(maimemo_token: str = Form("")):
    cfg = load_config()
    if maimemo_token.strip():
        cfg.maimemo_token = maimemo_token.strip()
        save_config(cfg)
    conn = connect(cfg)
    try:
        spellings = [r["lemma"] for r in conn.execute("SELECT lemma FROM user_words")]
        profile = load_profile(conn)
        bands = load_band_words(conn)
        center = min(19, max(0, (profile.vocab_estimate - 1) // 1000))
        for b in range(max(0, center - 1), min(20, center + 2)):
            spellings.extend(bands.get(b, [])[:200])
        if not spellings:
            return RedirectResponse(
                "/import?err=" + _q("没有可查询的词。请先做分级测试、导入 TXT，或等语料导入后再同步墨墨。"),
                status_code=303,
            )
        recs = fetch_maimemo_records(cfg.maimemo_token, spellings)
        n = 0
        for rec in recs:
            lemma, status, conf = map_record(rec)
            if not lemma:
                continue
            upsert_word(conn, lemma, status=status, source="maimemo", confidence=conf)
            n += 1
        conn.commit()
        return RedirectResponse(f"/import?msg=maimemo&n={n}", status_code=303)
    except MaimemoError as exc:
        return RedirectResponse(f"/import?err={_q(str(exc))}", status_code=303)
    finally:
        conn.close()


def _q(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:220])
