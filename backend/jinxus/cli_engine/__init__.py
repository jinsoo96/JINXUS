"""cli_engine — Claude Code CLI 실행 엔진

모든 에이전트의 실제 작업 수행은 이 패키지를 통한다.
에이전트 하나 = ClaudeProcess 하나 = Claude Code CLI subprocess 하나.
"""
from jinxus.cli_engine.models import (
    SessionStatus,
    SessionInfo,
    ExecutionResult,
    StreamEventType,
    StreamEvent,
    ExecutionSummary,
    LogLevel,
    LogEntry,
)
from jinxus.cli_engine.stream_parser import StreamParser
from jinxus.cli_engine.session_logger import SessionLogger, get_session_logger, remove_session_logger
from jinxus.cli_engine.process_manager import ClaudeProcess
from jinxus.cli_engine.agent_session import AgentSession
from jinxus.cli_engine.session_manager import AgentSessionManager, get_agent_session_manager
from jinxus.cli_engine.session_freshness import (
    FreshnessState,
    FreshnessTracker,
    FreshnessThresholds,
    FreshnessEntry,
    get_freshness_tracker,
    reset_freshness_tracker,
)

__all__ = [
    "SessionStatus", "SessionInfo", "ExecutionResult",
    "StreamEventType", "StreamEvent", "ExecutionSummary",
    "LogLevel", "LogEntry",
    "StreamParser",
    "SessionLogger", "get_session_logger", "remove_session_logger",
    "ClaudeProcess",
    "AgentSession",
    "AgentSessionManager", "get_agent_session_manager",
    "FreshnessState", "FreshnessTracker", "FreshnessThresholds",
    "FreshnessEntry", "get_freshness_tracker", "reset_freshness_tracker",
]
