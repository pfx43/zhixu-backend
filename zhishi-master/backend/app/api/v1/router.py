from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    chat,
    dashboard,
    kb,
    kt,
    notes,
    onboarding,
    plan,
    questions,
    quiz,
    reports,
    search,
    training,
    tutor,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["账号认证"])
api_router.include_router(plan.router, prefix="/plan", tags=["用户套餐"])
api_router.include_router(chat.router, prefix="/chat", tags=["智能聊天"])
api_router.include_router(kt.router, prefix="/kt", tags=["知识追踪"])
api_router.include_router(kb.router, prefix="/kb", tags=["知识库管理"])
api_router.include_router(questions.router, prefix="/questions", tags=["题目"])
api_router.include_router(quiz.router, prefix="/quiz", tags=["刷题"])
api_router.include_router(tutor.router, prefix="/tutor", tags=["辅导"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["首页建议"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["学习分析"])
api_router.include_router(reports.router, prefix="/reports", tags=["学习报告"])
api_router.include_router(training.router, prefix="/training", tags=["针对训练"])
api_router.include_router(notes.router, prefix="/notes", tags=["笔记系统"])
api_router.include_router(search.router, prefix="/search", tags=["知识搜索"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["引导"])
