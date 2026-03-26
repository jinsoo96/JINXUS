"""CompetitiveDispatch — 동일 태스크 경쟁 실행 모드

동일 태스크를 2명의 에이전트에게 동시 위임하고, 우수한 결과를 채택한다.
- RAID 타입 + 중요도 높은 서브태스크에만 적용 (비용 2배)
- 2명 병렬 실행 → LLM 비교 평가 → 우수 결과 채택
"""
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)


async def _compare_results(
    task_instruction: str,
    result_a: dict,
    result_b: dict,
) -> dict:
    """LLM으로 두 결과를 비교 평가하여 우수한 것을 선택한다.

    Returns:
        선택된 결과 dict (winner 필드 추가)
    """
    from jinxus.config import get_settings
    from anthropic import Anthropic

    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)

    agent_a = result_a.get("agent", "Agent_A")
    agent_b = result_b.get("agent", "Agent_B")
    output_a = result_a.get("output", "")[:2000]
    output_b = result_b.get("output", "")[:2000]

    # 한쪽만 성공한 경우 비교 불필요
    if result_a.get("success") and not result_b.get("success"):
        result_a["competitive_winner"] = True
        result_a["competitive_reason"] = f"{agent_b} 실행 실패로 {agent_a} 자동 채택"
        return result_a
    if result_b.get("success") and not result_a.get("success"):
        result_b["competitive_winner"] = True
        result_b["competitive_reason"] = f"{agent_a} 실행 실패로 {agent_b} 자동 채택"
        return result_b
    if not result_a.get("success") and not result_b.get("success"):
        # 둘 다 실패 → 첫 번째 반환
        result_a["competitive_winner"] = True
        result_a["competitive_reason"] = "양쪽 모두 실패"
        return result_a

    prompt = f"""두 에이전트가 동일한 작업을 수행했다. 더 우수한 결과를 선택하라.

## 작업
{task_instruction[:1000]}

## {agent_a}의 결과
{output_a}

## {agent_b}의 결과
{output_b}

## 평가 기준
1. 완성도: 작업 요구사항 충족 정도
2. 정확성: 오류 유무
3. 품질: 코드 품질, 문서 가독성 등

## 응답 형식 (JSON만)
{{"winner": "A" 또는 "B", "reason": "선택 사유 한 줄"}}
"""

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.claude_fast_model or "claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        else:
            data = json.loads(text)

        winner_label = data.get("winner", "A").upper()
        reason = data.get("reason", "")

        if winner_label == "B":
            winner = result_b
            loser_agent = agent_a
        else:
            winner = result_a
            loser_agent = agent_b

        winner["competitive_winner"] = True
        winner["competitive_reason"] = f"{reason} (vs {loser_agent})"
        return winner

    except Exception as e:
        logger.warning("[CompetitiveDispatch] 비교 평가 실패: %s", e)
        # 평가 실패 시 첫 번째 결과 반환
        result_a["competitive_winner"] = True
        result_a["competitive_reason"] = f"비교 평가 오류로 기본 선택: {str(e)[:100]}"
        return result_a


async def competitive_execute(
    task: dict,
    agents: list[str],
    executor_fn: Callable[..., Coroutine[Any, Any, dict]],
) -> dict:
    """동일 태스크를 2명의 에이전트에게 동시 위임하고 우수한 결과를 채택한다.

    Args:
        task: 서브태스크 dict — {"instruction": str, ...}
        agents: 경쟁 실행할 에이전트 이름 리스트 (2명)
        executor_fn: 에이전트 실행 함수
                     시그니처: async (subtask: dict) -> dict
                     subtask에 "agent" 키가 있어야 하고,
                     반환값에 "agent", "success", "output" 키가 있어야 한다.

    Returns:
        우수한 결과 dict (competitive_winner, competitive_reason 필드 추가)
    """
    if len(agents) < 2:
        logger.warning("[CompetitiveDispatch] 에이전트 2명 필요, %d명 제공됨", len(agents))
        # 1명이면 그냥 실행
        subtask = {**task, "agent": agents[0]}
        result = await executor_fn(subtask)
        result["competitive_winner"] = True
        result["competitive_reason"] = "경쟁 대상 부족, 단독 실행"
        return result

    # 2명에게 동일 태스크 병렬 실행
    agent_a, agent_b = agents[0], agents[1]
    subtask_a = {**task, "agent": agent_a}
    subtask_b = {**task, "agent": agent_b}

    logger.info(
        "[CompetitiveDispatch] 경쟁 실행: %s vs %s — %s",
        agent_a, agent_b, task.get("instruction", "")[:80],
    )

    result_a, result_b = await asyncio.gather(
        executor_fn(subtask_a),
        executor_fn(subtask_b),
    )

    # 비교 평가
    winner = await _compare_results(
        task_instruction=task.get("instruction", ""),
        result_a=result_a,
        result_b=result_b,
    )

    logger.info(
        "[CompetitiveDispatch] 승자: %s — %s",
        winner.get("agent", "?"),
        winner.get("competitive_reason", "")[:100],
    )

    return winner


def should_use_competitive(
    mission_type: str,
    subtask: dict,
    subtask_count: int,
) -> bool:
    """이 서브태스크에 competitive 모드를 적용할지 판단한다.

    조건:
    - RAID 미션 타입
    - 서브태스크에 execution_mode: "competitive" 지정됨
    - 또는 RAID이면서 서브태스크가 3개 이하 (비용 부담 낮음)

    Args:
        mission_type: "quick" | "standard" | "epic" | "raid"
        subtask: 서브태스크 dict (LLM이 분해한 것)
        subtask_count: 전체 서브태스크 수
    """
    if mission_type != "raid":
        return False

    # 명시적으로 competitive 모드가 지정된 경우만 적용
    # (LLM이 decompose 시 핵심 서브태스크에 지정)
    if subtask.get("execution_mode") == "competitive":
        return True

    return False
