from pathlib import Path

from fastapi.templating import Jinja2Templates

from era.config import load_config
from era.db import connect, dict_count, dict_ready

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def nav_context() -> dict:
    cfg = load_config()
    conn = connect(cfg)
    try:
        ready = dict_ready(conn)
        count = dict_count(conn) if ready else 0
    finally:
        conn.close()
    return {
        "cfg": cfg,
        "dict_ready": ready,
        "dict_count": count,
        "has_key": cfg.has_llm_key,
        "nav": [
            ("/setup", "设置"),
            ("/placement", "分级测试"),
            ("/import", "导入词汇"),
            ("/vocab", "词表"),
            ("/corpora", "语料"),
            ("/review", "复习"),
            ("/glossary", "术语审核"),
            ("/dashboard", "仪表盘"),
            ("/evals", "评测"),
            ("/debug/llm-calls", "调用日志"),
            ("/debug/traces", "Trace"),
        ],
    }


def page(request, name: str, extra: dict | None = None):
    ctx = {"request": request, **nav_context(), **(extra or {})}
    return templates.TemplateResponse(request, name, ctx)
