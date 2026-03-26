"""에이전트 성과 프로파일 시스템

agent_task_logs(SQLite)에 누적된 데이터를 집계하여
에이전트별 task_type 단위 성과 통계를 제공한다.

- 메모리 캐시 + DB 동기화 (TTL 60초)
- record_result()로 실시간 기록
- get_recommendation_prompt()로 decompose 프롬프트에 주입할 텍스트 생성
"""
import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import aiosqlite

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# 캐시 TTL (초) — 60초마다 DB에서 리프레시
_CACHE_TTL = 60


class _AgentTaskProfile:
    """에이전트 + task_type 단위 성과 프로파일"""

    __slots__ = (
        "agent_name", "task_type", "success_count", "fail_count",
        "total_duration_ms", "last_updated",
    )

    def __init__(self, agent_name: str, task_type: str):
        self.agent_name = agent_name
        self.task_type = task_type
        self.success_count: int = 0
        self.fail_count: int = 0
        self.total_duration_ms: int = 0
        self.last_updated: str = datetime.now().isoformat()

    @property
    def total_count(self) -> int:
        return self.success_count + self.fail_count

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    @property
    def avg_duration_ms(self) -> int:
        return self.total_duration_ms // self.total_count if self.total_count > 0 else 0

    def record(self, success: bool, duration_ms: int) -> None:
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
        self.total_duration_ms += duration_ms
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "total_count": self.total_count,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": self.avg_duration_ms,
            "last_updated": self.last_updated,
        }


class AgentPerformanceTracker:
    """에이전트 성과 추적기 — 메모리 캐시 + SQLite 동기화"""

    def __init__(self):
        settings = get_settings()
        self._db_path = str(settings.sqlite_path)
        # (agent_name, task_type) -> _AgentTaskProfile
        self._cache: Dict[tuple, _AgentTaskProfile] = {}
        self._cache_loaded_at: float = 0.0
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_table(self) -> None:
        """성과 집계 테이블 생성 (없으면)"""
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    agent_name      TEXT NOT NULL,
                    task_type       TEXT NOT NULL,
                    success_count   INTEGER NOT NULL DEFAULT 0,
                    fail_count      INTEGER NOT NULL DEFAULT 0,
                    total_duration_ms INTEGER NOT NULL DEFAULT 0,
                    last_updated    TEXT NOT NULL,
                    PRIMARY KEY (agent_name, task_type)
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_perf_agent "
                "ON agent_performance(agent_name)"
            )
            await db.commit()
        self._initialized = True

    async def _load_cache(self) -> None:
        """DB에서 캐시로 로드 (TTL 만료 시)"""
        now = time.monotonic()
        if now - self._cache_loaded_at < _CACHE_TTL and self._cache:
            return

        await self._ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM agent_performance")
            rows = await cursor.fetchall()

        new_cache: Dict[tuple, _AgentTaskProfile] = {}
        for row in rows:
            key = (row["agent_name"], row["task_type"])
            profile = _AgentTaskProfile(row["agent_name"], row["task_type"])
            profile.success_count = row["success_count"]
            profile.fail_count = row["fail_count"]
            profile.total_duration_ms = row["total_duration_ms"]
            profile.last_updated = row["last_updated"]
            new_cache[key] = profile

        self._cache = new_cache
        self._cache_loaded_at = now

    async def record_result(
        self,
        agent_name: str,
        task_type: str,
        success: bool,
        duration_ms: int,
    ) -> None:
        """성과 기록 — 캐시 업데이트 + DB 영속화"""
        await self._ensure_table()

        async with self._lock:
            key = (agent_name, task_type)
            profile = self._cache.get(key)
            if profile is None:
                profile = _AgentTaskProfile(agent_name, task_type)
                self._cache[key] = profile
            profile.record(success, duration_ms)

            # DB 동기화 (UPSERT)
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute("""
                        INSERT INTO agent_performance
                            (agent_name, task_type, success_count, fail_count,
                             total_duration_ms, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(agent_name, task_type) DO UPDATE SET
                            success_count = excluded.success_count,
                            fail_count = excluded.fail_count,
                            total_duration_ms = excluded.total_duration_ms,
                            last_updated = excluded.last_updated
                    """, (
                        agent_name,
                        task_type,
                        profile.success_count,
                        profile.fail_count,
                        profile.total_duration_ms,
                        profile.last_updated,
                    ))
                    await db.commit()
            except Exception as e:
                logger.warning("[Performance] DB 저장 실패: %s", e)

    async def get_agent_stats(self, agent_name: str) -> dict:
        """에이전트별 통계 반환"""
        await self._load_cache()

        profiles = [
            p for (a, _), p in self._cache.items()
            if a == agent_name
        ]

        if not profiles:
            return {
                "agent_name": agent_name,
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0,
                "task_types": [],
            }

        total_success = sum(p.success_count for p in profiles)
        total_fail = sum(p.fail_count for p in profiles)
        total_count = total_success + total_fail
        total_duration = sum(p.total_duration_ms for p in profiles)

        return {
            "agent_name": agent_name,
            "total_tasks": total_count,
            "success_count": total_success,
            "fail_count": total_fail,
            "success_rate": round(total_success / total_count, 4) if total_count > 0 else 0.0,
            "avg_duration_ms": total_duration // total_count if total_count > 0 else 0,
            "task_types": [p.to_dict() for p in profiles],
        }

    async def get_all_stats(self) -> list:
        """전체 에이전트 통계 반환"""
        await self._load_cache()

        # 에이전트별 그룹
        agent_names = sorted(set(a for a, _ in self._cache.keys()))
        result = []
        for name in agent_names:
            stats = await self.get_agent_stats(name)
            result.append(stats)
        return result

    async def get_recommendation_prompt(self) -> str:
        """decompose 프롬프트에 주입할 성과 요약 텍스트 생성

        예:
        - JX_CODER: coding 성공률 92% (23/25), 평균 45초
        - JX_RESEARCHER: research 성공률 88% (15/17), 평균 30초
        """
        await self._load_cache()

        if not self._cache:
            return ""

        lines = []
        # 에이전트별로 가장 많이 수행한 task_type 기준 통계
        agent_names = sorted(set(a for a, _ in self._cache.keys()))
        for agent_name in agent_names:
            if agent_name == "JINXUS_CORE":
                continue  # CORE는 조율 역할이므로 제외

            profiles = [
                p for (a, _), p in self._cache.items()
                if a == agent_name
            ]
            if not profiles:
                continue

            parts = []
            for p in sorted(profiles, key=lambda x: x.total_count, reverse=True):
                rate_pct = int(p.success_rate * 100)
                avg_sec = p.avg_duration_ms / 1000
                parts.append(
                    f"{p.task_type} 성공률 {rate_pct}% "
                    f"({p.success_count}/{p.total_count}), "
                    f"평균 {avg_sec:.0f}초"
                )

            lines.append(f"- {agent_name}: {' / '.join(parts)}")

        if not lines:
            return ""

        return "## 에이전트 과거 성과 데이터\n" + "\n".join(lines)


# ── 싱글톤 ──────────────────────────────────────────────────────────

_tracker: Optional[AgentPerformanceTracker] = None


def get_performance_tracker() -> AgentPerformanceTracker:
    """AgentPerformanceTracker 싱글톤 반환"""
    global _tracker
    if _tracker is None:
        _tracker = AgentPerformanceTracker()
    return _tracker
