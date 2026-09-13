"""对话多模态：上下文管理器、MultimodalAgent 分支、图片上传/服务。"""
from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tina import Tools
from tina.agent.core.context_manager import MultimodalContextManager

from app.api.deps import get_current_active_user
from app.api.v1 import chat as chat_api
from app.schemas.common import ChatRequest
from app.services.knowledge.storage_service import storage_service
from app.services.llm.safe_context import PairedContextManager


# ── 上下文管理器 ────────────────────────────────────────────

def test_paired_context_manager_inherits_multimodal():
    cm = PairedContextManager(tools=Tools(name="_test"))
    assert isinstance(cm, MultimodalContextManager)


def test_paired_context_manager_text_message_stays_string():
    cm = PairedContextManager(tools=Tools(name="_test"))
    cm.add_user_message("hello")
    assert cm.messages[-1] == {"role": "user", "content": "hello"}


def test_paired_context_manager_image_message_is_multimodal(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    cm = PairedContextManager(tools=Tools(name="_test"))
    cm.add_user_message("看这个", image=[str(img)])
    content = cm.messages[-1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "看这个"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    decoded = base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1])
    assert decoded.startswith(b"\x89PNG")


def test_paired_context_manager_accepts_assistant_name():
    """历史回填 assistant 消息会带 name；MultimodalContextManager 少了该参数会 TypeError。"""
    cm = PairedContextManager(tools=Tools(name="_test"))
    cm.add_assistant_message("答案", "tina")
    assert cm.messages[-1] == {"role": "assistant", "content": "答案", "name": "tina"}
    cm.add_assistant_message("无名字")
    assert cm.messages[-1] == {"role": "assistant", "content": "无名字"}


# ── ZhixuAgent 走多模态分支 ────────────────────────────────

class _FakeAgent:
    instances: list["_FakeAgent"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.predict_calls: list[dict] = []
        _FakeAgent.instances.append(self)

    def clear_messages(self):
        pass

    def set_system_prompt(self, prompt):
        pass

    def add_message(self, **kwargs):
        pass

    def add_on_stream_chunk_handler(self, func):
        pass

    def add_before_tool_calls_handler(self, func):
        pass

    def add_after_tool_call_handler(self, func):
        pass

    async def apredict(self, **kwargs):
        self.predict_calls.append(kwargs)
        return
        yield {}  # pragma: no cover


class _FakeRetriever:
    def __init__(self, retrieve_fn):
        self.last_hits = []
        self.user_id = 1

    async def set_token(self, token):
        pass

    def get_tools(self):
        return Tools(name="kb")


class _FakeTaskTools:
    def __init__(self, **kwargs):
        pass

    def get_tools(self):
        return Tools(name="task")

    def drain_ui(self):
        return []


class _FakeCanvasTools:
    def get_tools(self):
        return Tools(name="canvas")

    def drain_ui(self):
        return []


class _FakePool:
    instance_count = 1

    def acquire(self):
        return object()


def test_generate_with_images_uses_multimodal_agent(monkeypatch):
    import app.services.agents.zhixu_agent as za

    captured = {}

    class FakeTextAgent(_FakeAgent):
        pass

    class FakeMultimodalAgent(_FakeAgent):
        pass

    monkeypatch.setattr(za, "Agent", FakeTextAgent)
    monkeypatch.setattr(za, "MultimodalAgent", FakeMultimodalAgent)
    monkeypatch.setattr(za, "llm_pool", _FakePool())
    monkeypatch.setattr(za, "KnowledgeRetriever", _FakeRetriever)
    monkeypatch.setattr(za, "TaskPlannerTools", _FakeTaskTools)
    monkeypatch.setattr(za, "CanvasTools", _FakeCanvasTools)
    monkeypatch.setattr(za, "build_user_context", lambda user_id: "")

    _FakeAgent.instances.clear()
    agent = za.ZhixuAgent(user_id=1, dataset_id="")

    async def _drain(coro):
        return [x async for x in coro]

    asyncio.run(_drain(agent.generate("看题", mode="qa", image_paths=["/tmp/a.png"])))

    assert _FakeAgent.instances, "应实例化 Agent"
    created = _FakeAgent.instances[-1]
    assert isinstance(created, FakeMultimodalAgent)
    assert created.predict_calls[0]["image"] == ["/tmp/a.png"]


def test_generate_without_images_uses_text_agent(monkeypatch):
    import app.services.agents.zhixu_agent as za

    class FakeTextAgent(_FakeAgent):
        pass

    class FakeMultimodalAgent(_FakeAgent):
        pass

    monkeypatch.setattr(za, "Agent", FakeTextAgent)
    monkeypatch.setattr(za, "MultimodalAgent", FakeMultimodalAgent)
    monkeypatch.setattr(za, "llm_pool", _FakePool())
    monkeypatch.setattr(za, "KnowledgeRetriever", _FakeRetriever)
    monkeypatch.setattr(za, "TaskPlannerTools", _FakeTaskTools)
    monkeypatch.setattr(za, "CanvasTools", _FakeCanvasTools)
    monkeypatch.setattr(za, "build_user_context", lambda user_id: "")

    _FakeAgent.instances.clear()
    agent = za.ZhixuAgent(user_id=1, dataset_id="")

    async def _drain(coro):
        return [x async for x in coro]

    asyncio.run(_drain(agent.generate("你好", mode="qa")))

    created = _FakeAgent.instances[-1]
    assert isinstance(created, FakeTextAgent)
    assert "image" not in created.predict_calls[0]


# ── 上传 / 服务 ────────────────────────────────────────────

def _image_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(storage_service._backend, "base", tmp_path)
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")
    app.dependency_overrides[get_current_active_user] = lambda: {
        "user_id": 4242,
        "is_active": True,
    }
    return TestClient(app)


def test_upload_and_fetch_chat_image(monkeypatch, tmp_path):
    client = _image_client(monkeypatch, tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"z" * 32
    resp = client.post(
        "/chat/images",
        files={"file": ("problem.png", png, "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].endswith(".png")
    assert body["url"].endswith(body["id"])

    got = client.get(f"/chat/images/{body['id']}")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.content == png


def test_upload_rejects_non_image(monkeypatch, tmp_path):
    client = _image_client(monkeypatch, tmp_path)
    resp = client.post(
        "/chat/images",
        files={"file": ("notes.txt", b"hi", "text/plain")},
    )
    assert resp.status_code == 400


def test_chat_request_accepts_images_only():
    req = ChatRequest(images=["a.png"])
    assert req.content == ""
    assert req.images == ["a.png"]
