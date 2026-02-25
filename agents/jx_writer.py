"""JX_WRITER - 글쓰기/문서화 전문 에이전트

LangGraph 패턴 적용:
- retry 로직 (최대 3회, 지수 백오프)
- reflect (반성 → 개선점 도출)
- memory_write (장기기억 저장)
"""
import asyncio
import uuid
import time

from anthropic import Anthropic

from config import get_settings
from memory import get_jinx_memory


class JXWriter:
    """글쓰기 전문가 에이전트

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_WRITER"
    description = "글쓰기, 문서화, 자소서 작성을 전담하는 에이전트"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"

    def _get_system_prompt(self) -> str:
        return """너는 JX_WRITER야. 주인님을 모시는 JINXUS의 글쓰기 전문가.

## 역할
주인님의 글쓰기 요청을 받아 고품질 문서를 작성한다.

## 글쓰기 원칙
- 핵심을 먼저, 근거는 나중에
- 화려한 수식어 최소화
- 간결하고 명확한 문장
- 주인님의 스타일에 맞게

## 문서 유형별 가이드
- 자소서: 진정성 있고 구체적인 경험
- 보고서: 체계적 구조, 데이터 기반
- 이메일: 예의 바르고 명확한 목적
- 기술문서: 정확하고 이해하기 쉽게

## 말투
- 주인님을 "주인님"이라고 부른다
- 공손하고 순종적인 태도
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        # === [receive] 과거 경험 로드 ===
        memory_context = []
        try:
            memory_context = self._memory.search_long_term(
                agent_name=self.name,
                query=instruction,
                limit=3,
            )
        except Exception:
            pass  # 메모리 실패해도 진행

        # === [plan] 문서 유형 판단 ===
        doc_type = self._determine_doc_type(instruction)
        plan = {"strategy": "write_document", "doc_type": doc_type, "instruction": instruction}

        # === [execute] + [evaluate] + [retry] ===
        result = await self._execute_with_retry(instruction, context, memory_context, doc_type)

        # === [reflect] 반성 ===
        reflection = await self._reflect(instruction, result)

        # === [memory_write] 장기기억 저장 ===
        await self._memory_write(task_id, instruction, result, reflection)

        # === [return_result] ===
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "task_id": task_id,
            "agent_name": self.name,
            "success": result["success"],
            "success_score": result["score"],
            "output": result["output"],
            "failure_reason": result.get("error"),
            "duration_ms": duration_ms,
            "reflection": reflection,
        }

    def _determine_doc_type(self, instruction: str) -> str:
        """문서 유형 판단"""
        instruction_lower = instruction.lower()
        if any(k in instruction_lower for k in ["자소서", "자기소개서", "지원서"]):
            return "cover_letter"
        elif any(k in instruction_lower for k in ["보고서", "리포트", "분석"]):
            return "report"
        elif any(k in instruction_lower for k in ["이메일", "메일", "편지"]):
            return "email"
        elif any(k in instruction_lower for k in ["readme", "문서화", "기술문서"]):
            return "technical"
        else:
            return "general"

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list, doc_type: str
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # === [execute] ===
                result = await self._execute(instruction, context, memory_context, doc_type, last_error)

                # === [evaluate] ===
                if result["success"]:
                    # 품질 검사
                    quality = self._evaluate_quality(result["content"], doc_type)
                    if quality >= 0.7:
                        return result
                    else:
                        last_error = f"품질 점수 {quality:.2f}로 기준 미달. 더 좋은 글이 필요합니다."
                else:
                    last_error = result.get("error", "Unknown error")

                # 지수 백오프 (마지막 시도가 아니면)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 1, 2, 4초
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # 모든 재시도 실패
        return {
            "success": False,
            "score": 0.0,
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 만족스러운 결과를 얻지 못했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
            "content": "",
        }

    async def _execute(
        self, instruction: str, context: list, memory_context: list, doc_type: str, last_error: str = None
    ) -> dict:
        """단일 실행 시도"""
        # 이전 실패가 있으면 프롬프트에 포함
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도 피드백: {last_error}\n이 피드백을 반영해서 더 좋은 글을 작성해줘."

        # 메모리 컨텍스트
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 작성 경험\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        # 문서 유형별 추가 가이드
        type_guide = self._get_type_guide(doc_type)

        prompt = f"""주인님의 요청: {instruction}
{memory_str}
{error_context}

{type_guide}

위 요청에 맞는 글을 작성해줘. 완성된 글 앞에 간단한 보고를 넣어줘."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text

        return {
            "success": True,
            "score": 0.9,
            "output": content,
            "error": None,
            "content": content,
        }

    def _get_type_guide(self, doc_type: str) -> str:
        """문서 유형별 가이드"""
        guides = {
            "cover_letter": "자소서 작성 시: 구체적 경험, STAR 기법, 진정성 강조",
            "report": "보고서 작성 시: 서론-본론-결론 구조, 데이터 인용, 객관적 톤",
            "email": "이메일 작성 시: 인사-목적-요청-마무리 구조, 예의 바른 톤",
            "technical": "기술문서 작성 시: 설치-사용법-예제-FAQ 구조",
            "general": "",
        }
        return guides.get(doc_type, "")

    def _evaluate_quality(self, content: str, doc_type: str) -> float:
        """간단한 품질 평가"""
        score = 0.5

        # 길이 체크
        if len(content) > 200:
            score += 0.2
        if len(content) > 500:
            score += 0.1

        # 구조 체크 (마크다운 헤딩 등)
        if "#" in content or "##" in content:
            score += 0.1

        # 문단 체크
        if content.count("\n\n") >= 2:
            score += 0.1

        return min(score, 1.0)

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 품질 기준을 더 명확히 해야 함."

        # 성공 시 간단한 반성
        content_length = len(result.get("content", ""))
        reflect_prompt = f"""방금 완료한 글쓰기:
요청: {instruction}
결과: 성공
글 길이: {content_length}자

이 작업에서 배운 핵심 포인트를 1-2문장으로 정리해줘."""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text
        except Exception:
            return "글쓰기 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 중요도 계산
            importance = 0.3
            if not result["success"]:
                importance += 0.4  # 실패에서 배움
            if len(result.get("content", "")) > 1000:
                importance += 0.2  # 긴 문서는 더 중요
            if len(reflection) > 50:
                importance += 0.1

            # 저장 조건: 실패했거나 중요도가 높으면
            if not result["success"] or importance > 0.5:
                self._memory.save_long_term(
                    agent_name=self.name,
                    task_id=task_id,
                    instruction=instruction,
                    summary=result["output"][:300],
                    outcome="success" if result["success"] else "failure",
                    success_score=result["score"],
                    key_learnings=reflection,
                    importance_score=importance,
                    prompt_version=self._prompt_version,
                )
        except Exception:
            pass  # 메모리 저장 실패해도 계속 진행
