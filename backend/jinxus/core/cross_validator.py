"""CrossValidator — 에이전트 결과 교차 검증

HARD/RAID 작업에서 에이전트 결과를 다른 전문 에이전트가 검증하는 시스템.
- 각 결과에 대해 LLM으로 신뢰도 평가 (0.0~1.0)
- 신뢰도 0.5 미만이면 needs_retry 플래그
- 검증자 매핑: JX_CODER→JX_REVIEWER, JX_RESEARCHER→JX_ANALYST 등
- 검증자가 없으면 LLM 자체 검증으로 대체
"""
import asyncio
import json
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── 검증자 매핑 ──────────────────────────────────────────────────
# 작업 수행 에이전트 → 검증 담당 에이전트
_VERIFY_MAP: Dict[str, str] = {
    "JX_CODER": "JX_REVIEWER",
    "JX_RESEARCHER": "JX_ANALYST",
    "JX_WRITER": "JX_ANALYST",
    "JX_OPS": "JX_SECURITY",
    "JX_DESIGNER": "JX_REVIEWER",
    "JX_DATA": "JX_ANALYST",
}


def _get_verifier(agent_name: str, available_agents: List[str]) -> str | None:
    """검증 에이전트를 결정. 자기 자신이거나 존재하지 않으면 None (LLM 자체 검증)."""
    verifier = _VERIFY_MAP.get(agent_name)
    if not verifier:
        return None
    if verifier == agent_name:
        return None
    # 실제 사용 가능한 에이전트인지 확인은 호출자가 판단
    # 여기서는 매핑만 반환
    return verifier


async def _llm_evaluate(
    original_task: str,
    agent_name: str,
    agent_output: str,
    verifier_name: str | None = None,
) -> dict:
    """LLM으로 결과 신뢰도를 평가한다.

    Returns:
        {"confidence": float, "reason": str, "verified_by": str}
    """
    from jinxus.config import get_settings
    from anthropic import Anthropic

    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)

    verifier_label = verifier_name or "LLM_SELF_CHECK"

    prompt = f"""당신은 {verifier_label} 역할로, 다른 에이전트의 작업 결과를 검증한다.

## 원래 작업
{original_task[:1000]}

## {agent_name}의 결과
{agent_output[:2000]}

## 검증 기준
1. 결과가 원래 작업 요구사항을 충족하는가?
2. 사실 관계에 오류가 없는가?
3. 코드라면 문법적/논리적 오류가 없는가?
4. 결과의 완성도는 어떤가?

## 응답 형식 (JSON만)
{{"confidence": 0.0~1.0, "reason": "검증 사유 한 줄"}}
"""

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.claude_fast_model or "claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # JSON 추출
        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        else:
            data = json.loads(text)

        confidence = float(data.get("confidence", 0.5))
        reason = str(data.get("reason", ""))

        return {
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason,
            "verified_by": verifier_label,
        }

    except Exception as e:
        logger.warning("[CrossValidator] LLM 평가 실패 (%s): %s", agent_name, e)
        # 평가 실패 시 중립 점수
        return {
            "confidence": 0.5,
            "reason": f"평가 오류: {str(e)[:100]}",
            "verified_by": verifier_label,
        }


async def cross_validate(
    results: list[dict],
    mission: "Mission",  # noqa: F821 — forward ref
) -> list[dict]:
    """에이전트 결과 리스트를 교차 검증하여 신뢰도와 retry 플래그를 추가한다.

    Args:
        results: _execute_hard()에서 나온 에이전트 결과 리스트
                 각 항목: {"agent": str, "success": bool, "output": str, ...}
        mission: 현재 미션 객체 (original_input 참조용)

    Returns:
        results 리스트에 각 항목마다 다음 필드가 추가됨:
        - validation: {"confidence": float, "reason": str, "verified_by": str}
        - needs_retry: bool (confidence < 0.5)
    """
    if not results:
        return results

    # 이미 실패한 결과는 검증 스킵 (retry 플래그만 설정)
    tasks = []
    indices_to_validate = []

    for i, r in enumerate(results):
        if not r.get("success"):
            r["validation"] = {
                "confidence": 0.0,
                "reason": "에이전트 실행 자체가 실패함",
                "verified_by": "SYSTEM",
            }
            r["needs_retry"] = True
            continue

        output = r.get("output", "")
        if not output or not output.strip():
            r["validation"] = {
                "confidence": 0.0,
                "reason": "결과 출력이 비어있음",
                "verified_by": "SYSTEM",
            }
            r["needs_retry"] = True
            continue

        agent_name = r.get("agent", "UNKNOWN")
        verifier = _get_verifier(agent_name, [])

        tasks.append(
            _llm_evaluate(
                original_task=mission.original_input,
                agent_name=agent_name,
                agent_output=output,
                verifier_name=verifier,
            )
        )
        indices_to_validate.append(i)

    # 병렬 검증 실행
    if tasks:
        evaluations = await asyncio.gather(*tasks)
        for idx, evaluation in zip(indices_to_validate, evaluations):
            results[idx]["validation"] = evaluation
            results[idx]["needs_retry"] = evaluation["confidence"] < 0.5

    retry_count = sum(1 for r in results if r.get("needs_retry"))
    if retry_count > 0:
        logger.info(
            "[CrossValidator] Mission %s: %d/%d 결과 재시도 필요",
            mission.id[:8], retry_count, len(results),
        )
    else:
        logger.info(
            "[CrossValidator] Mission %s: 전체 %d건 검증 통과",
            mission.id[:8], len(results),
        )

    return results
