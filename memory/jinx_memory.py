"""JinxMemory - 통합 메모리 인터페이스"""
from typing import Optional

from .short_term import ShortTermMemory, get_short_term_memory
from .long_term import LongTermMemory, get_long_term_memory
from .meta_store import MetaStore, get_meta_store


class JinxMemory:
    """JINXUS 통합 메모리 관리 인터페이스

    3계층 메모리 시스템:
    - 단기기억 (Redis): 세션 대화 히스토리
    - 장기기억 (Qdrant): 에이전트별 경험 벡터
    - 메타기억 (SQLite): 통계, 프롬프트 버전, 개선 이력
    """

    def __init__(self):
        self._short_term: ShortTermMemory = get_short_term_memory()
        self._long_term: LongTermMemory = get_long_term_memory()
        self._meta: MetaStore = get_meta_store()

    # ===== 초기화 =====

    async def initialize(self) -> None:
        """메모리 시스템 초기화"""
        # Redis 연결
        await self._short_term.connect()

        # Qdrant 컬렉션 생성
        self._long_term.ensure_collections()

        # SQLite 테이블 초기화
        await self._meta.init_db()

    async def health_check(self) -> dict:
        """메모리 시스템 상태 확인"""
        return {
            "redis": await self._short_term.is_connected(),
            "qdrant": self._long_term.is_connected(),
            "sqlite": True,  # 파일 기반이라 항상 True
        }

    # ===== 단기기억 =====

    async def save_short_term(
        self, session_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        """단기기억에 메시지 저장"""
        await self._short_term.save_message(session_id, role, content, metadata)

    async def get_short_term(self, session_id: str, limit: int = 10) -> list[dict]:
        """단기기억에서 최근 대화 조회"""
        return await self._short_term.get_history(session_id, limit)

    # ===== 장기기억 =====

    def save_long_term(
        self,
        agent_name: str,
        task_id: str,
        instruction: str,
        summary: str,
        outcome: str,
        success_score: float,
        key_learnings: str,
        importance_score: float,
        prompt_version: str,
    ) -> str:
        """장기기억에 작업 결과 저장"""
        return self._long_term.save(
            agent_name=agent_name,
            task_id=task_id,
            instruction=instruction,
            summary=summary,
            outcome=outcome,
            success_score=success_score,
            key_learnings=key_learnings,
            importance_score=importance_score,
            prompt_version=prompt_version,
        )

    def search_long_term(
        self, agent_name: str, query: str, limit: int = 5
    ) -> list[dict]:
        """장기기억에서 유사 경험 검색"""
        return self._long_term.search(agent_name, query, limit)

    def search_all_memories(self, query: str, limit: int = 5) -> list[dict]:
        """모든 에이전트 메모리에서 검색"""
        return self._long_term.search_all(query, limit)

    def delete_memory(self, agent_name: str, task_id: str) -> bool:
        """특정 기억 삭제"""
        return self._long_term.delete_by_task_id(agent_name, task_id)

    def prune_low_quality(self, agent_name: str) -> int:
        """저품질 기억 정리"""
        return self._long_term.prune_low_quality(agent_name)

    # ===== 메타 저장 =====

    async def log_agent_stat(
        self,
        main_task_id: str,
        agent_name: str,
        instruction: str,
        success: bool,
        success_score: float,
        duration_ms: int,
        failure_reason: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> str:
        """작업 통계 로깅"""
        return await self._meta.log_task(
            main_task_id=main_task_id,
            agent_name=agent_name,
            instruction=instruction,
            success=success,
            success_score=success_score,
            duration_ms=duration_ms,
            failure_reason=failure_reason,
            prompt_version=prompt_version,
        )

    async def get_agent_performance(self, agent_name: str, days: int = 7) -> dict:
        """에이전트 성능 통계 조회"""
        return await self._meta.get_agent_performance(agent_name, days)

    async def get_recent_failures(self, agent_name: str, limit: int = 5) -> list[dict]:
        """최근 실패 작업 조회"""
        return await self._meta.get_recent_failures(agent_name, limit)

    # ===== 프롬프트 버전 =====

    async def save_prompt_version(
        self,
        agent_name: str,
        version: str,
        prompt_content: str,
        change_reason: Optional[str] = None,
        is_active: bool = False,
    ) -> str:
        """프롬프트 버전 저장"""
        return await self._meta.save_prompt_version(
            agent_name, version, prompt_content, change_reason, is_active
        )

    async def get_active_prompt(self, agent_name: str) -> Optional[dict]:
        """현재 활성 프롬프트 조회"""
        return await self._meta.get_active_prompt(agent_name)

    async def rollback_prompt(self, agent_name: str, version: str) -> bool:
        """프롬프트 버전 롤백"""
        return await self._meta.activate_prompt_version(agent_name, version)

    async def get_prompt_history(self, agent_name: str) -> list[dict]:
        """프롬프트 버전 이력 조회"""
        return await self._meta.get_prompt_history(agent_name)

    # ===== 피드백 =====

    async def save_feedback(
        self,
        task_id: str,
        rating: int,
        comment: Optional[str] = None,
        target_agent: Optional[str] = None,
        triggered_improve: bool = False,
    ) -> str:
        """피드백 저장"""
        return await self._meta.save_feedback(
            task_id, rating, comment, target_agent, triggered_improve
        )

    async def get_agent_feedback(self, agent_name: str, limit: int = 10) -> list[dict]:
        """에이전트별 피드백 조회"""
        return await self._meta.get_agent_feedback(agent_name, limit)

    # ===== 개선 이력 =====

    async def log_improvement(
        self,
        target_agent: str,
        trigger_type: str,
        trigger_source: str,
        old_version: str,
        new_version: str,
        failure_patterns: str,
        improvement_applied: str,
        score_before: Optional[float] = None,
    ) -> str:
        """개선 이력 저장"""
        return await self._meta.log_improvement(
            target_agent,
            trigger_type,
            trigger_source,
            old_version,
            new_version,
            failure_patterns,
            improvement_applied,
            score_before,
        )

    async def get_improve_history(
        self, agent_name: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """개선 이력 조회"""
        return await self._meta.get_improve_history(agent_name, limit)

    # ===== 전체 통계 =====

    async def get_total_tasks_count(self) -> int:
        """전체 처리된 작업 수"""
        return await self._meta.get_total_tasks_count()


# 싱글톤 인스턴스
_jinx_memory: Optional[JinxMemory] = None


def get_jinx_memory() -> JinxMemory:
    """JinxMemory 싱글톤 반환"""
    global _jinx_memory
    if _jinx_memory is None:
        _jinx_memory = JinxMemory()
    return _jinx_memory
