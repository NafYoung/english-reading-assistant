from __future__ import annotations

import sqlite3
from pathlib import Path

# Tiny ECDICT-shaped table for tests. frq/bnc are ranks (smaller = more frequent).
MINI_ROWS = [
    ("the", "", "art. definite article", "art. 这", "art", 5, 1, "gk", 1, 1, ""),
    ("be", "", "v. to exist", "v. 是", "v", 5, 1, "gk", 2, 2, "d:being/i:is/p:was"),
    ("act", "", "v. to do something\nn. a law", "v. 行动\nn. 行为", "v", 4, 1, "gk", 500, 400, "d:acting/s:acts"),
    ("acting", "", "n. the art of performing", "n. 演技", "n", 3, 0, "", 8000, 7000, "0:act"),
    ("number", "", "n. a quantity", "n. 数字, 号码", "n", 5, 1, "gk", 200, 150, "1:numb"),
    ("numb", "", "adj. without feeling", "adj. 麻木的", "j", 3, 0, "", 9000, 8000, ""),
    ("reach", "", "v. to arrive at\nn. range", "v. 到达, 伸出\nn. 范围", "v", 4, 1, "gk", 800, 700, ""),
    ("latency", "", "n. delay between stimulus and response", "n. 潜伏; 延迟", "n", 2, 0, "", 18000, 17000, ""),
    ("transformer", "", "n. electrical device that changes voltage", "n. 变压器", "n", 2, 0, "", 15000, 14000, ""),
    ("embedding", "", "n. [医] implantation / [化] embedding", "n. [化]包埋; [医]植入", "n", 1, 0, "", 25000, 24000, ""),
    ("attention", "", "n. notice taken of someone", "n. 注意, 关心", "n", 4, 1, "gk", 1200, 1100, ""),
    ("orchestrator", "", "n. [医] a person who orchestrates", "n. [医]管弦乐演奏家", "n", 0, 0, "", 0, 0, "0:orchestrate"),
    ("agent", "", "n. a person who acts for another", "n. 代理人, 特工", "n", 4, 1, "gk", 2500, 2400, ""),
    ("workflow", "", "n. the sequence of processes", "n. 工作流程", "n", 1, 0, "", 22000, 21000, ""),
    ("and", "", "conj. connecting words", "conj. 和", "c", 5, 1, "gk", 3, 3, ""),
    ("of", "", "prep. belonging to", "prep. 的", "i", 5, 1, "gk", 4, 4, ""),
    ("to", "", "prep. toward", "prep. 到", "i", 5, 1, "gk", 5, 5, ""),
    ("in", "", "prep. inside", "prep. 在…里", "i", 5, 1, "gk", 6, 6, ""),
    ("context", "", "n. circumstances", "n. 上下文, 语境", "n", 3, 1, "cet6", 3500, 3400, ""),
    ("routing", "", "n. the path of a route", "n. 路由选择", "n", 1, 0, "", 19000, 18500, ""),
    ("rout", "", "n. a disorderly retreat", "n. 溃退", "n", 2, 0, "", 16000, 15500, ""),
    ("paper", "", "n. academic article", "n. 论文, 纸", "n", 4, 1, "gk", 900, 850, ""),
    ("model", "", "n. a representation", "n. 模型", "n", 4, 1, "cet4", 2000, 1900, ""),
    ("language", "", "n. a system of communication", "n. 语言", "n", 5, 1, "gk", 700, 650, ""),
    ("read", "", "v. to look at and understand written words", "v. 阅读", "v", 5, 1, "gk", 300, 280, ""),
]


def write_slim_dict(path: Path, extra_rows: list[tuple] | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE dict(word TEXT PRIMARY KEY, phonetic, definition, translation, "
        "pos, collins INTEGER, oxford INTEGER, tag, bnc INTEGER, frq INTEGER, exchange)"
    )
    rows = list(MINI_ROWS)
    if extra_rows:
        rows.extend(extra_rows)
    conn.executemany("INSERT OR IGNORE INTO dict VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM dict").fetchone()[0]
    conn.close()
    return int(n)


def write_stardict(path: Path, extra_rows: list[tuple] | None = None) -> None:
    """Create a tiny source DB with the same columns the slim builder expects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE stardict("
        "word TEXT, phonetic, definition, translation, pos, "
        "collins INTEGER, oxford INTEGER, tag, bnc INTEGER, frq INTEGER, exchange)"
    )
    rows = list(MINI_ROWS) + (extra_rows or [])
    conn.executemany("INSERT INTO stardict VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
