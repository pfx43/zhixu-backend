from typing import List, Optional

from pydantic import BaseModel

from app.schemas.quiz import QuizSessionOut


class WeakTagOut(BaseModel):
    tag: str
    wrong_count: int
    correct_count: int
    accuracy_rate: Optional[int] = None


class TargetedTrainingStartIn(BaseModel):
    report_id: Optional[str] = None
    force_new: bool = False


class TargetedTrainingStartOut(BaseModel):
    session: QuizSessionOut
    weak_tags: List[WeakTagOut] = []
    question_ids: List[str] = []
    report_id: Optional[str] = None
    rationale: Optional[str] = None
    agent_session_id: Optional[str] = None


class TargetedTrainingActiveSessionOut(BaseModel):
    session_id: str
    report_id: Optional[str] = None
    answered_count: int
    total_questions: int
    agent_session_id: Optional[str] = None
    status: str


class TrainingTutorMessageCreate(BaseModel):
    content: str
    stream: bool = True


class TrainingTutorReplyOut(BaseModel):
    role: str = "assistant"
    content: str
    agent_session_id: str
