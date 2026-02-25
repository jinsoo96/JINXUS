"""Task API - 비동기 작업 관리"""
import asyncio
from typing import Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.models import TaskRequest, TaskResponse, TaskStatusResponse
from core import get_orchestrator

router = APIRouter(prefix="/task", tags=["task"])

# 작업 저장소 (실제로는 Redis나 DB 사용 권장)
_tasks: Dict[str, dict] = {}


async def _run_task(task_id: str, message: str, session_id: str):
    """백그라운드 작업 실행"""
    orchestrator = get_orchestrator()

    try:
        _tasks[task_id]["status"] = "in_progress"

        result = await orchestrator.run_task(message, session_id)

        _tasks[task_id].update({
            "status": "completed",
            "result": result["response"],
            "agents_used": result["agents_used"],
            "completed_at": result["completed_at"],
        })

    except Exception as e:
        _tasks[task_id].update({
            "status": "failed",
            "result": str(e),
            "completed_at": None,
        })


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

    background_tasks.add_task(_run_task, task_id, request.message, session_id)

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
    """작업 취소"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]

    if task["status"] == "completed":
        raise HTTPException(status_code=400, detail="Task already completed")

    # 실제 취소 로직 (복잡한 구현 필요)
    _tasks[task_id]["status"] = "cancelled"

    return {"task_id": task_id, "status": "cancelled"}


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
