"""
KT 知识追踪路由 — TCN 引擎层对接版
所有接口需要登录鉴权
"""

from fastapi import APIRouter, HTTPException, Depends, Query, status
from app.api.deps import get_current_active_user
from app.services.kt_service import (
    recommend_learning_path,
    get_prerequisites,
    get_skill_graph,
    get_skill_states,
)
from app.services.tcn_client import tcn_client
from app.models.tcn_schemas import (
    TCNSummaryResponse,
    TCNGapsResponse,
    TCNVulnerabilitiesResponse,
    TCNLvrAlertResponse,
)
from models import (
    LearningPathRequest,
    PrerequisiteRequest,
)

router = APIRouter(tags=["知识追踪"])


def _user_hash_or_503(current_user: dict) -> str:
    """从 current_user 中提取 user_hash，未就绪时返回 503。

    与 fix.md 中的交付规则一致：若用户未初始化 user_hash，
    接口应返回 503，提示依赖未就绪，而不是继续执行空结果逻辑。
    """
    user_hash = current_user.get("user_hash")
    if not user_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TCN 用户哈希未初始化，请检查 User 模型迁移",
        )
    return user_hash


# ─── 基础 KT 接口 ──────────────────────────────────────────

@router.post("/learning-path")
async def kt_learning_path(
    req: LearningPathRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """基于 TCN 掌握度推荐学习路径"""
    user_hash = _user_hash_or_503(current_user)
    return await recommend_learning_path(user_hash, req.top_k)


@router.post("/prerequisites")
async def kt_prerequisites(
    req: PrerequisiteRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """查询指定节点的先修关系"""
    user_hash = _user_hash_or_503(current_user)
    result = await get_prerequisites(user_hash, req.skill_id)
    if result["skill"] is None:
        raise HTTPException(404, f"节点 {req.skill_id} 在图谱中不存在")
    return result


@router.get("/skill-graph")
async def kt_skill_graph(
    current_user: dict = Depends(get_current_active_user),
):
    """全量技能图谱叠加用户掌握度"""
    user_hash = _user_hash_or_503(current_user)
    return await get_skill_graph(user_hash)


@router.get("/states")
async def kt_states(
    current_user: dict = Depends(get_current_active_user),
):
    """获取用户已练习节点的掌握度快照 {node_id: mastery}"""
    user_hash = _user_hash_or_503(current_user)
    return await get_skill_states(user_hash)


# ─── 4 个新接口（respond_fix.md 真实格式对接） ─────────────

@router.get("/summary", response_model=TCNSummaryResponse)
async def kt_summary(
    current_user: dict = Depends(get_current_active_user),
):
    """用户知识状态摘要（LLM System Prompt 注入用）。"""
    user_hash = _user_hash_or_503(current_user)
    try:
        return await tcn_client.get_summary(user_hash)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TCN 摘要服务异常: {exc}",
        ) from exc


@router.get("/gaps", response_model=TCNGapsResponse)
async def kt_gaps(
    limit: int = Query(50, ge=1, le=200),
    threshold: float = Query(0.6, ge=0.0, le=1.0),
    current_user: dict = Depends(get_current_active_user),
):
    """先修断层查询。"""
    user_hash = _user_hash_or_503(current_user)
    try:
        return await tcn_client.get_gaps(user_hash, limit=limit, threshold=threshold)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TCN 断层查询异常: {exc}",
        ) from exc


@router.get("/vulnerabilities", response_model=TCNVulnerabilitiesResponse)
async def kt_vulnerabilities(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_active_user),
):
    """认知脆弱点（伪掌握）预警。"""
    user_hash = _user_hash_or_503(current_user)
    try:
        return await tcn_client.get_vulnerabilities(user_hash, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TCN 脆弱点预警异常: {exc}",
        ) from exc


@router.get("/lvr-alert", response_model=TCNLvrAlertResponse)
async def kt_lvr_alert(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_active_user),
):
    """LVR 预警状态（含回溯建议）。"""
    user_hash = _user_hash_or_503(current_user)
    try:
        return await tcn_client.get_lvr_alert(user_hash, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TCN LVR 预警异常: {exc}",
        ) from exc
