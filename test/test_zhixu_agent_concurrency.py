"""ZhixuAgent 并发隔离与 key lease 释放测试。"""
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from app.services.agents.zhixu_agent import ZhixuAgent


class _FakeRuntime:
    def __init__(self):
        self.llm = None


class _FakeTinaAgent:
    """predict 期间持续断言运行态不被他人覆盖；每个 chunk 带当前 collection 前缀。"""

    def __init__(self, owner):
        self.owner = owner
        self.llm = None
        self.runtime = _FakeRuntime()
        self.context_manager = SimpleNamespace(set_system_message=lambda m: None)

    def clear_messages(self):
        pass

    def add_message(self, **kwargs):
        pass

    def predict(self, instruction, **kwargs):
        seen = self.owner._active_collection_id
        for i in range(20):
            assert self.owner._active_collection_id == seen, "并发串线：运行态被覆盖"
            time.sleep(0.001)
            yield {"role": "assistant", "content": f"{seen}-{i}"}

    async def apredict(self, instruction, **kwargs):
        for chunk in self.predict(instruction, **kwargs):
            yield chunk


def _make_agent(user_id=42, dataset_id="ds"):
    agent = ZhixuAgent(user_id=user_id, dataset_id=dataset_id)
    agent._llm_ready = True
    agent._agent = _FakeTinaAgent(agent)
    return agent


def test_concurrent_same_user_sessions_do_not_interleave():
    """同一用户两个 session 并发生成：运行态互斥，正文/聚合结果不串线。"""
    agent = _make_agent()
    fake_llm = SimpleNamespace(leased_key="k1")
    fake_llm.set_token = lambda t: None
    results = {}
    errors = []
    barrier = threading.Barrier(3)

    def run(collection):
        try:
            barrier.wait()
            chunks = list(agent.predict_stream(
                "hi", collection_id=collection, mode="qa",
            ))
            results[collection] = "".join(c["content"] for c in chunks)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=run, args=("coll-A",))
    t2 = threading.Thread(target=run, args=("coll-B",))
    with patch(
        "app.services.tina_gateway.tina_gateway.create_base_api", return_value=fake_llm
    ):
        t1.start(); t2.start()
        barrier.wait()
        t1.join(); t2.join()

    assert not errors, errors
    # 每个 session 拿到的正文只含自己的 collection 前缀
    assert results["coll-A"] and all("coll-B" not in c for c in results["coll-A"])
    assert results["coll-B"] and all("coll-A" not in c for c in results["coll-B"])
    # 各自的正文集合互不包含
    assert set(results["coll-A"].split("coll-A-")) and set(results["coll-B"].split("coll-B-"))


def test_key_lease_released_after_stream_and_on_close():
    """key lease 在正常完成与生成器提前关闭路径都释放。"""
    agent = _make_agent()
    fake_llm = SimpleNamespace(leased_key="k1")
    fake_llm.set_token = lambda t: None

    with patch(
        "app.services.tina_gateway.tina_gateway.create_base_api", return_value=fake_llm
    ) as create, patch(
        "app.services.tina_gateway.tina_gateway.release_base_api_key"
    ) as release:
        gen = agent.predict_stream("hi", collection_id="c1", mode="qa")
        next(gen)
        gen.close()  # 提前关闭（模拟断连）

    create.assert_called_once_with()
    release.assert_called_once_with(fake_llm)

    # 正常耗尽路径同样释放
    with patch(
        "app.services.tina_gateway.tina_gateway.create_base_api", return_value=fake_llm
    ), patch(
        "app.services.tina_gateway.tina_gateway.release_base_api_key"
    ) as release2:
        list(agent.predict_stream("hi", collection_id="c2", mode="qa"))
    release2.assert_called_once_with(fake_llm)


def test_release_base_api_key_releases_lease_only():
    """release_base_api_key 按 leased_key 释放；无 lease（回退默认 key）不释放。"""
    from app.services.tina_gateway import tina_gateway

    held = SimpleNamespace(leased_key="key-1")
    fallback = SimpleNamespace(leased_key=None)
    with patch.object(tina_gateway, "_release_key") as release:
        tina_gateway.release_base_api_key(held)
        tina_gateway.release_base_api_key(fallback)
    release.assert_called_once_with("key-1")
