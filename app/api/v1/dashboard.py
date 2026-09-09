"""
首页智能建议 — 根据知识库文档生成个性化建议
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_token, get_db
from app.core.config import is_local_rag
from app.crud import kb as kb_crud
from app.services.knowledge.dify_kb import DifyKB
from app.services.llm.llm_pool import llm_pool
from app.services.llm.reasoning_roundtrip import attach_reasoning_roundtrip
from app.utils.prompt_loader import load_prompt
from tina import Agent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["首页建议"])

SYSTEM_PROMPT = load_prompt("dashboard_suggestions")

_FALLBACK = [
    "查看知识库中的文档",
    "尝试向 Tina 提问相关问题",
    "上传更多相关资料丰富知识库",
]


def _parse_suggestions(content: str) -> list[str]:
    suggestions = [
        line.strip()[2:]
        for line in content.split("\n")
        if line.strip().startswith("- ")
    ]
    return suggestions[:3] if suggestions else _FALLBACK.copy()


@router.get("/suggestions")
async def get_dashboard_suggestions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    token: str = Depends(get_current_token),
):
    """
    根据用户知识库文档生成个性化建议

    流程：
        1. 获取用户知识库文档列表
        2. 提取文档名称和上传日期
        3. 构建提示词，调用 LLM 生成建议
    """
    dataset_id = current_user.get("dataset_id")

    if not dataset_id and not is_local_rag():
        return {
            "suggestions": ["上传你的第一份文档，开启智能学习", "完善学习画像，获得精准推荐"]
        }

    docs: list = []
    if is_local_rag():
        rows, _ = kb_crud.list_documents(db, current_user["user_id"], page=1, limit=20)
        docs = [
            {
                "name": row.display_name or "未命名文档",
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in rows
        ]
    elif dataset_id:
        try:
            kb = DifyKB(dataset_id)
            result = kb.list_documents(page=1, limit=20)
            docs = result.get("data", [])
        except Exception as e:
            logger.warning(f"获取文档列表失败: {e}")

    if not docs:
        return {
            "suggestions": ["上传你的第一份文档，开启智能学习", "完善学习画像，获得精准推荐"]
        }

    doc_lines = []
    for doc in docs[:10]:
        name = doc.get("name", "未命名文档")
        created = doc.get("created_at", "")
        created = created[:10] if created else "未知时间"
        doc_lines.append(f"- {name}（{created}）")

    user_prompt = (
        "用户知识库中有以下文档：\n"
        + "\n".join(doc_lines)
        + "\n\n请根据上述文档给出学习建议。"
    )

    try:
        llm = llm_pool.acquire()
        if llm is None:
            return {"suggestions": _FALLBACK.copy()}
        if token and hasattr(llm, "set_token"):
            llm.set_token(token)
        agent = Agent(
            llm=llm,
            tools=None,
            system_prompt=SYSTEM_PROMPT,
            name="dashboard_suggestions",
        )
        attach_reasoning_roundtrip(agent)
        result = await agent.apredict_no_stream(instruction=user_prompt, temperature=0.7)
        content = result.get("content", "") if isinstance(result, dict) else getattr(result, "content", "") or ""
        return {"suggestions": _parse_suggestions(content)}
    except Exception as e:
        logger.error(f"生成建议失败: {e}")
        return {"suggestions": _FALLBACK.copy()}
