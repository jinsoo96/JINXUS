"""백그라운드 작업 실행기 v1.7.0

긴 작업을 백그라운드에서 실행하고 완료 시 알림을 보낸다.

v1.7.0 추가:
- 실제 진행률 (AutonomousRunner에서 step별 업데이트)
- 일시정지/재개 (PAUSED 상태)
- 작업 체이닝 (depends_on: 선행 작업 완료 후 자동 시작)

사용 예:
    worker = get_background_worker()
    task_id = await worker.submit(
        task_description="이 프로젝트 분석해줘",
        session_id="telegram_123",
        notify_callback=send_telegram_notification,
    )
"""
import asyncio
import time
import uuid
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class _SSELogHandler(logging.Handler):
    """jinxus 로그를 SSE progress 이벤트로 실시간 스트리밍.

    핸들러 생성 시 실행 중인 루프를 캡처해두고
    emit()에서 call_soon_threadsafe로 안전하게 스케줄링한다.
    """

    _SKIP_PREFIXES = (
        "[Worker", "체크포인트", "drain_writes", "작업 영속화",
        "Qdrant", "Redis", "HTTP Request", "httpx", "작업 제출",
    )

    def __init__(self, callback: Callable, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.INFO)
        self._callback = callback
        self._loop = loop
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            short = record.getMessage()
            if any(short.startswith(p) for p in self._SKIP_PREFIXES):
                return
            msg = self.format(record)
            coro = self._callback(msg)
            self._loop.call_soon_threadsafe(self._loop.create_task, coro)
        except Exception as e:
            logger.debug(f"[AsyncLogHandler] 로그 이벤트 emit 실패 (무시): {e}")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


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
    # v1.7.0: 작업 체이닝 + 조건부 분기
    depends_on: Optional[str] = None        # 선행 작업 ID
    run_condition: str = "always"            # "always" | "on_success" | "on_failure"
    # v1.7.0: step 진행 정보
    steps_completed: int = 0
    steps_total: int = 0


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
        # 이벤트 버퍼 (구독 전 발생한 이벤트 보관, 구독 시 replay)
        self._event_buffer: dict[str, list[dict]] = {}
        self._event_lock = asyncio.Lock()  # 이벤트 버퍼/구독자 동시 접근 보호
        _EVENT_BUFFER_MAX = 100  # 작업당 최대 버퍼 수
        # v1.7.0: 체이닝 대기 작업 (depends_on task_id -> [waiting task_ids])
        self._waiting_tasks: dict[str, list[str]] = {}

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
        depends_on: Optional[str] = None,
        run_condition: str = "always",
    ) -> str:
        """작업 제출

        Args:
            depends_on: 선행 작업 ID (체이닝)
            run_condition: 선행 작업 결과에 따른 실행 조건
                - "always": 선행 작업 결과와 무관하게 실행 (기본)
                - "on_success": 선행 작업 성공 시에만 실행
                - "on_failure": 선행 작업 실패 시에만 실행
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
            depends_on=depends_on,
            run_condition=run_condition,
        )

        self._tasks[task_id] = task

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

        # 체이닝: 선행 작업이 있으면 대기
        if depends_on:
            dep_task = self._tasks.get(depends_on)
            if dep_task and dep_task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                # 선행 작업 미완료 → 대기열에 추가
                if depends_on not in self._waiting_tasks:
                    self._waiting_tasks[depends_on] = []
                self._waiting_tasks[depends_on].append(task_id)
                logger.info(f"[BackgroundWorker] 작업 {task_id[:8]} → 선행 작업 {depends_on[:8]} 대기")
                return task_id
            elif dep_task and dep_task.status == TaskStatus.COMPLETED:
                # 선행 작업 이미 완료 → 결과를 컨텍스트로 주입
                task.description = self._inject_dependency_context(task.description, dep_task)

        await self._queue.put(task_id)
        logger.info(f"[BackgroundWorker] 작업 제출: {task_id[:8]} - {task_description[:50]}")

        return task_id

    def _inject_dependency_context(self, description: str, dep_task: BackgroundTask) -> str:
        """선행 작업 결과를 현재 작업 설명에 주입"""
        if dep_task.result:
            dep_preview = dep_task.result[:1000]
            return (
                f"[선행 작업 결과]\n{dep_preview}\n\n"
                f"[현재 작업]\n{description}"
            )
        return description

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

        if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()

            # 자율 실행 중이면 runner도 취소
            runner = self._autonomous_runners.get(task_id)
            if runner:
                runner.cancel()

            logger.info(f"[BackgroundWorker] 작업 취소: {task_id[:8]}")
            return True

        return False

    async def pause_task(self, task_id: str) -> bool:
        """작업 일시정지"""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return False

        runner = self._autonomous_runners.get(task_id)
        if not runner:
            return False

        runner.pause()
        task.status = TaskStatus.PAUSED

        await self._publish_progress(task_id, "paused", {
            "progress": task.progress,
            "steps_completed": task.steps_completed,
            "steps_total": task.steps_total,
        })

        # 알림
        if task.notify_callback:
            try:
                await task.notify_callback(
                    f"[작업 일시정지]\n"
                    f"ID: {task_id[:8]}\n"
                    f"진행: {task.steps_completed}/{task.steps_total} 단계 ({task.progress}%)\n"
                    f"재개: /resume {task_id[:8]}"
                )
            except Exception as e:
                logger.warning(f"[BackgroundWorker] 일시정지 알림 콜백 실패: {e}")

        logger.info(f"[BackgroundWorker] 작업 일시정지: {task_id[:8]}")
        return True

    async def resume_task(self, task_id: str) -> bool:
        """작업 재개"""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return False

        runner = self._autonomous_runners.get(task_id)
        if not runner:
            return False

        runner.resume()
        task.status = TaskStatus.RUNNING

        await self._publish_progress(task_id, "resumed", {
            "progress": task.progress,
        })

        if task.notify_callback:
            try:
                await task.notify_callback(f"[작업 재개] ID: {task_id[:8]}")
            except Exception as e:
                logger.warning(f"[BackgroundWorker] 재개 알림 콜백 실패: {e}")

        logger.info(f"[BackgroundWorker] 작업 재개: {task_id[:8]}")
        return True

    async def clear_completed_tasks(self) -> int:
        """완료된 작업 정리 (모든 관련 데이터 일괄 제거)"""
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]
            self._event_buffer.pop(task_id, None)
            self._event_subscribers.pop(task_id, None)
            self._waiting_tasks.pop(task_id, None)
            self._autonomous_runners.pop(task_id, None)

        if to_remove:
            logger.info(f"[BackgroundWorker] 완료된 작업 {len(to_remove)}개 정리")
        return len(to_remove)

    async def _worker_loop(self, worker_id: int):
        """워커 루프"""
        logger.info(f"[Worker-{worker_id}] 시작")

        # worker 0만 주기적 정리 담당 (중복 방지)
        _cleanup_interval = 3600  # 1시간마다 완료 작업 정리
        _last_cleanup = time.monotonic() if worker_id == 0 else float('inf')

        while self._running:
            try:
                # 큐에서 작업 가져오기 (타임아웃 1초)
                try:
                    task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # worker 0: 주기적 완료 작업 정리
                    if worker_id == 0:
                        now = time.monotonic()
                        if now - _last_cleanup >= _cleanup_interval:
                            _last_cleanup = now
                            removed = await self.clear_completed_tasks()
                            if removed:
                                logger.info(f"[Worker-0] 주기 정리: 완료 작업 {removed}개 제거")
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
        """결과에서 첨부파일(스크린샷 등) 경로 추출"""
        import os
        import re

        attachments = []
        response_text = result.get("response", "")

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

        agent_results = result.get("agent_results", [])
        for agent_result in agent_results:
            output = agent_result.get("output", "")
            for pattern in screenshot_patterns:
                matches = re.findall(pattern, output, re.IGNORECASE)
                for match in matches:
                    if os.path.exists(match) and match not in attachments:
                        attachments.append(match)

        return attachments[:5]

    async def subscribe_events(self, task_id: str) -> asyncio.Queue:
        """작업 이벤트 구독 (SSE 스트림용)

        구독 전 발생한 이벤트가 버퍼에 있으면 자동 replay.
        """
        q: asyncio.Queue = asyncio.Queue()
        async with self._event_lock:
            if task_id not in self._event_subscribers:
                self._event_subscribers[task_id] = []
            self._event_subscribers[task_id].append(q)

            # 버퍼된 이벤트 replay (구독 전 발생한 이벤트)
            for buffered in self._event_buffer.get(task_id, []):
                try:
                    q.put_nowait(buffered)
                except asyncio.QueueFull:
                    break

        return q

    async def unsubscribe_events(self, task_id: str, q: asyncio.Queue):
        """이벤트 구독 해제"""
        async with self._event_lock:
            subs = self._event_subscribers.get(task_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._event_subscribers.pop(task_id, None)
                # 마지막 구독자 해제 시 버퍼도 정리
                self._event_buffer.pop(task_id, None)

    async def _publish_progress(self, task_id: str, event_type: str, data: dict):
        """인메모리 이벤트 큐로 진행 상황 전파 + 버퍼 저장"""
        event = {"event": event_type, "task_id": task_id, **data}

        async with self._event_lock:
            # 버퍼에 저장 (구독자 없을 때 유실 방지)
            if task_id not in self._event_buffer:
                self._event_buffer[task_id] = []
            buf = self._event_buffer[task_id]
            buf.append(event)
            if len(buf) > 100:
                buf[:] = buf[-100:]

            # 구독자에게 전달
            for q in self._event_subscribers.get(task_id, []):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull as e:
                    logger.debug(f"[BackgroundWorker] 이벤트 큐 가득 참, 이벤트 드롭: {e}")

    async def _trigger_dependent_tasks(self, completed_task_id: str):
        """체이닝: 선행 작업 완료 시 조건부 분기로 대기 작업 실행

        run_condition에 따라:
        - "always": 선행 작업 성공/실패 무관하게 실행
        - "on_success": 선행 작업이 COMPLETED일 때만 실행
        - "on_failure": 선행 작업이 FAILED일 때만 실행
        """
        waiting = self._waiting_tasks.pop(completed_task_id, [])
        completed_task = self._tasks.get(completed_task_id)

        if not completed_task:
            return

        dep_succeeded = completed_task.status == TaskStatus.COMPLETED
        dep_failed = completed_task.status == TaskStatus.FAILED

        for waiting_task_id in waiting:
            task = self._tasks.get(waiting_task_id)
            if not task or task.status != TaskStatus.PENDING:
                continue

            # 조건부 분기 체크
            condition = task.run_condition
            if condition == "on_success" and not dep_succeeded:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.result = f"선행 작업 {completed_task_id[:8]} 실패로 인해 건너뜀"
                logger.info(
                    f"[BackgroundWorker] 체이닝 건너뜀: {waiting_task_id[:8]} "
                    f"(on_success 조건, 선행 작업 {completed_task.status.value})"
                )
                continue

            if condition == "on_failure" and not dep_failed:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.result = f"선행 작업 {completed_task_id[:8]} 성공으로 인해 건너뜀"
                logger.info(
                    f"[BackgroundWorker] 체이닝 건너뜀: {waiting_task_id[:8]} "
                    f"(on_failure 조건, 선행 작업 {completed_task.status.value})"
                )
                continue

            # 선행 작업 결과를 컨텍스트로 주입
            if completed_task.result:
                task.description = self._inject_dependency_context(
                    task.description, completed_task
                )

            await self._queue.put(waiting_task_id)
            logger.info(
                f"[BackgroundWorker] 체이닝: {completed_task_id[:8]} "
                f"({completed_task.status.value}) → {waiting_task_id[:8]} 큐 투입 "
                f"(조건: {condition})"
            )

    async def _execute_task(self, task: BackgroundTask, worker_id: int):
        """작업 실행"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        logger.info(f"[Worker-{worker_id}] 작업 시작: {task.task_id[:8]} (autonomous={task.autonomous})")

        # 진행 보고 콜백 — 프론트엔드 SSE만 전송 (텔레그램 제거)
        async def progress_callback(message: str):
            await self._publish_progress(task.task_id, "progress", {"message": message})

        try:
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

            await self._persist_status(task.task_id, "running")

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
                steps_completed=task.steps_completed,
                steps_total=task.steps_total,
                result_summary=task.result[:2000] if task.result else None,
            )

            # 체이닝: 완료 시 대기 작업 트리거
            await self._trigger_dependent_tasks(task.task_id)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error = str(e)

            await self._persist_status(task.task_id, "failed", error=str(e))

            logger.error(f"[Worker-{worker_id}] 작업 실패: {task.task_id[:8]} - {e}")

            await self._publish_progress(task.task_id, "failed", {
                "error": str(e)[:500],
            })

            if task.notify_callback:
                try:
                    await task.notify_callback(
                        f"[작업 실패]\n"
                        f"ID: {task.task_id[:8]}\n"
                        f"오류: {str(e)[:500]}"
                    )
                except Exception as notify_err:
                    logger.warning(f"[BackgroundWorker] 실패 알림 콜백 실패: {notify_err}")

            # 실패해도 체이닝 트리거 (후속 작업이 실패를 처리할 수 있도록)
            await self._trigger_dependent_tasks(task.task_id)

    async def _execute_single(self, task: BackgroundTask, progress_callback):
        """단일 실행 (기존 방식)"""
        if self._orchestrator is None:
            from jinxus.core.orchestrator import get_orchestrator
            self._orchestrator = get_orchestrator()
            if not self._orchestrator.is_initialized:
                await self._orchestrator.initialize()

        jinxus_log = logging.getLogger("jinxus")
        log_handler = _SSELogHandler(progress_callback, asyncio.get_running_loop())
        jinxus_log.addHandler(log_handler)
        try:
            result = await self._orchestrator.run_task(
                user_input=task.description,
                session_id=task.session_id,
                progress_callback=progress_callback,
            )
        finally:
            jinxus_log.removeHandler(log_handler)

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        task.progress = 100
        task.result = result.get("response", "")
        task.attachments = self._extract_attachments(result)

        duration = (task.completed_at - task.started_at).total_seconds()
        logger.info(f"[BackgroundWorker] 작업 완료: {task.task_id[:8]} ({duration:.1f}초)")

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

        # 텔레그램 하트비트: 작업 규모에 비례 (총 스텝의 ~20%마다 보고)
        last_reported_pct = 0

        # 실시간 진행률 콜백 설정 (runner 생성 전에 정의)
        async def update_progress(pct: int, completed: int, total: int):
            nonlocal last_reported_pct
            task.progress = pct
            task.steps_completed = completed
            task.steps_total = total
            await self._publish_progress(task.task_id, "step_progress", {
                "progress": pct,
                "steps_completed": completed,
                "steps_total": total,
            })
            # 진행률 20% 구간마다 텔레그램 보고 (3스텝이면 33%마다, 50스텝이면 20%마다)
            report_interval = max(20, 100 // max(total, 1))  # 최소 20% 간격
            if task.notify_callback and pct - last_reported_pct >= report_interval:
                last_reported_pct = pct
                try:
                    await task.notify_callback(
                        f"⏱️ [진행중] ID: {task.task_id[:8]}\n"
                        f"진행: {completed}/{total} 단계 ({pct}%)"
                    )
                except Exception as e:
                    logger.warning(f"[BackgroundWorker] 하트비트 알림 콜백 실패: {e}")

        runner = AutonomousRunner(
            max_steps=task.max_steps,
            timeout_seconds=task.timeout_seconds,
            task_id=task.task_id,
            progress_update=update_progress,
        )

        self._autonomous_runners[task.task_id] = runner

        jinxus_log = logging.getLogger("jinxus")
        log_handler = _SSELogHandler(progress_callback, asyncio.get_running_loop())
        jinxus_log.addHandler(log_handler)
        try:
            result = await runner.run(
                task=task.description,
                session_id=task.session_id,
                progress_callback=progress_callback,
            )

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.progress = 100
            task.steps_completed = result.steps_completed
            task.steps_total = result.steps_total

            # 결과 요약 구성
            step_summary = "\n".join(
                f"  {'✓' if r.success else '✗'} Step {r.index}: {r.description} ({r.duration_s:.1f}s)"
                + (f" [재시도 {r.retry_count}회]" if r.retry_count > 0 else "")
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

            # 완료 이벤트
            await self._publish_progress(task.task_id, "completed", {
                "duration_s": round(result.total_duration_s, 1),
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "result_preview": task.result[:500] if task.result else "",
            })

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
            jinxus_log.removeHandler(log_handler)
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
