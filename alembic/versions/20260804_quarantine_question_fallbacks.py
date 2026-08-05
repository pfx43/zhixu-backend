"""隔离历史固定占位题模板

Revision ID: 20260804_question_fallbacks
Revises: 20260802_note_revision
Create Date: 2026-08-04 20:40:00.000000

只匹配旧生成器的完整结构签名：固定题干包裹格式、单选、答案 A、四个选项，
且 B/C/D 文本与旧模板逐字一致。不会使用“干扰项”等宽泛关键词删除题目。
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20260804_question_fallbacks"
down_revision = "20260802_note_revision"
branch_labels = None
depends_on = None


_FALLBACK_EXPLANATIONS = {"请参考原文段落。", "请参考原文页面。"}
_FALLBACK_OPTIONS = {
    "B": "与原文无关的干扰项",
    "C": "片面或不完整的描述",
    "D": "明显错误的描述",
}


def _is_fixed_fallback(row) -> bool:
    stem = (row["stem"] or "").strip()
    if not (
        stem.startswith("关于「")
        and stem.endswith("」，以下哪项最符合原文内容？")
        and len(stem) > len("关于「」，以下哪项最符合原文内容？")
    ):
        return False
    if (row["question_type"] or "").strip().lower() != "single_choice":
        return False
    if (row["answer"] or "").strip().upper() != "A":
        return False
    if (row["explanation"] or "").strip() not in _FALLBACK_EXPLANATIONS:
        return False

    try:
        options = json.loads(row["options"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(options, list) or len(options) != 4:
        return False

    by_key = {}
    for option in options:
        if not isinstance(option, dict):
            return False
        key = str(option.get("key", "")).strip().upper()
        text = str(option.get("text", "")).strip()
        if not key or key in by_key:
            return False
        by_key[key] = text

    if set(by_key) != {"A", "B", "C", "D"} or not by_key["A"]:
        return False
    return all(by_key[key] == text for key, text in _FALLBACK_OPTIONS.items())


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    required_tables = {
        "global_questions",
        "question_provenance",
        "user_question_refs",
    }
    if not all(inspector.has_table(table) for table in required_tables):
        return

    global_questions = sa.table(
        "global_questions",
        sa.column("id", sa.String()),
        sa.column("stem", sa.Text()),
        sa.column("question_type", sa.String()),
        sa.column("options", sa.Text()),
        sa.column("answer", sa.Text()),
        sa.column("explanation", sa.Text()),
        sa.column("source_type", sa.String()),
    )
    question_provenance = sa.table(
        "question_provenance",
        sa.column("question_id", sa.String()),
    )
    user_question_refs = sa.table(
        "user_question_refs",
        sa.column("question_id", sa.String()),
    )

    rows = bind.execute(
        sa.select(
            global_questions.c.id,
            global_questions.c.stem,
            global_questions.c.question_type,
            global_questions.c.options,
            global_questions.c.answer,
            global_questions.c.explanation,
        ).where(global_questions.c.source_type == "generated")
    ).mappings()
    fallback_ids = [row["id"] for row in rows if _is_fixed_fallback(row)]
    if not fallback_ids:
        return

    bind.execute(
        sa.delete(user_question_refs).where(
            user_question_refs.c.question_id.in_(fallback_ids)
        )
    )
    bind.execute(
        sa.delete(question_provenance).where(
            question_provenance.c.question_id.in_(fallback_ids)
        )
    )
    bind.execute(
        sa.update(global_questions)
        .where(global_questions.c.id.in_(fallback_ids))
        .values(source_type="fallback")
    )


def downgrade():
    # 清理 user refs / provenance 后无法无损还原其归属，因此迁移有意不可逆。
    pass
