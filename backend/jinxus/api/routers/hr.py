"""HR API - 에이전트 고용/해고/스폰"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from jinxus.hr import (
    get_hr_manager,
    HireSpec,
    SpawnSpec,
    AgentRole,
)

router = APIRouter(prefix="/hr", tags=["hr"])


# ===== Request/Response 모델 =====

class HireRequest(BaseModel):
    """에이전트 고용 요청"""
    specialty: str
    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: List[str] = []
    tools: List[str] = []
    role: str = "senior"
    system_prompt: Optional[str] = None


class SpawnRequest(BaseModel):
    """새끼 에이전트 스폰 요청"""
    parent_id: str
    specialty: str
    task_focus: str
    inherit_memory: bool = True
    temporary: bool = False


class AgentResponse(BaseModel):
    """에이전트 응답"""
    id: str
    name: str
    role: str
    specialty: str
    description: str
    is_active: bool


# ===== 엔드포인트 =====

@router.post("/hire")
async def hire_agent(request: HireRequest):
    """새 에이전트 고용

    Args:
        request: 고용 스펙

    Returns:
        생성된 에이전트 정보
    """
    hr = get_hr_manager()

    # Initialize if needed
    if not hr._initialized:
        from jinxus.core import get_orchestrator
        orchestrator = get_orchestrator()
        hr.initialize(orchestrator)

    role_map = {
        "senior": AgentRole.SENIOR,
        "junior": AgentRole.JUNIOR,
        "intern": AgentRole.INTERN,
    }

    spec = HireSpec(
        specialty=request.specialty,
        name=request.name,
        description=request.description,
        capabilities=request.capabilities,
        tools=request.tools,
        role=role_map.get(request.role, AgentRole.SENIOR),
        system_prompt=request.system_prompt,
    )

    try:
        record = await hr.hire(spec)
        # Personality 캐시 무효화 — 새 에이전트 반영
        try:
            from jinxus.personality.manager import get_personality_manager
            get_personality_manager().invalidate()
        except Exception:
            pass
        return {
            "success": True,
            "agent": record.to_dict(),
            "message": f"에이전트 '{record.name}' 고용 완료",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FireRequest(BaseModel):
    """에이전트 해고 요청"""
    reason: Optional[str] = None


@router.post("/fire/{agent_id}")
async def fire_agent(agent_id: str, request: FireRequest = None):
    """에이전트 해고 (Soft-Delete)

    Args:
        agent_id: 해고할 에이전트 ID
    """
    hr = get_hr_manager()
    reason = request.reason if request else ""

    success = await hr.fire(agent_id, reason=reason or "")

    if not success:
        raise HTTPException(status_code=400, detail="에이전트를 해고할 수 없습니다.")

    try:
        from jinxus.personality.manager import get_personality_manager
        get_personality_manager().invalidate()
    except Exception:
        pass

    return {
        "success": True,
        "agent_id": agent_id,
        "message": "에이전트 해고 완료 (soft-delete)",
    }


@router.post("/rehire/{agent_id}")
async def rehire_agent(agent_id: str):
    """해고된 에이전트 재고용

    Args:
        agent_id: 재고용할 에이전트 ID
    """
    hr = get_hr_manager()

    record = await hr.rehire(agent_id)

    if not record:
        raise HTTPException(status_code=400, detail="에이전트를 재고용할 수 없습니다.")

    try:
        from jinxus.personality.manager import get_personality_manager
        get_personality_manager().invalidate()
    except Exception:
        pass

    return {
        "success": True,
        "agent": record.to_dict(),
        "message": f"에이전트 '{record.name}' 재고용 완료",
    }


@router.get("/fired")
async def list_fired_agents():
    """해고된 에이전트 목록 조회"""
    hr = get_hr_manager()

    if not hr._initialized:
        from jinxus.core import get_orchestrator
        orchestrator = get_orchestrator()
        hr.initialize(orchestrator)

    records = hr.get_fired_records()
    return {
        "agents": [r.to_dict() for r in records],
        "total": len(records),
    }


@router.post("/spawn")
async def spawn_child_agent(request: SpawnRequest):
    """새끼 에이전트 스폰

    Args:
        request: 스폰 스펙
    """
    hr = get_hr_manager()

    spec = SpawnSpec(
        parent_id=request.parent_id,
        specialty=request.specialty,
        task_focus=request.task_focus,
        inherit_memory=request.inherit_memory,
        temporary=request.temporary,
    )

    try:
        record = await hr.spawn_child(spec)
        return {
            "success": True,
            "agent": record.to_dict(),
            "message": f"새끼 에이전트 '{record.name}' 스폰 완료",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/org-chart")
async def get_org_chart():
    """조직도 조회"""
    hr = get_hr_manager()

    if not hr._initialized:
        from jinxus.core import get_orchestrator
        orchestrator = get_orchestrator()
        hr.initialize(orchestrator)

    org_chart = hr.get_org_chart()
    return org_chart.to_dict()


@router.get("/agents")
async def list_agents(active_only: bool = True):
    """에이전트 목록 조회"""
    hr = get_hr_manager()

    if not hr._initialized:
        from jinxus.core import get_orchestrator
        orchestrator = get_orchestrator()
        hr.initialize(orchestrator)

    if active_only:
        records = hr.get_active_records()
    else:
        records = hr.get_all_records()

    return {
        "agents": [r.to_dict() for r in records],
        "total": len(records),
    }


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """특정 에이전트 조회"""
    hr = get_hr_manager()

    record = hr.get_record(agent_id)
    if not record:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    return record.to_dict()


@router.get("/available-specs")
async def get_available_specs():
    """고용 가능한 에이전트 스펙 목록"""
    hr = get_hr_manager()
    return {
        "specs": hr.get_available_specs(),
    }
