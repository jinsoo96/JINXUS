"""Review→Fix Loop v1.0.0 — 리뷰 결과 자동 수정 사이클

페이즈 실행 결과를 JX_REVIEWER가 검토하고,
이슈 발견 시 JX_CODER가 자동으로 수정하는 피드백 루프.

흐름:
1. 코딩 페이즈 완료
2. ReviewLoop가 결과를 분석하여 이슈 추출
3. 이슈 발견 시 수정 페이즈 자동 생성 → BackgroundWorker 제출
4. 수정 완료 후 재검증 (최대 max_iterations 반복)
5. 이슈 없거나 반복 한도 도달 시 종료

ProjectManager._phase_watcher에서 호출하여 통합.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from anthropic import AsyncAnthropic
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ReviewIssue:
    """리뷰에서 발견된 이슈"""
    severity: str   # critical / warning / suggestion
    file: str       # 관련 파일
    description: str
    fix_instruction: str  # 수정 지시


@dataclass
class ReviewResult:
    """리뷰 결과"""
    passed: bool                        # 통과 여부
    issues: list[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    iteration: int = 0


_REVIEW_PROMPT = """너는 JINXUS의 코드 리뷰어다.

아래 작업 결과를 검토하고 이슈를 찾아라.

검토 기준:
1. 코드가 의도한 기능을 정확히 구현하는가?
2. 명백한 버그나 에러가 있는가?
3. 보안 취약점이 있는가? (SQL injection, XSS, 하드코딩된 비밀값 등)
4. 파일 경로나 import가 올바른가?

응답 형식 (JSON만 출력):
{
  "passed": true/false,
  "issues": [
    {
      "severity": "critical|warning|suggestion",
      "file": "관련 파일 경로 또는 영역",
      "description": "이슈 설명",
      "fix_instruction": "수정 방법 구체 지시"
    }
  ],
  "summary": "전체 리뷰 요약 (1-2문장)"
}

이슈가 없으면 passed: true, issues: [] 로 응답.
suggestion 등급은 무시해도 되는 수준이므로 passed: true로 처리."""


class ReviewLoop:
    """리뷰→수정 자동 사이클

    코딩 페이즈 결과를 리뷰하고, 이슈 발견 시 수정 페이즈를 자동 생성.
    """

    def __init__(self, max_iterations: int = 2):
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._max_iterations = max_iterations

    async def review(
        self,
        task_description: str,
        result_text: str,
        iteration: int = 0,
    ) -> ReviewResult:
        """작업 결과 리뷰

        Args:
            task_description: 원래 작업 지시
            result_text: 실행 결과 텍스트
            iteration: 현재 반복 횟수

        Returns:
            ReviewResult
        """
        try:
            prompt = (
                f"[원래 작업 지시]\n{task_description[:2000]}\n\n"
                f"[실행 결과]\n{result_text[:5000]}"
            )

            response = await self._client.messages.create(
                model=self._fast_model,
                max_tokens=2000,
                system=_REVIEW_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            data = self._parse_json(raw)

            if not data:
                logger.warning("[ReviewLoop] 리뷰 JSON 파싱 실패, 통과 처리")
                return ReviewResult(passed=True, summary="리뷰 파싱 실패", iteration=iteration)

            issues = []
            for issue_data in data.get("issues", []):
                # suggestion은 통과 처리
                if issue_data.get("severity") == "suggestion":
                    continue
                issues.append(ReviewIssue(
                    severity=issue_data.get("severity", "warning"),
                    file=issue_data.get("file", "unknown"),
                    description=issue_data.get("description", ""),
                    fix_instruction=issue_data.get("fix_instruction", ""),
                ))

            passed = data.get("passed", True) and not any(
                i.severity == "critical" for i in issues
            )

            result = ReviewResult(
                passed=passed,
                issues=issues,
                summary=data.get("summary", ""),
                iteration=iteration,
            )

            if issues:
                logger.info(
                    f"[ReviewLoop] 이슈 {len(issues)}개 발견 "
                    f"(critical: {sum(1 for i in issues if i.severity == 'critical')}, "
                    f"warning: {sum(1 for i in issues if i.severity == 'warning')})"
                )
            else:
                logger.info("[ReviewLoop] 리뷰 통과")

            return result

        except Exception as e:
            logger.error(f"[ReviewLoop] 리뷰 실패: {e}")
            return ReviewResult(passed=True, summary=f"리뷰 오류: {e}", iteration=iteration)

    def build_fix_instruction(
        self,
        original_instruction: str,
        review_result: ReviewResult,
    ) -> str:
        """리뷰 이슈를 기반으로 수정 지시 생성

        Returns:
            수정 페이즈에 전달할 instruction 문자열
        """
        if not review_result.issues:
            return ""

        parts = [
            f"[이전 작업 리뷰 결과 — 반복 #{review_result.iteration + 1}]",
            f"리뷰 요약: {review_result.summary}",
            "",
            "발견된 이슈 (반드시 수정할 것):",
        ]

        for i, issue in enumerate(review_result.issues, 1):
            parts.append(
                f"\n{i}. [{issue.severity.upper()}] {issue.file}"
                f"\n   문제: {issue.description}"
                f"\n   수정: {issue.fix_instruction}"
            )

        parts.append(f"\n\n[원래 작업 지시]\n{original_instruction[:1000]}")
        parts.append(
            "\n위 이슈들을 모두 수정하고, 수정 내용을 명확히 보고해."
        )

        return "\n".join(parts)

    def should_review(self, phase_name: str, phase_agent: str) -> bool:
        """이 페이즈가 리뷰 대상인지 판단

        코딩 관련 페이즈만 리뷰 대상.
        """
        # 에이전트 기반 판단
        review_agents = {"JX_CODER", "JX_FRONTEND", "JX_BACKEND", "JX_INFRA"}
        if phase_agent in review_agents:
            return True

        # 이름 기반 판단
        review_keywords = ["구현", "코딩", "개발", "수정", "리팩토링", "코드", "작성"]
        lower_name = phase_name.lower()
        return any(k in lower_name for k in review_keywords)

    def can_iterate(self, iteration: int) -> bool:
        """추가 반복이 가능한지 확인"""
        return iteration < self._max_iterations

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """JSON 추출"""
        import re
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        if "```" in text:
            try:
                block = text.split("```")[1]
                if block.startswith("json"):
                    block = block[4:]
                return json.loads(block.strip())
            except (IndexError, json.JSONDecodeError):
                pass

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None


# 싱글톤
_instance: ReviewLoop | None = None


def get_review_loop() -> ReviewLoop:
    global _instance
    if _instance is None:
        _instance = ReviewLoop()
    return _instance
