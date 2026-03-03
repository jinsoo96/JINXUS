"""JINXUS API 요청 모델"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ChatRequest(BaseModel):
    """채팅 요청"""
    message: str = Field(..., description="진수의 명령")
    session_id: Optional[str] = Field(default=None, description="세션 ID (없으면 자동 생성)")


class TaskRequest(BaseModel):
    """비동기 작업 요청"""
    message: str = Field(..., description="작업 명령")
    session_id: Optional[str] = Field(default=None)
    priority: str = Field(default="normal", description="high | normal | low")


class FeedbackRequest(BaseModel):
    """피드백 요청"""
    task_id: str = Field(..., description="피드백 대상 작업 ID")
    rating: int = Field(..., ge=1, le=5, description="평점 1~5")
    comment: Optional[str] = Field(default=None, description="코멘트")
    target_agent: Optional[str] = Field(default=None, description="특정 에이전트 지정")


class ImproveRequest(BaseModel):
    """수동 개선 트리거 요청"""
    agent_name: Optional[str] = Field(default=None, description="특정 에이전트 지정 (없으면 전체 분석)")


class RollbackRequest(BaseModel):
    """프롬프트 롤백 요청"""
    agent_name: str = Field(..., description="에이전트 이름")
    version: str = Field(..., description="롤백할 버전")


class MemorySearchRequest(BaseModel):
    """메모리 검색 요청"""
    query: str = Field(..., description="검색 쿼리")
    agent_name: Optional[str] = Field(default=None, description="특정 에이전트 메모리만 검색")
    limit: int = Field(default=5, ge=1, le=20)
