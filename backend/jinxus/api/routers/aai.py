"""AAI (Agent-Agent Interaction) API 라우터

Geny + Paperclip 패턴에서 도입한 새 모듈들의 통합 API:
- Inbox: 에이전트 간 비동기 메시지
- Goals: 목표 계층 관리
- Heartbeat: 에이전트 주기적 깨어남
- Mission Lock: 미션 Atomic Checkout
- Budget: API 비용 추적
- Routine: 반복 작업 관리
- Config Revision: 설정 변경 이력/롤백
- Soul: 에이전트 인격 파일 관리
- Relevance Gate: 관련성 필터
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aai", tags=["AAI"])


# ===== Pydantic 모델 =====

class InboxSendRequest(BaseModel):
    from_agent: str
    to_agent: str
    content: str
    content_type: str = "text"
    priority: int = 0

class GoalCreateRequest(BaseModel):
    title: str
    description: str = ""
    level: str = "task"
    parent_id: Optional[str] = None
    owner: str = ""
    priority: int = 0

class GoalUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    priority: Optional[int] = None

class HeartbeatWakeRequest(BaseModel):
    agent: str
    reason: str = "manual"
    context: str = ""

class BudgetSetRequest(BaseModel):
    agent: str
    budget_usd: float

class RoutineCreateRequest(BaseModel):
    name: str
    cron_expr: str
    mission_template: str
    description: str = ""
    assigned_agent: str = ""
    concurrency_policy: str = "skip_if_active"
    goal_id: str = ""

class SoulSaveRequest(BaseModel):
    agent: str
    content: str
    file_type: str = "soul"


class AutonomyConfigRequest(BaseModel):
    agent: str
    autopilot_enabled: bool = False
    autonomy_level: int = 0  # 0=관찰, 1=계획, 2=확인후실행, 3=자율실행
    triggers_enabled: bool = True
    heartbeat_interval: int = 3600
    budget_usd: float = 100.0


class TriggerCreateRequest(BaseModel):
    name: str
    type: str = "cron"  # cron|event|idle|interaction|threshold
    agent: str = ""
    config: dict = {}
    description: str = ""  # soul / rules

class MissionLinkGoalRequest(BaseModel):
    mission_id: str
    goal_id: str

class CostRecordRequest(BaseModel):
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    task_id: str = ""


# ===== Inbox =====

@router.post("/inbox/send")
async def inbox_send(req: InboxSendRequest):
    from jinxus.core.inbox import get_inbox
    inbox = get_inbox()
    msg_id = await inbox.deliver(
        from_agent=req.from_agent,
        to_agent=req.to_agent,
        content=req.content,
        content_type=req.content_type,
        priority=req.priority,
    )
    return {"message_id": msg_id}


@router.get("/inbox/{agent}")
async def inbox_read(agent: str, unread_only: bool = False, limit: int = 20):
    from jinxus.core.inbox import get_inbox
    inbox = get_inbox()
    messages = await inbox.read(agent, limit=limit, unread_only=unread_only)
    return {"messages": messages, "count": len(messages)}


@router.post("/inbox/{agent}/read/{message_id}")
async def inbox_mark_read(agent: str, message_id: str):
    from jinxus.core.inbox import get_inbox
    inbox = get_inbox()
    success = await inbox.mark_read(agent, message_id)
    return {"success": success}


@router.get("/inbox/unread/all")
async def inbox_all_unread():
    from jinxus.core.inbox import get_inbox
    inbox = get_inbox()
    counts = await inbox.get_all_unread_counts()
    return {"unread": counts}


# ===== Goals =====

@router.post("/goals")
async def goal_create(req: GoalCreateRequest):
    from jinxus.core.goals import get_goal_manager
    from dataclasses import asdict
    mgr = get_goal_manager()
    goal = await mgr.create(
        title=req.title,
        description=req.description,
        level=req.level,
        parent_id=req.parent_id,
        owner=req.owner,
        priority=req.priority,
    )
    return asdict(goal)


@router.get("/goals")
async def goal_list(level: Optional[str] = None, status: Optional[str] = None):
    from jinxus.core.goals import get_goal_manager
    from dataclasses import asdict
    mgr = get_goal_manager()
    goals = await mgr.list_all(level=level, status=status)
    return {"goals": [asdict(g) for g in goals]}


@router.get("/goals/{goal_id}")
async def goal_get(goal_id: str):
    from jinxus.core.goals import get_goal_manager
    from dataclasses import asdict
    mgr = get_goal_manager()
    goal = await mgr.get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return asdict(goal)


@router.patch("/goals/{goal_id}")
async def goal_update(goal_id: str, req: GoalUpdateRequest):
    from jinxus.core.goals import get_goal_manager
    from dataclasses import asdict
    mgr = get_goal_manager()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    goal = await mgr.update(goal_id, **updates)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return asdict(goal)


@router.delete("/goals/{goal_id}")
async def goal_delete(goal_id: str):
    from jinxus.core.goals import get_goal_manager
    mgr = get_goal_manager()
    success = await mgr.delete(goal_id)
    return {"success": success}


@router.get("/goals/{goal_id}/hierarchy")
async def goal_hierarchy(goal_id: str):
    from jinxus.core.goals import get_goal_manager
    from dataclasses import asdict
    mgr = get_goal_manager()
    chain = await mgr.get_hierarchy(goal_id)
    return {"hierarchy": [asdict(g) for g in chain]}


@router.post("/goals/link-mission")
async def goal_link_mission(req: MissionLinkGoalRequest):
    from jinxus.core.goals import get_goal_manager
    mgr = get_goal_manager()
    await mgr.link_mission(req.mission_id, req.goal_id)
    return {"success": True}


# ===== Heartbeat =====

@router.post("/heartbeat/wake")
async def heartbeat_wake(req: HeartbeatWakeRequest):
    from jinxus.core.heartbeat import get_heartbeat
    from dataclasses import asdict
    hb = get_heartbeat()
    result = await hb.wake(agent=req.agent, reason=req.reason, context=req.context)
    return asdict(result)


@router.get("/heartbeat/status")
async def heartbeat_all_status():
    from jinxus.core.heartbeat import get_heartbeat
    hb = get_heartbeat()
    status = await hb.get_all_status()
    return {"heartbeats": status}


@router.get("/heartbeat/{agent}")
async def heartbeat_status(agent: str):
    from jinxus.core.heartbeat import get_heartbeat
    hb = get_heartbeat()
    status = await hb.get_status(agent)
    return {"status": status}


# ===== Mission Lock =====

@router.post("/mission-lock/{mission_id}/checkout")
async def mission_checkout(mission_id: str, agent_name: str):
    from jinxus.core.mission_lock import get_mission_lock, MissionAlreadyLockedError
    lock = get_mission_lock()
    try:
        await lock.checkout(mission_id, agent_name)
        return {"locked": True, "by": agent_name}
    except MissionAlreadyLockedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/mission-lock/{mission_id}/release")
async def mission_release(mission_id: str, agent_name: str):
    from jinxus.core.mission_lock import get_mission_lock
    lock = get_mission_lock()
    success = await lock.release(mission_id, agent_name)
    return {"released": success}


@router.get("/mission-lock/{mission_id}")
async def mission_lock_info(mission_id: str):
    from jinxus.core.mission_lock import get_mission_lock
    lock = get_mission_lock()
    info = await lock.get_lock_info(mission_id)
    return {"lock": info}


@router.get("/mission-lock")
async def mission_all_locks():
    from jinxus.core.mission_lock import get_mission_lock
    lock = get_mission_lock()
    locks = await lock.get_all_locks()
    return {"locks": locks}


# ===== Budget =====

@router.post("/budget/record")
async def budget_record(req: CostRecordRequest):
    from jinxus.core.budget import get_budget_manager
    from dataclasses import asdict
    mgr = get_budget_manager()
    event = await mgr.record_cost(
        agent=req.agent,
        model=req.model,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        task_id=req.task_id,
    )
    return asdict(event)


@router.post("/budget/set")
async def budget_set(req: BudgetSetRequest):
    from jinxus.core.budget import get_budget_manager
    mgr = get_budget_manager()
    await mgr.set_budget(req.agent, req.budget_usd)
    return {"success": True}


@router.get("/budget/{agent}")
async def budget_report(agent: str, month: Optional[str] = None):
    from jinxus.core.budget import get_budget_manager
    from dataclasses import asdict
    mgr = get_budget_manager()
    report = await mgr.get_report(agent, month)
    return asdict(report)


@router.get("/budget")
async def budget_all_reports(month: Optional[str] = None):
    from jinxus.core.budget import get_budget_manager
    from dataclasses import asdict
    mgr = get_budget_manager()
    reports = await mgr.get_all_reports(month)
    total = await mgr.get_total_cost(month)
    return {"reports": [asdict(r) for r in reports], "total_cost_usd": total}


# ===== Routine =====

@router.post("/routines")
async def routine_create(req: RoutineCreateRequest):
    from jinxus.core.routine import get_routine_manager
    from dataclasses import asdict
    mgr = get_routine_manager()
    routine = await mgr.create(
        name=req.name,
        cron_expr=req.cron_expr,
        mission_template=req.mission_template,
        description=req.description,
        assigned_agent=req.assigned_agent,
        concurrency_policy=req.concurrency_policy,
        goal_id=req.goal_id,
    )
    return asdict(routine)


@router.get("/routines")
async def routine_list(status: Optional[str] = None):
    from jinxus.core.routine import get_routine_manager
    from dataclasses import asdict
    mgr = get_routine_manager()
    routines = await mgr.list_all(status=status)
    return {"routines": [asdict(r) for r in routines]}


@router.post("/routines/{routine_id}/toggle")
async def routine_toggle(routine_id: str):
    """루틴 상태 토글 (active ↔ paused)"""
    from jinxus.core.routine import get_routine_manager
    mgr = get_routine_manager()
    routine = await mgr.get(routine_id)
    if not routine:
        raise HTTPException(status_code=404, detail="루틴을 찾을 수 없습니다")
    new_status = "paused" if routine.status == "active" else "active"
    updated = await mgr.update(routine_id, status=new_status)
    if not updated:
        raise HTTPException(status_code=500, detail="상태 변경 실패")
    from dataclasses import asdict
    return asdict(updated)


@router.delete("/routines/{routine_id}")
async def routine_delete(routine_id: str):
    from jinxus.core.routine import get_routine_manager
    mgr = get_routine_manager()
    success = await mgr.delete(routine_id)
    return {"success": success}


@router.get("/routines/{routine_id}/runs")
async def routine_runs(routine_id: str, limit: int = 20):
    from jinxus.core.routine import get_routine_manager
    mgr = get_routine_manager()
    runs = await mgr.get_runs(routine_id, limit)
    return {"runs": runs}


# ===== Config Revision =====

@router.get("/config-revision/{agent}")
async def config_revision_history(agent: str, limit: int = 20):
    from jinxus.core.config_revision import get_config_revision
    mgr = get_config_revision()
    history = await mgr.get_history(agent, limit)
    return {"revisions": history}


@router.post("/config-revision/{agent}/rollback/{version}")
async def config_revision_rollback(agent: str, version: int):
    from jinxus.core.config_revision import get_config_revision
    from dataclasses import asdict
    mgr = get_config_revision()
    revision = await mgr.rollback(agent, version)
    if not revision:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return asdict(revision)


# ===== Soul =====

@router.get("/souls")
async def soul_list():
    from jinxus.agents.soul_loader import list_agents_with_souls
    agents = list_agents_with_souls()
    return {"agents": agents}


@router.get("/souls/{agent}")
async def soul_get(agent: str):
    from jinxus.agents.soul_loader import load_soul, load_rules
    soul = load_soul(agent)
    rules = load_rules(agent)
    return {"agent": agent, "soul": soul, "rules": rules}


@router.post("/souls")
async def soul_save(req: SoulSaveRequest):
    from jinxus.agents.soul_loader import save_soul, save_rules
    if req.file_type == "rules":
        success = save_rules(req.agent, req.content)
    else:
        success = save_soul(req.agent, req.content)
    return {"success": success}


# ===== Autonomy Config =====

@router.get("/autonomy")
async def autonomy_list():
    """전체 에이전트 자율 설정 조회"""
    from jinxus.core.trigger_engine import get_trigger_engine
    engine = get_trigger_engine()
    configs = await engine.get_all_autonomy_configs()
    return {"agents": {k: v.to_dict() for k, v in configs.items()}}


@router.get("/autonomy/{agent}")
async def autonomy_get(agent: str):
    from jinxus.core.trigger_engine import get_trigger_engine
    engine = get_trigger_engine()
    config = await engine.get_autonomy_config(agent)
    return config.to_dict()


@router.post("/autonomy")
async def autonomy_set(req: AutonomyConfigRequest):
    """에이전트 자율 설정 저장"""
    from jinxus.core.trigger_engine import get_trigger_engine, AutonomyConfig
    engine = get_trigger_engine()
    config = AutonomyConfig(
        agent=req.agent,
        autopilot_enabled=req.autopilot_enabled,
        autonomy_level=max(0, min(3, req.autonomy_level)),
        triggers_enabled=req.triggers_enabled,
        heartbeat_interval=max(60, req.heartbeat_interval),
        budget_usd=max(0, req.budget_usd),
    )
    result = await engine.set_autonomy_config(config)
    return result.to_dict()


# ===== Triggers =====

@router.get("/triggers")
async def trigger_list(type: Optional[str] = None):
    """트리거 전체 목록"""
    from jinxus.core.trigger_engine import get_trigger_engine
    engine = get_trigger_engine()
    triggers = await engine.list_triggers(type)
    return {"triggers": [t.to_dict() for t in triggers]}


@router.post("/triggers")
async def trigger_create(req: TriggerCreateRequest):
    """트리거 생성"""
    from jinxus.core.trigger_engine import get_trigger_engine, TriggerConfig
    engine = get_trigger_engine()
    config = TriggerConfig(
        name=req.name,
        type=req.type,
        agent=req.agent,
        config=req.config,
        description=req.description,
    )
    result = await engine.create_trigger(config)
    return result.to_dict()


@router.delete("/triggers/{trigger_id}")
async def trigger_delete(trigger_id: str):
    from jinxus.core.trigger_engine import get_trigger_engine
    engine = get_trigger_engine()
    success = await engine.delete_trigger(trigger_id)
    if not success:
        raise HTTPException(status_code=404, detail="트리거를 찾을 수 없습니다")
    return {"success": True}


@router.post("/triggers/{trigger_id}/toggle")
async def trigger_toggle(trigger_id: str, enabled: bool = True):
    from jinxus.core.trigger_engine import get_trigger_engine
    engine = get_trigger_engine()
    success = await engine.toggle_trigger(trigger_id, enabled)
    if not success:
        raise HTTPException(status_code=404, detail="트리거를 찾을 수 없습니다")
    return {"success": True}
