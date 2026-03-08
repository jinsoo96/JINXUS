"""스케줄러 도구 - APScheduler 기반 반복 작업 관리"""
import asyncio
import uuid
import logging
from typing import Optional, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .base import JinxTool, ToolResult
from jinxus.memory.meta_store import get_meta_store

logger = logging.getLogger(__name__)


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
        self._notification_callback: Optional[Callable] = None  # 알림용
        self._jobs: dict[str, dict] = {}  # 메모리 내 작업 정보
        self._jobs_lock = asyncio.Lock()  # _jobs 동시 접근 보호
        self._meta_store = get_meta_store()

    def initialize(
        self,
        task_callback: Callable = None,
        notification_callback: Callable = None,
    ) -> None:
        """스케줄러 초기화

        Args:
            task_callback: 스케줄된 작업 실행 시 호출될 콜백
                          async def callback(task_prompt: str) -> str
            notification_callback: 작업 완료 알림 콜백
                          async def callback(message: str) -> None
        """
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
            self._task_callback = task_callback
            self._notification_callback = notification_callback
            self._scheduler.start()
            logger.info("Scheduler initialized")

    def _ensure_initialized(self) -> None:
        """스케줄러가 초기화되지 않았으면 자동 초기화"""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
            self._scheduler.start()

    async def restore_from_db(self) -> int:
        """서버 재시작 시 SQLite에서 스케줄 작업 복구

        Returns:
            복구된 작업 수
        """
        self._ensure_initialized()

        tasks = await self._meta_store.get_scheduled_tasks(active_only=True)
        restored = 0

        for task in tasks:
            try:
                task_id = task["id"]
                name = task["name"]
                cron_expr = task["cron_expression"]
                task_prompt = task["task_prompt"]

                trigger = CronTrigger.from_crontab(cron_expr)

                # 클로저에서 task_id 캡처를 위한 함수 생성
                def make_job_func(tid: str, prompt: str, jname: str):
                    async def job_func():
                        await self._execute_scheduled_task(tid, prompt, jname)
                    return job_func

                self._scheduler.add_job(
                    make_job_func(task_id, task_prompt, name),
                    trigger=trigger,
                    id=task_id,
                    name=name,
                )

                # 메모리에 정보 저장
                self._jobs[task_id] = {
                    "id": task_id,
                    "name": name,
                    "cron": cron_expr,
                    "task_prompt": task_prompt,
                    "is_active": True,
                    "created_at": task.get("created_at"),
                }

                # next_run_at 업데이트
                next_run = trigger.get_next_fire_time(None, datetime.now())
                if next_run:
                    await self._meta_store.update_scheduled_task_run(
                        task_id, task.get("last_run_at", ""), next_run.isoformat()
                    )

                restored += 1
                logger.info(f"Restored scheduled task: {name} ({task_id[:8]})")

            except Exception as e:
                logger.error(f"Failed to restore task {task.get('name')}: {e}")

        logger.info(f"Restored {restored} scheduled tasks from database")
        return restored

    async def _execute_scheduled_task(
        self, task_id: str, task_prompt: str, task_name: str
    ) -> None:
        """스케줄된 작업 실행"""
        logger.info(f"Executing scheduled task: {task_name}")

        result_message = None
        try:
            if self._task_callback:
                result_message = await self._task_callback(task_prompt)
            else:
                logger.warning("No task callback set, skipping task execution")
                return
        except Exception as e:
            logger.error(f"Scheduled task failed: {task_name} - {e}")
            result_message = f"작업 실패: {str(e)}"

        # 실행 기록 업데이트
        try:
            job = self._scheduler.get_job(task_id)
            next_run = None
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

            await self._meta_store.update_scheduled_task_run(
                task_id, datetime.utcnow().isoformat(), next_run
            )
        except Exception as e:
            logger.error(f"Failed to update task run record: {e}")

        # 텔레그램 알림
        if self._notification_callback:
            try:
                notification = f"📅 스케줄 작업 완료: {task_name}\n\n{result_message or '완료'}"
                await self._notification_callback(notification)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")

    def shutdown(self) -> None:
        """스케줄러 종료"""
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None
            logger.info("Scheduler shutdown")

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

        # 자동 초기화 (콜백 없이 기본 동작)
        if not self._scheduler:
            self._ensure_initialized()

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

        next_run = trigger.get_next_fire_time(None, datetime.now())

        # 작업 등록
        def make_job_func(tid: str, prompt: str, jname: str):
            async def job_func():
                await self._execute_scheduled_task(tid, prompt, jname)
            return job_func

        self._scheduler.add_job(
            make_job_func(job_id, task_prompt, name),
            trigger=trigger,
            id=job_id,
            name=name,
        )

        # 메모리에 정보 저장
        async with self._jobs_lock:
            self._jobs[job_id] = {
                "id": job_id,
                "name": name,
                "cron": cron_expr,
                "task_prompt": task_prompt,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
            }

        # SQLite에 저장 (영속화)
        try:
            await self._meta_store.save_scheduled_task(
                task_id=job_id,
                name=name,
                cron_expression=cron_expr,
                task_prompt=task_prompt,
                is_active=True,
                next_run_at=next_run.isoformat() if next_run else None,
            )
            logger.info(f"Scheduled task saved: {name} ({job_id[:8]})")
        except Exception as e:
            logger.error(f"Failed to save scheduled task to DB: {e}")

        return ToolResult(
            success=True,
            output={
                "job_id": job_id,
                "name": name,
                "cron": cron_expr,
                "next_run": str(next_run),
            },
            duration_ms=self._get_duration_ms(),
        )

    def _find_job_id_by_name(self, name: str) -> Optional[str]:
        """이름으로 job_id 찾기"""
        for job_id, job_info in self._jobs.items():
            if job_info.get("name") == name:
                return job_id
        return None

    async def _remove_job(self, input_data: dict) -> ToolResult:
        """스케줄 작업 삭제"""
        job_id = input_data.get("job_id")
        name = input_data.get("name")

        # name으로 job_id 찾기
        if not job_id and name:
            job_id = self._find_job_id_by_name(name)

        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id or name is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.remove_job(job_id)
            async with self._jobs_lock:
                self._jobs.pop(job_id, None)

            # SQLite에서도 삭제
            try:
                await self._meta_store.delete_scheduled_task(job_id)
                logger.info(f"Scheduled task deleted: {job_id[:8]}")
            except Exception as e:
                logger.error(f"Failed to delete scheduled task from DB: {e}")

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
        name = input_data.get("name")

        if not job_id and name:
            job_id = self._find_job_id_by_name(name)

        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id or name is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.pause_job(job_id)
            async with self._jobs_lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["is_active"] = False

            # SQLite 상태 업데이트
            try:
                await self._meta_store.set_scheduled_task_active(job_id, False)
            except Exception as e:
                logger.error(f"Failed to update task status in DB: {e}")

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
        name = input_data.get("name")

        if not job_id and name:
            job_id = self._find_job_id_by_name(name)

        if not job_id:
            return ToolResult(
                success=False,
                output=None,
                error="job_id or name is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            self._scheduler.resume_job(job_id)
            async with self._jobs_lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["is_active"] = True

            # SQLite 상태 업데이트
            try:
                await self._meta_store.set_scheduled_task_active(job_id, True)
            except Exception as e:
                logger.error(f"Failed to update task status in DB: {e}")

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

    # ==================== 헬퍼 메서드 (텔레그램용) ====================

    def list_jobs(self) -> list[dict]:
        """등록된 작업 목록 반환 (간단 버전)"""
        self._ensure_initialized()

        jobs = []
        for job in self._scheduler.get_jobs():
            job_info = self._jobs.get(job.id, {})
            jobs.append({
                "id": job.id,
                "name": job.name or job_info.get("name", "unnamed"),
                "cron": job_info.get("cron", ""),
                "task_prompt": job_info.get("task_prompt", ""),
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
        return jobs

    async def add_daily_job(
        self,
        hour: int,
        minute: int,
        task_description: str,
        callback: Callable = None,
    ) -> str:
        """매일 특정 시간에 실행되는 작업 추가

        Args:
            hour: 시 (0-23)
            minute: 분 (0-59)
            task_description: 작업 설명/프롬프트
            callback: 작업 실행 시 호출될 콜백

        Returns:
            job_id: 생성된 작업 ID
        """
        self._ensure_initialized()

        job_id = str(uuid.uuid4())
        cron_expr = f"{minute} {hour} * * *"  # 매일 HH:MM

        # 콜백 설정
        task_callback = callback or self._task_callback

        async def job_func():
            if task_callback:
                await task_callback(task_description)

        trigger = CronTrigger(hour=hour, minute=minute)

        self._scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=task_description[:50],  # 이름은 작업 설명 앞부분
        )

        # 메모리에 정보 저장
        self._jobs[job_id] = {
            "id": job_id,
            "name": task_description[:50],
            "cron": cron_expr,
            "task_prompt": task_description,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        }

        return job_id

    def remove_job(self, job_id: str) -> bool:
        """작업 삭제 (간단 버전)

        Args:
            job_id: 작업 ID (앞 8자리도 가능)

        Returns:
            성공 여부
        """
        self._ensure_initialized()

        # 짧은 ID로 전체 ID 찾기
        full_job_id = None
        for jid in self._jobs.keys():
            if jid.startswith(job_id):
                full_job_id = jid
                break

        if not full_job_id:
            return False

        try:
            self._scheduler.remove_job(full_job_id)
            self._jobs.pop(full_job_id, None)
            return True
        except Exception:
            return False
