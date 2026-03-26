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

from jinxus.core.mission import (
    Mission, MissionType, MissionStatus, get_mission_store,
)

logger = logging.getLogger(__name__)


# 패턴 매칭 (SmartRouter 기반 확장)
_RAID_PATTERNS = [
    "프로젝트", "시스템 만들", "시스템을 만들", "앱 만들", "웹사이트 만들", "서비스 만들",
    "플랫폼 만들", "전체 설계", "아키텍처", "풀스택",
    "end-to-end", "e2e", "처음부터 끝까지",
    "여러 단계", "단계별로", "phase", "마일스톤",
    "파이프라인", "에이전트를 만들", "봇을 만들",
    "배포까지", "테스트까지", "운영까지",
]

_EPIC_PATTERNS = [
    "백그라운드", "밤새", "자율", "autonomous",
    "오래 걸", "시간 걸", "천천히", "꼼꼼히",
    "전부 분석", "전체 분석", "깊이 분석", "심층",
    "모니터링해", "감시해", "수집해",
    "대량", "일괄", "벌크", "batch",
    "리팩토링", "전체 코드", "코드베이스",
    "블로그 만들", "사이트 만들", "페이지 만들",
    "블로그를 만들", "사이트를 만들",
    "처럼 만들", "참고해서 만들", "클론", "clone",
    "처럼 좀", "참고해서", "소스처럼", "처럼 해",
    "전체 리뷰", "전체 점검", "전수 조사",
    "크롤링해서", "스크래핑", "데이터 수집",
    "레포 분석", "레포지토리 분석", "소스 분석",
    "문서화해", "문서 작성", "보고서 작성",
    "개선안", "개선 방안", "마이그레이션",
    "테스트 작성", "테스트 코드", "테스트를 작성",
    "CI/CD", "자동화",
]

_COMPOUND_MARKERS = [
    "그리고", "또한", "다음으로", "이후에",
    "1.", "2.", "3.", "첫째", "둘째",
    "- ", "만들고", "하고", "작성하고", "분석하고",
]

# QUICK 판별: 도구 없이 즉답 가능한 패턴
_QUICK_PATTERNS = [
    # 인사/잡담
    "안녕", "하이", "ㅎㅇ", "hello", "hi ", "hey",
    "고마워", "감사", "ㄱㅅ", "ㅇㅇ", "ㅇㅋ", "ㄱㄱ",
    "뭐해", "심심", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ",
    # 간단 질문
    "몇 시", "현재 시간", "시간 알려", "날짜", "오늘",
    "몇 살", "이름이 뭐", "누구야", "뭐야", "소개",
    "뭘 할 수 있", "도와줘", "도움",
    "뭐 가능", "할 수 있어", "기능이 뭐",
    # 상태 확인 (도구 불필요한 것들)
    "테스트", "잘 되나", "작동하나", "살아있",
    # 의견/추천/개념 질문
    "어떻게 생각", "추천해", "골라", "뭐가 좋",
    "설명해", "알려줘", "가르쳐",
    "차이가 뭐", "차이점", "비교해", "뭐가 다",
    "의미가 뭐", "뜻이 뭐", "정의가",
    "왜 그런", "이유가 뭐", "원인이 뭐",
    "장단점", "단점이 뭐", "장점이 뭐",
    "어떤 걸 써", "어떤 게 좋",
    # 짧은 명령형
    "번역해", "요약해",
    "계산해", "환산해", "변환해",
    # 응답/확인
    "맞아", "그래", "아니", "좋아", "알겠",
    "잘했", "수고", "오케이", "ok",
]

# QUICK 제외 키워드: 이게 있으면 QUICK이 아님 (도구가 필요한 작업)
_QUICK_EXCLUDES = [
    "만들어", "구현", "코드", "파일", "생성", "작성",
    "검색", "찾아", "크롤", "조사", "분석",
    "배포", "도커", "서버", "설치", "실행",
    "github", "레포", "커밋", "푸시",
    "수정해", "고쳐", "바꿔", "변경",
    "삭제", "제거",
]



class MissionRouter:
    """사용자 입력 → 미션 변환"""

    def __init__(self):
        self._store = get_mission_store()

    async def create_mission(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> Mission:
        """사용자 입력을 미션으로 변환"""
        start = time.time()
        stripped = user_input.strip()
        # [후속] 접두어 제거 — 분류/제목은 실제 내용 기준
        is_followup = stripped.startswith("[후속]")
        if is_followup:
            stripped = stripped.replace("[후속]", "", 1).strip()
        lower = stripped.lower()
        mission_id = f"m-{uuid.uuid4().hex[:8]}"

        # 패턴 매칭 (LLM 호출 없이 즉시 완료)
        mission_type, title, agents = self._pattern_classify(stripped, lower)
        # 후속 지시는 최소 STANDARD (이미 맥락이 있는 작업)
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

    @staticmethod
    def _make_title(text: str) -> str:
        """입력 텍스트에서 미션 제목 생성 — 첫 줄 전체 사용 (자르지 않음)"""
        first_line = text.split("\n")[0].strip()
        return first_line or "미션"

    def _detect_agents(self, lower: str) -> list[str]:
        """입력에서 필요한 에이전트 추론 (패턴 기반)"""
        agents = ["JINXUS_CORE"]
        if any(k in lower for k in ("코드", "코딩", "개발", "구현", "함수", "클래스", "버그", "수정")):
            agents.append("JX_CODER")
        if any(k in lower for k in ("조사", "검색", "찾아", "리서치", "크롤링", "레포")):
            agents.append("JX_RESEARCHER")
        if any(k in lower for k in ("문서", "작성", "글", "보고서", "정리")):
            agents.append("JX_WRITER")
        if any(k in lower for k in ("분석", "데이터", "통계", "차트")):
            agents.append("JX_ANALYST")
        if any(k in lower for k in ("배포", "인프라", "서버", "도커", "CI")):
            agents.append("JX_OPS")
        return agents

    def _pattern_classify(
        self, stripped: str, lower: str
    ) -> tuple[Optional[MissionType], Optional[str], list[str]]:
        """패턴 매칭 분류 — LLM 호출 없이 즉시 완료"""

        title = self._make_title(stripped)

        # URL이 포함되면 도구가 필요 → QUICK 제외, 최소 STANDARD
        has_url = "http://" in lower or "https://" in lower or "github.com" in lower

        # 도구가 필요한 작업 키워드 체크 (QUICK 제외용)
        has_exclude = any(p in lower for p in _QUICK_EXCLUDES)

        # QUICK 판별: 도구 불필요한 간단 질문/인사
        # 개념 질문 패턴: exclude 키워드가 있어도 질문형이면 QUICK
        is_concept_question = any(p in lower for p in (
            "차이가 뭐", "차이점", "뭐가 다", "뜻이 뭐", "의미가",
            "뭐야", "뭔가", "어떤 거", "설명해", "알려줘",
            "왜 그런", "이유가", "장단점", "비교해",
        ))

        if not has_url and len(stripped) < 80:
            if not has_exclude or is_concept_question:
                # 매우 짧은 입력이거나 QUICK 패턴 매칭
                if len(stripped) < 10 or any(p in lower for p in _QUICK_PATTERNS):
                    return MissionType.QUICK, title or "간단 질의", ["JINXUS_CORE"]

        agents = self._detect_agents(lower)

        # RAID 패턴
        raid_score = sum(1 for p in _RAID_PATTERNS if p in lower)
        compound_count = sum(1 for m in _COMPOUND_MARKERS if m in stripped)

        if raid_score >= 2:
            return MissionType.RAID, title, agents

        if raid_score >= 1 and compound_count >= 2:
            return MissionType.RAID, title, agents

        if compound_count >= 3 and len(stripped) > 80:
            return MissionType.RAID, title, agents

        # EPIC 패턴
        epic_score = sum(1 for p in _EPIC_PATTERNS if p in lower)
        if epic_score >= 2:
            return MissionType.EPIC, title, agents

        # URL + 작업 키워드 → EPIC (외부 소스 참고 작업은 복잡)
        if has_url and has_exclude:
            return MissionType.EPIC, title, agents

        if epic_score >= 1:
            return MissionType.EPIC, title, agents

        # STANDARD (기본)
        return MissionType.STANDARD, title, agents



# 싱글톤
_router: Optional[MissionRouter] = None


def get_mission_router() -> MissionRouter:
    global _router
    if _router is None:
        _router = MissionRouter()
    return _router
