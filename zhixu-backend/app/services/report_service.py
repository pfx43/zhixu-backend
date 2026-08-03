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
from app.services import analytics_service
from app.services.llm_runner import llm_predict_no_stream

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """你是知拾学习分析助手。根据用户的学习统计数据，生成一份清晰、可执行的 Markdown 学习报告。
报告结构建议：
1. ## 学习概览
2. ## 薄弱知识点（按 tag）
3. ## 题型表现
4. ## 建议与下一步
使用中文，语气鼓励但具体；列出优先复习的 tag 名称，便于后续针对训练。"""

_llm_instance = None


def _get_llm():
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    try:
        from app.utils.tina_loader import tina_env_path
        from tina.llm import BaseAPI

        _llm_instance = BaseAPI(env_path=tina_env_path())
        return _llm_instance
    except Exception:
        logger.warning("Tina LLM 不可用，将使用模板报告", exc_info=True)
        return None


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


def generate_learning_report(
    db: Session, user_id: int
) -> LearningReportGenerateOut:
    stats_text = _build_stats_payload(db, user_id)
    llm = _get_llm()
    content_md: str

    if llm:
        try:
            resp = llm_predict_no_stream(
                llm,
                input_text=f"请根据以下学习数据生成 Markdown 学习报告：\n\n{stats_text}",
                sys_prompt=REPORT_SYSTEM_PROMPT,
                temperature=0.4,
            )
            content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
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
