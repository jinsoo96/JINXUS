"""JinxMemory - 통합 메모리 인터페이스

v1.7.0: 비동기 메모리 쓰기 (ThreadPoolExecutor + drain barrier)
- 장기기억(Qdrant) 쓰기를 백그라운드에서 처리
- recall() 전 drain_writes()로 모든 pending write 완료 보장
"""
import asyncio
import logging

from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock
from typing import Optional

from .short_term import ShortTermMemory, get_short_term_memory
from .long_term import LongTermMemory, get_long_term_memory
from .meta_store import MetaStore, get_meta_store

logger = logging.getLogger(__name__)


class JinxMemory:
    """JINXUS 통합 메모리 관리 인터페이스

    3계층 메모리 시스템:
    - 단기기억 (Redis): 세션 대화 히스토리
    - 장기기억 (Qdrant): 에이전트별 경험 벡터
    - 메타기억 (SQLite): 통계, 프롬프트 버전, 개선 이력

    v1.7.0: 비동기 쓰기 풀 (Qdrant 저장 지연 방지)
    """

    def __init__(self):
        self._short_term: ShortTermMemory = get_short_term_memory()
        self._long_term: LongTermMemory = get_long_term_memory()
        self._meta: MetaStore = get_meta_store()
        # 비동기 쓰기 풀 (단일 스레드 → 직렬화, race condition 방지)
        self._write_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jinx-mem-write")
        self._pending_writes: list[Future] = []
        self._pending_lock = Lock()

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

    async def get_full_session_history(self, session_id: str) -> list[dict]:
        """세션 전체 히스토리 조회"""
        return await self._short_term.get_full_history(session_id)

    async def list_sessions(self) -> list[dict]:
        """모든 세션 목록 조회"""
        return await self._short_term.list_sessions()

    async def clear_session(self, session_id: str) -> None:
        """세션 삭제"""
        await self._short_term.clear_session(session_id)

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
        """장기기억에 작업 결과 저장 (비동기 — 백그라운드 스레드에서 처리)

        즉시 task_id를 반환하고, 실제 Qdrant 쓰기는 백그라운드에서 수행.
        search_long_term 호출 전 drain_writes()가 자동 호출되어 일관성 보장.
        """
        def _do_save():
            try:
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
            except Exception as e:
                logger.warning(f"[JinxMemory] 장기기억 비동기 쓰기 실패: {e}")
                return None

        future = self._write_pool.submit(_do_save)
        future.add_done_callback(self._on_write_done)

        with self._pending_lock:
            self._pending_writes.append(future)

        return task_id

    def _on_write_done(self, future: Future):
        """쓰기 완료 콜백 — pending 리스트에서 제거"""
        with self._pending_lock:
            if future in self._pending_writes:
                self._pending_writes.remove(future)

    def drain_writes(self, timeout: float = 30.0) -> int:
        """모든 pending 쓰기 완료 대기 (recall 전 자동 호출)

        Returns:
            완료된 쓰기 수
        """
        with self._pending_lock:
            pending = list(self._pending_writes)

        if not pending:
            return 0

        from concurrent.futures import wait
        done, not_done = wait(pending, timeout=timeout)

        if not_done:
            logger.warning(f"[JinxMemory] drain_writes 타임아웃: {len(not_done)}개 미완료")

        return len(done)

    def close(self):
        """메모리 시스템 종료 (서버 shutdown 시 호출)"""
        self.drain_writes(timeout=10.0)
        self._write_pool.shutdown(wait=True)
        logger.info("[JinxMemory] 비동기 쓰기 풀 종료 완료")

    def search_long_term(
        self, agent_name: str, query: str, limit: int = 5
    ) -> list[dict]:
        """장기기억에서 유사 경험 검색 (pending 쓰기 있을 때만 flush)"""
        if self._pending_writes:
            self.drain_writes()
        return self._long_term.search(agent_name, query, limit)

    async def search_long_term_async(
        self, agent_name: str, query: str, limit: int = 5
    ) -> list[dict]:
        """장기기억 검색 (비블로킹)"""
        if self._pending_writes:
            await asyncio.to_thread(self.drain_writes, 5.0)
        return await asyncio.to_thread(self._long_term.search, agent_name, query, limit)

    def search_all_memories(self, query: str, limit: int = 5) -> list[dict]:
        """모든 에이전트 메모리에서 검색 (pending 쓰기 있을 때만 flush)"""
        if self._pending_writes:
            self.drain_writes()
        return self._long_term.search_all(query, limit)

    async def search_all_memories_async(self, query: str, limit: int = 5) -> list[dict]:
        """모든 에이전트 메모리 검색 (비블로킹)"""
        if self._pending_writes:
            await asyncio.to_thread(self.drain_writes, 5.0)
        return await asyncio.to_thread(self._long_term.search_all, query, limit)

    def delete_memory(self, agent_name: str, task_id: str) -> bool:
        """특정 기억 삭제"""
        return self._long_term.delete_by_task_id(agent_name, task_id)

    def prune_low_quality(self, agent_name: str) -> int:
        """저품질 기억 정리"""
        return self._long_term.prune_low_quality(agent_name)

    def get_failure_patterns(self, agent_name: str, limit: int = 10) -> list[dict]:
        """실패 패턴 분석용 데이터 조회 (JinxLoop용)"""
        return self._long_term.get_failure_patterns(agent_name, limit)

    def get_success_patterns(self, agent_name: str, min_score: float = 0.8, limit: int = 10) -> list[dict]:
        """성공 패턴 분석용 데이터 조회 (좋은 패턴 학습용)"""
        return self._long_term.get_success_patterns(agent_name, min_score, limit)

    def get_memory_stats(self, agent_name: str) -> dict:
        """에이전트별 메모리 통계"""
        return self._long_term.get_collection_stats(agent_name)

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
        output: Optional[str] = None,
        tool_calls: Optional[list[str]] = None,
    ) -> str:
        """작업 통계 로깅 (도구 호출 이력 포함)"""
        return await self._meta.log_task(
            main_task_id=main_task_id,
            agent_name=agent_name,
            instruction=instruction,
            success=success,
            success_score=success_score,
            duration_ms=duration_ms,
            failure_reason=failure_reason,
            prompt_version=prompt_version,
            output=output,
            tool_calls=tool_calls,
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
        ab_test_score: Optional[float] = None,
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
            ab_test_score,
        )

    async def get_improve_history(
        self, agent_name: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """개선 이력 조회"""
        return await self._meta.get_improve_history(agent_name, limit)

    # ===== A/B 테스트 =====

    async def log_ab_test(
        self,
        agent_name: str,
        old_score: float,
        new_score: float,
        winner: str,
        test_count: int,
    ) -> str:
        """A/B 테스트 결과 저장"""
        return await self._meta.log_ab_test(
            agent_name, old_score, new_score, winner, test_count
        )

    async def get_successful_tasks(
        self, agent_name: str, limit: int = 10
    ) -> list[dict]:
        """성공한 작업 목록 조회 (테스트 케이스용)"""
        return await self._meta.get_successful_tasks(agent_name, limit)

    async def get_prompt_versions(self, agent_name: str) -> list[dict]:
        """프롬프트 버전 목록 조회"""
        return await self._meta.get_prompt_history(agent_name)

    async def activate_prompt_version(self, agent_name: str, version: str) -> bool:
        """특정 프롬프트 버전 활성화"""
        return await self._meta.activate_prompt_version(agent_name, version)

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
