"""MissionRouter v1.0.0 — 입력을 미션으로 변환

모든 사용자 입력을 미션으로 변환한다.
SmartRouter의 분류 로직을 확장하여 미션 타입/제목/설명을 생성.

분류:
- QUICK: 간단 질문, 인사, 잡담 (도구 불필요)
- STANDARD: 단일 작업 (검색, 코드 수정 등)
- EPIC: 장시간 대규모 작업
- RAID: 멀티에이전트 협업 필수 프로젝트
"""
import logging
import time
import uuid
from typing import Optional

from anthropic import AsyncAnthropic
from jinxus.config import get_settings
from jinxus.core.mission import (
    Mission, MissionType, MissionStatus, get_mission_store,
)

logger = logging.getLogger(__name__)


# 패턴 매칭 (SmartRouter 기반 확장)
_RAID_PATTERNS = [
    "프로젝트", "시스템 만들", "앱 만들", "웹사이트 만들", "서비스 만들",
    "플랫폼 만들", "전체 설계", "아키텍처", "풀스택",
    "end-to-end", "e2e", "처음부터 끝까지",
    "여러 단계", "단계별로", "phase", "마일스톤",
    "파이프라인", "에이전트를 만들", "봇을 만들",
]

_EPIC_PATTERNS = [
    "백그라운드", "밤새", "자율", "autonomous",
    "오래 걸", "시간 걸", "천천히", "꼼꼼히",
    "전부 분석", "전체 분석", "깊이 분석", "심층",
    "모니터링해", "감시해", "수집해",
    "대량", "일괄", "벌크", "batch",
    "리팩토링 전체", "전체 코드", "코드베이스",
]

_COMPOUND_MARKERS = [
    "그리고", "또한", "다음으로", "이후에",
    "1.", "2.", "3.", "첫째", "둘째",
    "- ", "만들고", "하고", "작성하고", "분석하고",
]

_CLASSIFY_PROMPT = """사용자 요청을 분석하여 미션을 생성해.

입력: "{user_input}"

다음 JSON 형식으로만 답해 (다른 텍스트 없이):
{{"type": "quick|standard|epic|raid", "title": "미션 제목 (15자 이내)", "agents": ["필요한 에이전트 코드명"]}}

미션 타입 기준:
- quick: 일상 대화, 인사, 잡담, 간단 질문 (에이전트 불필요)
- standard: 단일 작업 (검색, 코드 수정, 문서 작성 등)
- epic: 장시간 대규모 작업 (대량 분석, 크롤링 등)
- raid: 다단계 복합 프로젝트 (여러 에이전트 협업 필수)

에이전트 목록:
- JINXUS_CORE: 총괄 지휘
- JX_CODER: 코딩 전문 (JX_FRONTEND, JX_BACKEND, JX_INFRA, JX_REVIEWER, JX_TESTER 포함)
- JX_RESEARCHER: 조사/검색 (JX_WEB_SEARCHER, JX_DEEP_READER, JX_FACT_CHECKER 포함)
- JX_WRITER: 문서/글 작성
- JX_ANALYST: 데이터 분석
- JX_OPS: 인프라/운영
- JX_PRODUCT: 기획
- JX_MARKETING: 마케팅

quick이면 agents는 ["JINXUS_CORE"]만."""


class MissionRouter:
    """사용자 입력 → 미션 변환"""

    def __init__(self):
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._fast_model = settings.claude_fast_model
        self._store = get_mission_store()

    async def create_mission(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> Mission:
        """사용자 입력을 미션으로 변환"""
        start = time.time()
        stripped = user_input.strip()
        lower = stripped.lower()
        mission_id = f"m-{uuid.uuid4().hex[:8]}"

        # === 1단계: 패턴 매칭 (빠른 판별) ===
        mission_type, title, agents = self._pattern_classify(stripped, lower)

        if mission_type and title:
            elapsed = (time.time() - start) * 1000
            logger.info(f"[MissionRouter] 패턴 → {mission_type.value} '{title}' ({elapsed:.0f}ms)")
        else:
            # === 2단계: LLM 분류 ===
            mission_type, title, agents = await self._llm_classify(user_input)
            elapsed = (time.time() - start) * 1000
            logger.info(f"[MissionRouter] LLM → {mission_type.value} '{title}' ({elapsed:.0f}ms)")

        mission = Mission(
            id=mission_id,
            title=title,
            description=user_input,
            type=mission_type,
            status=MissionStatus.BRIEFING,
            assigned_agents=agents,
            session_id=session_id,
            original_input=user_input,
        )

        await self._store.save(mission)
        return mission

    def _pattern_classify(
        self, stripped: str, lower: str
    ) -> tuple[Optional[MissionType], Optional[str], list[str]]:
        """패턴 매칭 분류 — 확실한 케이스만"""

        # 매우 짧은 입력 → QUICK
        if len(stripped) < 10:
            return MissionType.QUICK, stripped[:15] or "간단 질의", ["JINXUS_CORE"]

        # RAID 패턴
        raid_score = sum(1 for p in _RAID_PATTERNS if p in lower)
        compound_count = sum(1 for m in _COMPOUND_MARKERS if m in stripped)

        if raid_score >= 2:
            return MissionType.RAID, None, []  # 제목은 LLM에서

        if raid_score >= 1 and compound_count >= 2 and len(stripped) > 100:
            return MissionType.RAID, None, []

        if compound_count >= 3 and len(stripped) > 200:
            return MissionType.RAID, None, []

        # EPIC 패턴
        epic_score = sum(1 for p in _EPIC_PATTERNS if p in lower)
        if epic_score >= 2:
            return MissionType.EPIC, None, []

        # 짧은 입력 → QUICK 또는 STANDARD
        if len(stripped) < 50:
            return MissionType.STANDARD, None, []

        # 나머지 → LLM에 위임
        return None, None, []

    async def _llm_classify(
        self, user_input: str
    ) -> tuple[MissionType, str, list[str]]:
        """LLM으로 미션 분류 + 제목 + 에이전트 추천"""
        try:
            import json
            response = await self._client.messages.create(
                model=self._fast_model,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": _CLASSIFY_PROMPT.format(user_input=user_input[:500]),
                }],
            )

            text = response.content[0].text.strip()
            # JSON 추출 (```json 블록 대응)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)

            type_map = {
                "quick": MissionType.QUICK,
                "standard": MissionType.STANDARD,
                "epic": MissionType.EPIC,
                "raid": MissionType.RAID,
            }
            mission_type = type_map.get(data.get("type", "standard"), MissionType.STANDARD)
            title = data.get("title", user_input[:15])
            agents = data.get("agents", ["JINXUS_CORE"])

            return mission_type, title, agents

        except Exception as e:
            logger.warning(f"[MissionRouter] LLM 분류 실패, STANDARD 폴백: {e}")
            return MissionType.STANDARD, user_input[:15], ["JINXUS_CORE"]


# 싱글톤
_router: Optional[MissionRouter] = None


def get_mission_router() -> MissionRouter:
    global _router
    if _router is None:
        _router = MissionRouter()
    return _router
