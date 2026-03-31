"""SQLite 기반 메타 저장소 - 통계, 프롬프트 버전, 개선 이력"""
import aiosqlite
import logging
import uuid
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


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
                    output          TEXT,
                    success         INTEGER NOT NULL,
                    success_score   REAL,
                    duration_ms     INTEGER,
                    failure_reason  TEXT,
                    prompt_version  TEXT,
                    created_at      TEXT NOT NULL
                )
            """)

            # 기존 테이블에 컬럼 추가 (마이그레이션)
            for col in ("output TEXT", "tool_calls TEXT"):
                try:
                    await db.execute(f"ALTER TABLE agent_task_logs ADD COLUMN {col}")
                except Exception as e:
                    logger.debug(f"[MetaStore] 컬럼 추가 건너뜀 (이미 존재): {e}")

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

            # 워크플로우 패턴 저장 (ToolGraph 학습용)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS workflow_patterns (
                    id              TEXT PRIMARY KEY,
                    query           TEXT NOT NULL,
                    tool_sequence   TEXT NOT NULL,
                    success         INTEGER NOT NULL,
                    score           REAL,
                    duration_ms     INTEGER,
                    use_count       INTEGER DEFAULT 1,
                    created_at      TEXT NOT NULL,
                    last_used_at    TEXT NOT NULL
                )
            """)

            # 백그라운드 작업 상태 (서버 재시작 시 복구/보고용)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS background_tasks (
                    task_id         TEXT PRIMARY KEY,
                    description     TEXT NOT NULL,
                    session_id      TEXT,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    autonomous      INTEGER DEFAULT 0,
                    steps_completed INTEGER DEFAULT 0,
                    steps_total     INTEGER DEFAULT 0,
                    result_summary  TEXT,
                    error           TEXT,
                    created_at      TEXT NOT NULL,
                    started_at      TEXT,
                    completed_at    TEXT
                )
            """)

            # 인덱스 생성
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bg_tasks_status ON background_tasks(status)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_query ON workflow_patterns(query)"
            )
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
        output: Optional[str] = None,
        tool_calls: Optional[list[str]] = None,
    ) -> str:
        """작업 로그 저장"""
        import json
        task_id = str(uuid.uuid4())
        # output은 A/B 테스트용으로 500자까지만 저장 (DB 용량 절약)
        truncated_output = output[:500] if output else None
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_task_logs
                (id, main_task_id, agent_name, instruction, output, success, success_score,
                 duration_ms, failure_reason, prompt_version, tool_calls, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    main_task_id,
                    agent_name,
                    instruction,
                    truncated_output,
                    1 if success else 0,
                    success_score,
                    duration_ms,
                    failure_reason,
                    prompt_version,
                    tool_calls_json,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()
        return task_id

    async def get_agent_performance(
        self, agent_name: str, days: int = 7
    ) -> dict:
        """에이전트 성능 통계 조회"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

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

    async def get_recent_logs(
        self,
        agent_name: Optional[str] = None,
        main_task_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """최근 작업 로그 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            conditions = []
            params: list = []

            if agent_name:
                conditions.append("agent_name = ?")
                params.append(agent_name)
            if main_task_id:
                conditions.append("main_task_id = ?")
                params.append(main_task_id)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.extend([limit, offset])

            cursor = await db.execute(
                f"""
                SELECT * FROM agent_task_logs
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_logs_count(self, agent_name: Optional[str] = None) -> int:
        """로그 총 개수"""
        async with aiosqlite.connect(self._db_path) as db:
            if agent_name:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM agent_task_logs WHERE agent_name = ?",
                    (agent_name,),
                )
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM agent_task_logs")

            row = await cursor.fetchone()
            return row[0] if row else 0

    async def delete_log(self, log_id: str) -> bool:
        """로그 단일 삭제"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM agent_task_logs WHERE id = ?",
                (log_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_logs_bulk(self, log_ids: list[str]) -> int:
        """로그 일괄 삭제"""
        async with aiosqlite.connect(self._db_path) as db:
            placeholders = ",".join("?" * len(log_ids))
            cursor = await db.execute(
                f"DELETE FROM agent_task_logs WHERE id IN ({placeholders})",
                log_ids,
            )
            await db.commit()
            return cursor.rowcount

    async def delete_logs_by_agent(self, agent_name: str) -> int:
        """에이전트별 로그 전체 삭제"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM agent_task_logs WHERE agent_name = ?",
                (agent_name,),
            )
            await db.commit()
            return cursor.rowcount

    async def delete_old_logs(self, days: int = 7, keep_failures: bool = True) -> int:
        """오래된 로그 삭제 (실패 로그는 선택적 유지)"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            if keep_failures:
                # 성공 로그만 삭제, 실패 로그는 유지
                cursor = await db.execute(
                    "DELETE FROM agent_task_logs WHERE created_at < ? AND success = 1",
                    (cutoff,),
                )
            else:
                cursor = await db.execute(
                    "DELETE FROM agent_task_logs WHERE created_at < ?",
                    (cutoff,),
                )
            await db.commit()
            return cursor.rowcount

    async def clear_all_logs(self) -> int:
        """전체 작업 로그 삭제"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM agent_task_logs")
            await db.commit()
            return cursor.rowcount

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
                    datetime.now().isoformat(),
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
                    datetime.now().isoformat(),
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
                    datetime.now().isoformat(),
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
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()
        return test_id

    async def get_successful_tasks(
        self, agent_name: str, limit: int = 10
    ) -> list[dict]:
        """성공한 작업 목록 조회 (테스트 케이스용)

        A/B 테스트에서 사용: 과거 성공 작업의 input/output 쌍을 반환
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT instruction as input, output, success_score
                FROM agent_task_logs
                WHERE agent_name = ? AND success = 1 AND success_score >= 0.7
                    AND output IS NOT NULL AND output != ''
                ORDER BY success_score DESC, created_at DESC
                LIMIT ?
                """,
                (agent_name, limit),
            )
            rows = await cursor.fetchall()
            return [
                {"input": row["input"], "output": row["output"]}
                for row in rows
            ]

    # ===== 스케줄 작업 =====

    async def save_scheduled_task(
        self,
        task_id: str,
        name: str,
        cron_expression: str,
        task_prompt: str,
        is_active: bool = True,
        next_run_at: Optional[str] = None,
    ) -> str:
        """스케줄 작업 저장"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO scheduled_tasks
                (id, name, cron_expression, task_prompt, is_active, next_run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    name,
                    cron_expression,
                    task_prompt,
                    1 if is_active else 0,
                    next_run_at,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()
        return task_id

    async def get_scheduled_tasks(self, active_only: bool = True) -> list[dict]:
        """스케줄 작업 목록 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if active_only:
                cursor = await db.execute(
                    "SELECT * FROM scheduled_tasks WHERE is_active = 1"
                )
            else:
                cursor = await db.execute("SELECT * FROM scheduled_tasks")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_scheduled_task(self, task_id: str) -> Optional[dict]:
        """스케줄 작업 단일 조회"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_scheduled_task_run(
        self, task_id: str, last_run_at: str, next_run_at: Optional[str] = None
    ) -> None:
        """스케줄 작업 실행 기록 업데이트"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = ?, next_run_at = ?
                WHERE id = ?
                """,
                (last_run_at, next_run_at, task_id),
            )
            await db.commit()

    async def delete_scheduled_task(self, task_id: str) -> bool:
        """스케줄 작업 삭제"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_scheduled_task_active(self, task_id: str, is_active: bool) -> bool:
        """스케줄 작업 활성화/비활성화"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "UPDATE scheduled_tasks SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, task_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # ===== 전체 통계 =====

    async def get_total_tasks_count(self) -> int:
        """전체 처리된 작업 수"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM agent_task_logs")
            row = await cursor.fetchone()
            return row[0] if row else 0

    # ===== 워크플로우 패턴 =====

    async def save_workflow_pattern(
        self, query: str, tool_sequence: list[str], success: bool,
        score: float = 0.0, duration_ms: int = 0,
    ) -> str:
        """워크플로우 패턴 저장"""
        import json
        pattern_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        seq_json = json.dumps(tool_sequence)

        async with aiosqlite.connect(self._db_path) as db:
            # 동일 시퀀스가 이미 있는지 확인
            cursor = await db.execute(
                "SELECT id, use_count FROM workflow_patterns WHERE tool_sequence = ?",
                (seq_json,)
            )
            existing = await cursor.fetchone()

            if existing:
                # 기존 패턴 업데이트 (사용 횟수 증가)
                await db.execute(
                    """UPDATE workflow_patterns
                       SET use_count = use_count + 1, last_used_at = ?,
                           score = ?, success = ?, duration_ms = ?
                       WHERE id = ?""",
                    (now, score, int(success), duration_ms, existing[0])
                )
                await db.commit()
                return existing[0]

            await db.execute(
                """INSERT INTO workflow_patterns
                   (id, query, tool_sequence, success, score, duration_ms, created_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pattern_id, query, seq_json, int(success), score, duration_ms, now, now)
            )
            await db.commit()
        return pattern_id

    async def find_similar_workflows(self, query: str, limit: int = 3) -> list[dict]:
        """유사 쿼리의 성공 워크플로우 패턴 조회"""
        import json
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # 성공한 패턴 중 사용 횟수가 높은 순
            cursor = await db.execute(
                """SELECT * FROM workflow_patterns
                   WHERE success = 1
                   ORDER BY use_count DESC, score DESC
                   LIMIT ?""",
                (limit,)
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "query": row["query"],
                    "tool_sequence": json.loads(row["tool_sequence"]),
                    "score": row["score"],
                    "use_count": row["use_count"],
                    "last_used_at": row["last_used_at"],
                }
                for row in rows
            ]

    # ===== 백그라운드 작업 영속화 =====

    async def save_background_task(
        self,
        task_id: str,
        description: str,
        session_id: str,
        autonomous: bool = False,
    ) -> None:
        """백그라운드 작업 상태 저장"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO background_tasks
                   (task_id, description, session_id, status, autonomous, created_at)
                   VALUES (?, ?, ?, 'pending', ?, ?)""",
                (task_id, description, session_id, int(autonomous),
                 datetime.now().isoformat()),
            )
            await db.commit()

    async def update_background_task(
        self,
        task_id: str,
        status: str,
        steps_completed: int = 0,
        steps_total: int = 0,
        result_summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """백그라운드 작업 상태 업데이트"""
        async with aiosqlite.connect(self._db_path) as db:
            now = datetime.now().isoformat()
            updates = {
                "status": status,
                "steps_completed": steps_completed,
                "steps_total": steps_total,
            }
            if result_summary:
                updates["result_summary"] = result_summary[:2000]
            if error:
                updates["error"] = error[:500]

            if status == "running":
                updates["started_at"] = now
            elif status in ("completed", "failed", "cancelled"):
                updates["completed_at"] = now

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [task_id]

            await db.execute(
                f"UPDATE background_tasks SET {set_clause} WHERE task_id = ?",
                values,
            )
            await db.commit()

    async def get_interrupted_tasks(self) -> list[dict]:
        """서버 재시작 시 중단된 작업 조회 (pending/running 상태)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM background_tasks
                   WHERE status IN ('pending', 'running')
                   ORDER BY created_at DESC""",
            )
            rows = await cursor.fetchall()

            # 중단된 작업을 'interrupted'로 업데이트
            for row in rows:
                await db.execute(
                    """UPDATE background_tasks
                       SET status = 'interrupted', completed_at = ?
                       WHERE task_id = ?""",
                    (datetime.now().isoformat(), row["task_id"]),
                )
            await db.commit()

            return [dict(row) for row in rows]

    async def cleanup_old_background_tasks(self, days: int = 7) -> int:
        """오래된 완료 작업 정리"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """DELETE FROM background_tasks
                   WHERE status IN ('completed', 'failed', 'cancelled', 'interrupted')
                   AND created_at < ?""",
                (cutoff,),
            )
            await db.commit()
            return cursor.rowcount

    async def vacuum(self) -> None:
        """SQLite VACUUM — 삭제 후 빈 페이지 회수하여 파일 크기 축소"""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("VACUUM")
            logger.info(f"[MetaStore] VACUUM 완료: {self._db_path}")
        except Exception as e:
            logger.warning(f"[MetaStore] VACUUM 실패: {e}")


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
