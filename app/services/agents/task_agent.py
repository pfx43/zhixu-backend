"""任务 Agent：看见目标与学情后从候选人里布置今日任务。

可以少派、可以 0 条。失败才走规则兜底（ensure 里处理）。
pytest 期间不跑模型，避免单测打到真实 LLM。
"""
from __future__ import annotations

import logging
import os

from tina import Agent

from app.core.config import LLM_MAX_TOOL_LOOP
from app.services.llm.llm_pool import llm_pool
from app.services.llm.reasoning_roundtrip import attach_reasoning_roundtrip
from app.services.tasks.candidates import collect_task_candidates, task_agent_context
from app.services.tools.task_assign_tools import TaskAssignTools
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def task_agent_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("ZHIXU_TASK_AGENT", "1").strip().lower() in ("0", "false", "off"):
        return False
    return llm_pool.instance_count > 0


def _section(title: str, lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "- （无）"
    return f"## {title}\n{body}"


def render_task_agent_prompt(ctx: dict, candidates: list) -> str:
    base = load_prompt("task_agent")
    blocks = [base]

    if ctx.get("is_refill"):
        blocks.append(
            "## 这是做完后再评估\n"
            "用户已经完成今天目前布置的全部任务。你可以再派一轮，"
            "也可以认为今天够了、**一条都不要派**。\n"
            "- 不要把刚做完的同一件事再派一遍，除非名单里仍有明显缺口\n"
            "- 命中收工信号时，默认 0 条"
        )
        signals = ctx.get("stop_signals") or []
        blocks.append(
            _section("收工信号", [f"- {s}" for s in signals] if signals else [])
        )
        done = ctx.get("today_done") or []
        blocks.append(
            _section(
                "今天已经完成",
                [
                    f"- [{t.get('kind')}] {t.get('title')} — {t.get('reason')}"
                    for t in done
                ]
                if done
                else [],
            )
        )
    else:
        blocks.append(
            "## 怎么设计第一轮\n"
            "- 没有书：只派上传\n"
            "- 有书缺页没题：按目标和精力选出题页数（页码已在候选人里）\n"
            "- 有未做/不会/错题：用检索选题或选 quiz 候选人，对准目标薄弱点\n"
            "- 今天已经有未完成任务时不要再加\n"
            "- 完成率低就少派、量轻；目标紧、缺口大、最近完成得好，可以派重一些\n"
            "- 资料和目标对不上（科目/用途明显无关）：宁可 0 条或只派上传，不要硬派出题"
        )

    goal = ctx.get("goal_text") or "还没有目标"
    attrs = ctx.get("goal_attributes") or "未设"
    until = ctx.get("valid_until") or "未设"
    rate = ctx.get("completion_rate_7d")
    rate_s = f"，完成率 {rate}" if rate is not None else ""
    pending = "；".join(ctx.get("pending_titles") or []) or "无"
    blocks.append(
        "## 当前档案\n"
        f"- 目标：{goal}\n"
        f"- 目标属性：{attrs}\n"
        f"- 有效期：{until}\n"
        f"- 今天：{ctx.get('today')}\n"
        f"- 近 7 天：派 {ctx.get('assigned_7d')} / 完成 {ctx.get('completed_7d')}{rate_s}\n"
        f"- 今日：已派 {ctx.get('today_assigned')} 条，完成 {ctx.get('today_completed')}，"
        f"未完成 {ctx.get('pending_count')}（{pending}）"
    )

    weak = ctx.get("weak_tags") or []
    blocks.append(
        _section(
            "薄弱标签",
            [
                f"- {t['tag']} 正确率 {t['accuracy_pct']}%（错 {t['wrong']} / 作答 {t['attempts']}）"
                for t in weak
            ]
            if weak
            else [],
        )
    )

    books = ctx.get("books") or []
    book_lines = []
    for b in books:
        chs = b.get("chapters") or []
        ch_s = ""
        if chs:
            bits = [
                f"{c['title']}({c['pages_with_questions']}/{c['page_count']}页有题)"
                for c in chs[:8]
            ]
            ch_s = " 章：" + "、".join(bits)
        book_lines.append(
            f"- 《{b['name']}》（id={b['document_id']}）页={b['pages']} "
            f"已出题页={b['pages_with_questions']} 缺页={b['missing_pages']} "
            f"题={b['question_count']} 未做={b['undone']} 不会={b['unknown']} "
            f"错={b['wrong']} 对={b['correct']}{ch_s}"
        )
    blocks.append(_section("资料学情", book_lines if book_lines else []))

    hist = ctx.get("history") or []
    hist_lines = []
    for h in hist:
        titles = "、".join(h.get("titles") or [])
        extra = f"｜{titles}" if titles else ""
        hist_lines.append(
            f"- {h['date']} 派{h['assigned']} 完成{h['completed']} 未完成{h['pending']}{extra}"
        )
    blocks.append(_section("近两周任务", hist_lines if hist_lines else []))

    cand_lines = [
        f"- id=`{c['id']}` type={c['task_type']} 可派 {c.get('unit')} "
        f"1～{c.get('max_quantity')}（不填则 {c.get('default_quantity')}）缺口：{c.get('gap')}"
        for c in candidates
    ]
    blocks.append(_section("候选人", cand_lines if cand_lines else []))
    blocks.append("按你的判断派完就停。派完不用再说话给用户看。可以 0 条。")
    return "\n\n".join(blocks)


async def run_task_agent(db, user_id: int, *, is_refill: bool = False) -> int:
    candidates = collect_task_candidates(db, user_id)
    ctx = task_agent_context(db, user_id, is_refill=is_refill)
    if not candidates and not is_refill:
        return 0

    llm = llm_pool.acquire()
    if llm is None:
        raise RuntimeError("task agent: llm pool empty")

    tools = TaskAssignTools(user_id, candidates, db)
    prompt = render_task_agent_prompt(ctx, candidates)
    agent = Agent(
        llm=llm,
        tools=tools.get_tools(),
        system_prompt=prompt,
        max_tool_loop=min(16, LLM_MAX_TOOL_LOOP),
        name=f"task_{user_id}",
    )
    attach_reasoning_roundtrip(agent)
    if is_refill:
        user = (
            "用户已经做完今天目前所有任务。根据已完成任务、目标和学情决定要不要再派。"
            "不要为凑数而派。今天已经够了就一条都不要派。"
            "可用 assign_task 或 search_book_questions + assign_quiz_task。"
        )
    else:
        user = (
            "根据目标和学情设计今天的任务。条数、每条做多少都由你决定。"
            "可以一条都不派。刷题务必带具体 question_ids。"
        )
    try:
        async for _chunk in agent.apredict(user, temperature=0.3):
            pass
    except Exception:
        logger.warning("任务 Agent 推理失败 user=%s", user_id, exc_info=True)
        raise
    return len(tools.assigned)
