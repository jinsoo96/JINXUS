"""자동 Reflection 시스템

Generative Agents 논문 기반: 에이전트가 경험을 축적하면 자동으로
고수준 인사이트(reflection)를 생성하여 장기기억에 저장.

트리거 조건: 최근 20개 메모리의 importance_score 합계 > 8.0
결과: 3개의 고수준 인사이트를 node_type="reflection", depth=1로 저장
"""
import json
import logging
import uuid
from typing import Optional

import anthropic

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# reflection 트리거 임계값
REFLECTION_IMPORTANCE_THRESHOLD = 8.0
REFLECTION_MEMORY_COUNT = 20

REFLECTION_PROMPT = """다음은 에이전트 {agent_name}의 최근 작업 기록이다:
{memories}

이 기록들에서 고수준 인사이트 3개를 추출하라.
각 인사이트는 향후 작업에 활용할 수 있는 교훈이어야 한다.
JSON 배열로 반환: [{{"insight": "...", "importance": 0.0-1.0}}]"""


def _get_recent_memories(
    long_term_memory,
    agent_name: str,
    limit: int = 20,
) -> list[dict]:
    """Qdrant scroll API로 최근 메모리 조회 (created_at 기준 정렬)"""
    try:
        long_term_memory.connect()
        collection = long_term_memory._collection_for_agent(agent_name)

        result = long_term_memory._client.scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result

        memories = [
            {
                "summary": p.payload.get("summary", ""),
                "outcome": p.payload.get("outcome", ""),
                "key_learnings": p.payload.get("key_learnings", ""),
                "importance_score": p.payload.get("importance_score", 0.0),
                "created_at": p.payload.get("created_at", ""),
            }
            for p in points
        ]

        # created_at 기준 내림차순 정렬 (최신 우선)
        memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return memories[:limit]

    except Exception as e:
        logger.warning(f"[Reflection] 최근 메모리 조회 실패 ({agent_name}): {e}")
        return []


def check_and_trigger_reflection(
    agent_name: str,
    long_term_memory,
) -> bool:
    """reflection 트리거 조건 확인 후 실행

    Args:
        agent_name: 에이전트 이름
        long_term_memory: LongTermMemory 인스턴스

    Returns:
        reflection이 실행되었으면 True
    """
    try:
        # 최근 메모리 조회 — scroll API 사용
        recent = _get_recent_memories(long_term_memory, agent_name, limit=REFLECTION_MEMORY_COUNT)

        if len(recent) < 5:
            # 메모리가 너무 적으면 스킵
            return False

        # importance_score 합산
        total_importance = sum(m.get("importance_score", 0.0) for m in recent)

        if total_importance < REFLECTION_IMPORTANCE_THRESHOLD:
            return False

        logger.info(
            f"[Reflection] {agent_name} reflection 트리거 "
            f"(importance 합계: {total_importance:.1f} >= {REFLECTION_IMPORTANCE_THRESHOLD})"
        )

        # reflection 생성
        insights = _generate_reflection(agent_name, recent)

        if not insights:
            return False

        # 각 인사이트를 장기기억에 저장
        for insight in insights:
            insight_text = insight.get("insight", "")
            importance = min(1.0, max(0.0, insight.get("importance", 0.5)))

            if not insight_text:
                continue

            long_term_memory.save(
                agent_name=agent_name,
                task_id=f"reflection_{uuid.uuid4().hex[:8]}",
                instruction="[자동 reflection]",
                summary=insight_text,
                outcome="reflection",
                success_score=1.0,
                key_learnings=f"[reflection] {insight_text}",
                importance_score=importance,
                prompt_version="reflection_v1",
            )

        logger.info(
            f"[Reflection] {agent_name} reflection 완료: {len(insights)}개 인사이트 저장"
        )
        return True

    except Exception as e:
        logger.error(f"[Reflection] {agent_name} reflection 실패: {e}")
        return False


def _generate_reflection(
    agent_name: str,
    memories: list[dict],
) -> list[dict]:
    """Claude Haiku로 reflection 인사이트 생성

    Args:
        agent_name: 에이전트 이름
        memories: 최근 메모리 리스트

    Returns:
        [{"insight": str, "importance": float}] 형태의 인사이트 리스트
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        logger.warning("[Reflection] ANTHROPIC_API_KEY 미설정, reflection 스킵")
        return []

    # 메모리를 텍스트로 포매팅
    memory_lines = []
    for i, m in enumerate(memories, 1):
        summary = m.get("summary", "")
        outcome = m.get("outcome", "")
        learnings = m.get("key_learnings", "")
        importance = m.get("importance_score", 0.0)
        memory_lines.append(
            f"{i}. [중요도: {importance:.1f}] {summary} "
            f"(결과: {outcome}, 교훈: {learnings})"
        )

    memories_text = "\n".join(memory_lines)

    prompt = REFLECTION_PROMPT.format(
        agent_name=agent_name,
        memories=memories_text,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        # 응답 텍스트에서 JSON 추출
        response_text = response.content[0].text.strip()

        # JSON 배열 파싱 (코드블록 감싸기 대응)
        if "```" in response_text:
            # 코드블록 내부 추출
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            if start >= 0 and end > start:
                response_text = response_text[start:end]

        insights = json.loads(response_text)

        if not isinstance(insights, list):
            logger.warning(f"[Reflection] 응답이 배열이 아님: {type(insights)}")
            return []

        # 유효성 검증
        valid_insights = []
        for item in insights:
            if isinstance(item, dict) and "insight" in item:
                valid_insights.append({
                    "insight": str(item["insight"]),
                    "importance": float(item.get("importance", 0.5)),
                })

        return valid_insights[:3]  # 최대 3개

    except json.JSONDecodeError as e:
        logger.error(f"[Reflection] JSON 파싱 실패: {e}")
        return []
    except Exception as e:
        logger.error(f"[Reflection] Claude API 호출 실패: {e}")
        return []
