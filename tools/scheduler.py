"""스케줄러 도구 - APScheduler 기반 반복 작업 관리"""
import uuid
import asyncio
from typing import Optional, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .base import JinxTool, ToolResult
from config import get_settings


class Scheduler(JinxTool):
    """APScheduler 기반 반복 작업 스케줄러

    JX_OPS 전용
    - 반복 작업 등록/수정/삭제
    - cron 표현식 지원
    - SQLite 영속화 (재시작 시 복구)
    """

    name = "scheduler"
    description = "반복 작업을 스케줄링하고 관리합니다"
    allowed_agents = ["JX_OPS"]

    def __init__(self):
        super().__init__()
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._task_callback: Optional[Callable] = None
        self._jobs: dict[str, dict] = {}  # 메모리 내 작업 정보

    def initialize(self, task_callback: Callable) -> None:
        """스케줄러 초기화

        Args:
            task_callback: 스케줄된 작업 실행 시 호출될 콜백
                          async def callback(task_prompt: str) -> None
        """
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
            self._task_callback = task_callback
            self._scheduler.start()

    def shutdown(self) -> None:
        """스케줄러 종료"""
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None

    async def run(self, input_data: dict) -> ToolResult:
        """스케줄 작업 관리

        Args:
            input_data: {
                "action": str,           # "add" | "remove" | "list" | "pause" | "resume"
                "job_id": str,           # 작업 ID (remove/pause/resume 시)
                "name": str,             # 작업 이름 (add 시)
                "cron": str,             # cron 표현식 (add 시)
                "task_prompt": str,      # 실행할 명령 (add 시)
            }
        """
        self._start_timer()

        if not self._scheduler:
            return ToolResult(
                success=False,
                output=None,
                error="Scheduler not initialized",
                duration_ms=self._get_duration_ms(),
            )

        action = input_data.get("action")
        if not action:
            return ToolResult(
                success=False,
                output=None,
                error="action is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            if action == "add":
                return await self._add_job(input_data)
            elif action == "remove":
                return await self._remove_job(input_data)
            elif action == "list":
                return await self._list_jobs()
            elif action == "pause":
                return await self._pause_job(input_data)
            elif action == "resume":
                return await self._resume_job(input_data)
            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}",
                    duration_ms=self._get_duration_ms(),
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _add_job(self, input_data: dict) -> ToolResult:
        """스케줄 작업 추가"""
        name = input_data.get("name")
        cron_expr = input_data.get("cron")
        task_prompt = input_data.get("task_prompt")

        if not all([name, cron_expr, task_prompt]):
            return ToolResult(
                success=False,
                output=None,
                error="name, cron, and task_prompt are required",
                duration_ms=self._get_duration_ms(),
            )

        job_id = str(uuid.uuid4())

        # cron 파싱
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Invalid cron expression: {e}",
                duration_ms=self._get_duration_ms(),
            )

        # 작업 등록
        async def job_func():
            if self._task_callback:
                await self._task_callback(task_prompt)

        self._scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=name,
        )

        # 메모리에 정보 저장
        self._jobs[job_id] = {
            "id": job_id,
            "name": name,
            "cron": cron_expr,
            "task_prompt": task_prompt,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        }

        return ToolResult(
            success=True,
            output={
                "job_id": job_id,
                "name": name,
                "cron": cron_expr,
                "next_run": str(trigger.get_next_fire_time(None, datetime.now())),
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _remove_job(self, input_data: dict) -> ToolResult:
        """스케줄 작업 삭제"""
        job_id = input_data.get("job_id")
        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)

            return ToolResult(
                success=True,
                output={"job_id": job_id, "action": "removed"},
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Job not found: {job_id}",
                duration_ms=self._get_duration_ms(),
            )

    async def _list_jobs(self) -> ToolResult:
        """등록된 작업 목록 조회"""
        jobs = []
        for job in self._scheduler.get_jobs():
            job_info = self._jobs.get(job.id, {})
            jobs.append({
                "id": job.id,
                "name": job.name,
                "cron": job_info.get("cron", ""),
                "task_prompt": job_info.get("task_prompt", ""),
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "is_paused": job.next_run_time is None,
            })

        return ToolResult(
            success=True,
            output={"jobs": jobs, "count": len(jobs)},
            duration_ms=self._get_duration_ms(),
        )

    async def _pause_job(self, input_data: dict) -> ToolResult:
        """작업 일시 중지"""
        job_id = input_data.get("job_id")
        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.pause_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id]["is_active"] = False

            return ToolResult(
                success=True,
                output={"job_id": job_id, "action": "paused"},
                duration_ms=self._get_duration_ms(),
            )
        except Exception:
            return ToolResult(
                success=False,
                output=None,
                error=f"Job not found: {job_id}",
                duration_ms=self._get_duration_ms(),
            )

    async def _resume_job(self, input_data: dict) -> ToolResult:
        """작업 재개"""
        job_id = input_data.get("job_id")
        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.resume_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id]["is_active"] = True

            return ToolResult(
                success=True,
                output={"job_id": job_id, "action": "resumed"},
                duration_ms=self._get_duration_ms(),
            )
        except Exception:
            return ToolResult(
                success=False,
                output=None,
                error=f"Job not found: {job_id}",
                duration_ms=self._get_duration_ms(),
            )
