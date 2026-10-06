from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from era.config import load_config
from era.db import connect, dict_ready
from era.web.routes import debug, setup

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


def create_app() -> FastAPI:
    application = FastAPI(title="阅读教练", docs_url=None, redoc_url=None)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    application.include_router(setup.router)
    application.include_router(debug.router)

    # Later milestones register extra routers; missing modules are ignored.
    for mod_name in (
        "era.web.routes.placement",
        "era.web.routes.vocab",
        "era.web.routes.corpora",
        "era.web.routes.reader",
        "era.web.routes.review",
        "era.web.routes.glossary",
        "era.web.routes.dashboard",
        "era.web.routes.evals",
        "era.web.routes.stubs",
    ):
        try:
            mod = importlib.import_module(mod_name)
            application.include_router(mod.router)
        except ImportError:
            continue

    @application.get("/")
    def home() -> RedirectResponse:
        cfg = load_config()
        conn = connect(cfg)
        try:
            ready = dict_ready(conn)
        finally:
            conn.close()
        if not ready or not cfg.has_llm_key:
            return RedirectResponse("/setup", status_code=302)
        return RedirectResponse("/corpora", status_code=302)

    return application


app = create_app()
