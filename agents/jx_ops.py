"""JX_OPS - 시스템/운영 전문 에이전트

LangGraph 패턴 적용:
- retry 로직 (최대 3회, 지수 백오프)
- reflect (반성 → 개선점 도출)
- memory_write (장기기억 저장)

실제 도구 사용:
- github_agent: GitHub 작업 실행
- scheduler: 스케줄 작업 등록
- file_manager: 파일 CRUD
"""
import asyncio
import uuid
import time
import json
import re

from anthropic import Anthropic

from config import get_settings
from memory import get_jinx_memory
from tools.github_agent import GitHubAgent
from tools.scheduler import Scheduler
from tools.file_manager import FileManager


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

        # 실제 도구 초기화
        self._github = GitHubAgent()
        self._scheduler = Scheduler()
        self._file_manager = FileManager()

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
        """단일 실행 시도 - 실제 도구 사용"""
        # 파괴적 작업이면 확인 요청만
        if is_destructive:
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, 이 작업은 파괴적입니다.\n\n요청: {instruction}\n\n실행 전 확인이 필요합니다. '확인'이라고 말씀해주시면 진행하겠습니다.",
                "error": None,
                "task_type": task_type,
                "is_destructive": is_destructive,
                "requires_confirmation": True,
            }

        # 작업 유형별 실제 실행
        if task_type == "github":
            return await self._execute_github(instruction)
        elif task_type == "schedule":
            return await self._execute_schedule(instruction)
        elif task_type == "file":
            return await self._execute_file(instruction)
        else:
            # 일반 작업은 안내만
            return await self._execute_guide(instruction, context, memory_context, task_type)

    async def _execute_github(self, instruction: str) -> dict:
        """GitHub 작업 실제 실행"""
        # Claude에게 어떤 GitHub 작업을 해야 하는지 분석 요청
        analysis_prompt = f"""다음 GitHub 관련 요청을 분석해서 실행할 작업을 JSON으로 알려줘.

요청: {instruction}

사용 가능한 action:
- get_repo: 레포 정보 조회 (repo 필요)
- list_branches: 브랜치 목록 (repo 필요)
- create_branch: 브랜치 생성 (repo, branch, base 필요)
- commit_file: 파일 커밋 (repo, path, content, message 필요)
- create_pr: PR 생성 (repo, title, body, branch, base 필요)
- list_prs: PR 목록 (repo 필요)
- create_issue: 이슈 생성 (repo, title, body 필요)
- list_issues: 이슈 목록 (repo 필요)

JSON 형식으로만 응답해:
```json
{{"action": "...", "repo": "owner/repo", ...}}
```

실행할 수 없거나 정보가 부족하면:
```json
{{"action": "none", "reason": "이유..."}}
```"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        response_text = response.content[0].text

        # JSON 파싱
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group(1))
            else:
                params = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, GitHub 작업을 분석했지만 추가 정보가 필요합니다.\n\n분석 결과:\n{response_text}",
                "error": None,
                "task_type": "github",
                "is_destructive": False,
            }

        if params.get("action") == "none":
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, {params.get('reason', '요청을 처리할 수 없습니다.')}",
                "error": None,
                "task_type": "github",
                "is_destructive": False,
            }

        # 실제 GitHub 작업 실행
        result = await self._github.run(params)

        if result.success:
            return {
                "success": True,
                "score": 0.95,
                "output": f"주인님, GitHub 작업을 완료했습니다.\n\n작업: {params.get('action')}\n결과:\n```json\n{json.dumps(result.output, ensure_ascii=False, indent=2)}\n```",
                "error": None,
                "task_type": "github",
                "is_destructive": False,
            }
        else:
            return {
                "success": False,
                "score": 0.3,
                "output": f"주인님, GitHub 작업 중 오류가 발생했습니다.\n\n오류: {result.error}",
                "error": result.error,
                "task_type": "github",
                "is_destructive": False,
            }

    async def _execute_schedule(self, instruction: str) -> dict:
        """스케줄 작업 실제 실행"""
        # Claude에게 스케줄 작업 분석 요청
        analysis_prompt = f"""다음 스케줄 관련 요청을 분석해서 실행할 작업을 JSON으로 알려줘.

요청: {instruction}

사용 가능한 action:
- add: 스케줄 추가 (name, cron, task_prompt 필요)
- remove: 스케줄 제거 (name 필요)
- list: 스케줄 목록 조회
- pause: 스케줄 일시정지 (name 필요)
- resume: 스케줄 재개 (name 필요)

cron 형식: "분 시 일 월 요일" (예: "0 9 * * *" = 매일 9시)

JSON 형식으로만 응답해:
```json
{{"action": "add", "name": "daily_news", "cron": "0 9 * * *", "task_prompt": "AI 뉴스 검색해서 요약해줘"}}
```"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        response_text = response.content[0].text

        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group(1))
            else:
                params = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, 스케줄 작업을 분석했습니다.\n\n{response_text}",
                "error": None,
                "task_type": "schedule",
                "is_destructive": False,
            }

        # 실제 스케줄 작업 실행
        result = await self._scheduler.run(params)

        if result.success:
            return {
                "success": True,
                "score": 0.95,
                "output": f"주인님, 스케줄 작업을 완료했습니다.\n\n작업: {params.get('action')}\n결과:\n```json\n{json.dumps(result.output, ensure_ascii=False, indent=2)}\n```",
                "error": None,
                "task_type": "schedule",
                "is_destructive": False,
            }
        else:
            return {
                "success": False,
                "score": 0.3,
                "output": f"주인님, 스케줄 작업 중 오류가 발생했습니다.\n\n오류: {result.error}",
                "error": result.error,
                "task_type": "schedule",
                "is_destructive": False,
            }

    async def _execute_file(self, instruction: str) -> dict:
        """파일 작업 실제 실행"""
        # Claude에게 파일 작업 분석 요청
        analysis_prompt = f"""다음 파일 관련 요청을 분석해서 실행할 작업을 JSON으로 알려줘.

요청: {instruction}

사용 가능한 action:
- read: 파일 읽기 (path 필요)
- write: 파일 쓰기 (path, content 필요)
- list: 디렉토리 목록 (path 필요)
- delete: 파일 삭제 (path 필요) - 주의: 파괴적 작업
- move: 파일 이동 (source, destination 필요)
- copy: 파일 복사 (source, destination 필요)

JSON 형식으로만 응답해:
```json
{{"action": "read", "path": "/path/to/file"}}
```

삭제 등 파괴적 작업이면:
```json
{{"action": "delete", "path": "...", "destructive": true}}
```"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        response_text = response.content[0].text

        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group(1))
            else:
                params = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, 파일 작업을 분석했습니다.\n\n{response_text}",
                "error": None,
                "task_type": "file",
                "is_destructive": False,
            }

        # 파괴적 작업이면 확인 요청
        if params.get("destructive"):
            return {
                "success": True,
                "score": 0.7,
                "output": f"주인님, 이 작업은 파괴적입니다.\n\n작업: {params.get('action')}\n경로: {params.get('path')}\n\n실행하려면 '확인'이라고 말씀해주세요.",
                "error": None,
                "task_type": "file",
                "is_destructive": True,
                "pending_action": params,
            }

        # 실제 파일 작업 실행
        result = await self._file_manager.run(params)

        if result.success:
            output_str = result.output if isinstance(result.output, str) else json.dumps(result.output, ensure_ascii=False, indent=2)
            return {
                "success": True,
                "score": 0.95,
                "output": f"주인님, 파일 작업을 완료했습니다.\n\n작업: {params.get('action')}\n결과:\n```\n{output_str[:2000]}\n```",
                "error": None,
                "task_type": "file",
                "is_destructive": False,
            }
        else:
            return {
                "success": False,
                "score": 0.3,
                "output": f"주인님, 파일 작업 중 오류가 발생했습니다.\n\n오류: {result.error}",
                "error": result.error,
                "task_type": "file",
                "is_destructive": False,
            }

    async def _execute_guide(
        self, instruction: str, context: list, memory_context: list, task_type: str
    ) -> dict:
        """일반 작업 안내 (기존 방식)"""
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        type_guide = self._get_type_guide(task_type)

        prompt = f"""주인님의 운영 요청: {instruction}
{memory_str}

{type_guide}

이 요청을 어떻게 처리할지 계획을 세우고, 실행 방법을 안내해줘."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "success": True,
            "score": 0.85,
            "output": response.content[0].text,
            "error": None,
            "task_type": task_type,
            "is_destructive": False,
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
