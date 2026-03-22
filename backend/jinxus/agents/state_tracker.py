"""에이전트 상태 추적기

에이전트의 실시간 상태를 추적하고 UI에 제공한다.
도구 호출 로그는 Redis에 영속화 (재시작 시에도 유지).
SSE 구독자에게 상태 변경을 실시간 푸시한다.
"""
import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


class AgentStatus(Enum):
    """에이전트 상태"""
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"


class GraphNode(Enum):
    """LangGraph 노드"""
    RECEIVE = "receive"
    PLAN = "plan"
    PRE_EXECUTE_GUARD = "pre_execute_guard"
    EXECUTE = "execute"
    POST_EXECUTE = "post_execute"
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    MEMORY_WRITE = "memory_write"
    RETURN_RESULT = "return_result"


@dataclass
class AgentRuntimeState:
    """에이전트 런타임 상태"""
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_node: Optional[GraphNode] = None
    current_task: Optional[str] = None
    current_tools: List[str] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "current_node": self.current_node.value if self.current_node else None,
            "current_task": self.current_task,
            "current_tools": self.current_tools,
            "last_update": self.last_update.isoformat(),
            "error_message": self.error_message,
        }


class AgentStateTracker:
    """에이전트 상태 추적기 (싱글톤)"""

    _instance: Optional["AgentStateTracker"] = None

    _REDIS_KEY = "jinxus:tool_call_logs"
    _REDIS_MAX_LOGS = 500

    def __init__(self):
        self._states: Dict[str, AgentRuntimeState] = {}
        self._tool_call_logs: deque[dict] = deque(maxlen=100)
        self._redis = None
        self._redis_ready = False
        self._subscribers: list[asyncio.Queue] = []

    # ── SSE 구독 ──

    def subscribe(self) -> asyncio.Queue:
        """실시간 상태 변경 이벤트 구독."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """구독 해제."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _notify(self, event: dict) -> None:
        """모든 구독자에게 이벤트 푸시 (논블로킹)."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 느린 구독자는 이벤트 드롭

    @classmethod
    def get_instance(cls) -> "AgentStateTracker":
        if cls._instance is None:
            cls._instance = AgentStateTracker()
        return cls._instance

    async def init_redis(self) -> None:
        """Redis 연결 초기화 (서버 시작 시 호출)"""
        try:
            import redis.asyncio as aioredis
            from jinxus.config import get_settings
            settings = get_settings()
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )
            await self._redis.ping()
            self._redis_ready = True
            logger.info("[StateTracker] Redis 연결 완료 — 도구 로그 영속화 활성화")
        except Exception as e:
            logger.warning(f"[StateTracker] Redis 연결 실패, 인메모리 모드: {e}")
            self._redis_ready = False

    def register_agent(self, agent_name: str) -> None:
        """에이전트 등록"""
        if agent_name not in self._states:
            self._states[agent_name] = AgentRuntimeState(name=agent_name)

    def start_task(self, agent_name: str, task_description: str) -> None:
        """작업 시작"""
        if agent_name not in self._states:
            self.register_agent(agent_name)

        state = self._states[agent_name]
        state.status = AgentStatus.WORKING
        state.current_task = task_description[:100]
        state.current_node = GraphNode.RECEIVE
        state.current_tools = []
        state.error_message = None
        now = datetime.now()
        state.last_update = now
        self._notify({"type": "state_change", "agent": agent_name, "status": "working", "task": state.current_task, "ts": now.isoformat()})

    def update_node(self, agent_name: str, node: GraphNode) -> None:
        """현재 노드 업데이트"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.current_node = node
            now = datetime.now()
            state.last_update = now
            self._notify({"type": "node_change", "agent": agent_name, "node": node.value, "ts": now.isoformat()})

    def update_tools(self, agent_name: str, tools: List[str]) -> None:
        """사용 중인 도구 업데이트"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.current_tools = tools
            now = datetime.now()
            state.last_update = now
            self._notify({"type": "tools_change", "agent": agent_name, "tools": tools, "ts": now.isoformat()})

    def complete_task(self, agent_name: str) -> None:
        """작업 완료"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.status = AgentStatus.IDLE
            state.current_node = None
            state.current_task = None
            state.current_tools = []
            now = datetime.now()
            state.last_update = now
            self._notify({"type": "state_change", "agent": agent_name, "status": "idle", "ts": now.isoformat()})

    def set_error(self, agent_name: str, error: str) -> None:
        """에러 상태 설정"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.status = AgentStatus.ERROR
            state.error_message = error[:200]
            now = datetime.now()
            state.last_update = now
            self._notify({"type": "state_change", "agent": agent_name, "status": "error", "error": state.error_message, "ts": now.isoformat()})

    def get_state(self, agent_name: str) -> Optional[AgentRuntimeState]:
        """에이전트 상태 조회"""
        return self._states.get(agent_name)

    def get_all_states(self) -> Dict[str, AgentRuntimeState]:
        """모든 에이전트 상태 조회"""
        return self._states.copy()

    def get_working_agents(self) -> List[AgentRuntimeState]:
        """작업 중인 에이전트 목록"""
        return [
            state for state in self._states.values()
            if state.status == AgentStatus.WORKING
        ]

    # ── 도구 호출 로그 ──

    def log_tool_call(
        self,
        agent_name: str,
        tool_name: str,
        status: str,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """도구 호출 로그 기록

        Args:
            agent_name: 호출한 에이전트 이름
            tool_name: 도구 이름
            status: "success" | "error"
            duration_ms: 실행 시간 (ms)
            error: 에러 메시지 (실패 시)
        """
        now = datetime.now(KST)
        entry = {
            "timestamp": now.isoformat(),
            "agent": agent_name,
            "tool": tool_name,
            "status": status,
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "error": error[:200] if error else None,
        }
        self._tool_call_logs.append(entry)
        self._notify({
            "type": "tool_call",
            "agent": agent_name,
            "tool": tool_name,
            "status": status,
            "duration_ms": entry["duration_ms"],
            "ts": now.isoformat(),
        })
        # Redis 영속화 (비동기, 실패해도 인메모리에는 남음)
        if self._redis_ready and self._redis:
            try:
                asyncio.get_running_loop().create_task(self._persist_log(entry))
            except Exception as e:
                logger.debug(f"[StateTracker] Redis 도구 호출 로그 영속화 실패 (인메모리에는 보존): {e}")

    def get_tool_call_logs(self, limit: int = 50) -> List[dict]:
        """최근 도구 호출 로그 반환 (최신순)

        Args:
            limit: 반환할 최대 개수

        Returns:
            도구 호출 로그 리스트 (최신순)
        """
        logs = list(self._tool_call_logs)
        logs.reverse()
        return logs[:limit]


    async def _persist_log(self, entry: dict) -> None:
        """도구 로그를 Redis에 영속화"""
        try:
            await self._redis.lpush(self._REDIS_KEY, json.dumps(entry, ensure_ascii=False))
            await self._redis.ltrim(self._REDIS_KEY, 0, self._REDIS_MAX_LOGS - 1)
        except Exception as e:
            logger.debug(f"[StateTracker] Redis 로그 저장 실패: {e}")

    async def close(self) -> None:
        """Redis 연결 종료 (서버 종료 시 호출)"""
        if self._redis:
            try:
                await self._redis.close()
            except Exception as e:
                logger.debug(f"[StateTracker] Redis 종료 중 오류: {e}")
            self._redis = None
            self._redis_ready = False

    async def get_tool_call_logs_persistent(self, limit: int = 50) -> List[dict]:
        """Redis에서 영속 도구 로그 조회 (재시작 후에도 유지)"""
        if not self._redis_ready or not self._redis:
            return self.get_tool_call_logs(limit)
        try:
            raw = await self._redis.lrange(self._REDIS_KEY, 0, limit - 1)
            return [json.loads(r) for r in raw]
        except Exception as e:
            logger.warning(f"[StateTracker] Redis 로그 조회 실패: {e}")
            return self.get_tool_call_logs(limit)


def get_state_tracker() -> AgentStateTracker:
    """상태 추적기 싱글톤 반환"""
    return AgentStateTracker.get_instance()
