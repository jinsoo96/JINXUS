"""FastAPI 공통 의존성"""
from jinxus.core import get_orchestrator
from jinxus.core.orchestrator import Orchestrator


async def get_ready_orchestrator() -> Orchestrator:
    """초기화된 오케스트레이터 반환 (필요 시 초기화 수행)"""
    orchestrator = get_orchestrator()
    if not orchestrator.is_initialized:
        await orchestrator.initialize()
    return orchestrator
