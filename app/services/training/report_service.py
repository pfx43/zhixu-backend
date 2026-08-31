"""学习报告生成 — 基于 tag 统计与 LLM"""
import json
import logging
from datetime import date
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import note as note_crud
from app.schemas.report import LearningReportGenerateOut, ReportOut
from app.services.llm.llm_pool import llm_pool
from app.services.llm.reasoning_roundtrip import attach_reasoning_roundtrip
from app.services.training import analytics_service
from app.utils.prompt_loader import load_prompt
from tina import Agent

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = load_prompt("report_analysis")


def _agent_text(result) -> str:
    if isinstance(result, dict):
        return result.get("content") or ""
    return getattr(result, "content", None) or ""


def _template_report(stats_text: str) -> str:
    today = date.today().isoformat()
    return f"""# 学习报告 {today}

## 学习概览

以下为系统自动汇总的数据摘要：

{stats_text}

## 说明

当前 LLM 服务不可用，以上为原始统计数据。请稍后重新生成以获取 AI 分析与建议。
"""


def _build_stats_payload(db: Session, user_id: int) -> str:
    learning = analytics_service.get_learning_stats(db, user_id)
    tag_stats = analytics_service.get_tag_stats(db, user_id)

    docs = learning.documents
    qs = learning.questions
    lines = [
        f"- 知识库文档：{docs.total}（学习区 {docs.study_zone}）",
        f"- 题库规模：{qs.total} 题，已作答 {qs.answered} 题",
        f"- 正确率：{qs.accuracy_rate}%" if qs.accuracy_rate is not None else "- 正确率：暂无",
        f"- 答对/答错/不会：{qs.correct}/{qs.wrong}/{qs.unknown}",
        "",
        "### 按 Tag 统计",
    ]
    for item in tag_stats.by_tag[:15]:
        acc = f"{item.accuracy_rate}%" if item.accuracy_rate is not None else "—"
        lines.append(
            f"- **{item.tag}**：对 {item.correct_count} / 错 {item.wrong_count} / 不会 {item.unknown_count}（正确率 {acc}）"
        )
    lines.append("")
    lines.append("### 按题型统计")
    for item in tag_stats.by_question_type:
        acc = f"{item.accuracy_rate}%" if item.accuracy_rate is not None else "—"
        lines.append(
            f"- **{item.question_type}**：对 {item.correct_count} / 错 {item.wrong_count}（正确率 {acc}）"
        )
    if learning.document_progress:
        lines.append("")
        lines.append("### 文档进度")
        for dp in learning.document_progress[:8]:
            acc = f"{dp.accuracy_rate}%" if dp.accuracy_rate is not None else "—"
            lines.append(
                f"- {dp.document_name}：{dp.answered_count}/{dp.question_total} 题，正确率 {acc}"
            )
    return "\n".join(lines)


async def generate_learning_report(
    db: Session, user_id: int, token: str = ""
) -> LearningReportGenerateOut:
    stats_text = _build_stats_payload(db, user_id)
    llm = llm_pool.acquire()
    content_md: str

    if llm:
        try:
            if token:
                llm.set_token(token)
            agent = Agent(
                llm=llm,
                tools=None,
                system_prompt=REPORT_SYSTEM_PROMPT,
                name="learning_report",
            )
            attach_reasoning_roundtrip(agent)
            result = await agent.apredict_no_stream(
                instruction=f"请根据以下学习数据生成 Markdown 学习报告：\n\n{stats_text}",
                temperature=0.4,
            )
            content = _agent_text(result)
            content_md = (content or "").strip() or _template_report(stats_text)
        except Exception:
            logger.warning("LLM 报告生成失败，回退模板", exc_info=True)
            content_md = _template_report(stats_text)
    else:
        content_md = _template_report(stats_text)

    today = date.today().isoformat()
    title = f"学习报告 {today}"

    life_coll = kb_crud.get_default_life_collection(db, user_id)
    collection_id = life_coll.id if life_coll else None

    note = note_crud.create_note(
        db,
        user_id=user_id,
        title=title,
        content_md=content_md,
        collection_id=collection_id,
        note_type="report",
    )
    db.flush()

    return LearningReportGenerateOut(
        report=ReportOut.model_validate(note),
        saved_to_notes=True,
    )


def list_reports(db: Session, user_id: int, limit: int = 30):
    from app.schemas.report import ReportListOut

    rows = note_crud.list_notes(db, user_id, note_type="report", limit=limit)
    reports = [ReportOut.model_validate(r) for r in rows]
    return ReportListOut(reports=reports, total=len(reports))


def get_latest_report(db: Session, user_id: int) -> ReportOut:
    note = note_crud.get_latest_note(db, user_id, note_type="report")
    if not note:
        raise HTTPException(status_code=404, detail="暂无学习报告，请先生成")
    return ReportOut.model_validate(note)


def get_report_by_id(db: Session, user_id: int, report_id: str) -> ReportOut:
    note = note_crud.get_note_by_id(db, user_id, report_id)
    if not note or note.note_type != "report":
        raise HTTPException(status_code=404, detail="学习报告不存在")
    return ReportOut.model_validate(note)
