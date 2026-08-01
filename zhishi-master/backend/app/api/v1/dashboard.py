"""
首页智能建议 — 根据知识库文档生成个性化建议
"""
import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.core.config import LLM_ASYNC, is_local_rag
from app.services.dify_kb import DifyKB
from app.services.llm_runner import llm_predict_no_stream
from app.utils.tina_loader import tina_env_path
from tina.llm import BaseAPI

logger = logging.getLogger(__name__)

router = APIRouter(tags=["首页建议"])

SYSTEM_PROMPT = """你是知拾（Zhishi）的知识管理助手 Tina。请根据用户知识库中的文档列表，生成 2-3 条简洁的个性化学习建议（每条不超过 30 字）。
建议方向：
- 提醒复习某些文档
- 建议整理或补充某个主题
- 推荐ai对话的方向
只输出建议列表，每行一条，以 "- " 开头，不要其他内容。"""

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
    current_user: dict = Depends(get_current_active_user),
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
    if dataset_id and not is_local_rag():
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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        llm = BaseAPI(env_path=tina_env_path())
        if LLM_ASYNC:
            response = await llm.apredict_no_stream(
                messages=messages, temperature=0.7, max_tokens=300
            )
        else:
            response = llm_predict_no_stream(
                llm, messages=messages, temperature=0.7, max_tokens=300
            )
        content = response.get("content", "")
        return {"suggestions": _parse_suggestions(content)}
    except Exception as e:
        logger.error(f"生成建议失败: {e}")
        return {"suggestions": _FALLBACK.copy()}
