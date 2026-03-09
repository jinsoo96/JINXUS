"""Context Summarizer — 대화 컨텍스트 LLM 요약

단순히 오래된 메시지를 버리는 대신, LLM으로 요약하여 핵심 컨텍스트를 보존한다.

사용 시점:
- SessionFreshness가 STALE_COMPACT를 반환할 때
- 메시지 수가 compact_after_messages를 초과할 때
"""
import logging
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


class ContextSummarizer:
    """대화 컨텍스트 요약기"""

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._fast_model = settings.claude_fast_model

    async def summarize_messages(
        self,
        messages: list[dict],
        keep_recent: int = 10,
    ) -> list[dict]:
        """메시지 목록을 요약하여 컴팩트하게 반환

        Args:
            messages: 전체 메시지 목록 [{role, content, ...}]
            keep_recent: 최근 N개 메시지는 원본 유지

        Returns:
            [요약 메시지] + [최근 N개 원본 메시지]
        """
        if len(messages) <= keep_recent:
            return messages

        # 오래된 메시지와 최근 메시지 분리
        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        # 오래된 메시지 요약
        summary = await self._generate_summary(old_messages)

        if not summary:
            # 요약 실패 시 최근 메시지만 반환
            return recent_messages

        # 요약 메시지 + 최근 메시지
        summary_message = {
            "role": "system",
            "content": f"[이전 대화 요약]\n{summary}",
            "metadata": {"type": "summary", "original_count": len(old_messages)},
        }

        return [summary_message] + recent_messages

    async def _generate_summary(self, messages: list[dict]) -> Optional[str]:
        """메시지 목록을 LLM으로 요약"""
        if not messages:
            return None

        # 메시지를 텍스트로 변환
        conversation_text = ""
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                conversation_text += f"[{role}]: {content[:200]}\n"

        if not conversation_text.strip():
            return None

        summary_prompt = f"""다음 대화 내용을 핵심만 3-5줄로 요약해줘.
주요 요청사항, 결정된 사항, 중요 정보만 포함해.

---
{conversation_text[:3000]}
---

요약:"""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=300,
                messages=[{"role": "user", "content": summary_prompt}],
            )
            summary = response.content[0].text.strip()
            logger.info(
                f"[ContextSummarizer] {len(messages)}개 메시지 → 요약 완료 "
                f"({len(summary)}자)"
            )
            return summary
        except Exception as e:
            logger.error(f"[ContextSummarizer] 요약 실패: {e}")
            return None


# 싱글톤
_summarizer: Optional[ContextSummarizer] = None


def get_context_summarizer() -> ContextSummarizer:
    """ContextSummarizer 싱글톤 반환"""
    global _summarizer
    if _summarizer is None:
        _summarizer = ContextSummarizer()
    return _summarizer
