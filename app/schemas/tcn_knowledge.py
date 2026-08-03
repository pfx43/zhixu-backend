from pydantic import BaseModel
from typing import List, Optional, Dict


class LearningPathRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    states: Dict[str, float]
    top_k: int = 5


class SkillInfo(BaseModel):
    """技能节点信息 — TCN 对接后 index 不再维护，mastery/confidence 为可选"""
    model_config = {"protected_namespaces": ()}
    id: str
    name: str
    index: Optional[int] = None
    mastery: Optional[float] = None
    confidence: Optional[float] = None


class DependencyEdge(BaseModel):
    model_config = {"protected_namespaces": ()}
    source: str  # 先修技能
    target: str  # 后继技能


class SkillGraphResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    skills: List[SkillInfo]
    edges: List[DependencyEdge]
    total_skills: int
    total_edges: int


class PrerequisiteRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    skill_id: str


class PrerequisiteResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    skill: SkillInfo
    prerequisites: List[SkillInfo]
    dependents: List[SkillInfo]  # 依赖此技能的后继技能


class HealthResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    status: str
    skills_count: int
    model_loaded: bool