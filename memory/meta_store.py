"""SQLite 기반 메타 저장소 - 통계, 프롬프트 버전, 개선 이력"""
import aiosqlite
import uuid
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

from config import get_settings


class MetaStore:
    """SQLite 기반 메타데이터 저장소"""

    def __init__(self):
        settings = get_settings()
        self._db_path = Path(settings.sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        """데이터베이스 테이블 초기화"""
        async with aiosqlite.connect(self._db_path) as db:
            # 에이전트별 작업 통계
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_task_logs (
                    id              TEXT PRIMARY KEY,
                    main_task_id    TEXT,
                    agent_name      TEXT NOT NULL,
                    instruction     TEXT,
                    success         INTEGER NOT NULL,
                    success_score   REAL,
                    duration_ms     INTEGER,
                    failure_reason  TEXT,
                    prompt_version  TEXT,
                    created_at      TEXT NOT NULL
                )
            """)

            # 에이전트별 프롬프트 버전
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_prompt_versions (
                    id              TEXT PRIMARY KEY,
                    agent_name      TEXT NOT NULL,
                    version         TEXT NOT NULL,
                    prompt_content  TEXT NOT NULL,
                    change_reason   TEXT,
                    avg_score       REAL DEFAULT 0.0,
                    task_count      INTEGER DEFAULT 0,
                    is_active       INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    UNIQUE(agent_name, version)
                )
            """)

            # 진수 피드백 이력
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id              TEXT PRIMARY KEY,
                    task_id         TEXT NOT NULL,
                    target_agent    TEXT,
                    rating          INTEGER NOT NULL,
                    comment         TEXT,
                    triggered_improve INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL
                )
            """)

            # 자가 강화 이력
            await db.execute("""
                CREATE TABLE IF NOT EXISTS improve_logs (
                    id              TEXT PRIMARY KEY,
                    target_agent    TEXT NOT NULL,
                    trigger_type    TEXT,
                    trigger_source  TEXT,
                    old_version     TEXT,
                    new_version     TEXT,
                    failure_patterns TEXT,
                    improvement_applied TEXT,
                    score_before    REAL,
                    score_after     REAL,
                    ab_test_done    INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL
                )
            """)

            # 스케줄 작업
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    task_prompt     TEXT NOT NULL,
                    is_active       INTEGER DEFAULT 1,
                    last_run_at     TEXT,
                    next_run_at     TEXT,
                    created_at      TEXT NOT NULL
                )
            """)

            # A/B 테스트 이력
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_logs (
                    id              TEXT PRIMARY KEY,
                    agent_name      TEXT NOT NULL,
                    old_score       REAL,
                    new_score       REAL,
                    winner          TEXT NOT NULL,
                    test_count      INTEGER,
                    created_at      TEXT NOT NULL
                )
            """)

            # 인덱스 생성
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_logs_agent ON agent_task_logs(agent_name)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_logs_created ON agent_task_logs(created_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_prompt_versions_agent ON agent_prompt_versions(agent_name)"
            )

            await db.commit()

    # ===== 작업 로그 =====

    async def log_task(
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
        """작업 로그 저장"""
        task_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_task_logs
                (id, main_task_id, agent_name, instruction, success, success_score,
                 duration_ms, failure_reason, prompt_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    main_task_id,
                    agent_name,
                    instruction,
                    1 if success else 0,
                    success_score,
                    duration_ms,
                    failure_reason,
                    prompt_version,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
        return task_id

    async def get_agent_performance(
        self, agent_name: str, days: int = 7
    ) -> dict:
        """에이전트 성능 통계 조회"""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # 기본 통계
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(success) as success_count,
                    AVG(success_score) as avg_score,
                    AVG(duration_ms) as avg_duration
                FROM agent_task_logs
                WHERE agent_name = ? AND created_at >= ?
                """,
                (agent_name, cutoff),
            )
            row = await cursor.fetchone()

            total = row["total"] or 0
            success_count = row["success_count"] or 0
            avg_score = row["avg_score"] or 0.0
            avg_duration = int(row["avg_duration"] or 0)

            # 최근 실패 수
            cursor = await db.execute(
                """
                SELECT COUNT(*) as failures
                FROM agent_task_logs
                WHERE agent_name = ? AND success = 0 AND created_at >= ?
                """,
                (agent_name, cutoff),
            )
            failures_row = await cursor.fetchone()

            return {
                "agent_name": agent_name,
                "total_tasks": total,
                "success_rate": success_count / total if total > 0 else 0.0,
                "avg_score": avg_score,
                "avg_duration_ms": avg_duration,
                "recent_failures": failures_row["failures"] or 0,
            }

    async def get_recent_failures(
        self, agent_name: str, limit: int = 5
    ) -> list[dict]:
        """최근 실패 작업 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM agent_task_logs
                WHERE agent_name = ? AND success = 0
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_name, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

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
        prompt_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            # 새 버전을 활성화하면 기존 활성 버전 비활성화
            if is_active:
                await db.execute(
                    "UPDATE agent_prompt_versions SET is_active = 0 WHERE agent_name = ?",
                    (agent_name,),
                )

            await db.execute(
                """
                INSERT INTO agent_prompt_versions
                (id, agent_name, version, prompt_content, change_reason, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id,
                    agent_name,
                    version,
                    prompt_content,
                    change_reason,
                    1 if is_active else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
        return prompt_id

    async def get_active_prompt(self, agent_name: str) -> Optional[dict]:
        """현재 활성 프롬프트 버전 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM agent_prompt_versions
                WHERE agent_name = ? AND is_active = 1
                """,
                (agent_name,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_prompt_history(self, agent_name: str) -> list[dict]:
        """프롬프트 버전 이력 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM agent_prompt_versions
                WHERE agent_name = ?
                ORDER BY created_at DESC
                """,
                (agent_name,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def activate_prompt_version(self, agent_name: str, version: str) -> bool:
        """특정 프롬프트 버전 활성화 (롤백)"""
        async with aiosqlite.connect(self._db_path) as db:
            # 기존 활성 버전 비활성화
            await db.execute(
                "UPDATE agent_prompt_versions SET is_active = 0 WHERE agent_name = ?",
                (agent_name,),
            )
            # 지정 버전 활성화
            cursor = await db.execute(
                """
                UPDATE agent_prompt_versions
                SET is_active = 1
                WHERE agent_name = ? AND version = ?
                """,
                (agent_name, version),
            )
            await db.commit()
            return cursor.rowcount > 0

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
        feedback_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO user_feedback
                (id, task_id, target_agent, rating, comment, triggered_improve, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    task_id,
                    target_agent,
                    rating,
                    comment,
                    1 if triggered_improve else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
        return feedback_id

    async def get_agent_feedback(
        self, agent_name: str, limit: int = 10
    ) -> list[dict]:
        """에이전트별 피드백 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM user_feedback
                WHERE target_agent = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_name, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

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
        improve_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO improve_logs
                (id, target_agent, trigger_type, trigger_source, old_version, new_version,
                 failure_patterns, improvement_applied, score_before, score_after, ab_test_done, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    improve_id,
                    target_agent,
                    trigger_type,
                    trigger_source,
                    old_version,
                    new_version,
                    failure_patterns,
                    improvement_applied,
                    score_before,
                    ab_test_score,
                    1 if ab_test_score is not None else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
        return improve_id

    async def get_improve_history(
        self, agent_name: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """개선 이력 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            if agent_name:
                cursor = await db.execute(
                    """
                    SELECT * FROM improve_logs
                    WHERE target_agent = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (agent_name, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM improve_logs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

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
        test_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO ab_test_logs
                (id, agent_name, old_score, new_score, winner, test_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_id,
                    agent_name,
                    old_score,
                    new_score,
                    winner,
                    test_count,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
        return test_id

    async def get_successful_tasks(
        self, agent_name: str, limit: int = 10
    ) -> list[dict]:
        """성공한 작업 목록 조회 (테스트 케이스용)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT instruction as input, success_score
                FROM agent_task_logs
                WHERE agent_name = ? AND success = 1 AND success_score >= 0.7
                ORDER BY success_score DESC, created_at DESC
                LIMIT ?
                """,
                (agent_name, limit),
            )
            rows = await cursor.fetchall()
            # 테스트 케이스 형식으로 반환 (output은 별도로 없으므로 빈값)
            return [{"input": row["input"], "output": ""} for row in rows]

    # ===== 전체 통계 =====

    async def get_total_tasks_count(self) -> int:
        """전체 처리된 작업 수"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM agent_task_logs")
            row = await cursor.fetchone()
            return row[0] if row else 0


# 싱글톤 인스턴스
_meta_store: Optional[MetaStore] = None


def get_meta_store() -> MetaStore:
    """메타 저장소 싱글톤 반환"""
    global _meta_store
    if _meta_store is None:
        _meta_store = MetaStore()
    return _meta_store


async def init_db() -> None:
    """데이터베이스 초기화 함수"""
    store = get_meta_store()
    await store.init_db()
