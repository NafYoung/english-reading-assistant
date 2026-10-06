from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from era.coach.senses import pick_sense
from era.coach.structure import chunks_ok, explain_structure
from era.config import AppConfig, load_config, project_root
from era.db import connect
from era.ingest.pdf import is_garbage_block
from era.nlp.analyze import dict_lookup_fn
from era.nlp.lemmatize import pick_lemma


def reports_dir() -> Path:
    env = os.environ.get("ERA_EVAL_REPORTS", "").strip()
    root = Path(env).expanduser() if env else project_root() / "evals" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def samples_dir() -> Path:
    env = os.environ.get("ERA_EVAL_DATA", "").strip()
    return Path(env).expanduser() if env else project_root() / "evals" / "data"


def load_samples(task: str) -> list[dict]:
    path = samples_dir() / f"{task}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def normalize_task(task: str) -> str:
    t = task.lower().strip()
    if t.startswith("e") and t[1:].isdigit():
        return t[1:]
    if t.isdigit():
        return t
    return t.lstrip("e")


def run_eval(task: str, cfg: AppConfig | None = None) -> Path:
    cfg = cfg or load_config()
    conn = connect(cfg)
    key = normalize_task(task)
    dispatch = {
        "1": e1_lemma,
        "2": e2_pdf,
        "3": e3_sense,
        "4": e4_unknown,
        "5": e5_quiz,
        "6": e6_structure,
    }
    fn = dispatch.get(key)
    if fn is None:
        conn.close()
        raise ValueError(f"未知任务 {task}")
    body = fn(conn, cfg)
    path = reports_dir() / f"{date.today().isoformat()}-e{key}.md"
    path.write_text(body, encoding="utf-8")
    conn.close()
    return path


def _labels(conn, task: str) -> list:
    return conn.execute(
        "SELECT * FROM eval_labels WHERE task=? ORDER BY id", (task,)
    ).fetchall()


def _label_map(conn, task: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in _labels(conn, task):
        try:
            item = json.loads(row["item_json"])
            lab = json.loads(row["label_json"])
        except json.JSONDecodeError:
            continue
        out[item_key(item)] = lab
    return out


def item_key(item: dict) -> str:
    if "lemma" in item and "sentence" in item:
        return f"{item['lemma']}|{item['sentence']}"
    if "surface" in item:
        return f"{item.get('surface')}|{item.get('sentence', '')}"
    if "text" in item:
        return str(item["text"])
    if "sentence" in item:
        return str(item["sentence"])
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def e1_lemma(conn, cfg) -> str:
    lookup = dict_lookup_fn(conn)
    samples = load_samples("e1") or [
        {"surface": "acting", "gold": {"lemma": "act"}},
        {"surface": "number", "gold": {"lemma": "number"}},
        {"surface": "routing", "gold": {"lemma": "routing"}},
        {"surface": "studies", "gold": {"lemma": "study"}},
    ]
    override = _label_map(conn, "e1")
    b0 = b2 = n = 0
    lines = [
        "# E1 词形还原\n",
        "| 词 | 金标准 | B0 小写 | B2 simplemma+词频 |",
        "|---|---|---|---|",
    ]
    for item in samples:
        surface = item.get("surface")
        if not surface:
            continue
        gold = override.get(item_key(item)) or item.get("gold") or {}
        want = gold.get("lemma")
        if not want:
            continue
        n += 1
        b0_pred = surface.lower()
        b2_pred = pick_lemma(surface, lookup) or surface.lower()
        b0 += int(b0_pred == want)
        b2 += int(b2_pred == want)
        lines.append(f"| {surface} | {want} | {b0_pred} | {b2_pred} |")
    b0_pct = (100 * b0 / n) if n else 0
    b2_pct = (100 * b2 / n) if n else 0
    lines += [
        "\n## 基线对比\n",
        "| 方案 | 准确率 |",
        "|---|---|",
        f"| B0 小写原形 | {b0}/{n} ({b0_pct:.0f}%) |",
        "| B1 只用 ECDICT exchange | 不采用（原型：number→numb） |",
        f"| B2 simplemma + 词频（本方案） | {b2}/{n} ({b2_pct:.0f}%) |",
        "\nB1 已知会把 number→numb、routing→rout，本方案不使用 exchange 反查。\n",
    ]
    return "\n".join(lines)


def e2_pdf(conn, cfg) -> str:
    lookup = dict_lookup_fn(conn)
    samples = load_samples("e2") or [
        {"text": "wkh dqg fw rx wkh", "gold": {"kind": "garbage"}},
        {"text": "The paper describes the model and the language.", "gold": {"kind": "body"}},
    ]
    override = _label_map(conn, "e2")
    tp = fp = fn = tn = 0
    lines = ["# E2 PDF 清洗\n", "| 文本 | 金标准 | 预测 |", "|---|---|---|"]
    for item in samples:
        text = item.get("text") or ""
        gold = override.get(item_key(item)) or item.get("gold") or {}
        kind = gold.get("kind")
        if kind not in {"garbage", "body"}:
            continue
        pred = bool(is_garbage_block(text, lookup))
        gold_g = kind == "garbage"
        tp += int(pred and gold_g)
        fp += int(pred and not gold_g)
        fn += int((not pred) and gold_g)
        tn += int((not pred) and not gold_g)
        preview = text.replace("\n", " ")[:48]
        lines.append(f"| `{preview}` | {kind} | {'garbage' if pred else 'body'} |")
    rec = (tp / (tp + fn)) if (tp + fn) else 0
    fpr = (fp / (fp + tn)) if (fp + tn) else 0
    lines += [
        "\n## 基线对比\n",
        "| 方案 | 垃圾块召回 | 正文误删 |",
        "|---|---|---|",
        "| B0 不过滤 | 0 | 0 |",
        f"| 本方案（OOV/短词比例 >0.35） | {tp}/{tp + fn} ({100 * rec:.0f}%) | {fp}/{fp + tn} ({100 * fpr:.0f}%) |",
        "\n被丢的典型是图里字体编码错乱的文字（如 `wkh`、`dqg`）。\n",
    ]
    return "\n".join(lines)


def e3_sense(conn, cfg) -> str:
    samples = load_samples("e3") or [
        {"lemma": "latency", "sentence": "The latency of the system is high.", "gold": {"en_sense": "E1", "fit": "good"}},
        {"lemma": "transformer", "sentence": "A transformer model encodes the input.", "gold": {"fit": "no_fit"}},
        {"lemma": "reach", "sentence": "They reach the same conclusion.", "gold": {"en_sense": "E1", "fit": "good"}},
    ]
    override = _label_map(conn, "e3")
    lines = [
        "# E3 义项选择\n",
        "| 词 | fit | chosen | no_fit | invalid | 金标准 | B0=E1 | B2 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    illegal = no_fit_n = n = top1 = b0_top1 = no_fit_tp = no_fit_fp = no_fit_fn = 0
    for item in samples:
        lemma = item.get("lemma")
        sent = item.get("sentence")
        if not lemma or not sent:
            continue
        conn.execute(
            "INSERT INTO sentences(doc_id, idx, para_idx, text, char_start, char_end) VALUES (0,0,0,?,0,0)",
            (sent,),
        )
        sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        out = pick_sense(conn, cfg, lemma=lemma, surface=lemma, sentence=sent, sentence_id=int(sid))
        gold = override.get(item_key(item)) or item.get("gold") or {}
        n += 1
        illegal += int(out["invalid"])
        pred_no_fit = bool(out["no_fit"])
        no_fit_n += int(pred_no_fit)
        gold_fit = gold.get("fit")
        gold_en = gold.get("en_sense")
        gold_no_fit = gold_fit == "no_fit"
        pred_en = out["chosen"].get("en_sense")
        b0_hit = (gold_en == "E1") if gold_en else (not gold_no_fit)
        if gold_no_fit:
            hit = pred_no_fit
            b0_hit = False
            no_fit_tp += int(pred_no_fit)
            no_fit_fn += int(not pred_no_fit)
        else:
            hit = (not pred_no_fit) and (gold_en is None or pred_en == gold_en)
            no_fit_fp += int(pred_no_fit)
        top1 += int(hit)
        b0_top1 += int(b0_hit)
        lines.append(
            f"| {lemma} | {out['chosen']['fit']} | {out['chosen']['en_sense']} | "
            f"{out['no_fit']} | {out['invalid']} | {gold_fit or gold_en} | {b0_hit} | {hit} |"
        )
    p = (no_fit_tp / (no_fit_tp + no_fit_fp)) if (no_fit_tp + no_fit_fp) else 0
    r = (no_fit_tp / (no_fit_tp + no_fit_fn)) if (no_fit_tp + no_fit_fn) else 0
    lines += [
        "\n## 基线对比\n",
        "| 方案 | top-1 | 非法输出 | no_fit P/R |",
        "|---|---|---|---|",
        f"| B0 总选 E1 | {b0_top1}/{n} | 0 | 无法标 no_fit |",
        "| B1 只看词不看句 | 未跑（需真实 LLM） | — | — |",
        f"| B2 本方案（关 thinking；当前 mock 或真实 Key） | {top1}/{n} | {illegal}/{n} | "
        f"{p:.2f}/{r:.2f} |",
        "| B3 开 thinking | MVP 选义项关闭 thinking | — | — |",
        "\n无合适义项时不得编造释义。`note_zh` 夹带新义项的比例需人工抽 30 条。\n",
    ]
    return "\n".join(lines)


def e4_unknown(conn, cfg) -> str:
    from era.learner.model import is_predicted_unknown, load_profile, p_known

    profile = load_profile(conn)
    samples = load_samples("e4")
    override = _label_map(conn, "e4")
    rows = []
    if samples:
        for item in samples:
            gold = override.get(item_key(item)) or item.get("gold")
            if gold is None or "unknown" not in gold:
                continue
            rows.append((item.get("lemma"), bool(gold["unknown"])))
    else:
        for row in _labels(conn, "e4"):
            item = json.loads(row["item_json"])
            lab = json.loads(row["label_json"])
            if "unknown" in lab and item.get("lemma"):
                rows.append((item["lemma"], bool(lab["unknown"])))

    def metrics(pred_fn):
        tp = fp = fn = 0
        for lemma, gold_unk in rows:
            pred = pred_fn(lemma)
            tp += int(pred and gold_unk)
            fp += int(pred and not gold_unk)
            fn += int((not pred) and gold_unk)
        prec = tp / (tp + fp) if (tp + fp) else 0
        rec = tp / (tp + fn) if (tp + fn) else 0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0
        return tp, fp, fn, prec, rec, f1

    def b0(lemma: str) -> bool:
        rank = None
        try:
            from era.learner.model import dict_rank

            rank = dict_rank(conn, lemma)
        except Exception:
            rank = None
        return rank is None or rank > 5000

    def b2(lemma: str) -> bool:
        return is_predicted_unknown(p_known(conn, lemma, profile))

    m0 = metrics(b0)
    m2 = metrics(b2)
    lines = [
        "# E4 未知词预测\n",
        f"样本 {len(rows)} 条（文件金标准 + `/evals` 标注）。词汇量估计 {profile.vocab_estimate}。",
        "\n## 基线对比\n",
        "| 方案 | P | R | F1 | TP/FP/FN |",
        "|---|---|---|---|---|",
        f"| B0 词频前 5000 以外都算未知 | {m0[3]:.2f} | {m0[4]:.2f} | {m0[5]:.2f} | {m0[0]}/{m0[1]}/{m0[2]} |",
        "| B1 只用分级先验 | 有分级结果后与 B2 在无导入时接近 | — | — | — |",
        f"| B2 先验+导入+阅读（本方案） | {m2[3]:.2f} | {m2[4]:.2f} | {m2[5]:.2f} | {m2[0]}/{m2[1]}/{m2[2]} |",
        "\n结束确认页会持续产生自然标签。n=1，不要写成普遍结论。\n",
    ]
    return "\n".join(lines)


def e5_quiz(conn, cfg) -> str:
    rows = conn.execute("SELECT verify_json FROM quizzes").fetchall()
    n = len(rows)
    kept = 0
    for row in rows:
        try:
            data = json.loads(row["verify_json"] or "{}")
        except json.JSONDecodeError:
            data = {}
        items = data.get("items") if isinstance(data, dict) else None
        if items:
            kept += len(items)
        elif data:
            kept += 1
    labels = _labels(conn, "e5")
    lines = [
        "# E5 理解题质量\n",
        f"已生成测验 {n} 份；校验后保留的理解题约 {kept} 道。人工标注 {len(labels)} 条。",
        "\n## 基线对比\n",
        "| 方案 | 说明 |",
        "|---|---|",
        "| 关闭校验 A/B | mock 模式下占位答案会把题判成「可猜」，因此 mock 跳过 A/B |",
        "| 开启校验 A/B（真实 Key） | 证据句必须能答对；不看原文答对则丢弃 |",
        "\n标注 30 道生成题：能否从原文作答、答案是否唯一、不看原文能否猜中。\n",
    ]
    return "\n".join(lines)


def e6_structure(conn, cfg) -> str:
    samples = load_samples("e6") or [
        {"sentence": "The model can reach the paper."},
        {"sentence": "Agents start simple and add tools later."},
    ]
    ok = 0
    n = 0
    lines = ["# E6 L2 结构\n", "| 句子 | 逐字一致 |", "|---|---|"]
    for item in samples:
        s = item.get("sentence") or ""
        if not s:
            continue
        n += 1
        out = explain_structure(conn, cfg, s)
        hit = bool(out.get("chunks") and chunks_ok(s, out["chunks"]))
        ok += int(hit)
        lines.append(f"| {s} | {hit} |")
    lines += [
        "\n## 基线对比\n",
        "| 方案 | 逐字一致率 | 人工有用度 |",
        "|---|---|---|",
        f"| 本方案（chunk 必须是原句子串） | {ok}/{n} | 在标注页打 1–3 分 |",
        "\n不满足则重试 1 次，仍失败只显示主干。\n",
    ]
    return "\n".join(lines)
