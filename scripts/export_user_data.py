"""导出指定用户的聊天记录、题目，并生成规范的统计报告（含 DeepSeek 费用）。

用法：
    python scripts/export_user_data.py --user-id 19
    python scripts/export_user_data.py --email test@test.com

输出（exports/）：
    chat_u<id>_<ts>.csv       聊天记录（每条消息一行）
    questions_u<id>_<ts>.csv  题目明细
    report_u<id>_<ts>.md      统计报告（用量 / 字数 / 题目 / 刷题）

费用口径（按用户要求）：高峰价与空闲价各自算一次，再取平均；输入默认按
“缓存未命中”计（库里没有 cache 命中数据），另给出“全部缓存命中”的下界。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text

from app.core.database import SessionLocal

EXPORT_DIR = REPO_ROOT / "exports"
HISTORY_DIR = REPO_ROOT / "storage"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

QUESTION_TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "short_answer": "简答题",
    "application": "应用题",
    "fill_blank": "填空题",
    "true_false": "判断题",
}

# 单价：元 / 百万 tokens；off=空闲时段，peak=高峰时段
PRICING = {
    "deepseek-flash": {
        "input_cache_hit": {"off": 0.02, "peak": 0.04},
        "input_cache_miss": {"off": 1.0, "peak": 2.0},
        "output": {"off": 4.0, "peak": 8.0},
    },
    "deepseek-v4-pro": {
        "input_cache_hit": {"off": 0.15, "peak": 0.30},
        "input_cache_miss": {"off": 4.5, "peak": 9.0},
        "output": {"off": 13.5, "peak": 27.0},
    },
}


# ── 基础工具 ──────────────────────────────────────────────


def _avg(prices: dict) -> float:
    """高峰/空闲各算一次后对半。"""
    return round((prices["off"] + prices["peak"]) / 2, 6)


def _cost(model: str, prompt: int, completion: int, cache: str) -> dict:
    p = PRICING[model]
    in_price = _avg(p[cache])
    out_price = _avg(p["output"])
    in_cost = prompt / 1_000_000 * in_price
    out_cost = completion / 1_000_000 * out_price
    return {
        "model": model,
        "input_price": in_price,
        "output_price": out_price,
        "input_cost": in_cost,
        "output_cost": out_cost,
        "total_cost": in_cost + out_cost,
    }


def _len(text_: str | None) -> int:
    return len(text_ or "")


def _cjk(text_: str | None) -> int:
    return len(_CJK_RE.findall(text_ or ""))


def _pct(part: int | float, whole: int | float) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "-"


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val] if isinstance(val, list) else []
    except Exception:
        return []


def _cost_section(prompt: int, completion: int) -> str:
    lines = [
        "| 模型 | 输入单价(元/M) | 输出单价(元/M) | 输入费用 | 输出费用 | 合计 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in PRICING:
        c = _cost(model, prompt, completion, "input_cache_miss")
        lines.append(
            f"| `{model}` | {c['input_price']} | {c['output_price']} | "
            f"{c['input_cost']:.4f} 元 | {c['output_cost']:.4f} 元 | **{c['total_cost']:.4f} 元** |"
        )
    lines.append("")
    lines.append("> 输入默认按**缓存未命中**（保守上界）。若输入全部**命中缓存**：")
    for model in PRICING:
        c = _cost(model, prompt, completion, "input_cache_hit")
        lines.append(
            f"> - `{model}`：输入 {c['input_cost']:.4f} + 输出 {c['output_cost']:.4f} "
            f"= **{c['total_cost']:.4f} 元**"
        )
    return "\n".join(lines)


# ── 查询 ──────────────────────────────────────────────────


def _resolve_user(db, user_id: int | None, email: str | None):
    if user_id is not None:
        row = db.execute(
            text("SELECT id, email, nickname FROM users WHERE id=:u"), {"u": user_id}
        ).fetchone()
    else:
        row = db.execute(
            text("SELECT id, email, nickname FROM users WHERE email=:e"), {"e": email}
        ).fetchone()
    if not row:
        raise SystemExit("找不到用户")
    return row[0], row[1], row[2]


def _usage_all(db, user_id: int) -> dict:
    t = db.execute(
        text(
            "SELECT coalesce(sum(prompt_tokens),0), coalesce(sum(completion_tokens),0), "
            "coalesce(sum(total_tokens),0) FROM usage_token WHERE user_id=:u"
        ),
        {"u": user_id},
    ).fetchone()
    calls = db.execute(
        text("SELECT coalesce(sum(api_calls),0) FROM usage_daily WHERE user_id=:u"),
        {"u": user_id},
    ).scalar()
    return {"prompt": int(t[0]), "completion": int(t[1]), "total": int(t[2]), "api_calls": int(calls)}


def _usage_month(db, user_id: int, yyyymm: str) -> dict:
    row = db.execute(
        text(
            "SELECT prompt_tokens, completion_tokens, total_tokens FROM usage_token "
            "WHERE user_id=:u AND yyyymm=:ym"
        ),
        {"u": user_id, "ym": yyyymm},
    ).fetchone()
    if not row:
        return {"prompt": 0, "completion": 0, "total": 0}
    return {"prompt": int(row[0]), "completion": int(row[1]), "total": int(row[2])}


def _daily_calls(db, user_id: int, date: str) -> int:
    row = db.execute(
        text("SELECT coalesce(api_calls,0) FROM usage_daily WHERE user_id=:u AND date=:d"),
        {"u": user_id, "d": date},
    ).fetchone()
    return int(row[0]) if row else 0


def _load_b0_session(user_id: int) -> dict | None:
    snaps = sorted(EXPORT_DIR.glob("usage_snapshot_B0_*.json"))
    if not snaps:
        return None
    try:
        b0 = json.loads(snaps[-1].read_text(encoding="utf-8"))
    except Exception:
        return None
    return b0 if b0.get("user_id") == user_id else None


# ── 导出 CSV ──────────────────────────────────────────────


def export_chat(user_id: int, ts: str):
    path = EXPORT_DIR / f"chat_u{user_id}_{ts}.csv"
    sessions, total_messages = [], 0
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["session_id", "session_title", "session_created_at", "role", "created_at", "content"]
        )
        hist_dir = HISTORY_DIR / str(user_id) / "history"
        files = sorted(hist_dir.glob("*.json")) if hist_dir.exists() else []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            meta = data.get("meta") or {}
            messages = data.get("messages") or []
            user_chars = sum(_len(m.get("content")) for m in messages if m.get("role") == "user")
            asst_chars = sum(_len(m.get("content")) for m in messages if m.get("role") == "assistant")
            user_cjk = sum(_cjk(m.get("content")) for m in messages if m.get("role") == "user")
            asst_cjk = sum(_cjk(m.get("content")) for m in messages if m.get("role") == "assistant")
            sessions.append(
                {
                    "session_id": f.stem,
                    "title": meta.get("title", "会话"),
                    "created_at": meta.get("created_at", ""),
                    "message_count": len(messages),
                    "user_chars": user_chars,
                    "asst_chars": asst_chars,
                    "total_chars": user_chars + asst_chars,
                    "cjk_chars": user_cjk + asst_cjk,
                }
            )
            for m in messages:
                writer.writerow(
                    [
                        f.stem,
                        meta.get("title", "会话"),
                        meta.get("created_at", ""),
                        m.get("role", ""),
                        m.get("created_at", ""),
                        m.get("content", ""),
                    ]
                )
                total_messages += 1
    return path, total_messages, sessions


def export_questions(user_id: int, ts: str) -> tuple[Path, int]:
    sql = """
        SELECT uqr.question_id, q.stem, q.question_type, q.options, q.answer,
               q.explanation, q.tags, q.source_type, d.display_name AS document_name,
               p.page_number, uqr.added_at
        FROM user_question_refs uqr
        JOIN global_questions q ON q.id = uqr.question_id
        LEFT JOIN documents d ON d.id = uqr.document_id
        LEFT JOIN question_provenance p ON p.question_id = q.id
        WHERE uqr.user_id = :uid
        ORDER BY uqr.added_at
    """
    path = EXPORT_DIR / f"questions_u{user_id}_{ts}.csv"
    with SessionLocal() as db:
        rows = list(db.execute(text(sql), {"uid": user_id}))
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "question_id", "stem", "question_type", "options", "answer",
                "explanation", "tags", "source_type", "document_name", "page_number", "added_at",
            ]
        )
        writer.writerows(rows)
    return path, len(rows)


# ── 统计 ──────────────────────────────────────────────────


def collect_question_stats(user_id: int) -> dict:
    with SessionLocal() as db:
        qrows = list(
            db.execute(
                text(
                    "SELECT q.stem, q.question_type, q.answer, q.explanation, q.tags, "
                    "q.source_type, d.display_name "
                    "FROM user_question_refs uqr "
                    "JOIN global_questions q ON q.id = uqr.question_id "
                    "LEFT JOIN documents d ON d.id = uqr.document_id "
                    "WHERE uqr.user_id = :uid"
                ),
                {"uid": user_id},
            )
        )
        jobs = list(
            db.execute(
                text(
                    "SELECT j.id, j.status, count(p.id), "
                    "coalesce(sum(p.questions_created),0), coalesce(sum(p.questions_reused),0), "
                    "j.created_at, j.finished_at "
                    "FROM qgen_jobs j LEFT JOIN qgen_job_pages p ON p.job_id = j.id "
                    "WHERE j.user_id = :uid GROUP BY j.id ORDER BY j.created_at"
                ),
                {"uid": user_id},
            )
        )
        ans = list(
            db.execute(
                text(
                    "SELECT status, user_answer, time_spent_seconds FROM quiz_answers "
                    "WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
        )
        sessions = db.execute(
            text("SELECT count(*) FROM quiz_sessions WHERE user_id=:u"), {"u": user_id}
        ).scalar()
        session_questions = db.execute(
            text(
                "SELECT count(*) FROM quiz_session_questions qs "
                "JOIN quiz_sessions s ON s.id = qs.session_id WHERE s.user_id=:u"
            ),
            {"u": user_id},
        ).scalar()

    tags = Counter()
    type_counter = Counter()
    source_counter = Counter()
    doc_counter = Counter()
    stem_chars = ans_chars = exp_chars = 0
    stem_cjk = ans_cjk = exp_cjk = 0
    for stem, qtype, answer, explanation, raw_tags, source, doc in qrows:
        type_counter[qtype or "unknown"] += 1
        source_counter[source or "unknown"] += 1
        doc_counter[doc or "未知文档"] += 1
        stem_chars += _len(stem); stem_cjk += _cjk(stem)
        ans_chars += _len(answer); ans_cjk += _cjk(answer)
        exp_chars += _len(explanation); exp_cjk += _cjk(explanation)
        for t in _parse_tags(raw_tags):
            tags[t] += 1

    q_count = len(qrows)
    return {
        "count": q_count,
        "type_counter": type_counter,
        "source_counter": source_counter,
        "doc_counter": doc_counter,
        "tags": tags,
        "stem_chars": stem_chars, "stem_cjk": stem_cjk,
        "ans_chars": ans_chars, "ans_cjk": ans_cjk,
        "exp_chars": exp_chars, "exp_cjk": exp_cjk,
        "jobs": jobs,
        "answers": ans,
        "sessions": int(sessions or 0),
        "session_questions": int(session_questions or 0),
    }


def collect_chat_totals(sessions: list[dict]) -> dict:
    return {
        "sessions": len(sessions),
        "messages": sum(s["message_count"] for s in sessions),
        "user_chars": sum(s["user_chars"] for s in sessions),
        "asst_chars": sum(s["asst_chars"] for s in sessions),
        "total_chars": sum(s["total_chars"] for s in sessions),
        "cjk_chars": sum(s["cjk_chars"] for s in sessions),
    }


# ── 报告 ──────────────────────────────────────────────────


def build_report(
    user_id: int, email: str, nickname: str, ts: str,
    chat_path: Path, chat_sessions: list[dict],
    q_path: Path, q_stats: dict,
) -> Path:
    now_utc = datetime.now(timezone.utc)
    yyyymm = now_utc.astimezone().strftime("%Y%m")
    today = now_utc.astimezone().date().isoformat()

    with SessionLocal() as db:
        allu = _usage_all(db, user_id)
        cur_month = _usage_month(db, user_id, yyyymm)
        cur_calls = _daily_calls(db, user_id, today)
        months = [
            (r[0], {"prompt": int(r[1]), "completion": int(r[2]), "total": int(r[3])})
            for r in db.execute(
                text(
                    "SELECT yyyymm, prompt_tokens, completion_tokens, total_tokens "
                    "FROM usage_token WHERE user_id=:u ORDER BY yyyymm"
                ),
                {"u": user_id},
            )
        ]

    chat = collect_chat_totals(chat_sessions)
    b0 = _load_b0_session(user_id)
    session_usage = None
    if b0 and b0.get("yyyymm") == yyyymm:
        session_usage = {
            "prompt": cur_month["prompt"] - int(b0.get("prompt_tokens", 0)),
            "completion": cur_month["completion"] - int(b0.get("completion_tokens", 0)),
            "total": cur_month["total"] - int(b0.get("total_tokens", 0)),
            "api_calls": cur_calls - int(b0.get("api_calls_today", 0))
            if b0.get("date") == today else cur_calls,
            "since": b0.get("captured_at_local", ""),
        }

    answers = q_stats["answers"]
    correct = sum(1 for a in answers if a[0] == "correct")
    wrong = sum(1 for a in answers if a[0] == "wrong")

    L: list[str] = []
    add = L.append

    # 标题
    add(f"# test 用户数据与用量统计报告")
    add("")
    add(f"| 项 | 值 |")
    add(f"|---|---|")
    add(f"| 用户 | `{email}`（{nickname}） |")
    add(f"| user_id | {user_id} |")
    add(f"| 生成时间 | {now_utc.astimezone().isoformat(timespec='seconds')} |")
    add(f"| 计费模型 | `deepseek-flash`（默认），并给出 `deepseek-v4-pro` 对照 |")
    add(f"| 计费口径 | 高峰 / 空闲价各算一次取平均；输入按缓存未命中 |")
    add("")

    # 一、总览
    add("## 一、总览")
    add("")
    add("| 分类 | 指标 | 数值 |")
    add("|---|---|---:|")
    add(f"| 聊天 | 会话数 | {chat['sessions']} |")
    add(f"| 聊天 | 消息数 | {chat['messages']} |")
    add(f"| 聊天 | 总字符数 | {chat['total_chars']:,} |")
    add(f"| 聊天 | 中文字符数 | {chat['cjk_chars']:,} |")
    add(f"| 题目 | 题目总数 | {q_stats['count']} |")
    add(f"| 题目 | 题干/答案/解析总字符 | {q_stats['stem_chars'] + q_stats['ans_chars'] + q_stats['exp_chars']:,} |")
    add(f"| 出题 | 出题任务数 | {len(q_stats['jobs'])} |")
    add(f"| 出题 | 出题页数 | {sum(int(j[2]) for j in q_stats['jobs'])} |")
    add(f"| 出题 | 新建题目数 | {sum(int(j[3]) for j in q_stats['jobs'])} |")
    add(f"| 刷题 | 刷题会话数 | {q_stats['sessions']} |")
    add(f"| 刷题 | 作答次数 | {len(answers)} |")
    add(f"| 刷题 | 正确 / 错误 | {correct} / {wrong} |")
    add(f"| 刷题 | 正确率 | {_pct(correct, len(answers))} |")
    add(f"| 用量 | 累计 API 调用 | {allu['api_calls']:,} |")
    add(f"| 用量 | 累计 token | {allu['total']:,} |")
    flash_all = _cost("deepseek-flash", allu["prompt"], allu["completion"], "input_cache_miss")
    add(f"| 费用 | 累计（flash，未命中） | {flash_all['total_cost']:.4f} 元 |")
    add("")

    # 二、用量与费用
    add("## 二、用量与费用")
    add("")
    add("### 2.1 Token 用量")
    add("")
    add("| 口径 | prompt | completion | total | API 调用 |")
    add("|---|---:|---:|---:|---:|")
    for ym, u in months:
        add(f"| {ym} | {u['prompt']:,} | {u['completion']:,} | {u['total']:,} | - |")
    add(f"| **全部** | **{allu['prompt']:,}** | **{allu['completion']:,}** | **{allu['total']:,}** | **{allu['api_calls']:,}** |")
    if session_usage:
        add(
            f"| 本次会话(B0 后) | {session_usage['prompt']:,} | {session_usage['completion']:,} "
            f"| {session_usage['total']:,} | {session_usage['api_calls']:,} |"
        )
    add("")
    if session_usage:
        add(f"> B0 快照时间：{session_usage['since']}（快照文件见第五节）")
        add("")

    add("### 2.2 费用 — 全部历史")
    add("")
    add(_cost_section(allu["prompt"], allu["completion"]))
    add("")
    if session_usage:
        add("### 2.3 费用 — 本次会话（出题 + 对话，B0 后增量）")
        add("")
        add(_cost_section(session_usage["prompt"], session_usage["completion"]))
        add("")

    # 三、字数统计
    add("## 三、字数统计")
    add("")
    add("### 3.1 聊天字数")
    add("")
    add("| 会话 | 标题 | 消息数 | 用户字符 | 助手字符 | 总字符 | 中文字符 |")
    add("|---|---|---:|---:|---:|---:|---:|")
    for s in chat_sessions:
        add(
            f"| {s['session_id'][:8]} | {s['title']} | {s['message_count']} | "
            f"{s['user_chars']:,} | {s['asst_chars']:,} | {s['total_chars']:,} | {s['cjk_chars']:,} |"
        )
    add(
        f"| **合计** | - | **{chat['messages']}** | **{chat['user_chars']:,}** | "
        f"**{chat['asst_chars']:,}** | **{chat['total_chars']:,}** | **{chat['cjk_chars']:,}** |"
    )
    add("")
    avg_msg = chat["total_chars"] // chat["messages"] if chat["messages"] else 0
    add(f"- 平均每条消息：{avg_msg:,} 字符")
    add(f"- 中文占比：{_pct(chat['cjk_chars'], chat['total_chars'])}")
    add("")

    add("### 3.2 题目字数")
    add("")
    qn = q_stats["count"] or 1
    add("| 字段 | 总字符 | 中文字符 | 平均字符/题 |")
    add("|---|---:|---:|---:|")
    add(f"| 题干 | {q_stats['stem_chars']:,} | {q_stats['stem_cjk']:,} | {q_stats['stem_chars'] / qn:.1f} |")
    add(f"| 答案 | {q_stats['ans_chars']:,} | {q_stats['ans_cjk']:,} | {q_stats['ans_chars'] / qn:.1f} |")
    add(f"| 解析 | {q_stats['exp_chars']:,} | {q_stats['exp_cjk']:,} | {q_stats['exp_chars'] / qn:.1f} |")
    add(
        f"| **合计** | **{q_stats['stem_chars'] + q_stats['ans_chars'] + q_stats['exp_chars']:,}** | "
        f"**{q_stats['stem_cjk'] + q_stats['ans_cjk'] + q_stats['exp_cjk']:,}** | "
        f"**{(q_stats['stem_chars'] + q_stats['ans_chars'] + q_stats['exp_chars']) / qn:.1f}** |"
    )
    add("")

    # 四、题目统计
    add("## 四、题目统计")
    add("")
    add("### 4.1 题型分布")
    add("")
    add("| 题型 | 数量 | 占比 |")
    add("|---|---:|---:|")
    for qtype, cnt in q_stats["type_counter"].most_common():
        label = QUESTION_TYPE_LABELS.get(qtype, qtype)
        add(f"| {label} | {cnt} | {_pct(cnt, q_stats['count'])} |")
    add(f"| **合计** | **{q_stats['count']}** | **100.0%** |")
    add("")

    add("### 4.2 来源与文档")
    add("")
    add("| 维度 | 值 | 数量 |")
    add("|---|---|---:|")
    for src, cnt in q_stats["source_counter"].most_common():
        add(f"| 来源 | {src} | {cnt} |")
    for doc, cnt in q_stats["doc_counter"].most_common():
        add(f"| 文档 | {doc} | {cnt} |")
    add("")

    add("### 4.3 知识点标签 Top 10")
    add("")
    add("| 排名 | 标签 | 出现题数 |")
    add("|---:|---|---:|")
    for i, (tag, cnt) in enumerate(q_stats["tags"].most_common(10), 1):
        add(f"| {i} | {tag} | {cnt} |")
    add(f"\n> 共 {len(q_stats['tags'])} 个不同标签。")
    add("")

    add("### 4.4 出题任务")
    add("")
    add("| 任务 | 状态 | 页数 | 新建 | 复用 | 创建时间 | 完成时间 |")
    add("|---|---|---:|---:|---:|---|---|")
    for jid, status, pages, created, reused, t0, t1 in q_stats["jobs"]:
        add(
            f"| {jid[:8]} | {status} | {int(pages)} | {int(created)} | {int(reused)} | "
            f"{t0.strftime('%Y-%m-%d %H:%M') if t0 else '-'} | "
            f"{t1.strftime('%Y-%m-%d %H:%M') if t1 else '-'} |"
        )
    add("")

    add("### 4.5 刷题与作答")
    add("")
    add("| 指标 | 数值 |")
    add("|---|---:|")
    add(f"| 刷题会话数 | {q_stats['sessions']} |")
    add(f"| 会话内题目数 | {q_stats['session_questions']} |")
    add(f"| 作答次数 | {len(answers)} |")
    add(f"| 正确 | {correct} |")
    add(f"| 错误 | {wrong} |")
    add(f"| 正确率 | {_pct(correct, len(answers))} |")
    add("")

    # 五、附件
    add("## 五、导出文件")
    add("")
    add("| 文件 | 说明 |")
    add("|---|---|")
    add(f"| `{chat_path.name}` | 聊天记录明细（每条消息一行） |")
    add(f"| `{q_path.name}` | 题目明细 |")
    add(f"| `report_u{user_id}_{ts}.md` | 本报告 |")
    add("")
    add("> 注：usage_token / usage_daily 为聚合表（无单次调用明细与时间戳），")
    add("> 出题与对话的 token 无法从库中分别拆出；“本次会话”为 B0 快照差值。")
    add("")

    path = EXPORT_DIR / f"report_u{user_id}_{ts}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="导出用户聊天/题目并生成统计报告")
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--email")
    args = parser.parse_args()

    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    with SessionLocal() as db:
        user_id, email, nickname = _resolve_user(db, args.user_id, args.email)

    chat_path, _, chat_sessions = export_chat(user_id, ts)
    q_path, _ = export_questions(user_id, ts)
    q_stats = collect_question_stats(user_id)
    report = build_report(user_id, email, nickname, ts, chat_path, chat_sessions, q_path, q_stats)
    for p in (chat_path, q_path, report):
        print(f"已导出: {p}")


if __name__ == "__main__":
    main()
