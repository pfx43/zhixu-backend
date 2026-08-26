"""今日任务服务（Issue #19）：查询 / 缺口生成（ensure）/ 完成检查器。

规则（程序定，模型不发明）：
- 缺口顺序：没书 → 上传；有书没题 → 按章出题；有题 → 刷题。
- 页码只来自目录（document_tocs）或入库分段页码（document_segments.page_start），
  禁止模型手填。
- 检查器只读任务自身的 payload / completion_rule 判定，不做语义判断：
  - upload：这次上传产生了一本「能解析的」新书（非 hash 去重、非解析失败）
  - generate_questions：payload 那些页上已经都有题（不看整本 status）
  - practice：任务范围内交够约定道数（含「不会」）
"""
import hashlib
import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import MAX_PAGES_PER_GEN
from app.crud import task as task_crud
from app.crud import toc as toc_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import kb as kb_crud
from app.models import (
    DailyTask,
    Document,
    DocumentSegment,
    Goal,
    UserQuestionRef,
)

logger = logging.getLogger(__name__)

# 任务类型常量
TYPE_UPLOAD = "upload"
TYPE_GENERATE = "generate_questions"
TYPE_PRACTICE = "practice"

# 当天任务上限（1~3 件）
_MAX_TASKS_PER_DAY = 3
# 刷题约定道数上限
_PRACTICE_COUNT_DEFAULT = 5


def today_local() -> date:
    """任务日期：服务器本地日期。"""
    return datetime.now().date()


def _active_goal_id(db: Session, user_id: int) -> Optional[int]:
    goal = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .first()
    )
    return goal.id if goal else None


def list_today(db: Session, user_id: int) -> List[DailyTask]:
    return task_crud.list_tasks(db, user_id, today_local())


# ── ensure：当天没有则按缺口生成，有未完成的先展示，不重复派 ──────

def ensure_today_tasks(db: Session, user_id: int) -> List[DailyTask]:
    task_date = today_local()
    pending = task_crud.list_pending_tasks(db, user_id, task_date)
    if pending:
        return pending

    generated = _generate_gap_tasks(db, user_id, task_date)
    if generated:
        db.commit()
    return generated


def _generate_gap_tasks(
    db: Session, user_id: int, task_date: date
) -> List[DailyTask]:
    goal_id = _active_goal_id(db, user_id)
    created: List[DailyTask] = []

    docs = _list_own_documents(db, user_id)
    doc_ids = [d.id for d in docs]
    doc_ids_with_questions = _document_ids_with_questions(db, user_id, doc_ids)

    # 1) 没书 → 上传
    if not doc_ids:
        task = task_crud.create_task(
            db,
            user_id=user_id,
            goal_id=goal_id,
            task_date=task_date,
            title="上传一本学习资料",
            reason="学习区还没有可用的书，先上传一本能解析的资料（PDF / Word / 图片等），之后出题和刷题都从它来。",
            task_type=TYPE_UPLOAD,
            payload={},
            completion_rule={"kind": "new_parsable_document"},
        )
        created.append(task)
        return created

    # 2) 有书没题 → 按章出题（页来自目录或入库分段页码）
    no_question_docs = [d for d in docs if d.id not in doc_ids_with_questions]
    target = _pick_document_with_pages(db, no_question_docs or docs)
    if target is not None:
        doc, pages = target
        if pages:
            task = task_crud.create_task(
                db,
                user_id=user_id,
                goal_id=goal_id,
                task_date=task_date,
                title=f"给《{doc.display_name}》的这几页出题",
                reason="有书还没题，先按页出题（每页独立进度），出完才能刷题。",
                task_type=TYPE_GENERATE,
                payload={
                    "document_id": doc.id,
                    "document_name": doc.display_name,
                    "page_numbers": pages,
                },
                completion_rule={
                    "kind": "pages_have_questions",
                    "document_id": doc.id,
                    "page_numbers": pages,
                },
            )
            created.append(task)

    # 3) 有题 → 刷题（任务范围内交够约定道数）
    if len(created) < _MAX_TASKS_PER_DAY and doc_ids_with_questions:
        practice_doc = _pick_document_for_practice(
            db, user_id, docs, doc_ids_with_questions
        )
        if practice_doc is not None:
            doc, count = practice_doc
            task = task_crud.create_task(
                db,
                user_id=user_id,
                goal_id=goal_id,
                task_date=task_date,
                title=f"刷《{doc.display_name}》的题",
                reason=f"有题了，交够 {count} 道就算完成（选「不会」也算，不用全对）。",
                task_type=TYPE_PRACTICE,
                payload={"document_id": doc.id, "document_name": doc.display_name, "count": count},
                completion_rule={
                    "kind": "practice_count",
                    "document_id": doc.id,
                    "count": count,
                },
            )
            created.append(task)

    return created


def _list_own_documents(db: Session, user_id: int) -> List[Document]:
    return db.query(Document).filter(Document.user_id == user_id).order_by(Document.created_at.desc()).all()


def _document_ids_with_questions(
    db: Session, user_id: int, doc_ids: List[str]
) -> set:
    if not doc_ids:
        return set()
    rows = (
        db.query(UserQuestionRef.document_id)
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.document_id.in_(doc_ids),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _pick_document_with_pages(
    db: Session, docs: List[Document]
) -> Optional[tuple]:
    """选一本「有可出页」的文档，返回 (doc, pages)。

    页优先来自目录（章 → 页范围），目录缺失时用入库分段页码
    （document_segments.page_start，程序提取，禁止模型手填）。
    """
    for doc in docs:
        pages = _pages_from_toc(db, doc)
        if not pages:
            pages = _pages_from_segments(db, doc.id)
        if pages:
            return doc, pages
    return None


def _pages_from_toc(db: Session, doc: Document) -> List[int]:
    entries = toc_crud.list_toc_for_document(db, doc.id)
    if not entries:
        return []
    pages: List[int] = []
    for entry in entries:
        for p in range(entry.page_start, entry.page_end + 1):
            if p not in pages:
                pages.append(p)
        if len(pages) >= MAX_PAGES_PER_GEN:
            break
    return pages[:MAX_PAGES_PER_GEN]


def _pages_from_segments(db: Session, document_id: str) -> List[int]:
    """入库分段页码（page_start~page_end 展开，一段可以跨页）。"""
    rows = (
        db.query(DocumentSegment.page_start, DocumentSegment.page_end)
        .filter(
            DocumentSegment.document_id == document_id,
            DocumentSegment.page_start.isnot(None),
        )
        .all()
    )
    pages: List[int] = []
    for ps, pe in rows:
        start = max(1, ps or 1)
        end = max(start, pe or start)
        for p in range(start, end + 1):
            if p not in pages:
                pages.append(p)
    return sorted(pages)[:MAX_PAGES_PER_GEN]


def _pick_document_for_practice(
    db: Session, user_id: int, docs: List[Document], doc_ids_with_questions: set
) -> Optional[tuple]:
    for doc in docs:
        if doc.id not in doc_ids_with_questions:
            continue
        total = _count_user_questions_for_document(db, user_id, doc.id)
        if total <= 0:
            continue
        count = min(total, _PRACTICE_COUNT_DEFAULT)
        return doc, count
    return None


def _count_user_questions_for_document(
    db: Session, user_id: int, document_id: str
) -> int:
    return (
        db.query(func.count(func.distinct(UserQuestionRef.question_id)))
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.document_id == document_id,
        )
        .scalar()
        or 0
    )


# ── 检查器：挂在成功路径后面，返回 completed_tasks ────────────────

def run_completion_checks(
    db: Session,
    user_id: int,
    event: str,
    ctx: Optional[dict] = None,
) -> List[dict]:
    """对当天 pending 任务跑一遍对应事件检查，翻转完成的并落库。

    返回 ``TaskCompletedOut`` 回执列表（Issue #5.X CompletionReceipt）：
    含 ``idempotency_key`` / ``source_action`` / ``before/after_status`` /
    ``evidence`` / ``completed_at``。空表示没有新完成的任务（前端不弹窗）。

    ``ctx`` 里可传 ``source_action``（默认取 event）+ ``evidence`` 字典，
    下传给各 _check_*，再写到 daily_tasks.evidence_json。
    """
    task_date = today_local()
    completed: List[dict] = []
    ctx = ctx or {}

    if event == "upload":
        completed = _check_upload(db, user_id, task_date, ctx)
    elif event == "questions_generated":
        completed = _check_pages_have_questions(db, user_id, task_date, ctx)
    elif event == "answer_submitted":
        completed = _check_practice(db, user_id, task_date, ctx)

    return completed


def _make_receipt(
    task: DailyTask,
    source_action: str,
    evidence: Optional[dict],
    before_status: str = "pending",
) -> dict:
    """生成 #5.X 完成回执：含幂等键 + 证据，供前端弹窗 + Evidence Impact 复用。"""
    completed_at = datetime.now()
    # 幂等键：同一用户 + 任务 + 来源动作 始终一致；前端用于去重弹窗
    payload = f"{task.user_id}:{task.id}:{source_action}".encode()
    idempotency_key = hashlib.sha256(payload).hexdigest()
    return {
        "id": task.id,
        "title": task.title,
        "idempotency_key": idempotency_key,
        "completed_at": completed_at,
        "source_action": source_action,
        "before_status": before_status,
        "after_status": "completed",
        "evidence": evidence or {},
    }


def _complete_tasks(
    db: Session,
    tasks: List[DailyTask],
    source_action: str,
    evidence_for_task: Optional[dict] = None,
) -> List[dict]:
    """标完成并写 evidence_json；返回 #5.X 回执列表。

    ``evidence_for_task``：按 task.id 给出每条任务的证据；或单个 dict 应用到所有。
    """
    if not tasks:
        return []
    receipts: List[dict] = []
    now = datetime.now()
    for t in tasks:
        if t.status == "completed":
            continue
        t.status = "completed"
        # Evidence Impact：把证据写到 daily_tasks.evidence_json
        if evidence_for_task is None:
            t.evidence_json = None
        elif isinstance(evidence_for_task, dict) and t.id in evidence_for_task:
            t.evidence_json = {
                **(evidence_for_task[t.id] or {}),
                "completed_at": now.isoformat(),
            }
        else:
            t.evidence_json = {
                **(evidence_for_task or {}),
                "completed_at": now.isoformat(),
            }
        receipt = _make_receipt(t, source_action, t.evidence_json)
        receipts.append(receipt)
    if receipts:
        db.commit()
    return receipts


def _check_upload(
    db: Session, user_id: int, task_date: date, ctx: dict
) -> List[dict]:
    # 这次上传是否真的给学习区带来了一本「能解析的」新书：
    # - status == duplicate → hash 去重，没有新书 → 不完成
    # - segment_status == failed（或 parse_warning）→ 解析失败 → 不完成
    if ctx.get("status") == "duplicate":
        return []
    if ctx.get("segment_status") == "failed" or ctx.get("parse_warning"):
        return []

    tasks = task_crud.list_pending_by_type(db, user_id, TYPE_UPLOAD, task_date)
    # Issue #5.X 证据：上传成功后的文档 id 与解析状态，供 Evidence Impact 展示
    evidence = {
        "document_id": ctx.get("document_id"),
        "segment_status": ctx.get("segment_status"),
        "status": ctx.get("status"),
    }
    return _complete_tasks(
        db, tasks, source_action="upload", evidence_for_task=evidence
    )


def _check_pages_have_questions(
    db: Session, user_id: int, task_date: date, ctx: dict = None
) -> List[dict]:
    tasks = task_crud.list_pending_by_type(db, user_id, TYPE_GENERATE, task_date)
    done: List[DailyTask] = []
    evidence_by_task: dict = {}
    for t in tasks:
        rule = t.completion_rule or {}
        doc_id = rule.get("document_id")
        pages = rule.get("page_numbers") or []
        if not doc_id or not pages:
            continue
        # payload 那些页是否都已有题（用户隔离）；不看整本 status
        counts = question_crud.count_questions_per_page(db, user_id, doc_id, pages)
        if all(counts.get(p, 0) > 0 for p in pages):
            done.append(t)
            evidence_by_task[t.id] = {
                "document_id": doc_id,
                "page_numbers": pages,
                "questions_count": sum(counts.get(p, 0) for p in pages),
            }
    return _complete_tasks(
        db,
        done,
        source_action="generate_questions",
        evidence_for_task=evidence_by_task,
    )


def _check_practice(
    db: Session, user_id: int, task_date: date, ctx: dict
) -> List[dict]:
    session_id = ctx.get("session_id")
    if not session_id:
        return []
    session = quiz_crud.get_session(db, session_id, user_id)
    if not session:
        return []
    tasks = task_crud.list_pending_by_type(db, user_id, TYPE_PRACTICE, task_date)
    done: List[DailyTask] = []
    evidence_by_task: dict = {}
    for t in tasks:
        rule = t.completion_rule or {}
        count = int(rule.get("count") or 0)
        if count <= 0:
            continue
        # 任务范围：指定了文档时，会话必须落在同一本书
        rule_doc = rule.get("document_id")
        if rule_doc and session.document_id != rule_doc:
            continue
        # 交够约定道数（含「不会」unknown），不要求全对
        answered = quiz_crud.count_answers(db, session.id)
        if answered >= count:
            done.append(t)
            evidence_by_task[t.id] = {
                "session_id": session.id,
                "document_id": session.document_id,
                "answered_count": answered,
                "target_count": count,
            }
    return _complete_tasks(
        db,
        done,
        source_action="answer_submitted",
        evidence_for_task=evidence_by_task,
    )
