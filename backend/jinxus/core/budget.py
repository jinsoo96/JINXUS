"""Budget Enforcement — API 비용 추적 (Paperclip 패턴)

에이전트별/월별 API 비용 추적. ok→warning→hard_stop 3단계.
초과 시 자동 pause. 리소스 낭비 방지 원칙 구현.
"""
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

import redis.asyncio as aioredis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# Redis 키
_COST_KEY = "jinxus:cost:{year_month}:{agent}"
_BUDGET_KEY = "jinxus:budget:{agent}"
_GLOBAL_BUDGET_KEY = "jinxus:budget:global"

# Claude API 가격 (per 1M tokens, USD, 2025-04 기준)
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "default": {"input": 3.0, "output": 15.0},
}

# 기본 월 예산 (USD)
DEFAULT_MONTHLY_BUDGET = 100.0
WARNING_THRESHOLD = 0.75    # 75%에서 경고
HARD_STOP_THRESHOLD = 0.95  # 95%에서 중지


class BudgetStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    HARD_STOP = "hard_stop"


@dataclass
class CostEvent:
    """비용 이벤트"""
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class BudgetReport:
    """예산 보고서"""
    agent: str
    month: str
    total_cost_usd: float
    budget_usd: float
    usage_percent: float
    status: str
    event_count: int
    top_models: dict = field(default_factory=dict)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """API 호출 비용 계산 (USD)"""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


class BudgetManager:
    """예산 관리자"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            settings = get_settings()
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                decode_responses=True,
            )
        return self._redis

    def _current_month(self) -> str:
        return datetime.now().strftime("%Y-%m")

    async def record_cost(
        self,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str = "",
    ) -> CostEvent:
        """비용 기록"""
        cost = calculate_cost(model, input_tokens, output_tokens)
        event = CostEvent(
            agent=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            task_id=task_id,
        )

        r = await self._get_redis()
        month = self._current_month()
        key = _COST_KEY.format(year_month=month, agent=agent)

        await r.rpush(key, json.dumps(asdict(event), ensure_ascii=False))
        # 월말 자동 만료 (45일)
        await r.expire(key, 86400 * 45)

        return event

    async def get_agent_cost(self, agent: str, month: Optional[str] = None) -> float:
        """에이전트 월간 누적 비용"""
        r = await self._get_redis()
        month = month or self._current_month()
        key = _COST_KEY.format(year_month=month, agent=agent)

        events = await r.lrange(key, 0, -1)
        total = 0.0
        for raw in events:
            try:
                ev = json.loads(raw)
                total += ev.get("cost_usd", 0.0)
            except json.JSONDecodeError:
                continue
        return round(total, 4)

    async def get_total_cost(self, month: Optional[str] = None) -> float:
        """전체 월간 누적 비용"""
        r = await self._get_redis()
        month = month or self._current_month()
        total = 0.0

        async for key in r.scan_iter(match=f"jinxus:cost:{month}:*"):
            events = await r.lrange(key, 0, -1)
            for raw in events:
                try:
                    ev = json.loads(raw)
                    total += ev.get("cost_usd", 0.0)
                except json.JSONDecodeError:
                    continue

        return round(total, 4)

    async def set_budget(self, agent: str, budget_usd: float) -> None:
        """에이전트별 월 예산 설정"""
        r = await self._get_redis()
        key = _BUDGET_KEY.format(agent=agent)
        await r.set(key, str(budget_usd))

    async def set_global_budget(self, budget_usd: float) -> None:
        """전체 월 예산 설정"""
        r = await self._get_redis()
        await r.set(_GLOBAL_BUDGET_KEY, str(budget_usd))

    async def get_budget(self, agent: str) -> float:
        """에이전트 월 예산 조회"""
        r = await self._get_redis()
        key = _BUDGET_KEY.format(agent=agent)
        val = await r.get(key)
        if val:
            return float(val)

        # 글로벌 예산 fallback
        global_val = await r.get(_GLOBAL_BUDGET_KEY)
        if global_val:
            return float(global_val)

        return DEFAULT_MONTHLY_BUDGET

    async def check_budget(self, agent: str) -> BudgetStatus:
        """예산 상태 확인"""
        cost = await self.get_agent_cost(agent)
        budget = await self.get_budget(agent)

        if budget <= 0:
            return BudgetStatus.OK

        ratio = cost / budget
        if ratio >= HARD_STOP_THRESHOLD:
            logger.warning(f"[Budget] {agent} HARD_STOP: ${cost:.2f}/${budget:.2f} ({ratio:.0%})")
            return BudgetStatus.HARD_STOP
        elif ratio >= WARNING_THRESHOLD:
            logger.warning(f"[Budget] {agent} WARNING: ${cost:.2f}/${budget:.2f} ({ratio:.0%})")
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    async def should_block(self, agent: str) -> bool:
        """에이전트 실행 차단 여부"""
        status = await self.check_budget(agent)
        return status == BudgetStatus.HARD_STOP

    async def get_report(self, agent: str, month: Optional[str] = None) -> BudgetReport:
        """예산 보고서"""
        r = await self._get_redis()
        month = month or self._current_month()
        key = _COST_KEY.format(year_month=month, agent=agent)

        events = await r.lrange(key, 0, -1)
        total_cost = 0.0
        model_costs: dict[str, float] = {}

        for raw in events:
            try:
                ev = json.loads(raw)
                cost = ev.get("cost_usd", 0.0)
                total_cost += cost
                model = ev.get("model", "unknown")
                model_costs[model] = model_costs.get(model, 0.0) + cost
            except json.JSONDecodeError:
                continue

        budget = await self.get_budget(agent)
        usage_percent = (total_cost / budget * 100) if budget > 0 else 0.0
        status = (await self.check_budget(agent)).value

        return BudgetReport(
            agent=agent,
            month=month,
            total_cost_usd=round(total_cost, 4),
            budget_usd=budget,
            usage_percent=round(usage_percent, 1),
            status=status,
            event_count=len(events),
            top_models={k: round(v, 4) for k, v in sorted(model_costs.items(), key=lambda x: -x[1])},
        )

    async def get_all_reports(self, month: Optional[str] = None) -> list[BudgetReport]:
        """전체 에이전트 예산 보고서"""
        r = await self._get_redis()
        month = month or self._current_month()
        reports = []

        agents = set()
        async for key in r.scan_iter(match=f"jinxus:cost:{month}:*"):
            agent = key.split(":")[-1]
            agents.add(agent)

        for agent in sorted(agents):
            report = await self.get_report(agent, month)
            reports.append(report)

        return reports

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_budget_manager: Optional[BudgetManager] = None


def get_budget_manager() -> BudgetManager:
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = BudgetManager()
    return _budget_manager
