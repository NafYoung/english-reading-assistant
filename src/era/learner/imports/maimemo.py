from __future__ import annotations

from typing import Any

import httpx

MAIMEMO_URL = "https://open.maimemo.com/open/api/v1/memo/study/query_study_records"
BATCH = 1000


class MaimemoError(Exception):
    pass


def map_record(rec: dict[str, Any]) -> tuple[str, str, float]:
    """Return (lemma, status, confidence) from a Maimemo study record."""
    spelling = str(rec.get("voc_spelling") or rec.get("spelling") or "").strip().lower()
    last = str(rec.get("last_response") or "").upper()
    count = int(rec.get("study_count") or 0)
    if last == "WELL_FAMILIAR":
        return spelling, "known", 0.9
    if last == "FAMILIAR" and count >= 3:
        return spelling, "known", 0.8
    return spelling, "learning", 0.4


def fetch_maimemo_records(
    token: str,
    spellings: list[str],
    *,
    client: httpx.Client | None = None,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    if not token.strip():
        raise MaimemoError("未填写墨墨 Token")
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    headers = {"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"}
    records: list[dict[str, Any]] = []
    try:
        unique = []
        seen = set()
        for s in spellings:
            k = s.strip().lower()
            if k and k not in seen:
                seen.add(k)
                unique.append(k)
        for i in range(0, len(unique), BATCH):
            chunk = unique[i : i + BATCH]
            resp = client.post(MAIMEMO_URL, headers=headers, json={"spellings": chunk})
            if resp.status_code >= 400:
                raise MaimemoError(
                    f"墨墨接口失败 HTTP {resp.status_code}。接口仍是公测，请改用 CSV/TXT。"
                )
            payload = resp.json()
            recs = payload.get("records") if isinstance(payload, dict) else None
            if recs is None and isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict):
                    recs = data.get("records")
                elif isinstance(data, list):
                    recs = data
            if not recs:
                recs = []
            records.extend(recs)
        return records
    except httpx.HTTPError as exc:
        raise MaimemoError(f"无法连接墨墨：{exc}。请改用 CSV/TXT 导入。") from exc
    finally:
        if own:
            client.close()
