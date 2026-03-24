"""JX_CTO — 이채영 CTO / QA 총괄

코드 품질, 아키텍처 검토, QA 총괄을 전담한다.
엔지니어링 팀 산출물을 최종 검증하고 시스템 안정성을 책임진다.
"""
import logging
import time
import uuid

logger = logging.getLogger(__name__)

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker, GraphNode


class JXCTO:
    """CTO / QA 총괄 에이전트 — 이채영

    그래프:
    [receive] → [plan] → [execute] → [reflect] → [memory_write] → [return_result]
    """

    name = "JX_CTO"
    description = "CTO 겸 QA 총괄. 코드 품질·아키텍처 검토, 시스템 안정성 검증, 팀 기술 결정 최종 승인."
    max_retries = 2

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _get_system_prompt(self) -> str:
        return """너는 JX_CTO야. JINXUS의 CTO 겸 QA 총괄 이채영.

## 역할
- 코드 리뷰·아키텍처 검토: 설계 결함, 보안 취약점, 성능 병목 찾아냄
- QA 총괄: 테스트 전략 수립, 테스트 케이스 작성, 품질 게이트 통과 여부 판단
- 시스템 안정성: 장애 원인 분석, 리스크 식별, 롤백 판단
- 기술 결정: 아키텍처 Trade-off 분석 후 최적안 제시
- 팀 조율: 엔지니어링 팀(민준, 예린, 재원, 도현, 수빈, 하은)의 기술 방향 조율

## 검토 원칙
- 감정 없이 객관적으로. "이건 틀렸다"가 아니라 "이 부분에 리스크가 있다"
- 문제만 지적하지 않고 반드시 개선안 제시
- 치명적 버그 > 보안 취약점 > 성능 > 코드 품질 순으로 우선순위

## 말투
- 팀원들에게 간결하고 직설적으로
- 진수님한테는 기술적 판단을 요약해서 보고
- 불필요한 수식어 없이, 결론부터
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            # 장기 메모리 검색
            memory_context = []
            try:
                memory_context = self._memory.search_long_term(
                    agent_name=self.name,
                    query=instruction,
                    limit=3,
                )
            except Exception as e:
                logger.warning(f"[JXCTO] 메모리 검색 실패: {e}")

            # 작업 유형 판단
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            task_type = self._classify_task(instruction)

            # 실행
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute(instruction, context or [], memory_context, task_type)

            # 반성
            self._state_tracker.update_node(self.name, GraphNode.REFLECT)
            reflection = self._reflect(instruction, result)

            # 메모리 저장
            self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
            await self._memory_write(task_id, instruction, result, reflection)

            self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
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

        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            raise
        finally:
            self._state_tracker.complete_task(self.name)

    def _classify_task(self, instruction: str) -> str:
        lower = instruction.lower()
        if any(k in lower for k in ["리뷰", "review", "검토", "코드"]):
            return "code_review"
        elif any(k in lower for k in ["테스트", "qa", "품질", "버그", "검증"]):
            return "qa"
        elif any(k in lower for k in ["아키텍처", "설계", "구조", "architecture"]):
            return "architecture"
        elif any(k in lower for k in ["장애", "오류", "에러", "fail", "down"]):
            return "incident"
        else:
            return "general"

    async def _execute(
        self, instruction: str, context: list, memory_context: list, task_type: str
    ) -> dict:
        """LLM 호출로 CTO 관점 분석 수행"""
        import asyncio

        memory_str = ""
        if memory_context:
            memory_str = "\n\n과거 유사 사례:\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        context_str = ""
        if context:
            context_str = "\n\n컨텍스트:\n" + "\n".join(
                f"{c.get('role', 'user')}: {str(c.get('content', ''))[:300]}"
                for c in context[-3:]
            )

        type_guide = {
            "code_review": "코드 리뷰 관점: 로직 오류, 보안 취약점, 성능 문제, 코드 품질 순서로 검토.",
            "qa": "QA 관점: 테스트 커버리지, 엣지 케이스, 회귀 가능성, 배포 가능 여부 판단.",
            "architecture": "아키텍처 관점: 확장성, 결합도, 단일 장애점, Trade-off 분석.",
            "incident": "장애 관점: 원인 식별, 영향 범위, 즉각 조치, 재발 방지책 순서로.",
            "general": "CTO 관점에서 기술적 판단과 권고사항 제시.",
        }.get(task_type, "")

        prompt = f"""요청: {instruction}
{context_str}
{memory_str}

{type_guide}

명확하고 실행 가능한 분석 결과를 제시해."""

        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": prompt}],
            )
            output = resp.content[0].text.strip()
            return {"success": True, "score": 0.9, "output": output, "error": None}
        except Exception as e:
            logger.error(f"[JXCTO] LLM 호출 실패: {e}")
            return {"success": False, "score": 0.0, "output": "", "error": str(e)}

    def _reflect(self, instruction: str, result: dict) -> str:
        if not result["success"]:
            return f"실패: {result.get('error')}. 재시도 필요."
        return "검토 완료. 주요 리스크 및 개선안 전달됨."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        try:
            importance = 0.5 if result["success"] else 0.7
            if importance > 0.4:
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
        except Exception as e:
            logger.warning(f"[JXCTO] 메모리 저장 실패 (결과 정상): {e}")
