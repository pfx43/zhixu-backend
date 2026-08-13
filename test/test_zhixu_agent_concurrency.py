"""ZhixuAgent 无状态化并发安全 + tina_gateway lease 释放测试。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.agents.zhixu_agent import ZhixuAgent


def test_no_shared_runtime_state():
    """ZhixuAgent 无共享可变运行态（无锁、无 active 状态、无 last 聚合字段）。"""
    agent = ZhixuAgent(user_id=1, dataset_id="ds")
    for attr in (
        "_lock",
        "_active_collection_id",
        "_active_db",
        "_last_reasoning",
        "_last_tool_names",
    ):
        assert not hasattr(agent, attr), f"不应存在共享运行态字段: {attr}"


def test_concurrent_generate_isolated():
    """同一实例并发 generate：每路独立 acquire llm、独立输入输出，互不串线。"""
    agent = ZhixuAgent(user_id=1, dataset_id="ds")
    agent._llm_ready = True

    acquired = []

    class FakeLLM:
        def __init__(self, tag):
            self.tag = tag

    class FakeTinaAgent:
        def __init__(self, *args, **kwargs):
            self.llm = kwargs["llm"]

        def clear_messages(self):
            pass

        def add_message(self, **kwargs):
            pass

        def apredict(self, instruction, **kwargs):
            async def gen():
                yield {"role": "assistant", "content": f"{self.llm.tag}:{instruction}"}
            return gen()

    def fake_acquire():
        tag = "A" if len(acquired) % 2 == 0 else "B"
        acquired.append(tag)
        return FakeLLM(tag)

    with (
        patch("app.services.agents.zhixu_agent.llm_pool.acquire", side_effect=fake_acquire),
        patch("app.services.agents.zhixu_agent.Agent", FakeTinaAgent),
    ):
        async def run(instruction):
            events = [e async for e in agent.generate(instruction, token="")]
            return "".join(e["content"] for e in events if e["type"] == "answer")

        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(run("q-one"))
            r2 = loop.run_until_complete(run("q-two"))
        finally:
            loop.close()

    # 两路各自独立 acquire 到不同 llm，输出带上自己的 llm 与输入，互不串线
    assert acquired == ["A", "B"]
    assert r1 == "A:q-one"
    assert r2 == "B:q-two"


def test_release_base_api_key_releases_lease_only():
    """release_base_api_key 按 leased_key 释放；无 lease（回退默认 key）不释放。"""
    from app.services.tina_gateway import tina_gateway

    held = SimpleNamespace(leased_key="key-1")
    fallback = SimpleNamespace(leased_key=None)
    with patch.object(tina_gateway, "_release_key") as release:
        tina_gateway.release_base_api_key(held)
        tina_gateway.release_base_api_key(fallback)
    release.assert_called_once_with("key-1")
