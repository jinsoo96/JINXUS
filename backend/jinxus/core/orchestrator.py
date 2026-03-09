"""Orchestrator - 에이전트 레지스트리 및 실행 관리"""
import asyncio
import logging
from typing import Optional, Callable, Awaitable, TYPE_CHECKING
from datetime import datetime

from jinxus.memory import get_jinx_memory
from jinxus.tools import register_tools, register_mcp_tools, get_all_tools_info

if TYPE_CHECKING:
    from jinxus.agents import JinxusCore

logger = logging.getLogger(__name__)


class Orchestrator:
    """JINXUS 오케스트레이터

    - 에이전트 레지스트리 관리
    - JINXUS_CORE 실행 관리
    - 병렬/순차 실행 조율
    """

    _instance: Optional["Orchestrator"] = None

    def __init__(self):
        self._core = None  # JinxusCore (lazy import)
        self._memory = get_jinx_memory()
        self._initialized = False
        self._start_time: Optional[datetime] = None
        self._agent_registry = None

    @classmethod
    def get_instance(cls) -> "Orchestrator":
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            cls._instance = Orchestrator()
        return cls._instance

    async def initialize(self) -> None:
        """시스템 초기화"""
        if self._initialized:
            return

        logger.info("JINXUS 시스템 초기화 시작...")

        # 1. 메모리 시스템 초기화
        await self._memory.initialize()
        logger.info("메모리 시스템 초기화 완료")

        # 2. 기존 도구 등록
        register_tools()
        logger.info("기존 도구 등록 완료")

        # 3. MCP 도구 등록 (비동기)
        try:
            await register_mcp_tools()
            logger.info("MCP 도구 등록 완료")
        except Exception as e:
            logger.warning(f"MCP 도구 등록 실패 (계속 진행): {e}")

        # 4. 에이전트 등록 (lazy import로 순환 임포트 방지)
        from jinxus.agents import register_all_agents, create_jinxus_core
        # 반환값을 직접 사용 (모듈 바인딩 문제 방지)
        self._agent_registry = register_all_agents()
        logger.info("에이전트 등록 완료")

        # 5. JINXUS_CORE 생성
        self._core = create_jinxus_core()

        self._initialized = True
        self._start_time = datetime.now()
        logger.info("JINXUS 시스템 초기화 완료")

    @property
    def core(self) -> "JinxusCore":
        """JINXUS_CORE 반환"""
        if not self._core:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")
        return self._core

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def uptime_seconds(self) -> int:
        """가동 시간 (초)"""
        if not self._start_time:
            return 0
        return int((datetime.now() - self._start_time).total_seconds())

    async def run_task(
        self,
        user_input: str,
        session_id: str = None,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> dict:
        """작업 실행

        Args:
            user_input: 사용자 입력
            session_id: 세션 ID
            progress_callback: 진행 상황 보고 콜백 (백그라운드 작업용)

        Returns:
            실행 결과 딕셔너리
        """
        if not self._initialized:
            await self.initialize()

        return await self._core.run(user_input, session_id, progress_callback)

    async def run_task_stream(self, user_input: str, session_id: str = None):
        """스트리밍 작업 실행"""
        if not self._initialized:
            await self.initialize()

        async for event in self._core.run_stream(user_input, session_id):
            yield event

    def get_agents(self) -> list[str]:
        """등록된 에이전트 목록"""
        if self._agent_registry is None:
            return []
        return list(self._agent_registry.keys())

    async def get_agent_status(self, agent_name: str) -> dict:
        """에이전트 상태 조회"""
        if self._agent_registry is None or agent_name not in self._agent_registry:
            return {"error": f"Agent not found: {agent_name}"}

        performance = await self._memory.get_agent_performance(agent_name, days=7)
        prompt_info = await self._memory.get_active_prompt(agent_name)

        return {
            "name": agent_name,
            "prompt_version": prompt_info.get("version", "v1.0") if prompt_info else "v1.0",
            **performance,
        }

    async def get_system_status(self) -> dict:
        """시스템 상태 조회"""
        health = await self._memory.health_check()
        total_tasks = await self._memory.get_total_tasks_count()

        # 도구 정보
        tools_info = get_all_tools_info()
        native_tools = [t for t in tools_info if not t["is_mcp"]]
        mcp_tools = [t for t in tools_info if t["is_mcp"]]

        return {
            "status": "running" if self._initialized else "not_initialized",
            "uptime_seconds": self.uptime_seconds,
            "redis_connected": health.get("redis", False),
            "qdrant_connected": health.get("qdrant", False),
            "total_tasks_processed": total_tasks,
            "active_agents": self.get_agents(),
            "tools": {
                "native_count": len(native_tools),
                "mcp_count": len(mcp_tools),
                "total": len(tools_info),
            },
        }

    def get_tools_info(self) -> list[dict]:
        """등록된 도구 정보 반환"""
        return get_all_tools_info()


# 싱글톤 접근 함수
def get_orchestrator() -> Orchestrator:
    """오케스트레이터 싱글톤 반환"""
    return Orchestrator.get_instance()
