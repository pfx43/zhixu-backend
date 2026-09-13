import asyncio
import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import questions as question_api
from app.crud import question as question_crud
from app.services.quiz import question_gen_service
from app.services.quiz.question_generation_guard import (
    FallbackTemplateRejected,
    is_fixed_fallback_template,
    is_quarantined_question,
)


FALLBACK_OPTIONS = [
    {"key": "A", "text": "真实资料片段"},
    {"key": "B", "text": "与原文无关的干扰项"},
    {"key": "C", "text": "片面或不完整的描述"},
    {"key": "D", "text": "明显错误的描述"},
]


class _FailOnWriteDb:
    def __init__(self):
        self.written = False

    def add(self, _row):
        self.written = True
        raise AssertionError("fixed fallback must be rejected before db.add")

    def flush(self):
        self.written = True
        raise AssertionError("fixed fallback must be rejected before db.flush")


class _FlushOnlyDb:
    def __init__(self):
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1


class QuestionGenerationFailureTests(unittest.TestCase):
    def test_readiness_probe_error_is_reported_as_service_unavailable(self):
        with patch.object(
            question_gen_service,
            "get_question_agent_readiness",
            side_effect=RuntimeError("probe failed"),
        ):
            with self.assertRaises(HTTPException) as raised:
                question_gen_service._require_question_generation_ready()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail["code"],
            "question_generation_unavailable",
        )

    def test_exact_fallback_signature_is_detected(self):
        self.assertTrue(
            is_fixed_fallback_template(
                stem="关于「第一章」，以下哪项最符合原文内容？",
                options=FALLBACK_OPTIONS,
                answer="A",
                question_type="single_choice",
                explanation="请参考原文段落。",
            )
        )

    def test_similar_keywords_without_full_signature_are_not_detected(self):
        options = [dict(item) for item in FALLBACK_OPTIONS]
        options[3] = {"key": "D", "text": "根据原文可以推导出的结论"}
        self.assertFalse(
            is_fixed_fallback_template(
                stem="关于「第一章」，以下哪项最符合原文内容？",
                options=options,
                answer="A",
                question_type="single_choice",
                explanation="请参考原文段落。",
            )
        )

    def test_fixed_fallback_is_rejected_before_global_question_write(self):
        db = _FailOnWriteDb()
        with self.assertRaises(FallbackTemplateRejected):
            question_crud.create_global_question(
                db,
                content_hash="hash",
                stem="关于「第一章」，以下哪项最符合原文内容？",
                question_type="single_choice",
                options_json=json.dumps(FALLBACK_OPTIONS, ensure_ascii=False),
                answer="A",
                explanation="请参考原文页面。",
                tags_json="[]",
                source_type="generated",
            )
        self.assertFalse(db.written)

    def test_historical_fallback_is_quarantined_from_reads(self):
        question = SimpleNamespace(
            source_type="generated",
            stem="关于「第一章」，以下哪项最符合原文内容？",
            question_type="single_choice",
            options=json.dumps(FALLBACK_OPTIONS, ensure_ascii=False),
            answer="A",
            explanation="请参考原文段落。",
        )
        self.assertTrue(is_quarantined_question(question))

