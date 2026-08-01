"""TCN 接口请求/响应数据模型 — 核实依据：TCN_API_CONFIRMATION_REPLY.md v1.4"""

from pydantic import BaseModel
from typing import Optional


class TCNPredictRequest(BaseModel):
    api_key: str = ""
    user_hash: str
    domain_id: str = ""
    current_node: str
    user_action: str  # "correct" | "incorrect"
    step_index: int = 0
    session_id: str = ""


class TCNPredictResponse(BaseModel):
    user_hash: str
    lvr: float
    vs: float
    diagnosis: str = ""
    recommended_backtrack: Optional[str] = None
    node_mastery: dict[str, float] = {}  # 前 10 个节点（索引 0–9）
    epsilon_used: float = 0.05
    training_phase: str = "unknown"


class TCNProfileResponse(BaseModel):
    user_hash: str = ""
    total_steps: int = 0
    global_lvr: float = 0.0
    graph_version: int = 0
    node_count: int = 0


class TCNHealthResponse(BaseModel):
    status: str
    nodes: int
    graph_version: int = 0
    dense_mode: bool = False
    constraint: str = "static"
    model: str = "lekt"


# ─── 4 个新接口响应模型（respond_fix.md 真实格式） ──────────


class TCNSummaryDomainItem(BaseModel):
    domain: str
    mastery_avg: float
    node_count: int
    visited_count: int = 0


class TCNSummaryResponse(BaseModel):
    user_hash: str = ""
    diagnosis_version: str = "rule"
    total_steps: int = 0
    overall_mastery: float = 0.5
    global_lvr: float = 0.0
    lvr_level: str = "normal"
    graph_version: int = 0
    domain_summary: list[TCNSummaryDomainItem] = []
    last_active_node: Optional[str] = None
    computed_at: Optional[str] = None


class TCNGapsItem(BaseModel):
    node_id: str
    domain: str = ""
    mastery: float = 0.5
    children_count: int = 0
    is_visited: bool = False


class TCNGapsResponse(BaseModel):
    user_hash: str = ""
    diagnosis_version: str = "rule"
    mastery_threshold: float = 0.6
    total_gaps: int = 0
    returned_gaps: int = 0
    limit: int = 50
    gaps: list[TCNGapsItem] = []
    computed_at: Optional[str] = None


class TCNVulnerabilityWeakPrereq(BaseModel):
    node_id: str
    mastery: float = 0.5
    gap: float = 0.0


class TCNVulnerabilityItem(BaseModel):
    node_id: str
    domain: str = ""
    mastery: float = 0.5
    fragility_score: float = 0.0
    weak_prerequisites: list[TCNVulnerabilityWeakPrereq] = []


class TCNVulnerabilitiesResponse(BaseModel):
    user_hash: str = ""
    diagnosis_version: str = "rule"
    mastery_threshold_high: float = 0.7
    total_vulnerabilities: int = 0
    returned_vulnerabilities: int = 0
    limit: int = 50
    vulnerabilities: list[TCNVulnerabilityItem] = []
    computed_at: Optional[str] = None


class TCNLvrViolation(BaseModel):
    parent_node: str
    child_node: str
    parent_mastery: float = 0.5
    child_mastery: float = 0.5
    gap: float = 0.0


class TCNLvrAlertResponse(BaseModel):
    user_hash: str = ""
    diagnosis_version: str = "rule"
    global_lvr: float = 0.0
    lvr_level: str = "normal"
    alert_code: str = "LVR_NORMAL"
    alert_text: Optional[str] = None
    total_violations: int = 0
    returned_violations: int = 0
    limit: int = 10
    violations: list[TCNLvrViolation] = []
    backtrack_recommended: list[str] = []
    computed_at: Optional[str] = None
