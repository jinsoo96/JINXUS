"""JinxLoop - 자가 강화 엔진"""
import json
from typing import Optional
from datetime import datetime

from anthropic import Anthropic

from config import get_settings
from memory import get_jinx_memory


class JinxLoop:
    """자가 강화 엔진

    진수 피드백 + 성과 데이터 → 해당 에이전트 프롬프트 자동 개선

    트리거 조건:
    1. 진수 피드백 즉시 처리 (rating ≤ 2점)
    2. 누적 작업 자동 트리거 (10번 작업마다)
    3. 임계치 이하 자동 트리거 (성공률 < 0.6)
    4. 수동 트리거 (POST /improve)
    """

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._threshold = settings.auto_improve_threshold
        self._reflect_every_n = settings.reflect_every_n_tasks

    async def process_feedback(
        self,
        task_id: str,
        rating: int,
        comment: Optional[str] = None,
        target_agent: Optional[str] = None,
    ) -> dict:
        """피드백 처리

        Args:
            task_id: 피드백 대상 작업 ID
            rating: 평점 (1-5)
            comment: 코멘트
            target_agent: 특정 에이전트 지정

        Returns:
            처리 결과
        """
        # 피드백 저장
        triggered_improve = rating <= 2
        feedback_id = await self._memory.save_feedback(
            task_id=task_id,
            rating=rating,
            comment=comment,
            target_agent=target_agent,
            triggered_improve=triggered_improve,
        )

        result = {
            "feedback_id": feedback_id,
            "rating": rating,
            "triggered_improve": triggered_improve,
        }

        # 낮은 평점이면 즉시 개선 트리거
        if triggered_improve and target_agent:
            improve_result = await self.improve_agent(
                agent_name=target_agent,
                trigger_type="feedback",
                trigger_source=feedback_id,
            )
            result["improvement"] = improve_result

        return result

    async def improve_agent(
        self,
        agent_name: str,
        trigger_type: str = "manual",
        trigger_source: str = "user",
    ) -> dict:
        """에이전트 개선 실행

        Args:
            agent_name: 개선할 에이전트
            trigger_type: "feedback" | "auto_threshold" | "manual"
            trigger_source: 트리거 소스 (피드백 ID 등)

        Returns:
            개선 결과
        """
        # 1. 현재 프롬프트 버전 조회
        current_prompt = await self._memory.get_active_prompt(agent_name)
        old_version = current_prompt.get("version", "v1.0") if current_prompt else "v1.0"
        old_content = current_prompt.get("prompt_content", "") if current_prompt else ""

        # 2. 성능 분석
        performance = await self._memory.get_agent_performance(agent_name, days=7)
        recent_failures = await self._memory.get_recent_failures(agent_name, limit=5)
        feedback_list = await self._memory.get_agent_feedback(agent_name, limit=10)

        # 3. 실패 패턴 분석
        failure_patterns = self._analyze_failure_patterns(recent_failures, feedback_list)

        # 4. 개선안 생성
        improvement = await self._generate_improvement(
            agent_name=agent_name,
            old_prompt=old_content,
            failure_patterns=failure_patterns,
            performance=performance,
            feedback_list=feedback_list,
        )

        # 5. 새 버전 생성
        new_version = self._increment_version(old_version)

        # 6. 프롬프트 저장
        await self._memory.save_prompt_version(
            agent_name=agent_name,
            version=new_version,
            prompt_content=improvement["new_prompt"],
            change_reason=improvement["change_reason"],
            is_active=True,
        )

        # 7. 개선 이력 저장
        improve_id = await self._memory.log_improvement(
            target_agent=agent_name,
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            old_version=old_version,
            new_version=new_version,
            failure_patterns=json.dumps(failure_patterns),
            improvement_applied=improvement["change_reason"],
            score_before=performance.get("avg_score"),
        )

        return {
            "improve_id": improve_id,
            "agent_name": agent_name,
            "old_version": old_version,
            "new_version": new_version,
            "change_reason": improvement["change_reason"],
            "failure_patterns": failure_patterns,
        }

    async def check_auto_improve(self, agent_name: str) -> bool:
        """자동 개선 필요 여부 확인

        Returns:
            True면 개선 필요
        """
        performance = await self._memory.get_agent_performance(agent_name, days=7)

        # 성공률이 임계치 미만이면 개선 필요
        success_rate = performance.get("success_rate", 1.0)
        if success_rate < self._threshold:
            return True

        # 최근 실패가 많으면 개선 필요
        recent_failures = performance.get("recent_failures", 0)
        if recent_failures >= 3:
            return True

        return False

    async def run_scheduled_check(self) -> list[dict]:
        """스케줄된 전체 에이전트 점검"""
        from agents import AGENT_REGISTRY

        results = []

        for agent_name in AGENT_REGISTRY.keys():
            needs_improve = await self.check_auto_improve(agent_name)

            if needs_improve:
                result = await self.improve_agent(
                    agent_name=agent_name,
                    trigger_type="auto_threshold",
                    trigger_source="scheduled",
                )
                results.append(result)

        return results

    def _analyze_failure_patterns(
        self, failures: list[dict], feedback: list[dict]
    ) -> list[str]:
        """실패 패턴 분석"""
        patterns = []

        # 실패 이유 수집
        failure_reasons = [f.get("failure_reason", "") for f in failures if f.get("failure_reason")]

        # 피드백 코멘트 수집
        comments = [f.get("comment", "") for f in feedback if f.get("comment") and f.get("rating", 5) <= 3]

        # 패턴 추출 (간단한 구현)
        all_text = " ".join(failure_reasons + comments).lower()

        if "에러" in all_text or "error" in all_text:
            patterns.append("에러 핸들링 부족")
        if "느" in all_text or "slow" in all_text:
            patterns.append("실행 속도 문제")
        if "틀" in all_text or "wrong" in all_text or "incorrect" in all_text:
            patterns.append("결과 정확도 문제")
        if "부족" in all_text or "missing" in all_text:
            patterns.append("불완전한 응답")

        return patterns if patterns else ["일반적인 품질 개선 필요"]

    async def _generate_improvement(
        self,
        agent_name: str,
        old_prompt: str,
        failure_patterns: list[str],
        performance: dict,
        feedback_list: list[dict],
    ) -> dict:
        """개선안 생성"""
        feedback_summary = "\n".join(
            f"- 평점 {f.get('rating')}: {f.get('comment', 'N/A')}"
            for f in feedback_list[:5]
        )

        improve_prompt = f"""다음 에이전트의 프롬프트를 개선해줘.

## 에이전트
{agent_name}

## 현재 프롬프트
{old_prompt[:2000] if old_prompt else '(기본 프롬프트 사용 중)'}

## 성능 통계
- 성공률: {performance.get('success_rate', 0):.2%}
- 평균 점수: {performance.get('avg_score', 0):.2f}
- 최근 실패: {performance.get('recent_failures', 0)}건

## 발견된 문제 패턴
{chr(10).join(f'- {p}' for p in failure_patterns)}

## 최근 피드백
{feedback_summary if feedback_summary else '없음'}

## 요청
1. 위 문제 패턴을 해결할 수 있도록 프롬프트를 개선해줘
2. 기존 프롬프트의 좋은 점은 유지하면서 문제점만 보완
3. 개선 이유를 간단히 설명해줘

JSON으로 응답해:
```json
{{
  "new_prompt": "개선된 전체 프롬프트",
  "change_reason": "변경 이유 요약 (1-2문장)"
}}
```
"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": improve_prompt}],
        )

        response_text = response.content[0].text

        # JSON 파싱
        try:
            import re
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "new_prompt": old_prompt or f"{agent_name} 기본 프롬프트",
                "change_reason": "파싱 실패로 변경 없음",
            }

    def _increment_version(self, version: str) -> str:
        """버전 증가"""
        try:
            # v1.0 -> v1.1, v1.9 -> v2.0
            v = version.lstrip("v")
            major, minor = v.split(".")
            minor = int(minor) + 1
            if minor >= 10:
                major = int(major) + 1
                minor = 0
            return f"v{major}.{minor}"
        except Exception:
            return "v1.1"


# 싱글톤 인스턴스
_jinx_loop: Optional[JinxLoop] = None


def get_jinx_loop() -> JinxLoop:
    """JinxLoop 싱글톤 반환"""
    global _jinx_loop
    if _jinx_loop is None:
        _jinx_loop = JinxLoop()
    return _jinx_loop
