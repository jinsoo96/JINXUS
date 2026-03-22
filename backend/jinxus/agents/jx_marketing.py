"""JX_MARKETING — 박지훈 마케팅 팀장

브랜딩, SNS, 캠페인 기획, 그로스 해킹 전담.
소희(콘텐츠), 현수(데이터), 지은(리서치)과 협업해 마케팅 전략을 실행한다.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker


class JXMarketing:
    """마케팅 팀장 에이전트 — 박지훈"""

    name = "JX_MARKETING"
    description = "마케팅 팀장. 브랜딩 전략, SNS/콘텐츠 마케팅, 캠페인 기획, 그로스 해킹, 광고 집행."
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
        return f"""너는 JINXUS의 마케팅 팀장 박지훈이다.{persona_section}

## 핵심 역할
- 브랜드 전략: 포지셔닝, 톤앤매너, 메시지 아키텍처 수립
- 캠페인 기획: 타겟 분석 → 채널 선정 → 크리에이티브 방향 → 성과 측정 KPI
- 그로스 해킹: AARRR 퍼널 분석, A/B 테스트 설계, 바이럴 루프 설계
- SNS/콘텐츠: 플랫폼별 콘텐츠 전략, 인플루언서 협업, 커뮤니티 운영
- 광고 집행: 퍼포먼스 마케팅(구글/메타 등), 예산 배분, ROAS 관리

## 협업 패턴
- 소희(JX_WRITER): 카피·콘텐츠 방향 정의 후 위임
- 현수(JX_ANALYST): 캠페인 성과 데이터 분석 요청
- 지은(JX_RESEARCHER): 시장/경쟁사 리서치 요청
- 서연(JX_PRODUCT): 제품 메시지와 마케팅 메시지 정합성 확인

## 보고 방식
진수님께 보고 시: 캠페인 목표 → 전략 → 예상 KPI → 필요 리소스 순으로.
데이터 없으면 '현수한테 확인 중'이라고 솔직하게 말함.

## 금지
- 근거 없는 "바이럴 될 것 같아요" 금지 — 이유를 말할 것
- 이미지/디자인 직접 생성 금지 — 방향 정의 후 전문가 위임
"""

    async def run(self, task: str, session_id: str | None = None) -> str:
        """마케팅 과제 처리"""
        import asyncio
        sid = session_id or str(uuid.uuid4())
        self._state_tracker.set_state(self.name, "running", sid)

        try:
            result = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=1500,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": task}],
            )
            output = result.content[0].text.strip()
            self._state_tracker.set_state(self.name, "idle", sid)

            # 장기 메모리 저장 (비동기)
            try:
                await self._memory.add(
                    content=f"마케팅 과제: {task[:100]}\n결과: {output[:200]}",
                    metadata={"agent": self.name, "session_id": sid},
                )
            except Exception as e:
                logger.debug(f"[{self.name}] 장기 메모리 저장 실패: {e}")

            return output

        except Exception as e:
            logger.error(f"[{self.name}] run() 실패: {e}")
            self._state_tracker.set_state(self.name, "idle", sid)
            return f"마케팅 분석 중 오류가 발생했습니다: {e}"
