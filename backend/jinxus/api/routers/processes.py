"""프로세스 관리 API

장기 실행 프로세스의 시작, 중지, 모니터링을 담당한다.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from jinxus.core.subprocess_manager import (
    get_subprocess_manager, ProcessStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/processes", tags=["processes"])


# ── 요청 모델 ──

class ProcessStartRequest(BaseModel):
    id: str = Field(..., description="프로세스 고유 ID")
    name: str = Field(..., description="식별 이름")
    command: str = Field(..., description="실행 명령")
    cwd: str = Field(default="", description="작업 디렉토리")
    env: dict = Field(default_factory=dict, description="추가 환경변수")
    port: Optional[int] = Field(default=None, description="사용 포트")
    auto_restart: bool = Field(default=False, description="자동 재시작")


# ── 엔드포인트 ──

@router.post("")
async def start_process(req: ProcessStartRequest):
    """프로세스 시작"""
    mgr = get_subprocess_manager()
    try:
        proc = await mgr.start_process(
            process_id=req.id,
            name=req.name,
            command=req.command,
            cwd=req.cwd,
            env=req.env,
            port=req.port,
            auto_restart=req.auto_restart,
        )
        return {
            "success": True,
            "process": _process_to_dict(proc),
        }
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_processes():
    """모든 프로세스 목록"""
    mgr = get_subprocess_manager()
    processes = mgr.get_all_processes()
    return {
        "processes": [_process_to_dict(p) for p in processes],
        "total": len(processes),
        "running": sum(1 for p in processes if p.status == ProcessStatus.RUNNING),
    }


@router.get("/{process_id}")
async def get_process(process_id: str):
    """프로세스 상세 조회"""
    mgr = get_subprocess_manager()
    proc = mgr.get_process(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="프로세스를 찾을 수 없습니다")
    return _process_to_dict(proc)


@router.post("/{process_id}/stop")
async def stop_process(process_id: str):
    """프로세스 중지"""
    mgr = get_subprocess_manager()
    success = await mgr.stop_process(process_id)
    if not success:
        raise HTTPException(status_code=404, detail="프로세스를 찾을 수 없습니다")
    return {"success": True, "message": "프로세스 중지 완료"}


@router.post("/{process_id}/restart")
async def restart_process(process_id: str):
    """프로세스 재시작"""
    mgr = get_subprocess_manager()
    try:
        proc = await mgr.restart_process(process_id)
        return {
            "success": True,
            "process": _process_to_dict(proc),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{process_id}/logs")
async def get_process_logs(process_id: str, lines: int = 100):
    """프로세스 로그 조회"""
    mgr = get_subprocess_manager()
    proc = mgr.get_process(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="프로세스를 찾을 수 없습니다")

    logs = mgr.get_logs(process_id, lines=min(lines, 500))
    return {
        "process_id": process_id,
        "name": proc.name,
        "logs": logs,
        "total_lines": len(logs),
    }


@router.get("/{process_id}/health")
async def health_check(process_id: str):
    """프로세스 헬스체크"""
    mgr = get_subprocess_manager()
    result = await mgr.health_check(process_id)
    return result


@router.post("/cleanup")
async def cleanup_stopped():
    """종료된 프로세스 정리"""
    mgr = get_subprocess_manager()
    removed = await mgr.cleanup_stopped()
    return {"success": True, "removed": removed}


def _process_to_dict(proc) -> dict:
    """ManagedProcess → dict 변환"""
    return {
        "id": proc.id,
        "name": proc.name,
        "command": proc.command,
        "cwd": proc.cwd,
        "status": proc.status.value if isinstance(proc.status, ProcessStatus) else proc.status,
        "pid": proc.pid,
        "port": proc.port,
        "started_at": proc.started_at,
        "stopped_at": proc.stopped_at,
        "exit_code": proc.exit_code,
        "error": proc.error,
        "restart_count": proc.restart_count,
        "auto_restart": proc.auto_restart,
    }
