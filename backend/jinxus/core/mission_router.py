"""MissionRouter v2.0.0 — LLM 기반 미션 분류

모든 사용자 입력을 미션으로 변환한다.
LLM(haiku)이 난이도/제목/에이전트를 판단.

분류:
- QUICK: 간단 질문, 인사, 잡담 (도구 불필요)
- STANDARD: 단일 작업 (검색, 코드 수정 등)
- EPIC: 장시간/복합 작업
- RAID: 멀티에이전트 협업 필수 프로젝트

v2.0.0: 하드코딩 패턴 매칭 → LLM 기반 분류
- 10자 이하 인사/잡담만 패턴으로 빠른 분기
- 나머지 전부 LLM 판단
- LLM 실패 시 STANDARD fallback
"""
import json
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

# 10자 이하 인사/잡담 → QUICK 즉시 반환 (LLM 호출 절약)
_GREETING_PATTERNS = [
    "안녕", "하이", "ㅎㅇ", "hello", "hi", "hey",
    "고마워", "감사", "ㄱㅅ", "ㅇㅇ", "ㅇㅋ", "ㄱㄱ",
    "뭐해", "심심", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ",
    "맞아", "그래", "아니", "좋아", "알겠",
    "잘했", "수고", "오케이", "ok", "네", "응",
]

_CLASSIFY_PROMPT = """사용자의 요청을 분석하여 미션 유형을 분류하고, 제목과 필요한 에이전트를 판단해.

## 미션 유형
- **quick**: 인사, 잡담, 간단 질문, 개념 설명, 의견 요청 (도구 불필요, 지식만으로 답변 가능)
- **standard**: 단일 작업 (파일 수정, 검색 1건, 간단한 코드 수정 등). 동작이 1개뿐인 요청
- **epic**: 복합 작업 (여러 동작 연결, 조사+작성, 분석+개선, URL 참고 작업 등). 동작이 2개 이상이거나 시간이 걸리는 작업
- **raid**: 대규모 프로젝트 (시스템 구축, 풀스택 개발, 다단계 설계+구현+테스트+배포). 여러 전문가 협업 필수

## 판단 기준
1. 동작 수를 세라: "확인하고 만들어" = 2동작 → epic, "분석해서 정리하고 보고해" = 3동작 → epic/raid
2. "~해서 ~하고 ~해" 패턴이 있으면 복합 작업이다
3. "프로젝트", "시스템 만들", "처음부터 끝까지" 등은 raid
4. URL이 포함되고 작업 지시가 있으면 최소 epic
5. 단순 질문("뭐야?", "왜 그래?", "설명해줘")은 quick
6. 확신이 없으면 epic으로 (standard보다 epic이 안전)

## 사용 가능한 에이전트
- JINXUS_CORE: 총괄 오케스트레이터 (항상 포함)
- JX_CODER: 코드 작성/수정/리뷰
- JX_RESEARCHER: 웹 검색, 조사, 크롤링
- JX_WRITER: 문서/보고서 작성
- JX_ANALYST: 데이터 분석, 통계
- JX_OPS: 배포, 인프라, 서버 관리

## 응답 형식 (JSON만, 다른 텍스트 없이)
```json
{"type": "quick|standard|epic|raid", "title": "미션 제목 (한국어, 간결하게)", "agents": ["JINXUS_CORE", ...]}
```"""


class MissionRouter:
    """사용자 입력 → 미션 변환 (LLM 기반)"""

    def __init__(self):
        self._store = get_mission_store()
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._fast_model = settings.claude_fast_model

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

        # [후속] 접두어 제거 — 분류/제목은 실제 내용 기준
        is_followup = stripped.startswith("[후속]")
        classify_text = stripped.replace("[후속]", "", 1).strip() if is_followup else stripped

        # 10자 이하 인사/잡담 → QUICK 즉시 (LLM 호출 절약)
        if len(classify_text) <= 10 and any(p in lower for p in _GREETING_PATTERNS):
            mission_type = MissionType.QUICK
            title = classify_text or "간단 질의"
            agents = ["JINXUS_CORE"]
        else:
            # LLM 분류
            mission_type, title, agents = await self._llm_classify(classify_text)

        # 후속 지시는 최소 STANDARD
        if is_followup and mission_type == MissionType.QUICK:
            mission_type = MissionType.STANDARD

        elapsed = (time.time() - start) * 1000
        logger.info(f"[MissionRouter] 분류 → {mission_type.value} '{title}' ({elapsed:.0f}ms)")

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

    async def _llm_classify(
        self, user_input: str
    ) -> tuple[MissionType, str, list[str]]:
        """LLM 기반 미션 분류"""
        try:
            response = await self._client.messages.create(
                model=self._fast_model,
                max_tokens=200,
                system=_CLASSIFY_PROMPT,
                messages=[{"role": "user", "content": user_input[:1000]}],
            )

            raw = response.content[0].text.strip()

            # JSON 파싱 (```json ... ``` 래핑 제거)
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)

            # type
            type_str = data.get("type", "standard").lower()
            type_map = {
                "quick": MissionType.QUICK,
                "standard": MissionType.STANDARD,
                "epic": MissionType.EPIC,
                "raid": MissionType.RAID,
            }
            mission_type = type_map.get(type_str, MissionType.STANDARD)

            # title
            title = data.get("title", "")
            if not title:
                title = user_input.split("\n")[0].strip()[:80] or "미션"

            # agents
            agents = data.get("agents", ["JINXUS_CORE"])
            if "JINXUS_CORE" not in agents:
                agents.insert(0, "JINXUS_CORE")

            return mission_type, title, agents

        except Exception as e:
            logger.warning(f"[MissionRouter] LLM 분류 실패, STANDARD fallback: {e}")
            title = user_input.split("\n")[0].strip()[:80] or "미션"
            return MissionType.STANDARD, title, ["JINXUS_CORE"]


# 싱글톤
_router: Optional[MissionRouter] = None


def get_mission_router() -> MissionRouter:
    global _router
    if _router is None:
        _router = MissionRouter()
    return _router
