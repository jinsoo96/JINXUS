"""JX_OPS - 시스템/운영 전문 에이전트

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


class JXOps:
    """시스템/운영 전문가 에이전트

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_OPS"
    description = "파일, GitHub, 스케줄 관리를 전담하는 에이전트"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"

    def _get_system_prompt(self) -> str:
        return """너는 JX_OPS야. 주인님을 모시는 JINXUS의 운영 전문가.

## 역할
주인님의 시스템 운영 요청을 처리한다.
- 파일/폴더 관리
- GitHub 작업
- 스케줄 관리
- 서버/인프라 운영

## 안전 원칙
- 파괴적 작업은 반드시 주인님께 확인
- 작업 전후 상태 보고
- 되돌릴 수 없는 작업 경고

## 작업 유형별 가이드
- 파일: ls, cp, mv, rm 명령어 안내
- GitHub: git/gh CLI 사용법 안내
- 스케줄: cron 또는 시스템 스케줄러 안내
- 서버: Docker, 프로세스 관리 안내

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

        # === [plan] 작업 유형 판단 ===
        task_type = self._determine_task_type(instruction)
        is_destructive = self._is_destructive(instruction)
        plan = {
            "strategy": "ops_guide",
            "task_type": task_type,
            "is_destructive": is_destructive,
            "instruction": instruction
        }

        # === [execute] + [evaluate] + [retry] ===
        result = await self._execute_with_retry(instruction, context, memory_context, task_type, is_destructive)

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

    def _determine_task_type(self, instruction: str) -> str:
        """작업 유형 판단"""
        instruction_lower = instruction.lower()
        if any(k in instruction_lower for k in ["파일", "폴더", "디렉토리", "복사", "이동", "삭제"]):
            return "file"
        elif any(k in instruction_lower for k in ["git", "github", "커밋", "푸시", "풀"]):
            return "github"
        elif any(k in instruction_lower for k in ["스케줄", "cron", "예약", "자동화"]):
            return "schedule"
        elif any(k in instruction_lower for k in ["docker", "컨테이너", "서버", "프로세스"]):
            return "server"
        else:
            return "general"

    def _is_destructive(self, instruction: str) -> bool:
        """파괴적 작업인지 판단"""
        destructive_keywords = [
            "삭제", "제거", "rm ", "rm -rf", "drop", "delete",
            "포맷", "초기화", "reset", "force", "hard"
        ]
        instruction_lower = instruction.lower()
        return any(k in instruction_lower for k in destructive_keywords)

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list, task_type: str, is_destructive: bool
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # === [execute] ===
                result = await self._execute(instruction, context, memory_context, task_type, is_destructive, last_error)

                # === [evaluate] ===
                if result["success"]:
                    return result

                # 실패 시 다음 시도를 위해 에러 저장
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
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
        }

    async def _execute(
        self, instruction: str, context: list, memory_context: list,
        task_type: str, is_destructive: bool, last_error: str = None
    ) -> dict:
        """단일 실행 시도"""
        # 이전 실패가 있으면 프롬프트에 포함
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n다른 방법을 안내해줘."

        # 메모리 컨텍스트
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        # 작업 유형별 가이드
        type_guide = self._get_type_guide(task_type)

        # 파괴적 작업 경고
        destructive_warning = ""
        if is_destructive:
            destructive_warning = """
⚠️ 주의: 이 작업은 파괴적입니다. 되돌릴 수 없을 수 있습니다.
반드시 주인님께 확인을 받은 후 실행해야 합니다.
"""

        prompt = f"""주인님의 운영 요청: {instruction}
{memory_str}
{error_context}

{type_guide}
{destructive_warning}

이 요청을 어떻게 처리할지 계획을 세우고, 실행 방법을 안내해줘.
파괴적 작업이라면 주인님께 확인을 요청해."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )

        output = response.content[0].text

        return {
            "success": True,
            "score": 0.85,
            "output": output,
            "error": None,
            "task_type": task_type,
            "is_destructive": is_destructive,
        }

    def _get_type_guide(self, task_type: str) -> str:
        """작업 유형별 가이드"""
        guides = {
            "file": "파일 작업: ls, cp, mv, rm, mkdir, chmod 명령어 활용",
            "github": "GitHub 작업: git clone/add/commit/push, gh pr/issue 명령어 활용",
            "schedule": "스케줄 작업: crontab -e, launchd, systemd timer 활용",
            "server": "서버 작업: docker, systemctl, ps, kill 명령어 활용",
            "general": "",
        }
        return guides.get(task_type, "")

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 다른 접근 방식을 시도해야 함."

        # 성공 시 간단한 반성
        is_destructive = result.get("is_destructive", False)
        reflect_prompt = f"""방금 완료한 운영 작업:
요청: {instruction}
결과: 성공
파괴적 작업 여부: {'예' if is_destructive else '아니오'}

이 작업에서 배운 핵심 포인트를 1-2문장으로 정리해줘."""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text
        except Exception:
            return "운영 작업 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 중요도 계산
            importance = 0.3
            if not result["success"]:
                importance += 0.4  # 실패에서 배움
            if result.get("is_destructive"):
                importance += 0.3  # 파괴적 작업은 기억해야 함
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
