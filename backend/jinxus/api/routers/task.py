"""Task API - 비동기 작업 관리"""
import asyncio
from typing import Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks

from jinxus.api.models import TaskRequest, TaskResponse, TaskStatusResponse
from jinxus.core import get_orchestrator

router = APIRouter(prefix="/task", tags=["task"])

# 작업 저장소 (실제로는 Redis나 DB 사용 권장)
_tasks: Dict[str, dict] = {}
# asyncio Task 추적 (실제 취소용)
_running_tasks: Dict[str, asyncio.Task] = {}


async def _run_task(task_id: str, message: str, session_id: str):
    """백그라운드 작업 실행"""
    orchestrator = get_orchestrator()

    try:
        _tasks[task_id]["status"] = "in_progress"

        result = await orchestrator.run_task(message, session_id)

        # 취소된 경우 무시
        if _tasks[task_id]["status"] == "cancelled":
            return

        _tasks[task_id].update({
            "status": "completed",
            "result": result["response"],
            "agents_used": result["agents_used"],
            "completed_at": result["completed_at"],
        })

    except asyncio.CancelledError:
        _tasks[task_id].update({
            "status": "cancelled",
            "result": "작업이 사용자에 의해 취소되었습니다.",
            "completed_at": None,
        })
    except Exception as e:
        _tasks[task_id].update({
            "status": "failed",
            "result": str(e),
            "completed_at": None,
        })
    finally:
        # 완료 후 추적에서 제거
        _running_tasks.pop(task_id, None)


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
        "completed_at": None,
    }

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
        duration_ms=None,  # TODO: 계산
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
