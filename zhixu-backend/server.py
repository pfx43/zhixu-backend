"""
知拾 KT 后端服务 — FastAPI
启动方式（任选其一）:
    cd backend && uvicorn server:app --host 127.0.0.1 --port 8765
    cd backend && python server.py
    项目根目录: dev.bat 或 backend\\run.bat
"""

import sys
from pathlib import Path

# 保证从项目根 python -m backend.server 或任意 cwd 均可导入 app
_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core import paddle_env  # noqa: F401

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 初始化数据库
    try:
        from app.core.database import init_db
        init_db()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

    # 2. 探测 TCN 引擎
    try:
        from app.services.tcn.tcn_client import tcn_client
        from app.core.tcn_config import TCN_BASE_URL

        print(f"[Server] 正在探测 TCN 引擎 ({TCN_BASE_URL})...")
        health = await tcn_client.health_check()
        if health.get("status") == "ok":
            print(f"[Server] TCN 引擎就绪，{health.get('nodes', '?')} 个技能节点")

            # 3. 加载图谱缓存（node_id → 中文名称 + 先修/后继关系）
            from app.services.tcn.graph_cache import init_graph_cache, get_graph_cache

            print("[Server] 正在加载图谱数据缓存...")
            await init_graph_cache()
            cache = get_graph_cache()
            print(f"[Server] 图谱缓存就绪，{len(cache)} 个节点")
            app.state.tcn_healthy = True
            app.state.tcn_nodes = health.get("nodes", 0)
        else:
            print("[Server] 警告: TCN 引擎不可达，KT 功能将降级")
            app.state.tcn_healthy = False
            app.state.tcn_nodes = 0
    except Exception as e:
        logger.warning(f"TCN 探测失败: {e}")
        app.state.tcn_healthy = False
        app.state.tcn_nodes = 0

    # 4. 初始化 AgentManager（按用户维度管理 ZhishiAgent 实例）
    try:
        from app.core.agent_manager import AgentManager

        app.state.agent_manager = AgentManager()
        print("[Server] AgentManager 就绪")
    except Exception as e:
        logger.error(f"AgentManager 初始化失败: {e}")
        app.state.agent_manager = None

    yield

    # 退出时清理资源
    try:
        from app.services.tcn.tcn_client import tcn_client
        await tcn_client.close()
    except Exception:
        pass
    logger.info("服务关闭")


app = FastAPI(title="知拾 KT 后端", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"service": "知拾 KT 后端", "version": "2.1.0", "status": "running"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """确保未捕获异常也返回 JSON，便于 CORSMiddleware 附加 CORS 头。"""
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


# ─── 健康检查 ───

REQUIRED_DEPLOYMENT_PATHS = (
    "/api/v1/onboarding/complete",
    "/api/v1/onboarding/restart",
    "/api/v1/onboarding/state",
    "/api/v1/onboarding/step",
)

@app.get("/health")
async def health(request: Request):
    tcn_healthy = getattr(request.app.state, "tcn_healthy", False)
    tcn_nodes = getattr(request.app.state, "tcn_nodes", 0)
    available_paths = request.app.openapi().get("paths", {})
    missing_paths = [
        path for path in REQUIRED_DEPLOYMENT_PATHS if path not in available_paths
    ]
    return {
        "status": "ok" if tcn_healthy and not missing_paths else "degraded",
        "skills_count": tcn_nodes,
        "model_loaded": tcn_healthy,
        "api_contract": {
            "status": "ok" if not missing_paths else "invalid",
            "required_paths": list(REQUIRED_DEPLOYMENT_PATHS),
            "missing_paths": missing_paths,
        },
    }


# ─── 业务路由 ───

from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
