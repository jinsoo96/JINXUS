"""JX_RESEARCHER 하위 전문가 에이전트 팀

JX_RESEARCHER가 미니 오케스트레이터로서 이 전문가들을 관리한다.
JINXUS_CORE의 글로벌 레지스트리에는 등록되지 않음.
"""
from .jx_web_searcher import JXWebSearcher
from .jx_deep_reader import JXDeepReader
from .jx_fact_checker import JXFactChecker

__all__ = [
    "JXWebSearcher",
    "JXDeepReader",
    "JXFactChecker",
]

# 전문가 이름 → 클래스 매핑
RESEARCH_SPECIALISTS = {
    "JX_WEB_SEARCHER": JXWebSearcher,
    "JX_DEEP_READER": JXDeepReader,
    "JX_FACT_CHECKER": JXFactChecker,
}
