"""JINXUS API 응답 모델"""
from pydantic import BaseModel, Field
from typing import Optional


class TaskResponse(BaseModel):
    """작업 응답"""
    task_id: str
    status: str = Field(description="pending | in_progress | completed | failed")
    message: Optional[str] = None


class TaskStatusResponse(BaseModel):
    """작업 상태 조회 응답"""
    task_id: str
    status: str
    result: Optional[str] = None
    agents_used: list[str] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    created_at: str
    completed_at: Optional[str] = None


class FeedbackResponse(BaseModel):
    """피드백 응답"""
    success: bool
    message: str
    triggered_improve: bool = False


class AgentStatus(BaseModel):
    """에이전트 상태"""
    name: str
    prompt_version: str
    total_tasks: int
    success_rate: float
    avg_score: float
    avg_duration_ms: int
    recent_failures: int


class AgentListResponse(BaseModel):
    """에이전트 목록 응답"""
    agents: list[AgentStatus]


class MemorySearchResult(BaseModel):
    """메모리 검색 결과 항목"""
    task_id: str
    agent_name: str
    instruction: str
    summary: str
    outcome: str
    success_score: float
    created_at: str
    similarity_score: float


class MemorySearchResponse(BaseModel):
    """메모리 검색 응답"""
    results: list[MemorySearchResult]
    total: int


class SystemStatusResponse(BaseModel):
    """시스템 상태 응답"""
    status: str
    uptime_seconds: int
    redis_connected: bool
    qdrant_connected: bool
    total_tasks_processed: int
    active_agents: list[str]


class ImproveHistoryItem(BaseModel):
    """개선 이력 항목"""
    id: str
    target_agent: str
    trigger_type: str
    old_version: str
    new_version: str
    improvement_applied: str
    score_before: Optional[float]
    score_after: Optional[float]
    created_at: str


class ImproveHistoryResponse(BaseModel):
    """개선 이력 응답"""
    history: list[ImproveHistoryItem]


class ErrorResponse(BaseModel):
    """에러 응답"""
    error: str
    detail: Optional[str] = None
