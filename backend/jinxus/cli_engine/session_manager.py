"""AgentSessionManager — 전체 에이전트 세션 관리

에이전트 생성/조회/삭제, 유휴 모니터, 자동 부활 등
모든 에이전트 세션의 중앙 관리자.

사용:
    manager = get_agent_session_manager()
    session = await manager.create_session("JX_CODER", working_dir="/workspace")
    result = await session.invoke("회원가입 API 만들어")
"""
import asyncio
import os
from datetime import datetime
from logging import getLogger
from typing import Dict, List, Optional

from jinxus.cli_engine.agent_session import AgentSession
from jinxus.cli_engine.models import SessionInfo, SessionStatus
from jinxus.cli_engine.session_freshness import (
    FreshnessState,
    get_freshness_tracker,
)

logger = getLogger(__name__)


class AgentSessionManager:
    """에이전트 세션 중앙 관리자"""

    def __init__(self):
        self._sessions: Dict[str, AgentSession] = {}  # session_id → AgentSession
        self._by_name: Dict[str, str] = {}  # agent_name → session_id
        self._default_working_dir: str = os.environ.get(
            "WORKSPACE_ROOT", os.path.expanduser("~/jinxus-workspace")
        )
        self._default_model: Optional[str] = None
        self._global_mcp_config: Optional[dict] = None
        self._idle_monitor_task: Optional[asyncio.Task] = None

    def set_defaults(
        self,
        working_dir: Optional[str] = None,
        model: Optional[str] = None,
        mcp_config: Optional[dict] = None,
    ):
        """기본값 설정 (서버 startup에서 호출)"""
        if working_dir:
            self._default_working_dir = working_dir
        if model:
            self._default_model = model
        if mcp_config:
            self._global_mcp_config = mcp_config
            logger.info("Global MCP config set: %s", list(mcp_config.get("mcpServers", {}).keys()))

    # ── Session creation ──────────────────────────────────────────

    async def create_session(
        self,
        agent_name: str,
        working_dir: Optional[str] = None,
        persona: Optional[dict] = None,
        model: Optional[str] = None,
        mcp_config: Optional[dict] = None,
        max_turns: int = 50,
        timeout: float = 21600.0,
        env_vars: Optional[dict] = None,
        extra_system_prompt: str = "",
        memory_context: str = "",
    ) -> AgentSession:
        """에이전트 세션 생성

        이미 같은 agent_name으로 활성 세션이 있으면 기존 세션 반환.
        """
        # 기존 세션 확인
        existing = self.get_session_by_name(agent_name)
        if existing and existing.is_alive():
            logger.info("[%s] Reusing existing session for %s", existing.session_id, agent_name)
            return existing

        # 기존 죽은 세션 정리
        if existing:
            await self._remove_session(existing.session_id)

        # 페르소나 로드
        if persona is None:
            try:
                from jinxus.agents.personas import get_persona
                persona_obj = get_persona(agent_name)
                if persona_obj:
                    persona = {
                        "korean_name": persona_obj.korean_name,
                        "role": persona_obj.role,
                        "personality": persona_obj.personality,
                        "speech_style": persona_obj.speech_style,
                        "skills": persona_obj.skills,
                        "team": persona_obj.team,
                        "background": persona_obj.background,
                        "quirks": persona_obj.quirks,
                    }
            except Exception as e:
                logger.warning("Failed to load persona for %s: %s", agent_name, e)

        # MCP 설정 병합 (전역 + 세션별)
        merged_mcp = self._merge_mcp_config(mcp_config)

        # 메모리 컨텍스트 로드
        if not memory_context:
            memory_context = await self._load_memory_context(agent_name)

        # 작업 디렉토리: PROJECT_ROOT가 있으면 그걸 사용 (프로젝트 파일 접근 가능)
        # 없으면 에이전트별 격리 디렉토리
        project_root = os.environ.get("PROJECT_ROOT")
        wd = working_dir or project_root or os.path.join(self._default_working_dir, agent_name.lower())

        session = await AgentSession.create(
            agent_name=agent_name,
            working_dir=wd,
            persona=persona,
            model=model or self._default_model,
            mcp_config=merged_mcp,
            max_turns=max_turns,
            timeout=timeout,
            env_vars=env_vars,
            extra_system_prompt=extra_system_prompt,
            memory_context=memory_context,
        )

        # 등록
        self._sessions[session.session_id] = session
        self._by_name[agent_name] = session.session_id

        logger.info(
            "✅ Agent session created: %s (%s) → %s",
            agent_name, session.session_id[:8], wd,
        )
        return session

    # ── Session access ────────────────────────────────────────────

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def get_session_by_name(self, agent_name: str) -> Optional[AgentSession]:
        sid = self._by_name.get(agent_name)
        if sid:
            return self._sessions.get(sid)
        return None

    def resolve(self, name_or_id: str) -> Optional[AgentSession]:
        """이름 또는 ID로 조회"""
        s = self.get_session(name_or_id)
        if s:
            return s
        return self.get_session_by_name(name_or_id)

    def list_sessions(self) -> List[AgentSession]:
        return list(self._sessions.values())

    def list_session_infos(self) -> List[SessionInfo]:
        return [s.get_session_info() for s in self._sessions.values()]

    def has_session(self, agent_name: str) -> bool:
        return agent_name in self._by_name

    # ── Session lifecycle ─────────────────────────────────────────

    async def delete_session(self, session_id: str) -> bool:
        return await self._remove_session(session_id)

    async def _remove_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False

        await session.cleanup()

        # 레지스트리에서 제거
        del self._sessions[session_id]
        # by_name에서도 제거
        self._by_name = {
            name: sid for name, sid in self._by_name.items()
            if sid != session_id
        }

        logger.info("[%s] Session removed (%s)", session_id, session.agent_name)
        return True

    async def cleanup_dead_sessions(self):
        """죽은 세션 정리 — 프레시니스 기반 부활 시도 후 실패하면 제거"""
        tracker = get_freshness_tracker()
        dead = [
            sid for sid, s in self._sessions.items()
            if not s.is_alive()
        ]
        for sid in dead:
            session = self._sessions[sid]
            logger.info("[%s] Dead session detected (%s), attempting revive", sid, session.agent_name)

            # 프레시니스 트래커에서 부활 횟수 체크
            if not tracker.try_revive(sid):
                logger.warning(
                    "[%s] Session %s exceeded max revives, removing",
                    sid, session.agent_name,
                )
                await self._remove_session(sid)
                continue

            revived = await session.revive()
            if not revived:
                await self._remove_session(sid)

    # ── Batch operations ──────────────────────────────────────────

    async def ensure_agents(self, agent_names: List[str], working_dir: Optional[str] = None) -> Dict[str, AgentSession]:
        """여러 에이전트 세션을 한번에 확보 (없으면 생성)

        미션 실행 전에 필요한 에이전트들을 미리 준비할 때 사용.
        """
        sessions = {}
        for name in agent_names:
            session = self.get_session_by_name(name)
            if session and session.is_alive():
                sessions[name] = session
            else:
                sessions[name] = await self.create_session(
                    agent_name=name,
                    working_dir=working_dir,
                )
        return sessions

    async def broadcast(
        self,
        prompt: str,
        agent_names: Optional[List[str]] = None,
        timeout: float = 600.0,
    ) -> Dict[str, "ExecutionResult"]:
        """여러 에이전트에게 동시 명령 (병렬 실행)

        agent_names가 None이면 모든 활성 에이전트에게 전송.
        """
        from jinxus.cli_engine.models import ExecutionResult

        targets = agent_names or list(self._by_name.keys())
        sessions = await self.ensure_agents(targets)

        async def _invoke_one(name: str, session: AgentSession) -> tuple:
            try:
                result = await session.invoke(prompt, timeout=timeout)
                return name, result
            except Exception as e:
                return name, ExecutionResult(
                    success=False,
                    session_id=session.session_id,
                    error=str(e),
                )

        tasks = [
            asyncio.create_task(_invoke_one(name, session))
            for name, session in sessions.items()
        ]
        results_tuples = await asyncio.gather(*tasks)
        return dict(results_tuples)

    # ── Idle monitor ──────────────────────────────────────────────

    def start_idle_monitor(self, interval: float = 60.0):
        """유휴 세션 모니터 시작 (프레시니스 모니터 포함)"""
        if self._idle_monitor_task:
            return
        self._idle_monitor_task = asyncio.ensure_future(self._idle_loop(interval))

        # 프레시니스 모니터도 함께 시작
        tracker = get_freshness_tracker()
        tracker.set_callbacks(on_reset=self._on_freshness_reset)
        tracker.start_monitor(interval=interval)

        logger.info("Idle monitor started (interval=%ss, with freshness)", interval)

    async def stop_idle_monitor(self):
        if self._idle_monitor_task:
            self._idle_monitor_task.cancel()
            try:
                await self._idle_monitor_task
            except asyncio.CancelledError:
                pass
            self._idle_monitor_task = None

        # 프레시니스 모니터도 중지
        tracker = get_freshness_tracker()
        await tracker.stop_monitor()

    def _on_freshness_reset(self, session_id: str):
        """프레시니스 STALE_RESET 콜백 — 세션 제거 스케줄"""
        session = self._sessions.get(session_id)
        if session:
            logger.info(
                "[%s] Session %s reached STALE_RESET, scheduling removal",
                session_id, session.agent_name,
            )
            asyncio.ensure_future(self._remove_session(session_id))

    async def _idle_loop(self, interval: float):
        while True:
            try:
                await asyncio.sleep(interval)
                transitioned = 0
                for session in self._sessions.values():
                    if session.mark_idle():
                        transitioned += 1
                if transitioned:
                    logger.info("Idle monitor: %d session(s) -> IDLE", transitioned)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("Idle monitor tick error", exc_info=True)

    # ── Helpers ───────────────────────────────────────────────────

    def _merge_mcp_config(self, session_config: Optional[dict]) -> Optional[dict]:
        """전역 MCP + 세션별 MCP 병합"""
        if not self._global_mcp_config and not session_config:
            return None
        base = dict(self._global_mcp_config or {})
        if session_config:
            servers = base.get("mcpServers", {})
            servers.update(session_config.get("mcpServers", {}))
            base["mcpServers"] = servers
        return base if base.get("mcpServers") else None

    async def _load_memory_context(self, agent_name: str) -> str:
        """에이전트의 장기 메모리에서 컨텍스트 로드"""
        try:
            from jinxus.memory import get_jinx_memory
            memory = get_jinx_memory()
            results = await asyncio.to_thread(
                memory.recall_long_term, agent_name, "recent tasks", limit=5
            )
            if results:
                lines = []
                for r in results[:5]:
                    lines.append(f"- {r.get('content', '')[:200]}")
                return "\n".join(lines)
        except Exception:
            pass
        return ""


# ============================================================================
# Singleton
# ============================================================================

_manager: Optional[AgentSessionManager] = None


def get_agent_session_manager() -> AgentSessionManager:
    global _manager
    if _manager is None:
        _manager = AgentSessionManager()
    return _manager


def reset_agent_session_manager():
    global _manager
    _manager = None
