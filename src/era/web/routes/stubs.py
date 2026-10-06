from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from era.web.deps import page

router = APIRouter()

STUBS: list = []


def _stub(title: str, slug: str):
    def view(request: Request):
        return page(
            request,
            "stub.html",
            {
                "title": title,
                "slug": slug,
                "message": "这一页会在后续里程碑接上。现在请先完成设置：填 API Key、构建词典。",
            },
        )

    return view


for path, title, slug in STUBS:
    router.add_api_route(path, _stub(title, slug), methods=["GET"], response_class=HTMLResponse)
