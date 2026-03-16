"""프로젝트 관리자 v1.0.0

대규모 프로젝트를 페이즈 단위로 분해하여 순차/병렬 실행한다.
기존 AutonomousRunner의 10-step 한계를 넘어서, 페이즈당 독립 실행으로 사실상 무제한 확장.

핵심 흐름:
1. 사용자 지시 → LLM이 페이즈 분해 (DAG 의존성 포함)
2. 의존성 순서대로 페이즈 실행 (BackgroundWorker 활용)
3. 페이즈 완료 시 결과 요약 → 다음 페이즈에 컨텍스트 주입
4. 전체 완료/실패/취소 시 알림

중단 시:
- 실행 중인 모든 페이즈 취소
- Redis 영속 데이터 삭제
- BackgroundWorker 작업 정리
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Awaitable

from anthropic import AsyncAnthropic
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


# ── 데이터 모델 ──────────────────────────────────────────────────────────


class ProjectStatus(str, Enum):
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhaseStatus(str, Enum):
    PENDING = "pending"
    WAITING = "waiting"  # depends_on 대기 중
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProjectPhase:
    """프로젝트 페이즈"""
    id: str
    name: str
    instruction: str
    agent: str  # 주 담당 에이전트 (JINXUS_CORE가 알아서 배분)
    depends_on: list[str] = field(default_factory=list)  # 선행 페이즈 ID 목록
    status: PhaseStatus = PhaseStatus.PENDING
    result_summary: str = ""
    task_id: str = ""  # BackgroundWorker 작업 ID
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: str = ""
    max_steps: int = 10  # 페이즈당 최대 스텝
    review_iteration: int = 0  # 리뷰→수정 반복 횟수
    is_fix_phase: bool = False  # 리뷰 수정으로 생성된 페이즈인지


@dataclass
class Project:
    """프로젝트"""
    id: str
    title: str
    description: str  # 원본 사용자 지시
    phases: list[ProjectPhase] = field(default_factory=list)
    status: ProjectStatus = ProjectStatus.PLANNING
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    total_duration_s: float = 0.0
    error: str = ""


# Redis 키 패턴
_PROJECT_KEY = "jinxus:project:{project_id}"
_PROJECT_LIST_KEY = "jinxus:projects"

# 페이즈 분해 프롬프트
_DECOMPOSE_PROMPT = """너는 JINXUS의 프로젝트 설계자다.
사용자의 대규모 프로젝트 요청을 독립적인 페이즈(Phase)들로 분해해야 한다.

규칙:
- 각 페이즈는 하나의 완결된 작업 단위 (AutonomousRunner가 10단계 이내로 처리 가능)
- 페이즈 간 의존성을 명확히 설정 (depends_on)
- 병렬 실행 가능한 페이즈는 의존성 없이 설계
- 페이즈 수는 2~15개 사이로 유지
- 각 페이즈에 적합한 에이전트 지정 (JINXUS_CORE가 기본, 특화 작업은 JX_CODER / JX_RESEARCHER 등)
- 마지막 페이즈로 "검증 및 통합 테스트"를 포함하면 좋음
- 페이즈 이름은 간결하게, instruction은 구체적으로

중요 — 파일 생성 규칙:
- 코딩 페이즈의 instruction에는 반드시 "파일을 실제로 생성하라"고 명시할 것
- 사용자가 경로를 지정한 경우, 그 경로에 파일을 생성하도록 instruction에 포함할 것
- "코드를 작성해" 가 아니라 "다음 경로에 파일을 생성하고 코드를 작성해" 로 지시할 것
- 코드 실행이 필요하면 code_executor 도구를 사용하도록 지시할 것
- 디렉토리 생성, 파일 쓰기는 mcp:filesystem 도구를 사용하도록 지시할 것

사용 가능한 에이전트:
- JINXUS_CORE: 범용 오케스트레이터 (기본값)
- JX_CODER: 코딩 작업 (구현, 리팩토링, 버그 수정) — mcp:filesystem, code_executor 사용 가능
- JX_RESEARCHER: 조사 작업 (웹 검색, 분석, 보고서)
- JX_WRITER: 문서 작성
- JX_ANALYST: 데이터 분석
- JX_OPS: 인프라, 배포, 자동화 — 모든 도구 사용 가능

응답 형식 (JSON만 출력):
{
  "title": "프로젝트 한줄 제목",
  "phases": [
    {
      "name": "페이즈 이름",
      "instruction": "수행할 구체적 지시 (상세하게, 파일 경로 포함)",
      "agent": "담당 에이전트명",
      "depends_on": [],
      "max_steps": 10
    },
    {
      "name": "페이즈 2",
      "instruction": "...",
      "agent": "JX_CODER",
      "depends_on": ["페이즈 이름"],
      "max_steps": 8
    }
  ]
}"""


class ProjectManager:
    """프로젝트 관리자

    대규모 작업을 페이즈로 분해하고 순차/병렬 실행을 관리한다.
    """

    def __init__(self):
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._projects: dict[str, Project] = {}
        self._phase_watchers: dict[str, asyncio.Task] = {}  # project_id -> 감시 태스크
        self._redis = None
        # SSE 이벤트 구독자 (project_id -> [asyncio.Queue])
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._event_buffer: dict[str, list[dict]] = {}

    async def _get_redis(self):
        """Redis 연결 (lazy)"""
        if self._redis is None:
            import redis.asyncio as aioredis
            settings = get_settings()
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )
        return self._redis

    # ── 프로젝트 생성 ──

    async def create_project(self, description: str) -> Project:
        """프로젝트 생성 (LLM 페이즈 분해)"""
        project_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        project = Project(
            id=project_id,
            title="",
            description=description,
            status=ProjectStatus.PLANNING,
            created_at=now,
            updated_at=now,
        )
        self._projects[project_id] = project

        try:
            # LLM으로 페이즈 분해
            response = await self._client.messages.create(
                model=self._fast_model,
                max_tokens=4000,
                system=_DECOMPOSE_PROMPT,
                messages=[{"role": "user", "content": description}],
            )

            raw = response.content[0].text
            # JSON 추출
            plan = self._parse_json(raw)
            if not plan or "phases" not in plan:
                raise ValueError("페이즈 분해 실패: JSON 파싱 오류")

            project.title = plan.get("title", description[:50])
            phases = []
            phase_name_to_id = {}

            for p in plan["phases"]:
                phase_id = str(uuid.uuid4())[:8]
                phase_name_to_id[p["name"]] = phase_id
                phases.append(ProjectPhase(
                    id=phase_id,
                    name=p["name"],
                    instruction=p["instruction"],
                    agent=p.get("agent", "JINXUS_CORE"),
                    max_steps=min(p.get("max_steps", 10), 15),
                ))

            # depends_on 이름 → ID 변환
            for i, p in enumerate(plan["phases"]):
                deps = p.get("depends_on", [])
                phases[i].depends_on = [
                    phase_name_to_id[dep]
                    for dep in deps
                    if dep in phase_name_to_id
                ]

            project.phases = phases
            project.status = ProjectStatus.READY
            project.updated_at = datetime.now().isoformat()

            # Redis에 저장
            await self._save_project(project)

            logger.info(f"[ProjectManager] 프로젝트 생성: {project_id[:8]} - {project.title} ({len(phases)}개 페이즈)")
            return project

        except Exception as e:
            project.status = ProjectStatus.FAILED
            project.error = str(e)
            logger.error(f"[ProjectManager] 프로젝트 생성 실패: {e}")
            return project

    # ── 프로젝트 실행 ──

    async def start_project(self, project_id: str) -> bool:
        """프로젝트 실행 시작"""
        project = self._projects.get(project_id)
        if not project or project.status not in (ProjectStatus.READY, ProjectStatus.PAUSED):
            return False

        project.status = ProjectStatus.RUNNING
        project.updated_at = datetime.now().isoformat()

        # 실행 가능한 페이즈 찾기 (의존성 충족된 것)
        await self._dispatch_ready_phases(project)

        # 페이즈 완료 감시 태스크 시작
        watcher = asyncio.create_task(self._phase_watcher(project_id))
        self._phase_watchers[project_id] = watcher

        await self._save_project(project)
        await self._publish_event(project_id, "project_started", {
            "title": project.title,
            "total_phases": len(project.phases),
        })

        logger.info(f"[ProjectManager] 프로젝트 실행 시작: {project_id[:8]}")
        return True

    async def _dispatch_ready_phases(self, project: Project):
        """의존성이 충족된 대기 중 페이즈들을 BackgroundWorker에 제출"""
        from jinxus.core.background_worker import get_background_worker

        worker = get_background_worker()

        for phase in project.phases:
            if phase.status not in (PhaseStatus.PENDING, PhaseStatus.WAITING):
                continue

            # 의존성 확인
            deps_met = all(
                self._get_phase(project, dep_id).status == PhaseStatus.COMPLETED
                for dep_id in phase.depends_on
                if self._get_phase(project, dep_id)
            )

            if not deps_met:
                phase.status = PhaseStatus.WAITING
                continue

            # 선행 페이즈 결과 + 아티팩트를 컨텍스트로 주입
            context = await self._build_phase_context_with_artifacts(project, phase)
            full_instruction = f"{context}\n\n[현재 작업]\n{phase.instruction}" if context else phase.instruction

            # BackgroundWorker에 제출
            task_id = await worker.submit(
                task_description=full_instruction,
                session_id=f"project_{project.id}",
                autonomous=True,
                max_steps=phase.max_steps,
                timeout_seconds=2 * 3600,  # 페이즈당 2시간
            )

            phase.task_id = task_id
            phase.status = PhaseStatus.RUNNING
            phase.started_at = datetime.now().isoformat()

            await self._publish_event(project.id, "phase_started", {
                "phase_id": phase.id,
                "phase_name": phase.name,
                "agent": phase.agent,
                "task_id": task_id,
            })

            logger.info(f"[ProjectManager] 페이즈 시작: {phase.name} → task {task_id[:8]}")

    def _build_phase_context(self, project: Project, phase: ProjectPhase) -> str:
        """선행 페이즈 결과를 컨텍스트로 조합 (아티팩트 포함)"""
        if not phase.depends_on:
            return ""

        parts = []
        for dep_id in phase.depends_on:
            dep_phase = self._get_phase(project, dep_id)
            if dep_phase and dep_phase.result_summary:
                parts.append(f"[{dep_phase.name} 결과]\n{dep_phase.result_summary[:2000]}")

        if not parts:
            return ""

        return f"[선행 작업 결과]\n{''.join(parts)}"

    async def _build_phase_context_with_artifacts(
        self, project: Project, phase: ProjectPhase
    ) -> str:
        """선행 페이즈 결과 + 아티팩트를 컨텍스트로 조합"""
        if not phase.depends_on:
            return ""

        # 기존 텍스트 컨텍스트
        text_context = self._build_phase_context(project, phase)

        # 아티팩트 컨텍스트
        try:
            from jinxus.core.artifact_store import get_artifact_store
            store = get_artifact_store()
            artifact_context = await store.get_phase_artifacts_summary(
                project_id=project.id,
                phase_ids=phase.depends_on,
                max_content_len=2000,
            )
        except Exception as e:
            logger.debug(f"[ProjectManager] 아티팩트 컨텍스트 로드 실패: {e}")
            artifact_context = ""

        parts = []
        if text_context:
            parts.append(text_context)
        if artifact_context:
            parts.append(artifact_context)

        return "\n\n".join(parts)

    def _get_phase(self, project: Project, phase_id: str) -> Optional[ProjectPhase]:
        """ID로 페이즈 조회"""
        for p in project.phases:
            if p.id == phase_id:
                return p
        return None

    async def _maybe_review_phase(self, project: Project, phase: ProjectPhase):
        """코딩 페이즈 완료 시 리뷰→수정 루프 실행

        1. 코딩 관련 페이즈인지 확인
        2. 결과를 LLM으로 리뷰
        3. critical/warning 이슈 발견 시 수정 페이즈 자동 생성
        """
        try:
            from jinxus.core.review_loop import get_review_loop

            review_loop = get_review_loop()

            # FIX-2: 수정 페이즈는 리뷰 스킵 (무한 체인 방지)
            if phase.is_fix_phase:
                logger.debug(f"[ProjectManager] 수정 페이즈 리뷰 스킵: {phase.name}")
                return

            # FIX-3: 빈 결과 리뷰 방지 (계획 실패, 0 스텝 등)
            summary = phase.result_summary.strip()
            if not summary or len(summary) < 50 or "계획 생성 실패" in summary:
                logger.debug(f"[ProjectManager] 빈/실패 결과 리뷰 스킵: {phase.name}")
                return

            # 리뷰 대상인지 확인
            if not review_loop.should_review(phase.name, phase.agent):
                return

            # 반복 한도 확인
            if not review_loop.can_iterate(phase.review_iteration):
                logger.info(
                    f"[ProjectManager] 리뷰 반복 한도 도달: {phase.name} "
                    f"({phase.review_iteration}회)"
                )
                return

            # 리뷰 실행
            review_result = await review_loop.review(
                task_description=phase.instruction,
                result_text=phase.result_summary,
                iteration=phase.review_iteration,
            )

            if review_result.passed:
                await self._publish_event(project.id, "review_passed", {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "summary": review_result.summary,
                })
                return

            # 이슈 발견 → 수정 페이즈 생성
            fix_instruction = review_loop.build_fix_instruction(
                original_instruction=phase.instruction,
                review_result=review_result,
            )

            if not fix_instruction:
                return

            fix_phase_id = str(uuid.uuid4())[:8]
            fix_phase = ProjectPhase(
                id=fix_phase_id,
                name=f"{phase.name} 수정 #{phase.review_iteration + 1}",
                instruction=fix_instruction,
                agent=phase.agent,  # 같은 에이전트가 수정
                depends_on=[phase.id],
                status=PhaseStatus.PENDING,
                max_steps=phase.max_steps,
                review_iteration=phase.review_iteration + 1,
                is_fix_phase=True,
            )

            # 프로젝트에 수정 페이즈 추가
            project.phases.append(fix_phase)

            # 기존에 이 페이즈에 의존하던 페이즈들의 depends_on을 수정 페이즈로 교체
            for p in project.phases:
                if phase.id in p.depends_on and p.id != fix_phase_id:
                    p.depends_on = [
                        fix_phase_id if d == phase.id else d
                        for d in p.depends_on
                    ]

            await self._publish_event(project.id, "review_fix_created", {
                "phase_id": phase.id,
                "phase_name": phase.name,
                "fix_phase_id": fix_phase_id,
                "fix_phase_name": fix_phase.name,
                "issues_count": len(review_result.issues),
                "iteration": phase.review_iteration + 1,
            })

            logger.info(
                f"[ProjectManager] 리뷰→수정 페이즈 생성: {fix_phase.name} "
                f"(이슈 {len(review_result.issues)}개)"
            )

        except Exception as e:
            logger.warning(f"[ProjectManager] 리뷰 루프 오류: {e}")

    async def _phase_watcher(self, project_id: str):
        """페이즈 완료를 감시하고 다음 페이즈를 디스패치"""
        from jinxus.core.background_worker import get_background_worker

        worker = get_background_worker()

        try:
            while True:
                await asyncio.sleep(5)  # 5초 간격 확인

                project = self._projects.get(project_id)
                if not project or project.status not in (ProjectStatus.RUNNING,):
                    break

                changed = False
                for phase in project.phases:
                    if phase.status != PhaseStatus.RUNNING or not phase.task_id:
                        continue

                    # BackgroundWorker에서 작업 상태 확인
                    task = worker.get_task(phase.task_id)
                    if not task:
                        # FIX-6: 작업이 BackgroundWorker에서 사라짐
                        # (완료 후 정리됐거나 서버 재시작)
                        # → 완료 처리 (결과는 빈 값)
                        phase.status = PhaseStatus.COMPLETED
                        phase.completed_at = datetime.now().isoformat()
                        if not phase.result_summary:
                            phase.result_summary = "(작업 결과 유실 — BackgroundWorker에서 조기 정리됨)"
                        changed = True
                        logger.warning(
                            f"[ProjectManager] 페이즈 '{phase.name}' task {phase.task_id[:8]} "
                            f"이 BackgroundWorker에서 사라짐 → 완료 처리"
                        )
                        continue

                    if task.status.value == "completed":
                        phase.status = PhaseStatus.COMPLETED
                        phase.result_summary = (task.result or "")[:3000]
                        phase.completed_at = datetime.now().isoformat()
                        changed = True

                        # 아티팩트 자동 추출
                        try:
                            from jinxus.core.artifact_store import get_artifact_store
                            store = get_artifact_store()
                            await store.extract_artifacts_from_result(
                                project_id=project_id,
                                phase_id=phase.id,
                                phase_name=phase.name,
                                result_text=task.result or "",
                            )
                        except Exception as ae:
                            logger.debug(f"[ProjectManager] 아티팩트 추출 실패: {ae}")

                        await self._publish_event(project_id, "phase_completed", {
                            "phase_id": phase.id,
                            "phase_name": phase.name,
                            "result_preview": phase.result_summary[:200],
                        })
                        logger.info(f"[ProjectManager] 페이즈 완료: {phase.name}")

                        # 리뷰→수정 루프: 코딩 페이즈 완료 시 자동 리뷰
                        await self._maybe_review_phase(project, phase)

                    elif task.status.value == "failed":
                        phase.status = PhaseStatus.FAILED
                        phase.error = task.error or "알 수 없는 오류"
                        phase.completed_at = datetime.now().isoformat()
                        changed = True

                        await self._publish_event(project_id, "phase_failed", {
                            "phase_id": phase.id,
                            "phase_name": phase.name,
                            "error": phase.error[:200],
                        })
                        logger.warning(f"[ProjectManager] 페이즈 실패: {phase.name} - {phase.error[:100]}")

                    elif task.status.value == "cancelled":
                        phase.status = PhaseStatus.CANCELLED
                        phase.completed_at = datetime.now().isoformat()
                        changed = True

                if changed:
                    # 새로 실행 가능한 페이즈 디스패치
                    await self._dispatch_ready_phases(project)
                    project.updated_at = datetime.now().isoformat()
                    await self._save_project(project)

                    # 전체 완료 여부 확인
                    all_done = all(
                        p.status in (PhaseStatus.COMPLETED, PhaseStatus.FAILED, PhaseStatus.CANCELLED)
                        for p in project.phases
                    )

                    if all_done:
                        failed = [p for p in project.phases if p.status == PhaseStatus.FAILED]
                        if failed:
                            project.status = ProjectStatus.FAILED
                            project.error = f"{len(failed)}개 페이즈 실패"
                        else:
                            project.status = ProjectStatus.COMPLETED

                        project.completed_at = datetime.now().isoformat()
                        if project.created_at:
                            project.total_duration_s = (
                                datetime.fromisoformat(project.completed_at)
                                - datetime.fromisoformat(project.created_at)
                            ).total_seconds()

                        await self._save_project(project)
                        await self._publish_event(project_id, "project_completed", {
                            "status": project.status.value,
                            "total_phases": len(project.phases),
                            "completed": len([p for p in project.phases if p.status == PhaseStatus.COMPLETED]),
                            "failed": len(failed),
                            "duration_s": round(project.total_duration_s, 1),
                        })
                        logger.info(f"[ProjectManager] 프로젝트 {'완료' if not failed else '실패'}: {project_id[:8]}")
                        break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[ProjectManager] 페이즈 감시 오류: {e}", exc_info=True)

    # ── 프로젝트 중단 & 삭제 ──

    async def stop_project(self, project_id: str) -> bool:
        """프로젝트 중단 — 실행 중인 모든 페이즈 취소 + 데이터 삭제"""
        project = self._projects.get(project_id)
        if not project:
            return False

        # 1. 감시 태스크 취소
        watcher = self._phase_watchers.pop(project_id, None)
        if watcher:
            watcher.cancel()

        # 2. 실행 중인 페이즈들의 BackgroundWorker 작업 취소
        from jinxus.core.background_worker import get_background_worker
        worker = get_background_worker()

        for phase in project.phases:
            if phase.status in (PhaseStatus.RUNNING, PhaseStatus.WAITING, PhaseStatus.PENDING):
                phase.status = PhaseStatus.CANCELLED
                phase.completed_at = datetime.now().isoformat()

                if phase.task_id:
                    await worker.cancel_task(phase.task_id)

        # 3. 프로젝트 상태 업데이트
        project.status = ProjectStatus.CANCELLED
        project.completed_at = datetime.now().isoformat()
        project.updated_at = datetime.now().isoformat()

        await self._publish_event(project_id, "project_stopped", {
            "reason": "사용자 중단",
        })

        # 4. Redis 영속 데이터 삭제
        await self._delete_project_data(project_id)

        # 4.5. 아티팩트 삭제
        try:
            from jinxus.core.artifact_store import get_artifact_store
            await get_artifact_store().delete_project_artifacts(project_id)
        except Exception as ae:
            logger.debug(f"[ProjectManager] 아티팩트 삭제 실패: {ae}")

        # 5. 인메모리에서 제거
        self._projects.pop(project_id, None)
        self._subscribers.pop(project_id, None)
        self._event_buffer.pop(project_id, None)

        logger.info(f"[ProjectManager] 프로젝트 중단 및 삭제: {project_id[:8]}")
        return True

    async def delete_project(self, project_id: str) -> bool:
        """완료/실패/취소된 프로젝트 삭제"""
        project = self._projects.get(project_id)
        if not project:
            return False

        if project.status in (ProjectStatus.RUNNING, ProjectStatus.PLANNING):
            # 실행 중이면 먼저 중단
            await self.stop_project(project_id)
            return True

        await self._delete_project_data(project_id)
        self._projects.pop(project_id, None)
        self._subscribers.pop(project_id, None)
        self._event_buffer.pop(project_id, None)

        logger.info(f"[ProjectManager] 프로젝트 삭제: {project_id[:8]}")
        return True

    # ── 프로젝트 조회 ──

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_all_projects(self) -> list[Project]:
        return list(self._projects.values())

    # ── 페이즈 수정 ──

    async def update_phase_instruction(
        self, project_id: str, phase_id: str, new_instruction: str
    ) -> bool:
        """대기 중인 페이즈의 지시 수정"""
        project = self._projects.get(project_id)
        if not project:
            return False

        phase = self._get_phase(project, phase_id)
        if not phase or phase.status not in (PhaseStatus.PENDING, PhaseStatus.WAITING):
            return False

        phase.instruction = new_instruction
        project.updated_at = datetime.now().isoformat()
        await self._save_project(project)
        return True

    # ── SSE 이벤트 ──

    async def _publish_event(self, project_id: str, event_type: str, data: dict):
        """이벤트 발행"""
        event = {"event": event_type, "data": data, "timestamp": datetime.now().isoformat()}

        # 버퍼에 저장
        buf = self._event_buffer.setdefault(project_id, [])
        buf.append(event)
        if len(buf) > 200:
            buf[:] = buf[-200:]

        # 구독자에게 전달
        for queue in self._subscribers.get(project_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, project_id: str) -> asyncio.Queue:
        """프로젝트 이벤트 구독 (SSE용)"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # 버퍼 replay
        for event in self._event_buffer.get(project_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                break

        self._subscribers.setdefault(project_id, []).append(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue):
        """구독 해제"""
        subs = self._subscribers.get(project_id, [])
        if queue in subs:
            subs.remove(queue)

    # ── Redis 영속화 ──

    async def _save_project(self, project: Project):
        """프로젝트를 Redis에 저장"""
        try:
            redis = await self._get_redis()
            key = _PROJECT_KEY.format(project_id=project.id)
            data = {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "status": project.status.value,
                "phases": [asdict(p) for p in project.phases],
                "created_at": project.created_at,
                "updated_at": project.updated_at,
                "completed_at": project.completed_at,
                "total_duration_s": project.total_duration_s,
                "error": project.error,
            }
            # PhaseStatus enum → string
            for p in data["phases"]:
                if isinstance(p["status"], PhaseStatus):
                    p["status"] = p["status"].value

            await redis.set(key, json.dumps(data, ensure_ascii=False), ex=7 * 86400)  # 7일 TTL
            await redis.sadd(_PROJECT_LIST_KEY, project.id)
        except Exception as e:
            logger.warning(f"[ProjectManager] Redis 저장 실패: {e}")

    async def _delete_project_data(self, project_id: str):
        """Redis에서 프로젝트 데이터 삭제"""
        try:
            redis = await self._get_redis()
            key = _PROJECT_KEY.format(project_id=project_id)
            await redis.delete(key)
            await redis.srem(_PROJECT_LIST_KEY, project_id)
        except Exception as e:
            logger.warning(f"[ProjectManager] Redis 삭제 실패: {e}")

    async def restore_projects(self):
        """서버 시작 시 Redis에서 프로젝트 복원"""
        try:
            redis = await self._get_redis()
            project_ids = await redis.smembers(_PROJECT_LIST_KEY)

            for pid in project_ids:
                key = _PROJECT_KEY.format(project_id=pid)
                raw = await redis.get(key)
                if not raw:
                    continue

                data = json.loads(raw)
                phases = []
                for p in data.get("phases", []):
                    phase = ProjectPhase(
                        id=p["id"],
                        name=p["name"],
                        instruction=p["instruction"],
                        agent=p.get("agent", "JINXUS_CORE"),
                        depends_on=p.get("depends_on", []),
                        status=PhaseStatus(p.get("status", "pending")),
                        result_summary=p.get("result_summary", ""),
                        task_id=p.get("task_id", ""),
                        started_at=p.get("started_at"),
                        completed_at=p.get("completed_at"),
                        error=p.get("error", ""),
                        max_steps=p.get("max_steps", 10),
                        review_iteration=p.get("review_iteration", 0),
                        is_fix_phase=p.get("is_fix_phase", False),
                    )
                    phases.append(phase)

                project = Project(
                    id=data["id"],
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    phases=phases,
                    status=ProjectStatus(data.get("status", "ready")),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    completed_at=data.get("completed_at", ""),
                    total_duration_s=data.get("total_duration_s", 0),
                    error=data.get("error", ""),
                )

                self._projects[project.id] = project

                # 실행 중이던 프로젝트는 FAILED 처리 (서버 재시작이므로)
                if project.status == ProjectStatus.RUNNING:
                    for phase in project.phases:
                        if phase.status == PhaseStatus.RUNNING:
                            phase.status = PhaseStatus.FAILED
                            phase.error = "서버 재시작으로 중단"
                    project.status = ProjectStatus.FAILED
                    project.error = "서버 재시작으로 중단"
                    await self._save_project(project)

            if project_ids:
                logger.info(f"[ProjectManager] {len(project_ids)}개 프로젝트 복원")
        except Exception as e:
            logger.debug(f"[ProjectManager] 프로젝트 복원 실패: {e}")

    # ── 유틸 ──

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """LLM 응답에서 JSON 추출"""
        # 직접 파싱 시도
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 코드 블록에서 추출
        if "```" in text:
            try:
                block = text.split("```")[1]
                if block.startswith("json"):
                    block = block[4:]
                return json.loads(block.strip())
            except (IndexError, json.JSONDecodeError):
                pass

        return None


# ── 싱글톤 ──

_instance: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    global _instance
    if _instance is None:
        _instance = ProjectManager()
    return _instance
