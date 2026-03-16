"""프로젝트 관리 API

대규모 프로젝트의 생성, 실행, 모니터링, 중단을 담당한다.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from jinxus.core.project_manager import (
    get_project_manager, ProjectStatus, PhaseStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


# ── 요청/응답 모델 ──

class ProjectCreateRequest(BaseModel):
    description: str = Field(..., min_length=5, description="프로젝트 지시")


class PhaseUpdateRequest(BaseModel):
    instruction: str = Field(..., min_length=5, description="수정할 지시")


class PhaseResponse(BaseModel):
    id: str
    name: str
    instruction: str
    agent: str
    depends_on: list[str]
    status: str
    result_summary: str
    task_id: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error: str
    max_steps: int


class ProjectResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    phases: list[PhaseResponse]
    created_at: str
    updated_at: str
    completed_at: str
    total_duration_s: float
    error: str


def _project_to_response(project) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "status": project.status.value if isinstance(project.status, ProjectStatus) else project.status,
        "phases": [
            {
                "id": p.id,
                "name": p.name,
                "instruction": p.instruction,
                "agent": p.agent,
                "depends_on": p.depends_on,
                "status": p.status.value if isinstance(p.status, PhaseStatus) else p.status,
                "result_summary": p.result_summary,
                "task_id": p.task_id,
                "started_at": p.started_at,
                "completed_at": p.completed_at,
                "error": p.error,
                "max_steps": p.max_steps,
            }
            for p in project.phases
        ],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "completed_at": project.completed_at,
        "total_duration_s": project.total_duration_s,
        "error": project.error,
    }


# ── 엔드포인트 ──

@router.post("", response_model=ProjectResponse)
async def create_project(req: ProjectCreateRequest):
    """프로젝트 생성 (LLM이 페이즈 분해)"""
    pm = get_project_manager()
    project = await pm.create_project(req.description)

    if project.status == ProjectStatus.FAILED:
        raise HTTPException(status_code=500, detail=f"프로젝트 생성 실패: {project.error}")

    return _project_to_response(project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects():
    """모든 프로젝트 목록"""
    pm = get_project_manager()
    return [_project_to_response(p) for p in pm.get_all_projects()]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """프로젝트 상세 조회"""
    pm = get_project_manager()
    project = pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return _project_to_response(project)


@router.post("/{project_id}/start")
async def start_project(project_id: str):
    """프로젝트 실행 시작"""
    pm = get_project_manager()
    project = pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    success = await pm.start_project(project_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"실행 불가 (현재 상태: {project.status.value})")

    return {"success": True, "message": "프로젝트 실행 시작"}


@router.post("/{project_id}/stop")
async def stop_project(project_id: str):
    """프로젝트 중단 + 데이터 삭제"""
    pm = get_project_manager()
    success = await pm.stop_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    return {"success": True, "message": "프로젝트 중단 및 정리 완료"}


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """프로젝트 삭제"""
    pm = get_project_manager()
    success = await pm.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    return {"success": True, "message": "프로젝트 삭제 완료"}


@router.patch("/{project_id}/phases/{phase_id}")
async def update_phase(project_id: str, phase_id: str, req: PhaseUpdateRequest):
    """대기 중인 페이즈 지시 수정"""
    pm = get_project_manager()
    success = await pm.update_phase_instruction(project_id, phase_id, req.instruction)
    if not success:
        raise HTTPException(status_code=400, detail="수정 불가 (실행 중이거나 프로젝트 없음)")

    return {"success": True, "message": "페이즈 지시 수정 완료"}


@router.get("/{project_id}/artifacts")
async def get_project_artifacts(project_id: str, phase_id: Optional[str] = None):
    """프로젝트 아티팩트 조회"""
    from jinxus.core.artifact_store import get_artifact_store

    store = get_artifact_store()
    artifacts = await store.get_artifacts(project_id, phase_id=phase_id)

    return {
        "project_id": project_id,
        "artifacts": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.artifact_type,
                "content": a.content[:5000],
                "phase_id": a.phase_id,
                "phase_name": a.phase_name,
                "description": a.description,
                "created_at": a.created_at,
            }
            for a in artifacts
        ],
        "total": len(artifacts),
    }


@router.get("/{project_id}/stream")
async def stream_project(project_id: str):
    """프로젝트 진행 SSE 스트림"""
    pm = get_project_manager()
    project = pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    queue = pm.subscribe(project_id)

    async def event_generator():
        try:
            # 현재 상태 즉시 전송
            yield f"event: status\ndata: {json.dumps(_project_to_response(project), ensure_ascii=False)}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

                    # 프로젝트 완료/실패/취소 시 스트림 종료
                    if event["event"] in ("project_completed", "project_stopped"):
                        yield f"event: done\ndata: {json.dumps({'status': 'closed'})}\n\n"
                        break
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        finally:
            pm.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
