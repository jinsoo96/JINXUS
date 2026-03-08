"""Task API - 비동기 작업 관리"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
from fastapi import APIRouter, HTTPException, BackgroundTasks

from jinxus.api.models import TaskRequest, TaskResponse, TaskStatusResponse
from jinxus.core import get_orchestrator

router = APIRouter(prefix="/task", tags=["task"])
logger = logging.getLogger(__name__)

# 작업 저장소 (실제로는 Redis나 DB 사용 권장)
_tasks: Dict[str, dict] = {}
# asyncio Task 추적 (실제 취소용)
_running_tasks: Dict[str, asyncio.Task] = {}
# 완료된 작업 보관 시간 (1시간)
TASK_RETENTION_HOURS = 1
# 최대 저장 작업 수
MAX_TASKS = 100

# 텔레그램 알림 함수 (서버 시작 시 설정)
_telegram_notify: Optional[Callable] = None


def set_telegram_notify(func: Callable):
    """텔레그램 알림 함수 설정 (서버 시작 시 호출)"""
    global _telegram_notify
    _telegram_notify = func
    logger.info("Task API: 텔레그램 알림 연결됨")


def _cleanup_old_tasks():
    """오래된 완료 작업 정리 (메모리 누수 방지)"""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=TASK_RETENTION_HOURS)

    to_delete = []
    for task_id, task in _tasks.items():
        # 완료/실패/취소 상태의 오래된 작업 삭제
        if task["status"] in ["completed", "failed", "cancelled"]:
            if task.get("completed_at"):
                try:
                    completed = datetime.fromisoformat(task["completed_at"])
                    if completed < cutoff:
                        to_delete.append(task_id)
                except (ValueError, TypeError):
                    pass

    for task_id in to_delete:
        del _tasks[task_id]

    # 최대 개수 초과 시 가장 오래된 완료 작업부터 삭제
    if len(_tasks) > MAX_TASKS:
        completed_tasks = [
            (tid, t) for tid, t in _tasks.items()
            if t["status"] in ["completed", "failed", "cancelled"]
        ]
        completed_tasks.sort(key=lambda x: x[1].get("created_at", ""))
        excess = len(_tasks) - MAX_TASKS
        for i in range(min(excess, len(completed_tasks))):
            del _tasks[completed_tasks[i][0]]

    if to_delete:
        logger.debug(f"정리된 작업: {len(to_delete)}개")


async def _run_task(task_id: str, message: str, session_id: str):
    """백그라운드 작업 실행"""
    orchestrator = get_orchestrator()
    start_time = asyncio.get_event_loop().time()

    try:
        _tasks[task_id]["status"] = "in_progress"
        _tasks[task_id]["started_at"] = datetime.utcnow().isoformat()

        # 시작 알림
        if _telegram_notify:
            try:
                await _telegram_notify(
                    f"🚀 [작업 시작]\n"
                    f"ID: {task_id[:8]}\n"
                    f"내용: {message[:100]}"
                )
            except Exception as e:
                logger.warning(f"텔레그램 시작 알림 실패: {e}")

        result = await orchestrator.run_task(message, session_id)

        # 취소된 경우 무시
        if _tasks[task_id]["status"] == "cancelled":
            return

        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        _tasks[task_id].update({
            "status": "completed",
            "result": result["response"],
            "agents_used": result["agents_used"],
            "completed_at": result["completed_at"],
            "duration_ms": duration_ms,
        })

        # 완료 알림
        if _telegram_notify:
            try:
                duration = asyncio.get_event_loop().time() - start_time
                result_preview = result["response"][:1500] if result["response"] else "결과 없음"
                await _telegram_notify(
                    f"✅ [작업 완료]\n"
                    f"ID: {task_id[:8]}\n"
                    f"소요: {duration:.1f}초\n"
                    f"에이전트: {', '.join(result['agents_used'])}\n\n"
                    f"결과:\n{result_preview}"
                )
            except Exception as e:
                logger.warning(f"텔레그램 완료 알림 실패: {e}")

    except asyncio.CancelledError:
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        _tasks[task_id].update({
            "status": "cancelled",
            "result": "작업이 사용자에 의해 취소되었습니다.",
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
        })
    except Exception as e:
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        _tasks[task_id].update({
            "status": "failed",
            "result": str(e),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
        })

        # 실패 알림
        if _telegram_notify:
            try:
                await _telegram_notify(
                    f"❌ [작업 실패]\n"
                    f"ID: {task_id[:8]}\n"
                    f"오류: {str(e)[:500]}"
                )
            except Exception:
                pass
    finally:
        # 완료 후 추적에서 제거
        _running_tasks.pop(task_id, None)
        # 오래된 작업 정리
        _cleanup_old_tasks()


@router.post("", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """비동기 작업 생성

    즉시 task_id 반환, 작업은 백그라운드에서 실행
    """
    import uuid
    from datetime import datetime

    orchestrator = get_orchestrator()
    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    task_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    _tasks[task_id] = {
        "task_id": task_id,
        "session_id": session_id,
        "status": "pending",
        "message": request.message,
        "result": None,
        "agents_used": [],
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
    }

    # 자율 모드인 경우 BackgroundWorker를 통해 실행
    if request.autonomous:
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
            autonomous=True,
            max_steps=request.max_steps,
            timeout_seconds=request.timeout_seconds,
        )
        _tasks[task_id]["status"] = "in_progress"
        _tasks[task_id]["bg_task_id"] = bg_task_id
    else:
        # asyncio.Task로 추적하여 취소 가능하게
        task = asyncio.create_task(_run_task(task_id, request.message, session_id))
        _running_tasks[task_id] = task

    return TaskResponse(
        task_id=task_id,
        status="pending",
        message="Task created and queued",
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """작업 상태 조회"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
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
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = _tasks[task_id]

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
            pass

    _tasks[task_id]["status"] = "cancelled"
    _tasks[task_id]["result"] = "작업이 사용자에 의해 취소되었습니다."
    _running_tasks.pop(task_id, None)

    return {"task_id": task_id, "status": "cancelled", "message": "작업이 취소되었습니다."}


@router.get("")
async def list_tasks(limit: int = 20, status: str = None):
    """작업 목록 조회"""
    tasks = list(_tasks.values())

    if status:
        tasks = [t for t in tasks if t["status"] == status]

    # 최신순 정렬
    tasks.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "tasks": tasks[:limit],
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
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "created_at": t.created_at.isoformat(),
            "source": "background",
        }
        for t in bg_tasks
        if t.status.value in ["pending", "running"]
    ]

    # 일반 Task API의 작업들
    active_api = [
        {
            "id": t["task_id"],
            "description": t["message"][:100],
            "status": t["status"],
            "progress": 50 if t["status"] == "in_progress" else 0,
            "started_at": None,
            "created_at": t["created_at"],
            "source": "api",
        }
        for t in _tasks.values()
        if t["status"] in ["pending", "in_progress"]
    ]

    all_active = active_bg + active_api
    all_active.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "active_tasks": all_active,
        "count": len(all_active),
    }


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
    if task_id in _tasks:
        return await cancel_task(task_id)

    raise HTTPException(status_code=404, detail="Task not found")
