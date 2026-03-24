"""Task API - 비동기 작업 관리 (Redis 기반 저장소)"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from jinxus.api.models import TaskRequest, TaskResponse, TaskStatusResponse
from jinxus.api.deps import get_ready_orchestrator
from jinxus.core import get_orchestrator
from jinxus.config import get_settings

router = APIRouter(prefix="/task", tags=["task"])
logger = logging.getLogger(__name__)


class TaskStore:
    """Redis 기반 작업 저장소

    - 개별 작업: jinxus:tasks:{task_id} (Redis hash, JSON 직렬화)
    - 인덱스: jinxus:tasks:index (sorted set, score=created_at timestamp)
    """

    _KEY_PREFIX = "jinxus:tasks"
    _INDEX_KEY = "jinxus:tasks:index"

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        """Redis 연결 획득/생성"""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )
        return self._redis

    def _task_key(self, task_id: str) -> str:
        return f"{self._KEY_PREFIX}:{task_id}"

    def _ttl_seconds(self) -> int:
        settings = get_settings()
        return settings.task_retention_hours * 3600

    async def create(self, task_id: str, task_data: dict) -> None:
        """작업 저장"""
        r = await self.connect()
        key = self._task_key(task_id)
        await r.set(key, json.dumps(task_data, ensure_ascii=False))
        await r.expire(key, self._ttl_seconds())

        # sorted set 인덱스에 추가 (score = created_at timestamp)
        created_at = task_data.get("created_at", datetime.now().isoformat())
        try:
            ts = datetime.fromisoformat(created_at).timestamp()
        except (ValueError, TypeError):
            ts = datetime.now().timestamp()
        await r.zadd(self._INDEX_KEY, {task_id: ts})

    async def get(self, task_id: str) -> Optional[dict]:
        """작업 조회"""
        r = await self.connect()
        data = await r.get(self._task_key(task_id))
        if data is None:
            return None
        return json.loads(data)

    async def update(self, task_id: str, updates: dict) -> None:
        """작업 부분 업데이트"""
        r = await self.connect()
        key = self._task_key(task_id)
        data = await r.get(key)
        if data is None:
            logger.warning(f"업데이트 대상 작업 없음: {task_id}")
            return
        task = json.loads(data)
        task.update(updates)
        await r.set(key, json.dumps(task, ensure_ascii=False))
        await r.expire(key, self._ttl_seconds())

    async def delete(self, task_id: str) -> None:
        """작업 삭제"""
        r = await self.connect()
        await r.delete(self._task_key(task_id))
        await r.zrem(self._INDEX_KEY, task_id)

    async def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        """작업 목록 조회 (최신순)"""
        r = await self.connect()
        # sorted set에서 최신순으로 task_id 목록 획득
        task_ids = await r.zrevrange(self._INDEX_KEY, 0, -1)

        tasks = []
        for tid in task_ids:
            data = await r.get(self._task_key(tid))
            if data is None:
                # TTL 만료된 키는 인덱스에서 제거
                await r.zrem(self._INDEX_KEY, tid)
                continue
            task = json.loads(data)
            if status and task.get("status") != status:
                continue
            tasks.append(task)
            if len(tasks) >= limit:
                break

        return tasks

    async def cleanup_old(self) -> None:
        """만료된 작업 정리 (TTL 만료 후 인덱스 잔존 제거 + max_tasks 초과 처리)"""
        r = await self.connect()
        settings = get_settings()

        # 1) 인덱스에서 실제 키가 없는(TTL 만료) 항목 제거
        task_ids = await r.zrange(self._INDEX_KEY, 0, -1)
        for tid in task_ids:
            exists = await r.exists(self._task_key(tid))
            if not exists:
                await r.zrem(self._INDEX_KEY, tid)

        # 2) max_tasks 초과 시 가장 오래된 완료 작업부터 삭제
        remaining_ids = await r.zrange(self._INDEX_KEY, 0, -1)  # 오래된 순
        if len(remaining_ids) > settings.max_tasks:
            excess = len(remaining_ids) - settings.max_tasks
            deleted = 0
            for tid in remaining_ids:
                if deleted >= excess:
                    break
                data = await r.get(self._task_key(tid))
                if data is None:
                    await r.zrem(self._INDEX_KEY, tid)
                    deleted += 1
                    continue
                task = json.loads(data)
                if task.get("status") in ["completed", "failed", "cancelled"]:
                    await r.delete(self._task_key(tid))
                    await r.zrem(self._INDEX_KEY, tid)
                    deleted += 1

            if deleted:
                logger.debug(f"정리된 작업: {deleted}개")


# 싱글톤 TaskStore
_task_store: Optional[TaskStore] = None


def get_task_store() -> TaskStore:
    global _task_store
    if _task_store is None:
        _task_store = TaskStore()
    return _task_store


# asyncio Task 추적 (실제 취소용 - 직렬화 불가, 인메모리 유지)
_running_tasks: Dict[str, asyncio.Task] = {}

# 텔레그램 알림 함수 (서버 시작 시 설정)
_telegram_notify: Optional[Callable] = None


def set_telegram_notify(func: Callable):
    """텔레그램 알림 함수 설정 (서버 시작 시 호출)"""
    global _telegram_notify
    _telegram_notify = func
    logger.info("Task API: 텔레그램 알림 연결됨")


async def _send_telegram(message: str) -> None:
    """텔레그램 알림 전송 (실패해도 에러 무시)"""
    if not _telegram_notify:
        return
    try:
        await _telegram_notify(message)
    except Exception as e:
        logger.warning(f"텔레그램 알림 실패: {e}")


async def _run_task(task_id: str, message: str, session_id: str):
    """백그라운드 작업 실행"""
    orchestrator = get_orchestrator()
    store = get_task_store()
    start_time = asyncio.get_event_loop().time()

    try:
        await store.update(task_id, {
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
        })

        # 시작 알림
        await _send_telegram(
            f"🚀 [작업 시작]\n"
            f"ID: {task_id[:8]}\n"
            f"내용: {message[:100]}"
        )

        result = await orchestrator.run_task(message, session_id)

        # 취소된 경우 무시
        task = await store.get(task_id)
        if task and task["status"] == "cancelled":
            return

        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        await store.update(task_id, {
            "status": "completed",
            "result": result["response"],
            "agents_used": result["agents_used"],
            "completed_at": result["completed_at"],
            "duration_ms": duration_ms,
        })

        # 완료 알림
        duration = asyncio.get_event_loop().time() - start_time
        result_preview = result["response"][:1500] if result["response"] else "결과 없음"
        await _send_telegram(
            f"✅ [작업 완료]\n"
            f"ID: {task_id[:8]}\n"
            f"소요: {duration:.1f}초\n"
            f"에이전트: {', '.join(result['agents_used'])}\n\n"
            f"결과:\n{result_preview}"
        )

    except asyncio.CancelledError:
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        await store.update(task_id, {
            "status": "cancelled",
            "result": "작업이 사용자에 의해 취소되었습니다.",
            "completed_at": datetime.now().isoformat(),
            "duration_ms": duration_ms,
        })
    except Exception as e:
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        await store.update(task_id, {
            "status": "failed",
            "result": str(e),
            "completed_at": datetime.now().isoformat(),
            "duration_ms": duration_ms,
        })

        # 실패 알림
        await _send_telegram(
            f"❌ [작업 실패]\n"
            f"ID: {task_id[:8]}\n"
            f"오류: {str(e)[:500]}"
        )
    finally:
        # 완료 후 추적에서 제거
        _running_tasks.pop(task_id, None)
        # 오래된 작업 정리
        await store.cleanup_old()


@router.post("", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """비동기 작업 생성

    즉시 task_id 반환, 작업은 백그라운드에서 실행
    """
    import uuid
    from datetime import datetime

    orchestrator = await get_ready_orchestrator()
    store = get_task_store()
    task_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    task_data = {
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "message": request.message,
        "result": None,
        "agents_used": [],
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
    }
    await store.create(task_id, task_data)

    # 모든 작업을 BackgroundWorker를 통해 실행 (이벤트 스트림 지원)
    from jinxus.core.background_worker import get_background_worker
    worker = get_background_worker()

    notify_cb = None
    if _telegram_notify:
        async def notify_cb(message: str, image_paths: list[str] = None):
            await _telegram_notify(message)

    bg_task_id = await worker.submit(
        task_description=request.message,
        session_id=session_id,
        notify_callback=notify_cb,
        autonomous=request.autonomous,
        max_steps=request.max_steps,
        timeout_seconds=request.timeout_seconds,
    )
    await store.update(task_id, {
        "status": "in_progress",
        "bg_task_id": bg_task_id,
        "started_at": datetime.now().isoformat(),
    })

    # BackgroundWorker 완료 시 Task API 상태 동기화
    async def _sync_task_status():
        """BackgroundWorker 작업 완료까지 대기 후 Task Store 상태 갱신"""
        while True:
            await asyncio.sleep(2)
            bg_task = worker.get_task(bg_task_id)
            if bg_task is None:
                break
            if bg_task.status.value in ("completed", "failed", "cancelled"):
                updates = {
                    "status": bg_task.status.value,
                    "completed_at": bg_task.completed_at.isoformat() if bg_task.completed_at else datetime.now().isoformat(),
                }
                if bg_task.result:
                    updates["result"] = bg_task.result
                if bg_task.error:
                    updates["result"] = bg_task.error
                if bg_task.started_at and bg_task.completed_at:
                    updates["duration_ms"] = int((bg_task.completed_at - bg_task.started_at).total_seconds() * 1000)
                await store.update(task_id, updates)
                break

    asyncio.create_task(_sync_task_status())

    return TaskResponse(
        task_id=task_id,
        status="pending",
        message="Task created and queued",
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """작업 상태 조회"""
    store = get_task_store()
    task = await store.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        result=task["result"],
        agents_used=task["agents_used"],
        duration_ms=task.get("duration_ms"),
        created_at=task["created_at"],
        completed_at=task["completed_at"],
    )


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """작업 취소 - 실행 중인 작업 강제 중지"""
    store = get_task_store()
    task_info = await store.get(task_id)

    if task_info is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task_info["status"] == "completed":
        raise HTTPException(status_code=400, detail="Task already completed")

    if task_info["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Task already cancelled")

    # 실행 중인 asyncio Task 취소
    running_task = _running_tasks.get(task_id)
    if running_task and not running_task.done():
        running_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(running_task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug(f"[task] 작업 취소 대기 완료 (task_id={task_id})")

    await store.update(task_id, {
        "status": "cancelled",
        "result": "작업이 사용자에 의해 취소되었습니다.",
    })
    _running_tasks.pop(task_id, None)

    return {"task_id": task_id, "status": "cancelled", "message": "작업이 취소되었습니다."}


@router.get("")
async def list_tasks(limit: int = 20, status: str = None):
    """작업 목록 조회"""
    store = get_task_store()
    tasks = await store.list_tasks(status=status, limit=limit)

    return {
        "tasks": tasks,
        "total": len(tasks),
    }


@router.get("/active/list")
async def list_active_tasks():
    """활성(실행 중 + 대기 중) 작업 목록 조회 - UI용

    Returns:
        활성 작업 목록 (pending, in_progress 상태)
    """
    from jinxus.core.background_worker import get_background_worker

    worker = get_background_worker()

    # BackgroundWorker의 작업들
    bg_tasks = worker.get_all_tasks()
    active_bg = [
        {
            "id": t.task_id,
            "description": t.description[:100],
            "status": t.status.value,
            "progress": t.progress,
            "steps_completed": t.steps_completed,
            "steps_total": t.steps_total,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "created_at": t.created_at.isoformat(),
            "source": "background",
        }
        for t in bg_tasks
        if t.status.value in ["pending", "running", "paused"]
    ]

    # 일반 Task API의 작업들 (Redis에서 조회)
    # bg_task_id가 있는 작업은 이미 active_bg에 포함되므로 제외 (중복 방지)
    bg_task_ids = {t["id"] for t in active_bg}
    store = get_task_store()
    all_tasks = await store.list_tasks(limit=100)
    active_api = [
        {
            "id": t["task_id"],
            "description": t["message"][:100],
            "status": t["status"],
            "progress": t.get("progress", 50 if t["status"] == "in_progress" else 0),
            "started_at": None,
            "created_at": t["created_at"],
            "source": "api",
        }
        for t in all_tasks
        if t["status"] in ["pending", "in_progress"]
        and not t.get("bg_task_id")  # BackgroundWorker 작업은 이미 active_bg에 있음
        and t["task_id"] not in bg_task_ids
    ]

    all_active = active_bg + active_api
    all_active.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "active_tasks": all_active,
        "count": len(all_active),
    }


@router.get("/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """작업 진행 상황 SSE 스트림

    BackgroundWorker 인메모리 이벤트 큐를 통해 실시간 전달.
    작업 완료/실패/취소 시 자동 종료.
    """
    from jinxus.core.background_worker import get_background_worker

    worker = get_background_worker()

    async def event_generator():
        # 현재 상태 먼저 전송
        store = get_task_store()
        task = await store.get(task_id)

        # bg_task_id가 있으면 BackgroundWorker의 task_id 사용
        subscribe_id = task_id
        if task:
            bg_id = task.get("bg_task_id")
            if bg_id:
                subscribe_id = bg_id

            yield f"event: status\ndata: {json.dumps({'status': task['status'], 'task_id': task_id}, ensure_ascii=False)}\n\n"
            if task["status"] in ("completed", "failed", "cancelled"):
                yield f"event: done\ndata: {json.dumps({'status': task['status'], 'result': task.get('result', '')[:2000]}, ensure_ascii=False)}\n\n"
                return

        # 이벤트 큐 구독 (BackgroundWorker의 실제 task_id로)
        event_queue = await worker.subscribe_events(subscribe_id)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                    event_type = event.pop("event", "progress")
                    yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                    # 종료 이벤트
                    if event_type in ("completed", "failed"):
                        return
                except asyncio.TimeoutError:
                    # keepalive
                    yield f": keepalive\n\n"

                    # 작업 상태 확인 (이미 끝났는지)
                    task = await store.get(task_id)
                    if task and task["status"] in ("completed", "failed", "cancelled"):
                        yield f"event: done\ndata: {json.dumps({'status': task['status'], 'result': task.get('result', '')[:2000]}, ensure_ascii=False)}\n\n"
                        return
        finally:
            await worker.unsubscribe_events(subscribe_id, event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/active/{task_id}/pause")
async def pause_active_task(task_id: str):
    """작업 일시정지 (자율 모드만 지원)"""
    from jinxus.core.background_worker import get_background_worker

    worker = get_background_worker()
    success = await worker.pause_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="작업을 일시정지할 수 없습니다. (실행 중인 자율 작업만 가능)")
    return {"task_id": task_id, "status": "paused"}


@router.post("/active/{task_id}/resume")
async def resume_active_task(task_id: str):
    """작업 재개"""
    from jinxus.core.background_worker import get_background_worker

    worker = get_background_worker()
    success = await worker.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="작업을 재개할 수 없습니다. (일시정지된 작업만 가능)")
    return {"task_id": task_id, "status": "running"}


@router.delete("/active/{task_id}")
async def cancel_active_task(task_id: str):
    """활성 작업 취소 (BackgroundWorker + Task API 통합)"""
    from jinxus.core.background_worker import get_background_worker

    # 1. BackgroundWorker에서 찾기
    worker = get_background_worker()
    bg_task = worker.get_task(task_id)
    if bg_task:
        success = await worker.cancel_task(task_id)
        if success:
            return {"task_id": task_id, "status": "cancelled", "source": "background"}
        else:
            raise HTTPException(status_code=400, detail="작업을 취소할 수 없습니다.")

    # 2. Task API에서 찾기
    store = get_task_store()
    task = await store.get(task_id)
    if task is not None:
        return await cancel_task(task_id)

    raise HTTPException(status_code=404, detail="Task not found")
