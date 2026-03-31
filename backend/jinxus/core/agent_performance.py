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


# ═══════════════════════════════════════════════════════════════════════
# Multi-Dimensional Evaluation — SOTOPIA-EVAL 기반
# 단순 성공/실패를 넘어 5차원으로 에이전트 성과를 평가
# ═══════════════════════════════════════════════════════════════════════

class EvalDimension:
    """평가 차원 정의"""
    GOAL_COMPLETION = "goal_completion"       # 목표 달성도
    EFFICIENCY = "efficiency"                 # 효율성 (속도, 리소스)
    COLLABORATION = "collaboration"           # 협업 기여도
    KNOWLEDGE = "knowledge"                   # 지식 활용도
    COMPLIANCE = "compliance"                 # 규칙/지침 준수도

    ALL = [GOAL_COMPLETION, EFFICIENCY, COLLABORATION, KNOWLEDGE, COMPLIANCE]


class MultiDimEvaluation:
    """다차원 에이전트 평가 시스템

    SOTOPIA-EVAL에서 영감: 단일 점수 대신 여러 차원으로 평가하여
    에이전트의 강점/약점을 정밀하게 파악한다.

    사용:
        evaluator = MultiDimEvaluation()
        scores = evaluator.evaluate(result, context)
        profile = evaluator.get_profile("JX_CODER")
    """

    def __init__(self):
        # agent_name → {dimension: [scores]}
        self._history: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def evaluate(
        self,
        result: dict,
        context: Optional[dict] = None,
    ) -> dict[str, float]:
        """에이전트 결과를 5차원으로 평가

        Args:
            result: 에이전트 실행 결과
                - agent_name, success, output, duration_ms, tools_used, etc.
            context: 추가 컨텍스트
                - expected_output, instruction, collaboration_session, etc.

        Returns:
            {dimension: score} (각 0.0 ~ 1.0)
        """
        context = context or {}
        agent_name = result.get("agent_name", "unknown")
        scores = {}

        # 1. 목표 달성도
        scores[EvalDimension.GOAL_COMPLETION] = self._eval_goal(result, context)

        # 2. 효율성
        scores[EvalDimension.EFFICIENCY] = self._eval_efficiency(result)

        # 3. 협업 기여도
        scores[EvalDimension.COLLABORATION] = self._eval_collaboration(result, context)

        # 4. 지식 활용도
        scores[EvalDimension.KNOWLEDGE] = self._eval_knowledge(result)

        # 5. 규칙 준수도
        scores[EvalDimension.COMPLIANCE] = self._eval_compliance(result)

        # 이력에 저장
        for dim, score in scores.items():
            self._history[agent_name][dim].append(score)
            # 최근 50건만 유지
            if len(self._history[agent_name][dim]) > 50:
                self._history[agent_name][dim] = self._history[agent_name][dim][-50:]

        return scores

    def _eval_goal(self, result: dict, context: dict) -> float:
        """목표 달성도 평가"""
        if not result.get("success"):
            return 0.1  # 실패해도 시도는 했으므로 0.1

        score = result.get("success_score", 0.7)

        # 출력이 충분한가
        output = result.get("output", "")
        if len(output) < 10:
            score *= 0.5  # 너무 짧은 응답

        return min(1.0, score)

    def _eval_efficiency(self, result: dict) -> float:
        """효율성 평가 (속도 기준)"""
        duration = result.get("duration_ms", 0)

        if duration <= 0:
            return 0.5  # 측정 불가

        # 5초 이하: 1.0, 30초: 0.7, 60초: 0.4, 120초+: 0.2
        if duration <= 5000:
            return 1.0
        elif duration <= 30000:
            return 0.7 + 0.3 * (30000 - duration) / 25000
        elif duration <= 60000:
            return 0.4 + 0.3 * (60000 - duration) / 30000
        elif duration <= 120000:
            return 0.2 + 0.2 * (120000 - duration) / 60000
        else:
            return 0.2

    def _eval_collaboration(self, result: dict, context: dict) -> float:
        """협업 기여도 평가"""
        score = 0.5  # 기본

        # 워크스페이스에 결과 공유했는가
        if context.get("shared_to_workspace"):
            score += 0.2

        # 다른 에이전트의 결과를 참조했는가
        if context.get("used_peer_context"):
            score += 0.15

        # 도움 요청에 응답했는가
        if context.get("responded_to_help"):
            score += 0.15

        return min(1.0, score)

    def _eval_knowledge(self, result: dict) -> float:
        """지식 활용도 평가"""
        score = 0.5

        # 도구 사용 여부
        tools_used = result.get("tools_used", [])
        if tools_used:
            score += min(0.3, len(tools_used) * 0.1)

        # 출력에 구체적 근거가 있는가 (간이 체크)
        output = result.get("output", "")
        if any(marker in output for marker in ["http", "참고:", "근거:", "출처:", "```"]):
            score += 0.2

        return min(1.0, score)

    def _eval_compliance(self, result: dict) -> float:
        """규칙 준수도 평가"""
        score = 1.0

        # 실패했는데 에러 로깅 안 한 경우
        if not result.get("success") and not result.get("failure_reason"):
            score -= 0.3

        # 금지 도구 사용 시 (tool_policy 위반)
        if result.get("policy_violations"):
            score -= 0.2 * len(result["policy_violations"])

        return max(0.0, score)

    def get_profile(self, agent_name: str) -> dict:
        """에이전트의 다차원 성과 프로필 반환

        Returns:
            {
                "agent_name": str,
                "dimensions": {dim: {"avg": float, "trend": str, "count": int}},
                "overall_score": float,
                "strongest": str,
                "weakest": str,
            }
        """
        if agent_name not in self._history:
            return {
                "agent_name": agent_name,
                "dimensions": {},
                "overall_score": 0.0,
                "strongest": None,
                "weakest": None,
            }

        dimensions = {}
        for dim in EvalDimension.ALL:
            scores = self._history[agent_name].get(dim, [])
            if not scores:
                dimensions[dim] = {"avg": 0.0, "trend": "none", "count": 0}
                continue

            avg = sum(scores) / len(scores)

            # 최근 트렌드 (최근 5개 vs 이전 5개)
            if len(scores) >= 10:
                recent = sum(scores[-5:]) / 5
                earlier = sum(scores[-10:-5]) / 5
                if recent > earlier + 0.05:
                    trend = "improving"
                elif recent < earlier - 0.05:
                    trend = "declining"
                else:
                    trend = "stable"
            else:
                trend = "insufficient_data"

            dimensions[dim] = {
                "avg": round(avg, 3),
                "trend": trend,
                "count": len(scores),
            }

        # 전체 평균
        avgs = [d["avg"] for d in dimensions.values() if d["count"] > 0]
        overall = sum(avgs) / len(avgs) if avgs else 0.0

        # 최강/최약 차원
        sorted_dims = sorted(
            [(d, v["avg"]) for d, v in dimensions.items() if v["count"] > 0],
            key=lambda x: x[1],
        )

        return {
            "agent_name": agent_name,
            "dimensions": dimensions,
            "overall_score": round(overall, 3),
            "strongest": sorted_dims[-1][0] if sorted_dims else None,
            "weakest": sorted_dims[0][0] if sorted_dims else None,
        }

    def get_recommendation(self, agent_name: str) -> list[str]:
        """에이전트별 개선 권고사항 생성"""
        profile = self.get_profile(agent_name)
        recommendations = []

        for dim, data in profile.get("dimensions", {}).items():
            if data["avg"] < 0.4 and data["count"] >= 3:
                labels = {
                    EvalDimension.GOAL_COMPLETION: "목표 달성률이 낮습니다. 작업 이해도를 높이세요.",
                    EvalDimension.EFFICIENCY: "실행 속도가 느립니다. 도구 선택을 최적화하세요.",
                    EvalDimension.COLLABORATION: "협업 기여가 부족합니다. 결과 공유를 늘리세요.",
                    EvalDimension.KNOWLEDGE: "도구/지식 활용이 부족합니다. 관련 도구를 더 사용하세요.",
                    EvalDimension.COMPLIANCE: "규칙 준수가 미흡합니다. 에러 핸들링을 강화하세요.",
                }
                recommendations.append(labels.get(dim, f"{dim} 개선 필요"))

            if data.get("trend") == "declining":
                recommendations.append(f"{dim} 성과가 하락 추세입니다.")

        return recommendations


# ── 싱글톤 ──────────────────────────────────────────────────────────

_tracker: Optional[AgentPerformanceTracker] = None


def get_performance_tracker() -> AgentPerformanceTracker:
    """AgentPerformanceTracker 싱글톤 반환"""
    global _tracker
    if _tracker is None:
        _tracker = AgentPerformanceTracker()
    return _tracker


# 싱글톤
_evaluator: Optional[MultiDimEvaluation] = None


def get_multi_dim_evaluator() -> MultiDimEvaluation:
    """MultiDimEvaluation 싱글톤 반환"""
    global _evaluator
    if _evaluator is None:
        _evaluator = MultiDimEvaluation()
    return _evaluator
