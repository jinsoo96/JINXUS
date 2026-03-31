"""Smart Router v1.0.0 — 자동 라우팅

사용자 메시지를 분석하여 최적 실행 경로로 자동 라우팅한다.

분류:
- chat: 일상 대화, 인사, 감정 표현 → JINXUS_CORE 직접 응답
- task: 도구 필요한 단일 작업 → JINXUS_CORE 그래프 실행
- background: 장시간 자율 작업 → BackgroundWorker (AutonomousRunner)
- project: 다단계 대규모 프로젝트 → ProjectManager (Phase 분해)

2단계 분류:
1. 패턴 매칭 (빠름, 무료) → 확실한 케이스 즉시 반환
2. LLM 판단 (느림, 유료) → 애매한 케이스만 호출
"""
import logging
import time
from enum import Enum

from anthropic import AsyncAnthropic
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


class RouteType(str, Enum):
    CHAT = "chat"
    TASK = "task"
    BACKGROUND = "background"
    PROJECT = "project"


# 프로젝트 키워드 (다단계 복합 작업)
_PROJECT_PATTERNS = [
    "프로젝트", "시스템 만들", "앱 만들", "웹사이트 만들", "서비스 만들",
    "플랫폼 만들", "전체 설계", "아키텍처", "풀스택",
    "end-to-end", "e2e", "처음부터 끝까지",
    "여러 단계", "단계별로", "phase", "마일스톤",
    # 복합 구조 키워드
    "파이프라인", "에이전트를 만들", "봇을 만들", "봇 만들",
    "경로에", "테스트 코드", "기반으로",
    "모듈", "구성해", "구조",
]

# 백그라운드 키워드 (장시간 자율 작업 — 반복/수집 성격)
_BACKGROUND_PATTERNS = [
    "백그라운드", "밤새", "자율", "autonomous",
    "오래 걸", "시간 걸", "천천히", "꼼꼼히",
    "전부 분석", "전체 분석", "깊이 분석", "심층",
    "모니터링해", "감시해", "수집해",
    "대량", "일괄", "벌크", "batch",
    "리팩토링 전체", "전체 코드", "코드베이스",
    # 레포/리포지토리 분석 (GitHub 클론 + 코드 분석 필요)
    "레포 분석", "레포분석", "리포 분석", "리포지토리 분석",
    "repo 분석", "repository 분석",
]

# GitHub URL 패턴 (URL + 분석성 키워드 → background)
import re
_GITHUB_URL_RE = re.compile(r"github\.com/[\w\-]+/[\w\-]+", re.IGNORECASE)
_ANALYSIS_KEYWORDS = [
    "분석", "살펴", "파악", "리뷰", "조사", "알아봐", "봐줘", "확인",
    "analyze", "review", "check", "look", "inspect",
]

# 복합 작업 지표 (여러 개가 동시에 나오면 project)
_COMPOUND_MARKERS = [
    "그리고", "또한", "다음으로", "이후에",
    "1.", "2.", "3.", "첫째", "둘째",
    "- ", "① ", "② ",
    "만들고", "하고", "작성하고", "분석하고",
    "→",  # 파이프라인 화살표
]

# 메시지 길이 기반 분류 임계값
_SHORT_THRESHOLD = 50    # 이하 → chat/task
_LONG_THRESHOLD = 200    # 이상 → background/project 후보


_CLASSIFY_PROMPT = """사용자의 요청을 분류해.

입력: "{user_input}"

A) chat — 일상 대화, 인사, 잡담, 짧은 질문 (도구 불필요)
B) task — 단일 작업 (검색, 코드 수정, 파일 생성 등). 수 분 이내 완료 가능
C) background — 장시간 자율 작업 (대규모 분석, 크롤링, 일괄 처리). 수십 분~수 시간 소요
D) project — 다단계 복합 프로젝트 (여러 단계/팀이 필요, 설계→구현→테스트 등)

판단 기준:
- 단일 동사 + 단일 대상 → task
- 여러 동사 + 여러 대상 + "그리고/또한" → project
- "밤새/전체/깊이/대량" + 작업 동사 → background
- GitHub/레포/리포지토리 분석 요청 → background (코드 클론+분석 필요)
- 3단계 이상 명시적 나열 → project

한 단어만 답해: chat / task / background / project"""


class SmartRouter:
    """사용자 메시지 자동 라우팅"""

    def __init__(self):
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._fast_model = settings.claude_fast_model

    async def classify(self, user_input: str) -> RouteType:
        """메시지를 분류하여 최적 실행 경로 반환

        Returns:
            RouteType: CHAT, TASK, BACKGROUND, PROJECT
        """
        start = time.time()
        stripped = user_input.strip()
        lower = stripped.lower()

        # === 1단계: 패턴 매칭 (빠른 판별) ===

        # 매우 짧은 입력 → chat
        if len(stripped) < 10:
            logger.debug(f"[SmartRouter] 짧은 입력 → chat ({len(stripped)}자)")
            return RouteType.CHAT

        # GitHub URL + 분석 키워드 → background (레포 분석은 시간 걸림)
        if _GITHUB_URL_RE.search(lower):
            if any(k in lower for k in _ANALYSIS_KEYWORDS):
                logger.info("[SmartRouter] GitHub URL + 분석 키워드 → background")
                return RouteType.BACKGROUND

        # 프로젝트 키워드 매칭
        project_score = sum(1 for p in _PROJECT_PATTERNS if p in lower)
        compound_count = sum(1 for m in _COMPOUND_MARKERS if m in stripped)

        if project_score >= 2:
            logger.info(f"[SmartRouter] 프로젝트 패턴 {project_score}개 → project")
            return RouteType.PROJECT

        # 프로젝트 패턴 1개 + 복합 마커 2개 이상 + 긴 메시지 → project
        if project_score >= 1 and compound_count >= 2 and len(stripped) > 100:
            logger.info(
                f"[SmartRouter] 프로젝트 패턴 {project_score} + 복합 마커 {compound_count} → project"
            )
            return RouteType.PROJECT

        if compound_count >= 3 and len(stripped) > _LONG_THRESHOLD:
            logger.info(f"[SmartRouter] 복합 마커 {compound_count}개 + 긴 입력 → project")
            return RouteType.PROJECT

        # 백그라운드 키워드 매칭
        bg_score = sum(1 for p in _BACKGROUND_PATTERNS if p in lower)
        if bg_score >= 2:
            logger.info(f"[SmartRouter] 백그라운드 패턴 {bg_score}개 → background")
            return RouteType.BACKGROUND

        # 짧은 입력 + 키워드 없음 → JINXUS_CORE의 기존 분류에 위임 (chat/task)
        if len(stripped) < _SHORT_THRESHOLD:
            logger.debug(f"[SmartRouter] 짧은 입력, 기존 분류 위임 → task")
            return RouteType.TASK

        # === 2단계: LLM 판단 (애매한 케이스) ===
        try:
            response = await self._client.messages.create(
                model=self._fast_model,
                max_tokens=10,
                messages=[{
                    "role": "user",
                    "content": _CLASSIFY_PROMPT.format(user_input=user_input[:500]),
                }],
            )

            result = response.content[0].text.strip().lower()
            elapsed_ms = (time.time() - start) * 1000

            if "project" in result:
                route = RouteType.PROJECT
            elif "background" in result:
                route = RouteType.BACKGROUND
            elif "chat" in result:
                route = RouteType.CHAT
            else:
                route = RouteType.TASK

            logger.info(
                f"[SmartRouter] LLM 분류 → {route.value} ({elapsed_ms:.0f}ms)"
            )
            return route

        except Exception as e:
            logger.warning(f"[SmartRouter] LLM 분류 실패, task로 폴백: {e}")
            return RouteType.TASK


# 싱글톤
_instance: SmartRouter | None = None


def get_smart_router() -> SmartRouter:
    global _instance
    if _instance is None:
        _instance = SmartRouter()
    return _instance
