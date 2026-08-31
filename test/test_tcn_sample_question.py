"""用抽出的 TCN 知识点出一道题，并对照对接文档打一次 predict。

tag 用图谱 name（如「夹逼准则」）；predict 的 current_node 用图谱 id
（如 higher_math:夹逼准则）。不走 Learning OS 的 goals/today。
predict 只有 correct/incorrect，本测试按答对传 correct，不传「不会」。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest

_REPO = Path(__file__).resolve().parent.parent
_QUESTION_PATH = Path(__file__).resolve().parent / "fixtures" / "tcn_squeeze_theorem_question.json"
_TAGS_PATH = _REPO / "docs" / "api" / "TCN" / "higher_math.json"
_DOCUMENTED_TCN = "http://47.82.118.95:8001"


def _load_question() -> dict:
    return json.loads(_QUESTION_PATH.read_text(encoding="utf-8"))


def _load_tags() -> list[dict]:
    payload = json.loads(_TAGS_PATH.read_text(encoding="utf-8"))
    return payload["tags"]


def _tag_index() -> dict[str, str]:
    return {row["name"]: row["id"] for row in _load_tags()}


def test_sample_question_uses_extracted_tcn_tag():
    question = _load_question()
    by_name = _tag_index()

    assert question["question_type"] == "single_choice"
    assert question["answer"] in {opt["key"] for opt in question["options"]}
    assert len(question["tags"]) == 1

    tag_name = question["tags"][0]
    assert tag_name in by_name, f"tag「{tag_name}」不在抽出的 TCN 知识点里"
    assert question["tc_node_id"] == by_name[tag_name]
    assert question["tc_node_id"].startswith(question["domain_id"] + ":")
    assert question["tc_node_id"] != tag_name


def _probe_base(url: str) -> dict | None:
    try:
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=5.0)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    body = resp.json()
    if body.get("status") != "ok" or body.get("ready") is not True:
        return None
    return body


def _live_tcn_base() -> str:
    configured = os.environ.get("TCN_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    if _probe_base(configured):
        return configured
    if configured != _DOCUMENTED_TCN.rstrip("/") and _probe_base(_DOCUMENTED_TCN):
        return _DOCUMENTED_TCN.rstrip("/")
    pytest.skip("TCN 引擎不可达（本地与对接文档地址均未 ready）")


def test_sample_question_predict_on_live_tcn():
    question = _load_question()
    base = _live_tcn_base()
    user_hash = "zhixu_test_" + uuid.uuid4().hex[:12]
    payload = {
        "api_key": "",
        "user_hash": user_hash,
        "domain_id": question["domain_id"],
        "current_node": question["tc_node_id"],
        "user_action": "correct",
        "step_index": 1,
        "session_id": "squeeze-theorem-sample",
    }

    resp = httpx.post(f"{base}/v1/user/predict", json=payload, timeout=30.0)

    assert resp.status_code != 404, (
        f"current_node={question['tc_node_id']} 不在引擎图谱里: {resp.text[:300]}"
    )
    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()
    diagnosis = body.get("diagnosis") or ""
    assert not diagnosis.startswith("Unknown node"), diagnosis
    assert body.get("user_hash") == user_hash
    assert isinstance(body.get("lvr"), (int, float))
    assert isinstance(body.get("node_mastery"), dict)
    assert body.get("solver_converged") is not False
