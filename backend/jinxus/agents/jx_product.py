"""JX_PRODUCT — 김서연 제품 기획 PM

제품 전략, 유저 리서치, 로드맵 관리, 요구사항 정의 전담.
개발팀/디자인/마케팅 사이에서 제품 방향을 조율한다.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker


class JXProduct:
    """제품 기획 PM 에이전트 — 김서연"""

    name = "JX_PRODUCT"
    description = "제품 기획 PM. 유저 리서치, 제품 로드맵, 요구사항 정의, OKR 설정, 스프린트 관리."
    max_retries = 2

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _get_system_prompt(self) -> str:
        from jinxus.agents.personas import get_persona_system_addon
        persona_section = get_persona_system_addon(self.name)
        return f"""너는 JINXUS의 제품 기획 PM 김서연이다.{persona_section}

## 핵심 역할
- 제품 비전·전략: 사용자 문제 정의 → 솔루션 방향 → OKR 설정
- 요구사항 정의: 유저 스토리 작성, 수용 기준(Acceptance Criteria) 명세, 우선순위 결정
- 로드맵 관리: 분기별 로드맵 수립, 스프린트 계획, 백로그 정리
- 유저 리서치: 사용자 인터뷰 설계, 페르소나 정의, 사용성 테스트
- 지표 관리: DAU, retention, NPS 등 핵심 제품 지표 추적

## 협업 패턴
- 예린(JX_FRONTEND): 화면 플로우·UX 방향 정의 후 설계 협업
- 민준(JX_CODER): 기술 가능성·리소스 추정 확인
- 현수(JX_ANALYST): 제품 지표 분석 요청
- 지훈(JX_MARKETING): 출시 전략, 메시지 정합성 확인
- 채영(JX_CTO): 아키텍처 영향도 검토

## 보고 방식
진수님께: 현재 상황 → 사용자 문제 → 해결 방향 → 성공 지표 → 일정 순으로.
"왜 이 기능인지"를 항상 먼저 설명.

## 출력 포맷 (요구사항 정의 시)
사용자 스토리, 수용 기준, 우선순위 (P0/P1/P2), 예상 공수 순으로 구조화.

## 금지
- 개발팀 일정 약속 없이 "언제까지 가능"이라고 임의로 말하는 것
- 사용자 검증 없이 "이거 분명히 필요해요" 단언
"""

    async def run(self, task: str, session_id: str | None = None) -> str:
        """제품 기획 과제 처리"""
        import asyncio
        sid = session_id or str(uuid.uuid4())
        self._state_tracker.set_state(self.name, "running", sid)

        try:
            result = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=2000,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": task}],
            )
            output = result.content[0].text.strip()
            self._state_tracker.set_state(self.name, "idle", sid)

            try:
                await self._memory.add(
                    content=f"제품 기획 과제: {task[:100]}\n결과: {output[:200]}",
                    metadata={"agent": self.name, "session_id": sid},
                )
            except Exception as e:
                logger.debug(f"[{self.name}] 장기 메모리 저장 실패: {e}")

            return output

        except Exception as e:
            logger.error(f"[{self.name}] run() 실패: {e}")
            self._state_tracker.set_state(self.name, "idle", sid)
            return f"제품 기획 처리 중 오류가 발생했습니다: {e}"
