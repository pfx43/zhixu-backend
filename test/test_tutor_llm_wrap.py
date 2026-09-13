"""辅导 Agent：跟主对话一样，裸 BaseAPI + Agent 流里记 usage。"""

from app.services.tutor import tutor_service


class _FakeBaseAPI:
    """模拟池里的裸 BaseAPI（无 set_token）。"""


def test_socratic_tutor_init_ready_with_bare_baseapi(monkeypatch):
    class FakeCM:
        def set_system_message(self, *_a, **_k):
            return None

    class FakeAgent:
        def __init__(self, **kwargs):
            self.llm = kwargs["llm"]
            self.context_manager = FakeCM()

        def clear_messages(self):
            return None

    monkeypatch.setattr(tutor_service.llm_pool, "acquire", lambda: _FakeBaseAPI())
    monkeypatch.setattr(tutor_service, "attach_reasoning_roundtrip", lambda _agent: None)

    import tina

    monkeypatch.setattr(tina, "Agent", FakeAgent)

    class FakeContextManager:
        def __init__(self, *a, **k):
            pass

        def set_system_message(self, *a, **k):
            pass

    monkeypatch.setattr(tina, "ContextManager", FakeContextManager)

    agent = tutor_service.SocraticTutorAgent(system_prompt="test", token="tok")
    assert agent.is_ready is True
    assert isinstance(agent._llm, _FakeBaseAPI)
    assert not hasattr(agent._llm, "set_token")
