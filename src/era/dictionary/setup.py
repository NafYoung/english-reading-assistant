from __future__ import annotations

import sqlite3
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from era.config import AppConfig, load_config

ECDICT_URLS = [
    "https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip",
    "https://downloads.sourceforge.net/project/ecdict.mirror/1.0.28/ecdict-sqlite-28.zip",
]


def build_slim_ecdict(source_db: Path, dest_db: Path) -> int:
    """Filter the full ECDICT SQLite into the frequency/tag slim table."""
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    if dest_db.exists():
        dest_db.unlink()
    src = sqlite3.connect(str(source_db))
    slim = sqlite3.connect(str(dest_db))
    slim.execute(
        "CREATE TABLE dict("
        "word TEXT PRIMARY KEY, phonetic, definition, translation, pos, "
        "collins INTEGER, oxford INTEGER, tag, bnc INTEGER, frq INTEGER, exchange)"
    )
    rows = src.execute(
        "SELECT lower(word), phonetic, definition, translation, pos, "
        "collins, oxford, tag, bnc, frq, exchange FROM stardict "
        "WHERE (bnc > 0 OR frq > 0 "
        "OR (tag IS NOT NULL AND tag != '') "
        "OR collins > 0 OR oxford > 0 OR exchange LIKE '0:%') "
        "AND word NOT LIKE '% %'"
    )
    slim.executemany("INSERT OR IGNORE INTO dict VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    slim.execute("CREATE INDEX IF NOT EXISTS idx_dict_frq ON dict(frq)")
    slim.execute("CREATE INDEX IF NOT EXISTS idx_dict_bnc ON dict(bnc)")
    slim.commit()
    n = int(slim.execute("SELECT COUNT(*) FROM dict").fetchone()[0])
    slim.close()
    src.close()
    return n


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载 ECDICT：{url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "era-setup-dict/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            print(".", end="", flush=True)
    print(" 完成", flush=True)


def _extract_stardict(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        db_name = next((n for n in names if n.lower().endswith(".db")), None)
        if not db_name:
            raise FileNotFoundError(f"{zip_path} 中没有 .db 文件")
        target = dest_dir / "stardict.db"
        with zf.open(db_name) as src, target.open("wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        return target


def setup_dictionary(config: AppConfig | None = None, source_zip: Path | None = None) -> int:
    cfg = config or load_config()
    cfg.paths.ensure()
    cache_dir = cfg.paths.data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = source_zip or (cache_dir / "ecdict-sqlite-28.zip")
    if source_zip is None and not zip_path.exists():
        last_error: Exception | None = None
        for url in ECDICT_URLS:
            try:
                _download(url, zip_path)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 — try the next mirror
                last_error = exc
                print(f"下载失败：{exc}", file=sys.stderr)
        if last_error and not zip_path.exists():
            raise RuntimeError(f"无法下载 ECDICT：{last_error}")
    print("解压 stardict.db …", flush=True)
    source_db = _extract_stardict(zip_path, cache_dir)
    t0 = time.time()
    print("构建精简库 …", flush=True)
    n = build_slim_ecdict(source_db, cfg.paths.dict_path)
    print(f"词典已就绪：{n:,} 条（{time.time() - t0:.1f}s）→ {cfg.paths.dict_path}", flush=True)
    return n
