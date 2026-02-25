"""Orchestrator - 에이전트 레지스트리 및 실행 관리"""
import asyncio
from typing import Optional
from datetime import datetime

from agents import create_jinxus_core, JinxusCore, AGENT_REGISTRY, register_all_agents
from memory import get_jinx_memory


class Orchestrator:
    """JINXUS 오케스트레이터

    - 에이전트 레지스트리 관리
    - JINXUS_CORE 실행 관리
    - 병렬/순차 실행 조율
    """

    _instance: Optional["Orchestrator"] = None

    def __init__(self):
        self._core: Optional[JinxusCore] = None
        self._memory = get_jinx_memory()
        self._initialized = False
        self._start_time: Optional[datetime] = None

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

        # 메모리 시스템 초기화
        await self._memory.initialize()

        # 에이전트 등록
        register_all_agents()

        # JINXUS_CORE 생성
        self._core = create_jinxus_core()

        self._initialized = True
        self._start_time = datetime.utcnow()

    @property
    def core(self) -> JinxusCore:
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
        return int((datetime.utcnow() - self._start_time).total_seconds())

    async def run_task(self, user_input: str, session_id: str = None) -> dict:
        """작업 실행"""
        if not self._initialized:
            await self.initialize()

        return await self._core.run(user_input, session_id)

    async def run_task_stream(self, user_input: str, session_id: str = None):
        """스트리밍 작업 실행"""
        if not self._initialized:
            await self.initialize()

        async for event in self._core.run_stream(user_input, session_id):
            yield event

    def get_agents(self) -> list[str]:
        """등록된 에이전트 목록"""
        return list(AGENT_REGISTRY.keys())

    async def get_agent_status(self, agent_name: str) -> dict:
        """에이전트 상태 조회"""
        if agent_name not in AGENT_REGISTRY:
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

        return {
            "status": "running" if self._initialized else "not_initialized",
            "uptime_seconds": self.uptime_seconds,
            "redis_connected": health.get("redis", False),
            "qdrant_connected": health.get("qdrant", False),
            "total_tasks_processed": total_tasks,
            "active_agents": self.get_agents(),
        }


# 싱글톤 접근 함수
def get_orchestrator() -> Orchestrator:
    """오케스트레이터 싱글톤 반환"""
    return Orchestrator.get_instance()
