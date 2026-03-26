"""cli_engine 데이터 모델

세션 상태, 실행 결과, 스트림 이벤트, 로그 엔트리 등
cli_engine 전체에서 사용하는 공유 모델.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================================
# Session Status
# ============================================================================

class SessionStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    EXECUTING = "executing"
    STOPPED = "stopped"
    ERROR = "error"


# ============================================================================
# Session Info
# ============================================================================

@dataclass
class SessionInfo:
    session_id: str
    agent_name: str
    status: SessionStatus
    created_at: datetime
    model: Optional[str] = None
    working_dir: Optional[str] = None
    pid: Optional[int] = None
    execution_count: int = 0
    total_cost_usd: float = 0.0
    error_message: Optional[str] = None
    freshness_state: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        return d


# ============================================================================
# Execution Result
# ============================================================================

@dataclass
class ExecutionResult:
    success: bool
    session_id: str
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    cost_usd: float = 0.0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    file_changes: List[Dict[str, Any]] = field(default_factory=list)
    num_turns: int = 0
    model: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Stream Event Types (Claude CLI --output-format stream-json)
# ============================================================================

class StreamEventType(str, Enum):
    SYSTEM_INIT = "system_init"
    ASSISTANT_MESSAGE = "assistant"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    CONTENT_BLOCK_START = "content_start"
    CONTENT_BLOCK_DELTA = "content_delta"
    CONTENT_BLOCK_STOP = "content_stop"
    RESULT = "result"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class StreamEvent:
    event_type: StreamEventType
    timestamp: datetime
    raw_data: Dict[str, Any]

    # Common
    session_id: Optional[str] = None

    # System init
    tools: Optional[List[str]] = None
    mcp_servers: Optional[List[str]] = None
    model: Optional[str] = None

    # Assistant message
    message_id: Optional[str] = None
    text: Optional[str] = None
    stop_reason: Optional[str] = None

    # Tool use
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_use_id: Optional[str] = None

    # Tool result
    tool_output: Optional[str] = None
    is_error: Optional[bool] = None

    # Result
    duration_ms: Optional[int] = None
    total_cost_usd: Optional[float] = None
    num_turns: Optional[int] = None
    result_text: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionSummary:
    session_id: Optional[str] = None
    model: Optional[str] = None
    available_tools: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    assistant_messages: List[str] = field(default_factory=list)
    final_output: str = ""
    success: bool = False
    is_error: bool = False
    error_message: Optional[str] = None
    duration_ms: int = 0
    total_cost_usd: float = 0.0
    num_turns: int = 0
    usage: Optional[Dict[str, Any]] = None
    stop_reason: Optional[str] = None


# ============================================================================
# Log Models
# ============================================================================

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    COMMAND = "COMMAND"
    RESPONSE = "RESPONSE"
    GRAPH = "GRAPH"
    TOOL = "TOOL"
    TOOL_RES = "TOOL_RES"
    STREAM = "STREAM"


@dataclass
class LogEntry:
    timestamp: str
    level: LogLevel
    message: str
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "message": self.message,
            "metadata": self.metadata,
        }
