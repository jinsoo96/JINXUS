from .jinxus_core import JinxusCore
from .jx_coder import JXCoder
from .jx_researcher import JXResearcher
from .jx_writer import JXWriter
from .jx_analyst import JXAnalyst
from .jx_ops import JXOps
from .js_persona import JSPersona

__all__ = [
    "JinxusCore",
    "JXCoder",
    "JXResearcher",
    "JXWriter",
    "JXAnalyst",
    "JXOps",
    "JSPersona",
]


# 에이전트 레지스트리
AGENT_REGISTRY: dict = {}


def register_all_agents() -> dict:
    """모든 에이전트 등록 및 반환"""
    global AGENT_REGISTRY

    if not AGENT_REGISTRY:
        AGENT_REGISTRY = {
            "JX_CODER": JXCoder(),
            "JX_RESEARCHER": JXResearcher(),
            "JX_WRITER": JXWriter(),
            "JX_ANALYST": JXAnalyst(),
            "JX_OPS": JXOps(),
            "JS_PERSONA": JSPersona(),
        }

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

    return core
