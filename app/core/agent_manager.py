"""
Agent 池管理器 — 管理用户 → ZhishiAgent 的映射，保证用户隔离
"""
import logging
import time
import threading
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class AgentManager:
    """
    Agent 池管理器

    职责：
        - 懒加载：首次访问用户时创建 ZhishiAgent 实例
        - 缓存复用：同一用户多个请求共享同一个 Agent
        - 用户隔离：不同 user_id 的 Agent 完全独立
        - 资源释放：支持清理闲置 Agent
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._agents: Dict[int, "ZhishiAgent"] = {}  # user_id → ZhishiAgent
        self._last_access: Dict[int, float] = {}      # user_id → timestamp

    def get_agent(self, user_id: int, dataset_id: str = "") -> "ZhishiAgent":
        """
        获取或创建用户的 Agent 实例

        Args:
            user_id: 用户 ID
            dataset_id: Dify 知识库 ID

        Returns:
            ZhishiAgent 实例
        """
        from app.services.chat.zhishi_agent import ZhishiAgent

        with self._lock:
            agent = self._agents.get(user_id)

            # 如果 Agent 不存在，或 dataset_id 已变更，重新创建
            if agent is None or agent.dataset_id != dataset_id:
                if agent is not None:
                    logger.info(
                        f"AgentManager: user_id={user_id} knowledge base changed, "
                        f"recreating agent (old={agent.dataset_id}, new={dataset_id})"
                    )
                logger.info(f"AgentManager: creating agent for user_id={user_id}, dataset_id={dataset_id}")
                agent = ZhishiAgent(user_id=user_id, dataset_id=dataset_id)
                self._agents[user_id] = agent

            self._last_access[user_id] = time.time()
            return agent

    def remove_agent(self, user_id: int) -> bool:
        """
        移除用户的 Agent 实例

        Args:
            user_id: 用户 ID

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if user_id in self._agents:
                del self._agents[user_id]
                self._last_access.pop(user_id, None)
                logger.info(f"AgentManager: removed agent for user_id={user_id}")
                return True
            return False

    def cleanup_expired(self, max_idle_seconds: int = 3600) -> int:
        """
        清理超过 max_idle_seconds 未活动的 Agent

        Args:
            max_idle_seconds: 最大空闲时间（秒），默认 1 小时

        Returns:
            int: 清理了多少个 Agent
        """
        now = time.time()
        expired = []
        with self._lock:
            for user_id in list(self._agents.keys()):
                last = self._last_access.get(user_id, 0)
                if now - last > max_idle_seconds:
                    expired.append(user_id)

            for user_id in expired:
                del self._agents[user_id]
                self._last_access.pop(user_id, None)
                logger.info(f"AgentManager: cleaned up expired agent user_id={user_id}")

        return len(expired)

    @property
    def active_count(self) -> int:
        """当前活跃的 Agent 数量"""
        with self._lock:
            return len(self._agents)


# 全局单例
agent_manager = AgentManager()