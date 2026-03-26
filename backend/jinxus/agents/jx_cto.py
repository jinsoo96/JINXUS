"""JX_CTO — 이채영 CTO / 기술총괄

v2.1.0: 수직 위임 구조
CORE로부터 기술 과제를 위임받아 팀원(JX_CODER, JX_RESEARCHER 등)에게 분배,
결과를 취합·검토하여 CORE에 보고하는 중간관리자 역할.

직접 LLM으로 처리할 수도 있고, 팀원에게 재위임할 수도 있다.
"""
import asyncio
import json
import logging
import re
import time
import uuid

logger = logging.getLogger(__name__)

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker, GraphNode


class JXCTO:
    """CTO / 기술총괄 에이전트 — 이채영

    수직 위임 체인:
    JINXUS_CORE → JX_CTO → [JX_CODER, JX_RESEARCHER, JX_ANALYST, JX_OPS]
                                 ↓              ↓
                           JX_FRONTEND...   JX_WEB_SEARCHER...
    """

    name = "JX_CTO"
    description = (
        "CTO 겸 기술총괄. 기술 과제를 팀원(JX_CODER, JX_RESEARCHER 등)에게 분배하고 "
        "결과를 검토·취합하여 보고. 코드리뷰, 아키텍처, QA, 소스분석, 기술 조사 등."
    )
    max_retries = 2

    # CTO가 관리하는 팀원 (CORE의 _agents에서 참조)
    TEAM_AGENTS = ["JX_CODER", "JX_RESEARCHER", "JX_ANALYST", "JX_OPS"]

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v2.1"
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._team = {}  # 런타임에 CORE가 주입

    def set_team(self, agents: dict):
        """CORE가 CTO에게 팀원 에이전트 인스턴스를 주입"""
        self._team = {
            name: agents[name]
            for name in self.TEAM_AGENTS
            if name in agents
        }
        logger.info(f"[JXCTO] 팀 구성 완료: {list(self._team.keys())}")

    def _get_system_prompt(self) -> str:
        return """너는 JX_CTO야. JINXUS의 CTO 겸 기술총괄 이채영.

## 역할
- JINXUS_CORE(CEO)로부터 기술 과제를 위임받아 팀원에게 분배
- 팀원 결과를 검토·취합하여 CORE에게 보고
- 단순 기술 질문은 직접 답변 (팀원 불필요)

## 팀원
- JX_CODER: 코드 작성/실행/디버깅, GitHub 관리
- JX_RESEARCHER: 웹 검색/조사/분석, 소스코드 분석
- JX_ANALYST: 데이터 분석/시각화/통계
- JX_OPS: 시스템 운영/파일관리/스케줄

## 위임 판단 기준
- 코드 작성/실행 필요 → JX_CODER
- 정보 검색/조사 필요 → JX_RESEARCHER
- 데이터 분석 필요 → JX_ANALYST
- 시스템 관리 필요 → JX_OPS
- 여러 능력 필요 → 복수 팀원 배정
- 직접 답변 가능 → 위임 없이 직접

## 검토 원칙
- 팀원 결과가 돌아오면 품질/정확성 검토 후 보고
- 미흡하면 보충 지시 또는 다른 팀원 재위임
- 결론부터, 불필요한 수식어 없이
"""

    async def run(self, instruction: str, context: list = None,
                  progress_callback=None) -> dict:
        """에이전트 실행 — 팀원 위임 또는 직접 처리"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            # 장기 메모리 검색
            memory_context = []
            try:
                memory_context = self._memory.search_long_term(
                    agent_name=self.name, query=instruction, limit=3,
                )
            except Exception as e:
                logger.warning(f"[JXCTO] 메모리 검색 실패: {e}")

            # === 위임 판단 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            delegation_plan = await self._plan_delegation(instruction, memory_context)

            # === 실행 ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

            if delegation_plan["delegate"] and self._team:
                # 팀원에게 위임
                result = await self._execute_with_team(
                    instruction, delegation_plan, context or [], progress_callback
                )
            else:
                # 직접 처리
                result = await self._execute_direct(
                    instruction, context or [], memory_context
                )

            # === 반성 + 메모리 ===
            self._state_tracker.update_node(self.name, GraphNode.REFLECT)
            reflection = self._reflect(instruction, result)

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

    async def _plan_delegation(self, instruction: str, memory_context: list) -> dict:
        """위임 계획 수립 — LLM으로 어떤 팀원에게 무엇을 시킬지 결정"""
        team_list = ", ".join(self._team.keys()) if self._team else "(팀원 없음)"

        prompt = f"""## 과제
{instruction}

## 가용 팀원
{team_list}

## 판단
이 과제를 처리하려면 팀원에게 위임해야 하는가, 직접 처리할 수 있는가?
다음 JSON으로만 응답해:

```json
{{
  "delegate": true/false,
  "assignments": [
    {{"agent": "JX_CODER", "instruction": "구체적 지시"}},
  ],
  "execution_mode": "parallel" | "sequential",
  "reason": "판단 근거 한 줄"
}}
```

단순 질문/의견 요청 → delegate: false
코드/검색/분석 등 도구 필요 → delegate: true"""

        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=1024,
                system="너는 CTO야. 과제를 분석해서 위임 계획을 JSON으로만 응답해.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text

            # JSON 파싱
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                plan = json.loads(m.group(0))
                return plan
        except Exception as e:
            logger.warning(f"[JXCTO] 위임 계획 LLM 실패: {e}")

        # 기본: 직접 처리
        return {"delegate": False, "assignments": [], "execution_mode": "sequential", "reason": "fallback"}

    async def _execute_with_team(
        self, instruction: str, plan: dict, context: list,
        progress_callback=None,
    ) -> dict:
        """팀원에게 위임 실행 + 결과 취합"""
        assignments = plan.get("assignments", [])
        mode = plan.get("execution_mode", "sequential")

        if progress_callback:
            agents = [a["agent"] for a in assignments]
            await progress_callback(f"[CTO] 팀원 위임: {', '.join(agents)} ({mode})")

        results = []

        if mode == "parallel":
            tasks = []
            for assignment in assignments:
                agent_name = assignment["agent"]
                if agent_name in self._team:
                    tasks.append(
                        self._team[agent_name].run(
                            assignment["instruction"], context,
                            progress_callback=progress_callback,
                        )
                    )
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(raw_results):
                if isinstance(r, Exception):
                    results.append({"success": False, "output": "", "error": str(r),
                                    "agent_name": assignments[i]["agent"]})
                else:
                    results.append(r)
        else:
            # 순차 실행
            prev_output = ""
            for assignment in assignments:
                agent_name = assignment["agent"]
                if agent_name not in self._team:
                    continue
                inst = assignment["instruction"]
                if prev_output:
                    inst = f"[이전 결과]\n{prev_output[:500]}\n\n{inst}"
                try:
                    r = await self._team[agent_name].run(
                        inst, context, progress_callback=progress_callback,
                    )
                    results.append(r)
                    if r.get("success"):
                        prev_output = r.get("output", "")
                except Exception as e:
                    results.append({"success": False, "output": "", "error": str(e),
                                    "agent_name": agent_name})

        # === CTO 리뷰: 팀원 결과 취합 ===
        if progress_callback:
            await progress_callback("[CTO] 팀원 결과 검토 중...")

        team_outputs = []
        all_success = True
        for r in results:
            agent = r.get("agent_name", "?")
            output = r.get("output", "")
            success = r.get("success", False)
            if not success:
                all_success = False
            team_outputs.append(f"### {agent} {'✓' if success else '✗'}\n{output[:1000]}")

        combined = "\n\n".join(team_outputs)

        # CTO가 최종 검토·요약
        review_result = await self._review_team_output(instruction, combined)

        return {
            "success": all_success or review_result["success"],
            "score": review_result["score"],
            "output": review_result["output"],
            "error": None if all_success else "일부 팀원 실패",
        }

    async def _review_team_output(self, instruction: str, team_output: str) -> dict:
        """팀원 결과를 CTO가 검토·요약하여 최종 보고"""
        prompt = f"""## 원래 과제
{instruction}

## 팀원 실행 결과
{team_output[:3000]}

## 지시
위 팀원들의 결과를 검토하고, 진수님(CEO)에게 보고할 최종 결과를 작성해.
- 부족한 부분이 있으면 지적
- 핵심만 간결하게
- 결론부터"""

        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=4096,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": prompt}],
            )
            output = resp.content[0].text.strip()
            return {"success": True, "score": 0.85, "output": output}
        except Exception as e:
            # 리뷰 실패해도 팀원 결과는 전달
            return {"success": True, "score": 0.7, "output": f"[CTO 리뷰 생략]\n\n{team_output[:2000]}"}

    async def _execute_direct(
        self, instruction: str, context: list, memory_context: list
    ) -> dict:
        """직접 LLM 호출로 처리 (팀원 위임 불필요한 경우)"""
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

        prompt = f"""요청: {instruction}
{context_str}
{memory_str}

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
        return "기술총괄 리뷰 완료. 결과 취합 후 보고."

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
