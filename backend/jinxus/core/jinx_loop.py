"""JinxLoop - 자가 강화 엔진 + A/B 테스트"""
import json
import logging
import re
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory

logger = logging.getLogger(__name__)


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
        self._fast_model = settings.claude_fast_model
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

        # 3. 실패 패턴 분석 (키워드 + LLM 자동 학습)
        failure_patterns = self._analyze_failure_patterns(recent_failures, feedback_list)

        # 3.5. LLM 기반 실패 자동 학습 (실패가 충분히 쌓인 경우)
        auto_learning = await self.analyze_and_learn_failures(agent_name)
        if auto_learning and auto_learning.get("prompt_additions"):
            failure_patterns.extend(auto_learning["prompt_additions"])
            logger.info(f"[JinxLoop] {agent_name}: 자동 학습 패턴 {len(auto_learning['prompt_additions'])}개 추가")

        # 4. 개선안 생성
        improvement = await self._generate_improvement(
            agent_name=agent_name,
            old_prompt=old_content,
            failure_patterns=failure_patterns,
            performance=performance,
            feedback_list=feedback_list,
        )

        new_prompt = improvement["new_prompt"]

        # 5. A/B 테스트 실행
        ab_result = await self.run_ab_test(
            agent_name=agent_name,
            old_prompt=old_content,
            new_prompt=new_prompt,
        )

        # 6. A/B 테스트 결과에 따라 적용 여부 결정
        if ab_result["winner"] == "old":
            # 기존 프롬프트가 더 좋으면 적용 안 함
            logger.info(f"[JinxLoop] {agent_name}: A/B 테스트 실패, 변경 미적용")
            return {
                "improve_id": None,
                "agent_name": agent_name,
                "old_version": old_version,
                "new_version": None,
                "change_reason": "A/B 테스트 미통과",
                "ab_result": ab_result,
                "applied": False,
            }

        # 7. 새 버전 생성 및 저장
        new_version = self._increment_version(old_version)

        await self._memory.save_prompt_version(
            agent_name=agent_name,
            version=new_version,
            prompt_content=new_prompt,
            change_reason=improvement["change_reason"],
            is_active=True,
        )

        # 8. 개선 이력 저장
        improve_id = await self._memory.log_improvement(
            target_agent=agent_name,
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            old_version=old_version,
            new_version=new_version,
            failure_patterns=json.dumps(failure_patterns),
            improvement_applied=improvement["change_reason"],
            score_before=performance.get("avg_score"),
            ab_test_score=ab_result["new_score"],
        )

        logger.info(
            f"[JinxLoop] {agent_name}: {old_version} -> {new_version} "
            f"(A/B: {ab_result['old_score']:.2f} -> {ab_result['new_score']:.2f})"
        )

        return {
            "improve_id": improve_id,
            "agent_name": agent_name,
            "old_version": old_version,
            "new_version": new_version,
            "change_reason": improvement["change_reason"],
            "failure_patterns": failure_patterns,
            "ab_result": ab_result,
            "applied": True,
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

    async def run_improvement_cycle(self) -> dict[str, dict]:
        """전체 에이전트 강화 사이클 실행 (텔레그램용)

        Returns:
            에이전트별 강화 결과 딕셔너리
        """
        from agents import AGENT_REGISTRY

        results = {}

        for agent_name in AGENT_REGISTRY.keys():
            if agent_name == "JINXUS_CORE":
                continue  # Core는 스킵

            try:
                # 최근 작업이 있는지 확인
                performance = await self._memory.get_agent_performance(agent_name, days=7)
                task_count = performance.get("total_tasks", 0)

                if task_count == 0:
                    results[agent_name] = {"status": "skipped", "reason": "no_recent_tasks"}
                    continue

                # 강화 실행
                result = await self.improve_agent(
                    agent_name=agent_name,
                    trigger_type="manual",
                    trigger_source="telegram",
                )

                if result.get("applied"):
                    results[agent_name] = {
                        "status": "improved",
                        "old_version": result.get("old_version"),
                        "new_version": result.get("new_version"),
                        "improvement": result.get("change_reason"),
                    }
                else:
                    results[agent_name] = {
                        "status": "unchanged",
                        "reason": result.get("change_reason", "A/B 테스트 미통과"),
                    }

            except Exception as e:
                logger.error(f"[JinxLoop] {agent_name} 강화 실패: {e}")
                results[agent_name] = {"status": "error", "error": str(e)}

        return results

    def _analyze_failure_patterns(
        self, failures: list[dict], feedback: list[dict]
    ) -> list[str]:
        """실패 패턴 분석 (키워드 기반 + 빈도 분석)"""
        patterns = []

        # 실패 이유 수집
        failure_reasons = [f.get("failure_reason", "") for f in failures if f.get("failure_reason")]

        # 피드백 코멘트 수집
        comments = [f.get("comment", "") for f in feedback if f.get("comment") and f.get("rating", 5) <= 3]

        all_text = " ".join(failure_reasons + comments).lower()

        # 패턴 카테고리별 키워드 매핑
        pattern_map = {
            "에러 핸들링 부족": ["에러", "error", "exception", "traceback", "실패"],
            "실행 속도 문제": ["느", "slow", "timeout", "시간초과", "오래"],
            "결과 정확도 문제": ["틀", "wrong", "incorrect", "잘못", "부정확"],
            "불완전한 응답": ["부족", "missing", "불완전", "더 필요", "빠진"],
            "도구 선택 오류": ["도구", "tool", "mcp", "filesystem", "url"],
            "할루시네이션": ["지어", "fabricat", "없는 정보", "존재하지 않"],
            "컨텍스트 이해 부족": ["이해", "문맥", "context", "의도", "잘못 이해"],
        }

        for pattern, keywords in pattern_map.items():
            if any(k in all_text for k in keywords):
                patterns.append(pattern)

        # 도구 실패 빈도 분석
        tool_failures = [f for f in failures if "tool" in str(f.get("failure_reason", "")).lower()]
        if len(tool_failures) >= 2:
            patterns.append(f"반복적 도구 실패 ({len(tool_failures)}회)")

        # 연속 실패 감지
        if len(failures) >= 3:
            patterns.append(f"연속 실패 감지 ({len(failures)}건)")

        return patterns if patterns else ["일반적인 품질 개선 필요"]

    async def analyze_and_learn_failures(self, agent_name: str) -> Optional[dict]:
        """실패 패턴 자동 학습 — 주기적으로 호출되어 실패 패턴을 분석하고 프롬프트에 반영

        Returns:
            학습 결과 또는 None (학습 불필요 시)
        """
        recent_failures = await self._memory.get_recent_failures(agent_name, limit=10)

        if len(recent_failures) < 3:
            return None  # 데이터 부족

        # 실패 패턴 LLM 분석
        failure_texts = "\n".join(
            f"- 작업: {f.get('instruction', 'N/A')[:100]}\n  실패: {f.get('failure_reason', 'N/A')[:200]}"
            for f in recent_failures[:5]
        )

        analysis_prompt = f"""다음 에이전트({agent_name})의 최근 실패 기록을 분석해.

{failure_texts}

1. 반복되는 실패 패턴이 있는가?
2. 프롬프트에 추가할 구체적 지침을 1-3개 제안해줘.

JSON으로 응답:
```json
{{
  "has_pattern": true/false,
  "pattern_summary": "패턴 요약",
  "prompt_additions": ["추가할 지침1", "추가할 지침2"]
}}
```"""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=500,
                messages=[{"role": "user", "content": analysis_prompt}],
            )
            text = response.content[0].text
            json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
            else:
                analysis = json.loads(text)

            if analysis.get("has_pattern") and analysis.get("prompt_additions"):
                logger.info(
                    f"[JinxLoop] {agent_name} 실패 패턴 학습: {analysis['pattern_summary']}"
                )
                return analysis

        except Exception as e:
            logger.warning(f"[JinxLoop] 실패 분석 오류: {e}")

        return None

    async def _generate_improvement(
        self,
        agent_name: str,
        old_prompt: str,
        failure_patterns: list[str],
        performance: dict,
        feedback_list: list[dict],
    ) -> dict:
        """Self-Refine 패턴: Generation → Feedback → Refinement (3단계 프롬프트 분리)

        논문 참고: Self-Refine (Madaan et al., 2023)
        단일 프롬프트 대비 각 단계에 집중하여 품질 향상.
        """
        feedback_summary = "\n".join(
            f"- 평점 {f.get('rating')}: {f.get('comment', 'N/A')}"
            for f in feedback_list[:5]
        )

        context_block = f"""## 에이전트: {agent_name}

## 현재 프롬프트
{old_prompt[:2000] if old_prompt else '(기본 프롬프트 사용 중)'}

## 성능 통계
- 성공률: {performance.get('success_rate', 0):.2%}
- 평균 점수: {performance.get('avg_score', 0):.2f}
- 최근 실패: {performance.get('recent_failures', 0)}건

## 발견된 문제 패턴
{chr(10).join(f'- {p}' for p in failure_patterns)}

## 최근 피드백
{feedback_summary if feedback_summary else '없음'}"""

        # ── Step 1: Generation (초안 생성) ────────────────────────
        gen_prompt = f"""다음 에이전트의 프롬프트 개선 초안을 작성해줘.
기존 프롬프트의 장점을 유지하면서 문제 패턴을 해결하는 데 집중해.

{context_block}

JSON으로 응답:
```json
{{"draft_prompt": "개선된 전체 프롬프트 초안", "intended_fixes": ["해결하려는 문제1", "문제2"]}}
```"""

        gen_response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": gen_prompt}],
        )
        draft = self._parse_json_response(gen_response.content[0].text)
        draft_prompt = draft.get("draft_prompt", old_prompt or f"{agent_name} 기본 프롬프트")

        # ── Step 2: Feedback (자가 비평) ──────────────────────────
        feedback_prompt = f"""다음 프롬프트 개선안을 비평해줘. 냉정하게 평가해.

## 원본 프롬프트
{old_prompt[:1500] if old_prompt else '(기본 프롬프트)'}

## 개선 초안
{draft_prompt[:2000]}

## 해결하려던 문제
{chr(10).join(f'- {p}' for p in failure_patterns)}

## 비평 관점
1. 원래 문제를 실제로 해결하는가?
2. 기존 장점을 훼손하지 않았는가?
3. 지시가 모호하거나 상충하는 부분은 없는가?
4. 빠뜨린 개선 포인트는 없는가?

JSON으로 응답:
```json
{{"score": 0.0~1.0, "strengths": ["장점"], "weaknesses": ["약점"], "suggestions": ["구체적 제안"]}}
```"""

        fb_response = self._client.messages.create(
            model=self._fast_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": feedback_prompt}],
        )
        feedback = self._parse_json_response(fb_response.content[0].text)

        # 비평 점수가 충분히 높으면 바로 채택 (0.8 이상)
        if feedback.get("score", 0) >= 0.8:
            logger.info(f"[JinxLoop] {agent_name}: Self-Refine Step2 점수 {feedback.get('score'):.2f}, 초안 채택")
            return {
                "new_prompt": draft_prompt,
                "change_reason": f"Self-Refine 초안 채택 (비평 점수: {feedback.get('score', 0):.2f})",
            }

        # ── Step 3: Refinement (비평 반영 수정) ───────────────────
        refine_prompt = f"""프롬프트 개선 초안에 대한 비평을 반영하여 최종 버전을 만들어줘.

## 초안
{draft_prompt[:2000]}

## 비평 결과
- 점수: {feedback.get('score', 0):.2f}
- 장점: {', '.join(feedback.get('strengths', []))}
- 약점: {', '.join(feedback.get('weaknesses', []))}
- 제안: {', '.join(feedback.get('suggestions', []))}

## 원래 해결하려던 문제
{chr(10).join(f'- {p}' for p in failure_patterns)}

비평의 약점을 보완하고 제안을 반영한 최종 프롬프트를 만들어.

JSON으로 응답:
```json
{{"new_prompt": "최종 개선 프롬프트", "change_reason": "변경 이유 요약"}}
```"""

        refine_response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": refine_prompt}],
        )
        result = self._parse_json_response(refine_response.content[0].text)

        if not result.get("new_prompt"):
            result["new_prompt"] = draft_prompt
            result["change_reason"] = "Refinement 파싱 실패, 초안 사용"

        logger.info(
            f"[JinxLoop] {agent_name}: Self-Refine 완료 "
            f"(비평 점수: {feedback.get('score', 0):.2f}, 약점: {len(feedback.get('weaknesses', []))}개)"
        )

        return result

    def _parse_json_response(self, text: str) -> dict:
        """JSON 응답 파싱 (```json 블록 또는 raw JSON 지원)"""
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    async def run_ab_test(
        self,
        agent_name: str,
        old_prompt: str,
        new_prompt: str,
        test_cases: Optional[list[dict]] = None,
    ) -> dict:
        """A/B 테스트 실행

        Args:
            agent_name: 테스트할 에이전트
            old_prompt: 기존 프롬프트
            new_prompt: 새 프롬프트
            test_cases: 테스트 케이스 목록 [{input, expected_output}]

        Returns:
            A/B 테스트 결과
        """
        # 테스트 케이스 없으면 과거 작업에서 가져옴
        if not test_cases:
            test_cases = await self._get_test_cases(agent_name)

        if not test_cases:
            logger.info(f"[A/B] {agent_name}: 테스트 케이스 없음, 새 프롬프트 바로 적용")
            return {
                "winner": "new",
                "reason": "no_test_cases",
                "old_score": 0,
                "new_score": 0,
            }

        old_scores = []
        new_scores = []

        for case in test_cases[:5]:  # 최대 5개 케이스
            test_input = case.get("input", "")
            expected = case.get("expected_output", "")

            # 기존 프롬프트 테스트
            old_response = await self._run_with_prompt(
                prompt=old_prompt,
                user_input=test_input,
            )
            old_score = await self._score_response(old_response, expected, test_input)
            old_scores.append(old_score)

            # 새 프롬프트 테스트
            new_response = await self._run_with_prompt(
                prompt=new_prompt,
                user_input=test_input,
            )
            new_score = await self._score_response(new_response, expected, test_input)
            new_scores.append(new_score)

            logger.info(f"[A/B] 케이스: old={old_score:.2f}, new={new_score:.2f}")

        avg_old = sum(old_scores) / len(old_scores) if old_scores else 0
        avg_new = sum(new_scores) / len(new_scores) if new_scores else 0

        # 새 버전이 10% 이상 개선되어야 승리
        improvement_threshold = 0.1
        if avg_new > avg_old * (1 + improvement_threshold):
            winner = "new"
            reason = f"새 프롬프트가 {((avg_new - avg_old) / max(avg_old, 0.01)) * 100:.1f}% 개선"
        elif avg_old > avg_new * (1 + improvement_threshold):
            winner = "old"
            reason = f"기존 프롬프트가 더 좋음 (new: {avg_new:.2f} < old: {avg_old:.2f})"
        else:
            winner = "new"  # 비슷하면 새 버전 적용 (변화 시도)
            reason = "비슷한 성능, 새 프롬프트 시도"

        result = {
            "winner": winner,
            "reason": reason,
            "old_score": avg_old,
            "new_score": avg_new,
            "test_count": len(test_cases),
        }

        # A/B 테스트 결과 저장
        await self._memory.log_ab_test(
            agent_name=agent_name,
            old_score=avg_old,
            new_score=avg_new,
            winner=winner,
            test_count=len(test_cases),
        )

        logger.info(f"[A/B] {agent_name} 결과: {winner} 승리 ({reason})")
        return result

    async def _get_test_cases(self, agent_name: str) -> list[dict]:
        """에이전트의 테스트 케이스 가져오기

        과거 성공한 작업들 중에서 테스트 케이스 추출
        """
        # 과거 성공 작업에서 샘플링
        successful_tasks = await self._memory.get_successful_tasks(
            agent_name=agent_name,
            limit=10,
        )

        test_cases = []
        for task in successful_tasks:
            if task.get("input") and task.get("output"):
                test_cases.append({
                    "input": task["input"],
                    "expected_output": task["output"],
                })

        return test_cases

    async def _run_with_prompt(self, prompt: str, user_input: str) -> str:
        """특정 프롬프트로 테스트 실행"""
        system_prompt = prompt if prompt else "도움이 되는 AI 비서입니다."

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}],
        )

        return response.content[0].text

    async def _score_response(
        self,
        response: str,
        expected: str,
        original_input: str,
    ) -> float:
        """응답 품질 점수 (0-1)

        Claude를 사용하여 응답 품질 평가
        """
        if not expected:
            # 예상 출력 없으면 기본 점수
            return 0.5

        eval_prompt = f"""다음 응답의 품질을 평가해줘.

## 원본 요청
{original_input[:500]}

## 예상 출력
{expected[:500]}

## 실제 응답
{response[:500]}

## 평가 기준
- 정확성: 예상 출력과 의미적으로 일치하는가
- 완성도: 요청에 충분히 답변했는가
- 품질: 명확하고 유용한가

0.0 ~ 1.0 사이의 점수만 숫자로 응답해. (예: 0.85)
"""

        try:
            eval_response = self._client.messages.create(
                model=self._fast_model,  # 평가는 경량 모델로
                max_tokens=50,
                messages=[{"role": "user", "content": eval_prompt}],
            )
            score_text = eval_response.content[0].text.strip()
            # 숫자만 추출
            score_match = re.search(r"(0\.\d+|1\.0|0|1)", score_text)
            if score_match:
                return float(score_match.group(1))
            return 0.5
        except Exception as e:
            logger.warning(f"점수 평가 실패: {e}")
            return 0.5

    async def rollback_prompt(self, agent_name: str) -> dict:
        """프롬프트 롤백 (이전 버전으로)

        Returns:
            롤백 결과
        """
        versions = await self._memory.get_prompt_versions(agent_name)

        if len(versions) < 2:
            return {
                "success": False,
                "reason": "롤백할 이전 버전 없음",
            }

        # 현재 활성 버전
        current = next((v for v in versions if v.get("is_active")), None)
        # 이전 버전 (현재 다음으로 최신)
        previous = next(
            (v for v in versions if not v.get("is_active")),
            None,
        )

        if not previous:
            return {
                "success": False,
                "reason": "이전 버전 없음",
            }

        # 이전 버전 활성화
        await self._memory.activate_prompt_version(
            agent_name=agent_name,
            version=previous["version"],
        )

        logger.info(
            f"[Rollback] {agent_name}: {current['version']} -> {previous['version']}"
        )

        return {
            "success": True,
            "from_version": current["version"],
            "to_version": previous["version"],
            "reason": "롤백 완료",
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
