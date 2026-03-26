"""JINXUS 에이전트 시스템

에이전트 자동 스캔: agents/ 디렉토리의 모든 에이전트 클래스를 자동 등록한다.
새 에이전트 추가 시 파일만 만들면 자동으로 레지스트리에 포함된다.
"""
import importlib
import inspect
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 명시적 import (타입 힌트, 직접 참조용)
from .jinxus_core import JinxusCore

__all__ = [
    "JinxusCore",
    "AGENT_REGISTRY",
    "register_all_agents",
    "get_agent",
    "create_jinxus_core",
]


# 에이전트 레지스트리
AGENT_REGISTRY: dict = {}


def _scan_agents() -> dict:
    """agents/ 디렉토리에서 에이전트 클래스를 자동 스캔하여 등록

    규칙:
    - jx_*.py 또는 js_*.py 파일을 스캔
    - 'name' 클래스 속성이 있고, run() 메서드가 있는 클래스를 에이전트로 인식
    - JinxusCore, BaseAgent는 제외
    """
    agents = {}
    agents_dir = Path(__file__).parent

    for py_file in [*sorted(agents_dir.glob("jx_*.py")), *sorted(agents_dir.glob("js_*.py"))]:
        module_name = py_file.stem
        try:
            module = importlib.import_module(f"jinxus.agents.{module_name}")

            for attr_name in dir(module):
                cls = getattr(module, attr_name)
                if (
                    inspect.isclass(cls)
                    and hasattr(cls, "name")
                    and hasattr(cls, "run")
                    and cls.__name__ not in ("BaseAgent", "JinxusCore")
                    and cls.__module__ == module.__name__
                ):
                    instance = cls()
                    agents[instance.name] = instance
                    logger.debug(f"에이전트 자동 등록: {instance.name} ({cls.__name__})")

        except Exception as e:
            logger.error(f"에이전트 스캔 실패 [{module_name}]: {e}")

    return agents


def register_all_agents() -> dict:
    """모든 에이전트 등록 및 반환"""
    global AGENT_REGISTRY

    if not AGENT_REGISTRY:
        AGENT_REGISTRY = _scan_agents()
        logger.info(f"에이전트 {len(AGENT_REGISTRY)}개 등록: {list(AGENT_REGISTRY.keys())}")

    return AGENT_REGISTRY


def get_agent(name: str):
    """이름으로 에이전트 조회"""
    if not AGENT_REGISTRY:
        register_all_agents()
    return AGENT_REGISTRY.get(name)


def create_jinxus_core() -> JinxusCore:
    """JINXUS_CORE 생성 및 에이전트 등록"""
    core = JinxusCore()

    # 모든 에이전트 등록
    agents = register_all_agents()
    for agent in agents.values():
        core.register_agent(agent)

    # 수직 위임: 임원 에이전트에게 팀원 인스턴스 주입
    for agent in agents.values():
        if hasattr(agent, "set_team") and callable(agent.set_team):
            agent.set_team(agents)

    return core
