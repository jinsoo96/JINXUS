"""Memory API - 메모리 검색 및 관리"""
from fastapi import APIRouter, HTTPException, Query

from jinxus.api.models import MemorySearchResponse, MemorySearchResult
from jinxus.memory import get_jinx_memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/search", response_model=MemorySearchResponse)
async def search_memory(
    q: str = Query(..., description="검색 쿼리"),
    agent: str = Query(None, description="에이전트 이름 (선택)"),
    limit: int = Query(5, ge=1, le=20),
):
    """메모리 검색"""
    memory = get_jinx_memory()

    try:
        if agent:
            results = memory.search_long_term(agent, q, limit=limit)
        else:
            results = memory.search_all_memories(q, limit=limit)

        return MemorySearchResponse(
            results=[
                MemorySearchResult(
                    task_id=r.get("task_id", ""),
                    agent_name=r.get("agent_name", ""),
                    instruction=r.get("instruction", ""),
                    summary=r.get("summary", ""),
                    outcome=r.get("outcome", ""),
                    success_score=r.get("success_score", 0.0),
                    created_at=r.get("created_at", ""),
                    similarity_score=r.get("similarity_score", 0.0),
                )
                for r in results
            ],
            total=len(results),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def memory_stats():
    """메모리 통계"""
    memory = get_jinx_memory()

    try:
        health = await memory.health_check()
        total_tasks = await memory.get_total_tasks_count()

        # 에이전트별 메모리 통계
        from jinxus.memory.long_term import _DEFAULT_AGENTS, get_long_term_memory
        long_term = get_long_term_memory()

        collection_stats = {}
        for agent_name in _DEFAULT_AGENTS:
            stats = long_term.get_collection_stats(agent_name)
            collection_stats[agent_name] = stats

        return {
            "health": health,
            "total_tasks_logged": total_tasks,
            "collections": collection_stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_memory(task_id: str, agent: str = Query(None)):
    """특정 기억 삭제"""
    memory = get_jinx_memory()

    if not agent:
        raise HTTPException(
            status_code=400,
            detail="agent parameter is required for deletion",
        )

    try:
        success = memory.delete_memory(agent, task_id)

        if success:
            return {"success": True, "task_id": task_id}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prune/{agent_name}")
async def prune_memory(agent_name: str):
    """저품질 기억 정리"""
    memory = get_jinx_memory()

    try:
        deleted_count = memory.prune_low_quality(agent_name)
        return {
            "success": True,
            "agent_name": agent_name,
            "deleted_count": deleted_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
