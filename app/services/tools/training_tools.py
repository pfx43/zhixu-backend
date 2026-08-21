"""针对训练工具包 — 供 Tina Agent 或内部服务调用"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.crud import question as question_crud
from app.services.training import analytics_service
from tina import Tools


def search_questions_by_tags(
    db: Session,
    user_id: int,
    tags: List[str],
    *,
    limit: int = 30,
    question_types: Optional[List[str]] = None,
) -> List[str]:
    """
    按 tag 从用户题库检索题目 ID（不新生成题目）。

    Args:
        tags: 知识点 tag 名称列表，命中任一 tag 即纳入
        limit: 最多返回题目数
        question_types: 可选题型过滤，如 single_choice, short_answer
    """
    rows = question_crud.search_questions_by_tags(
        db,
        user_id,
        tags,
        limit=limit,
        question_types=question_types,
    )
    return [q.id for _, q in rows]


def get_user_wrong_stats_by_tag(
    db: Session,
    user_id: int,
    *,
    min_wrong: int = 1,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    按 tag 汇总用户错题统计（基于 quiz_answers 最新状态）。

    Returns:
        [{tag, correct_count, wrong_count, unknown_count, accuracy_rate}, ...]
    """
    tag_stats = analytics_service.get_tag_stats(db, user_id)
    result: List[Dict[str, Any]] = []
    for item in tag_stats.by_tag:
        if item.wrong_count < min_wrong:
            continue
        result.append(
            {
                "tag": item.tag,
                "correct_count": item.correct_count,
                "wrong_count": item.wrong_count,
                "unknown_count": item.unknown_count,
                "total_attempts": item.total_attempts,
                "accuracy_rate": item.accuracy_rate,
            }
        )
    result.sort(key=lambda x: (-x["wrong_count"], x.get("accuracy_rate") or 100))
    return result[:limit]


class TrainingTools:
    """针对训练工具包 — 检索题目、错题统计、提交训练计划。

    以类内方法注册为 tina Tools，submit_training_plan 调用即存储
    训练计划到 submitted_plan，供 Agent 制定计划后读取。
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.submitted_plan: Optional[dict] = None

        self.tools = Tools(name="training_coach")
        self.tools.register_tool(self.search_questions_by_tags)
        self.tools.register_tool(self.get_user_wrong_stats_by_tag)
        self.tools.register_tool(self.submit_training_plan)

    def search_questions_by_tags(
        self, tags: str, limit: int = 20, question_types: str = ""
    ) -> str:
        """
        按知识点 tag 从题库检索题目 ID。

        Args:
            tags (str): 逗号分隔的 tag 名称
            limit (int): 最多返回题目数
            question_types (str): 可选，逗号分隔题型
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        type_list = (
            [t.strip() for t in question_types.split(",") if t.strip()]
            if question_types
            else None
        )
        ids = search_questions_by_tags(
            self.db, self.user_id, tag_list, limit=limit, question_types=type_list
        )
        return json.dumps({"question_ids": ids, "count": len(ids)}, ensure_ascii=False)

    def get_user_wrong_stats_by_tag(self, min_wrong: int = 1, limit: int = 10) -> str:
        """
        获取用户按 tag 的错题统计。

        Args:
            min_wrong (int): 最少错题次数
            limit (int): 返回条数上限
        """
        stats = get_user_wrong_stats_by_tag(
            self.db, self.user_id, min_wrong=min_wrong, limit=limit
        )
        return json.dumps({"stats": stats}, ensure_ascii=False)

    def submit_training_plan(
        self,
        question_ids: List[str],
        weak_tags: List[str],
        rationale: str,
    ) -> str:
        """
        提交针对训练计划（制定计划时必须调用，计划会保存用于创建刷题会话）。

        Args:
            question_ids (List[str]): 选中的题目 ID 列表
            weak_tags (List[str]): 本次重点薄弱 tag
            rationale (str): 选题理由与薄弱点说明（中文）
        """
        self.submitted_plan = {
            "question_ids": list(question_ids or []),
            "weak_tags": list(weak_tags or []),
            "rationale": (rationale or "").strip(),
        }
        return json.dumps(
            {"status": "ok", "question_count": len(self.submitted_plan["question_ids"])},
            ensure_ascii=False,
        )

    def get_tools(self) -> Tools:
        """把工具包公开给 Agent 使用。"""
        return self.tools
