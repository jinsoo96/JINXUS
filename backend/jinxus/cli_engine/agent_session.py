"""AgentSession — 에이전트 하나의 전체 생명주기 관리

ClaudeProcess를 감싸서:
- 페르소나 기반 시스템 프롬프트 빌드
- 실행/부활/중지
- 메모리 연결
- 상태 추적

사용:
    session = await AgentSession.create(
        agent_name="JX_CODER",
        persona=get_persona("JX_CODER"),
        working_dir="/workspace",
    )
    result = await session.invoke("회원가입 API 만들어")
"""
import uuid
from datetime import datetime
from logging import getLogger
from typing import Any, Callable, Dict, Optional

from jinxus.cli_engine.models import (
    ExecutionResult,
    SessionInfo,
    SessionStatus,
    StreamEvent,
)
from jinxus.cli_engine.process_manager import ClaudeProcess
from jinxus.cli_engine.prompt_builder import build_agent_prompt
from jinxus.cli_engine.session_logger import get_session_logger, remove_session_logger
from jinxus.cli_engine.session_freshness import (
    FreshnessState,
    get_freshness_tracker,
)

logger = getLogger(__name__)


class AgentSession:
    """에이전트 세션 — ClaudeProcess + 메타데이터"""

    def __init__(self):
        self.session_id: str = ""
        self.agent_name: str = ""
        self.process: Optional[ClaudeProcess] = None
        self.persona: Optional[dict] = None
        self.memory_manager: Any = None
        self._total_cost: float = 0.0
        self._freshness_registered: bool = False

    @classmethod
    async def create(
        cls,
        agent_name: str,
        working_dir: str,
        persona: Optional[dict] = None,
        model: Optional[str] = None,
        mcp_config: Optional[dict] = None,
        max_turns: int = 50,
        timeout: float = 21600.0,
        env_vars: Optional[dict] = None,
        session_id: Optional[str] = None,
        extra_system_prompt: str = "",
        memory_context: str = "",
    ) -> "AgentSession":
        """에이전트 세션 생성 팩토리

        Args:
            agent_name: 에이전트 ID (JX_CODER, JX_RESEARCHER 등)
            working_dir: 작업 디렉토리
            persona: 페르소나 dict (personas.py에서)
            model: Claude 모델 ID
            mcp_config: MCP 서버 설정 dict
            max_turns: 최대 턴 수
            timeout: 실행 타임아웃 (초)
            env_vars: 추가 환경변수
            session_id: 기존 ID 재사용 (복원 시)
            extra_system_prompt: 추가 지시사항
            memory_context: 메모리 컨텍스트
        """
        session = cls()
        session.session_id = session_id or str(uuid.uuid4())
        session.agent_name = agent_name
        session.persona = persona

        # 시스템 프롬프트 빌드
        p = persona or {}
        system_prompt = build_agent_prompt(
            agent_name=agent_name,
            korean_name=p.get("korean_name", ""),
            role=p.get("role", "worker"),
            personality=p.get("personality", ""),
            speech_style=p.get("speech_style", ""),
            skills=p.get("skills"),
            team=p.get("team", ""),
            background=p.get("background", ""),
            quirks=p.get("quirks", ""),
            extra_system_prompt=extra_system_prompt,
            memory_context=memory_context,
        )

        # ClaudeProcess 생성
        session.process = ClaudeProcess(
            session_id=session.session_id,
            agent_name=agent_name,
            working_dir=working_dir,
            system_prompt=system_prompt,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
            mcp_config=mcp_config,
            env_vars=env_vars,
        )

        success = await session.process.initialize()
        if not success:
            raise RuntimeError(
                f"Failed to initialize agent session: {session.process.error_message}"
            )

        # 세션 로거 생성
        get_session_logger(session.session_id, agent_name, create_if_missing=True)

        # 프레시니스 트래커에 등록
        tracker = get_freshness_tracker()
        tracker.register(session.session_id)
        session._freshness_registered = True

        logger.info(
            "[%s] AgentSession created (agent=%s, model=%s)",
            session.session_id, agent_name, model,
        )
        return session

    # ── Execution ─────────────────────────────────────────────────

    async def invoke(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        **kwargs,
    ) -> ExecutionResult:
        """에이전트에게 작업 지시

        프로세스가 죽었으면 자동 부활 후 실행.
        """
        # 프레시니스 갱신 (활동 기록)
        tracker = get_freshness_tracker()
        tracker.touch(self.session_id)

        if not self.is_alive():
            logger.info("[%s] Process not alive, attempting revive", self.session_id)
            # 부활 횟수 체크
            if not tracker.try_revive(self.session_id):
                return ExecutionResult(
                    success=False,
                    session_id=self.session_id,
                    error=(
                        f"Agent {self.agent_name} exceeded max revive attempts "
                        f"and cannot be revived"
                    ),
                )
            revived = await self.revive()
            if not revived:
                return ExecutionResult(
                    success=False,
                    session_id=self.session_id,
                    error=f"Agent {self.agent_name} is not alive and revival failed",
                )

        result = await self.process.execute(
            prompt=prompt,
            timeout=timeout,
            on_event=on_event,
            **kwargs,
        )

        self._total_cost += result.cost_usd
        return result

    # ── Lifecycle ─────────────────────────────────────────────────

    @property
    def status(self) -> SessionStatus:
        if self.process:
            return self.process.status
        return SessionStatus.STOPPED

    def is_alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    async def revive(self) -> bool:
        """죽은 프로세스 부활 — 같은 설정으로 재초기화"""
        if self.process is None:
            return False

        try:
            success = await self.process.initialize()
            if success:
                logger.info("[%s] ✅ Agent revived", self.session_id)
            return success
        except Exception as e:
            logger.error("[%s] Revival failed: %s", self.session_id, e)
            return False

    def mark_idle(self) -> bool:
        """RUNNING → IDLE 전환 (유휴 모니터용)"""
        if self.process and self.process.status == SessionStatus.RUNNING:
            self.process.status = SessionStatus.IDLE
            return True
        return False

    @property
    def freshness_state(self) -> FreshnessState:
        """현재 프레시니스 상태"""
        tracker = get_freshness_tracker()
        state = tracker.get_state(self.session_id)
        return state if state is not None else FreshnessState.FRESH

    async def cleanup(self):
        """리소스 해제"""
        if self.process:
            await self.process.stop()
        # 프레시니스 트래커에서 등록 해제
        if self._freshness_registered:
            tracker = get_freshness_tracker()
            tracker.unregister(self.session_id)
            self._freshness_registered = False
        remove_session_logger(self.session_id)
        logger.info("[%s] AgentSession cleaned up", self.session_id)

    async def stop(self):
        """별칭"""
        await self.cleanup()

    # ── Info ──────────────────────────────────────────────────────

    @property
    def working_dir(self) -> Optional[str]:
        return self.process.working_dir if self.process else None

    @property
    def storage_path(self) -> Optional[str]:
        return self.process.storage_path if self.process else None

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def get_session_info(self) -> SessionInfo:
        info = SessionInfo(
            session_id=self.session_id,
            agent_name=self.agent_name,
            status=self.status,
            created_at=self.process.created_at if self.process else datetime.now(),
            model=self.process.model if self.process else None,
            working_dir=self.working_dir,
            pid=self.process.pid if self.process else None,
            execution_count=self.process._execution_count if self.process else 0,
            total_cost_usd=self._total_cost,
            freshness_state=self.freshness_state.value,
        )
        return info
