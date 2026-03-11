"""JX_CODER 하위 전문가 에이전트 팀

JX_CODER가 미니 오케스트레이터로서 이 전문가들을 관리한다.
JINXUS_CORE의 글로벌 레지스트리에는 등록되지 않음.
"""
from .jx_frontend import JXFrontend
from .jx_backend import JXBackend
from .jx_infra import JXInfra
from .jx_reviewer import JXReviewer
from .jx_tester import JXTester

__all__ = [
    "JXFrontend",
    "JXBackend",
    "JXInfra",
    "JXReviewer",
    "JXTester",
]

# 전문가 이름 → 클래스 매핑
CODING_SPECIALISTS = {
    "JX_FRONTEND": JXFrontend,
    "JX_BACKEND": JXBackend,
    "JX_INFRA": JXInfra,
    "JX_REVIEWER": JXReviewer,
    "JX_TESTER": JXTester,
}
