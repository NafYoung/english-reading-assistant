from __future__ import annotations

from era.ingest.pdf import IngestError


def fetch_url(url: str) -> tuple[str, str]:
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover
        raise IngestError("未安装 trafilatura") from exc
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise IngestError(f"无法抓取 URL：{url}")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
    if not text.strip():
        raise IngestError("抓到了页面，但抽不出正文")
    title = url
    try:
        meta = trafilatura.extract_metadata(downloaded)
        if meta and meta.title:
            title = meta.title
    except Exception:
        pass
    return title, text
