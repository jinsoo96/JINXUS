"""백그라운드 작업 실행기

긴 작업을 백그라운드에서 실행하고 완료 시 알림을 보낸다.

사용 예:
    worker = get_background_worker()
    task_id = await worker.submit(
        task_description="이 프로젝트 분석해줘",
        session_id="telegram_123",
        notify_callback=send_telegram_notification,
    )
"""
import asyncio
import uuid
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """백그라운드 작업"""
    task_id: str
    description: str
    session_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    result: Optional[str] = None
    error: Optional[str] = None
    attachments: list = field(default_factory=list)  # 이미지/파일 경로 리스트
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notify_callback: Optional[Callable] = None
    # 자율 실행 모드
    autonomous: bool = False
    max_steps: int = 10
    timeout_seconds: int = 4 * 3600


class BackgroundWorker:
    """백그라운드 작업 실행기"""

    def __init__(self, max_concurrent: int = 3):
        self._tasks: dict[str, BackgroundTask] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._max_concurrent = max_concurrent
        self._running = False
        self._orchestrator = None
        self._autonomous_runners: dict = {}  # task_id -> AutonomousRunner
        # 인메모리 이벤트 큐 (task_id -> list[asyncio.Queue]) — SSE 구독자용
        self._event_subscribers: dict[str, list[asyncio.Queue]] = {}

    async def start(self):
        """워커 시작"""
        if self._running:
            return

        self._running = True

        # 워커 태스크 생성
        for i in range(self._max_concurrent):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)

        logger.info(f"BackgroundWorker 시작 (워커 {self._max_concurrent}개)")

    async def stop(self):
        """워커 중지"""
        self._running = False

        # 모든 워커 취소
        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("BackgroundWorker 중지")

    async def submit(
        self,
        task_description: str,
        session_id: str,
        notify_callback: Optional[Callable] = None,
        autonomous: bool = False,
        max_steps: int = 10,
        timeout_seconds: int = 4 * 3600,
    ) -> str:
        """작업 제출

        Args:
            task_description: 작업 설명 (JINXUS에게 전달할 명령)
            session_id: 세션 ID
            notify_callback: 완료 시 호출될 콜백 (async def callback(message: str))
            autonomous: 자율 멀티스텝 모드 활성화
            max_steps: 자율 모드 최대 단계 수
            timeout_seconds: 자율 모드 타임아웃

        Returns:
            task_id: 작업 ID
        """
        task_id = str(uuid.uuid4())

        task = BackgroundTask(
            task_id=task_id,
            description=task_description,
            session_id=session_id,
            notify_callback=notify_callback,
            autonomous=autonomous,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
        )

        self._tasks[task_id] = task
        await self._queue.put(task_id)

        # 작업 상태 영속화 (서버 재시작 시 복구용)
        try:
            from jinxus.memory.meta_store import get_meta_store
            await get_meta_store().save_background_task(
                task_id=task_id,
                description=task_description,
                session_id=session_id,
                autonomous=autonomous,
            )
        except Exception as e:
            logger.debug(f"작업 영속화 실패 (계속 진행): {e}")

        logger.info(f"[BackgroundWorker] 작업 제출: {task_id[:8]} - {task_description[:50]}")

        return task_id

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """작업 조회"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[BackgroundTask]:
        """모든 작업 조회"""
        return list(self._tasks.values())

    def get_pending_tasks(self) -> list[BackgroundTask]:
        """대기 중인 작업 조회"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def get_running_tasks(self) -> list[BackgroundTask]:
        """실행 중인 작업 조회"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    async def cancel_task(self, task_id: str) -> bool:
        """작업 취소"""
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()

            # 자율 실행 중이면 runner도 취소
            runner = self._autonomous_runners.get(task_id)
            if runner:
                runner.cancel()

            logger.info(f"[BackgroundWorker] 작업 취소: {task_id[:8]}")
            return True

        return False

    async def clear_completed_tasks(self) -> int:
        """완료된 작업 정리 (completed, failed, cancelled 상태 삭제)

        Returns:
            삭제된 작업 수
        """
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]

        logger.info(f"[BackgroundWorker] 완료된 작업 {len(to_remove)}개 정리")
        return len(to_remove)

    async def _worker_loop(self, worker_id: int):
        """워커 루프"""
        logger.info(f"[Worker-{worker_id}] 시작")

        while self._running:
            try:
                # 큐에서 작업 가져오기 (타임아웃 1초)
                try:
                    task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                task = self._tasks.get(task_id)
                if not task or task.status == TaskStatus.CANCELLED:
                    continue

                # 작업 실행
                await self._execute_task(task, worker_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] 오류: {e}")

        logger.info(f"[Worker-{worker_id}] 종료")

    async def _persist_status(self, task_id: str, status: str, **kwargs):
        """작업 상태 DB 영속화"""
        try:
            from jinxus.memory.meta_store import get_meta_store
            await get_meta_store().update_background_task(
                task_id=task_id, status=status, **kwargs,
            )
        except Exception as e:
            logger.debug(f"작업 상태 영속화 실패: {e}")

    def _extract_attachments(self, result: dict) -> list[str]:
        """결과에서 첨부파일(스크린샷 등) 경로 추출

        MCP Playwright 스크린샷, 생성된 이미지 등을 찾아서 반환
        """
        import os
        import re

        attachments = []
        response_text = result.get("response", "")

        # 1. MCP Playwright 스크린샷 경로 패턴
        # 보통 /tmp/playwright_screenshots/xxx.png 형태
        screenshot_patterns = [
            r'/tmp/[^\s\'"<>]+\.png',
            r'/tmp/[^\s\'"<>]+\.jpg',
            r'/tmp/[^\s\'"<>]+\.jpeg',
            r'/var/folders/[^\s\'"<>]+\.png',
            r'screenshot[^\s\'"<>]*\.png',
        ]

        for pattern in screenshot_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if os.path.exists(match) and match not in attachments:
                    attachments.append(match)

        # 2. agent_results에서 추출 (있는 경우)
        agent_results = result.get("agent_results", [])
        for agent_result in agent_results:
            output = agent_result.get("output", "")
            for pattern in screenshot_patterns:
                matches = re.findall(pattern, output, re.IGNORECASE)
                for match in matches:
                    if os.path.exists(match) and match not in attachments:
                        attachments.append(match)

        # 3. 최대 5개로 제한
        return attachments[:5]

    def subscribe_events(self, task_id: str) -> asyncio.Queue:
        """작업 이벤트 구독 (SSE 스트림용). Queue를 반환."""
        q: asyncio.Queue = asyncio.Queue()
        if task_id not in self._event_subscribers:
            self._event_subscribers[task_id] = []
        self._event_subscribers[task_id].append(q)
        return q

    def unsubscribe_events(self, task_id: str, q: asyncio.Queue):
        """이벤트 구독 해제"""
        subs = self._event_subscribers.get(task_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._event_subscribers.pop(task_id, None)

    async def _publish_progress(self, task_id: str, event_type: str, data: dict):
        """인메모리 이벤트 큐로 진행 상황 전파 (웹 UI 실시간 스트림용)"""
        event = {"event": event_type, "task_id": task_id, **data}
        for q in self._event_subscribers.get(task_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 구독자가 느리면 건너뜀

    async def _execute_task(self, task: BackgroundTask, worker_id: int):
        """작업 실행"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        logger.info(f"[Worker-{worker_id}] 작업 시작: {task.task_id[:8]} (autonomous={task.autonomous})")

        # 진행 보고 콜백 생성
        async def progress_callback(message: str):
            """작업 진행 상황을 알림 + Redis Pub/Sub으로 전송"""
            # Redis Pub/Sub (웹 UI)
            await self._publish_progress(task.task_id, "progress", {"message": message})

            # 텔레그램 알림
            if task.notify_callback:
                try:
                    await task.notify_callback(f"📊 진행 보고\n{message}")
                except Exception as e:
                    logger.warning(f"진행 보고 전송 실패: {e}")

        try:
            # 진행 시작 알림
            if task.notify_callback:
                mode = "자율 모드" if task.autonomous else "단일 실행"
                try:
                    await task.notify_callback(
                        f"[작업 시작 - {mode}]\n"
                        f"ID: {task.task_id[:8]}\n"
                        f"내용: {task.description[:100]}"
                    )
                except Exception as e:
                    logger.warning(f"알림 전송 실패: {e}")

            # 상태 영속화: running
            await self._persist_status(task.task_id, "running")

            # 시작 이벤트 publish
            await self._publish_progress(task.task_id, "started", {
                "description": task.description[:100],
                "autonomous": task.autonomous,
            })

            if task.autonomous:
                await self._execute_autonomous(task, progress_callback)
            else:
                await self._execute_single(task, progress_callback)

            # 상태 영속화: completed
            await self._persist_status(
                task.task_id, "completed",
                result_summary=task.result[:2000] if task.result else None,
            )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error = str(e)

            # 상태 영속화: failed
            await self._persist_status(task.task_id, "failed", error=str(e))

            logger.error(f"[Worker-{worker_id}] 작업 실패: {task.task_id[:8]} - {e}")

            # 실패 이벤트 publish
            await self._publish_progress(task.task_id, "failed", {
                "error": str(e)[:500],
            })

            # 실패 알림
            if task.notify_callback:
                try:
                    await task.notify_callback(
                        f"[작업 실패]\n"
                        f"ID: {task.task_id[:8]}\n"
                        f"오류: {str(e)[:500]}"
                    )
                except Exception:
                    pass

    async def _execute_single(self, task: BackgroundTask, progress_callback):
        """단일 실행 (기존 방식)"""
        # Orchestrator 가져오기 (lazy load)
        if self._orchestrator is None:
            from jinxus.core.orchestrator import get_orchestrator
            self._orchestrator = get_orchestrator()
            if not self._orchestrator.is_initialized:
                await self._orchestrator.initialize()

        result = await self._orchestrator.run_task(
            user_input=task.description,
            session_id=task.session_id,
            progress_callback=progress_callback,
        )

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        task.result = result.get("response", "")
        task.attachments = self._extract_attachments(result)

        duration = (task.completed_at - task.started_at).total_seconds()
        logger.info(f"[BackgroundWorker] 작업 완료: {task.task_id[:8]} ({duration:.1f}초)")

        # 완료 이벤트 publish
        await self._publish_progress(task.task_id, "completed", {
            "duration_s": round(duration, 1),
            "result_preview": task.result[:500] if task.result else "",
        })

        if task.notify_callback:
            try:
                result_preview = task.result[:2000] if task.result else "결과 없음"
                message = (
                    f"[작업 완료]\n"
                    f"ID: {task.task_id[:8]}\n"
                    f"소요 시간: {duration:.1f}초\n\n"
                    f"결과:\n{result_preview}"
                )
                if task.attachments:
                    await task.notify_callback(message, image_paths=task.attachments)
                else:
                    await task.notify_callback(message)
            except Exception as e:
                logger.warning(f"완료 알림 전송 실패: {e}")

    async def _execute_autonomous(self, task: BackgroundTask, progress_callback):
        """자율 멀티스텝 실행"""
        from jinxus.core.autonomous_runner import AutonomousRunner

        runner = AutonomousRunner(
            max_steps=task.max_steps,
            timeout_seconds=task.timeout_seconds,
        )

        # BackgroundTask 취소 시 runner도 취소
        self._autonomous_runners[task.task_id] = runner

        try:
            result = await runner.run(
                task=task.description,
                session_id=task.session_id,
                progress_callback=progress_callback,
            )

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.progress = 100

            # 결과 요약 구성
            step_summary = "\n".join(
                f"  {'✓' if r.success else '✗'} Step {r.index}: {r.description} ({r.duration_s:.1f}s)"
                for r in result.records
            )
            task.result = (
                f"[자율 실행 결과]\n"
                f"완료: {result.steps_completed}/{result.steps_total} 단계\n"
                f"총 소요: {result.total_duration_s:.1f}초\n"
                f"{f'중단 사유: {result.stopped_reason}' if result.stopped_reason else ''}\n\n"
                f"단계별 결과:\n{step_summary}\n\n"
                f"최종 결과:\n{result.final_summary[:3000]}"
            )

            if task.notify_callback:
                try:
                    await task.notify_callback(
                        f"[자율 작업 완료]\n"
                        f"ID: {task.task_id[:8]}\n"
                        f"완료: {result.steps_completed}/{result.steps_total} 단계\n"
                        f"총 소요: {result.total_duration_s:.1f}초\n\n"
                        f"{step_summary}"
                    )
                except Exception as e:
                    logger.warning(f"완료 알림 전송 실패: {e}")

        finally:
            self._autonomous_runners.pop(task.task_id, None)


# 싱글톤 인스턴스
_background_worker: Optional[BackgroundWorker] = None


def get_background_worker() -> BackgroundWorker:
    """BackgroundWorker 싱글톤 반환"""
    global _background_worker
    if _background_worker is None:
        _background_worker = BackgroundWorker()
    return _background_worker


async def start_background_worker():
    """백그라운드 워커 시작 (main.py에서 호출)"""
    worker = get_background_worker()
    await worker.start()


async def stop_background_worker():
    """백그라운드 워커 중지"""
    worker = get_background_worker()
    await worker.stop()
