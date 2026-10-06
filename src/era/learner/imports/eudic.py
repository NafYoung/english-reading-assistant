from __future__ import annotations

from typing import Any

import httpx

EUDIC_URL = "https://api.frdic.com/api/open/v1/studylist/words/{category_id}"


class EudicError(Exception):
    pass


def fetch_eudic_words(
    api_key: str,
    category_id: int = 0,
    *,
    client: httpx.Client | None = None,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Pull the default Eudic study list.

    Pagination is not documented with a verified key. We try `page` until a page
    is empty or the API errors, then fall back to the first response.
    """
    if not api_key.strip():
        raise EudicError("未填写欧路 API Key")
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    headers = {"Authorization": api_key.strip()}
    words: list[dict[str, Any]] = []
    try:
        page = 1
        seen_empty = False
        while page <= 50:
            params: dict[str, Any] = {"language": "en", "page": page, "page_size": 100}
            resp = client.get(
                EUDIC_URL.format(category_id=category_id),
                headers=headers,
                params=params,
            )
            if resp.status_code >= 400:
                # retry once without pagination params — some deployments ignore them
                if page == 1:
                    resp = client.get(
                        EUDIC_URL.format(category_id=category_id),
                        headers=headers,
                        params={"language": "en"},
                    )
                if resp.status_code >= 400:
                    raise EudicError(
                        f"欧路接口失败 HTTP {resp.status_code}。请改用欧路导出的 TXT/CSV。"
                    )
                payload = resp.json()
                words.extend(_extract(payload))
                break
            payload = resp.json()
            chunk = _extract(payload)
            if not chunk:
                seen_empty = True
                break
            words.extend(chunk)
            if len(chunk) < 50:
                break
            page += 1
        if not words and not seen_empty:
            raise EudicError("欧路没有返回单词。请改用导出文件 + CSV/TXT 导入。")
        return words
    except httpx.HTTPError as exc:
        raise EudicError(f"无法连接欧路：{exc}。请改用 CSV/TXT 导入。") from exc
    finally:
        if own:
            client.close()


def _extract(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            rows = data["items"]
        else:
            rows = payload.get("words") or payload.get("list") or []
    else:
        rows = []
    out = []
    for row in rows:
        if isinstance(row, str):
            out.append({"word": row})
        elif isinstance(row, dict):
            word = row.get("word") or row.get("spell") or row.get("voc_spelling")
            if word:
                item = dict(row)
                item["word"] = str(word)
                out.append(item)
    return out
