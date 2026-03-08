"""시스템 관리 도구 - 세션, 작업, 메모리, 캐시 관리

텔레그램에서 자연어로 시스템 관리를 할 수 있게 해주는 도구.

예시:
- "완료된 작업 지워" → action: "clear_completed_tasks"
- "어제 세션 삭제해" → action: "clear_session"
- "실패한 기억 정리해" → action: "prune_memories"
- "캐시 정리해" → action: "clear_cache"
- "GitHub 캐시만 지워" → action: "clear_cache", namespace: "github"
- "캐시 상태 알려줘" → action: "get_cache_stats"
"""
import logging
from typing import Optional
from datetime import datetime

from .base import JinxTool, ToolResult
from jinxus.memory import get_jinx_memory

logger = logging.getLogger(__name__)


class SystemManager(JinxTool):
    """JINXUS 시스템 관리 도구

    JX_OPS 전용 - 세션, 작업, 메모리, 캐시 관리

    Actions:
        - list_sessions: 세션 목록 조회
        - clear_session: 특정 세션 삭제
        - clear_all_sessions: 모든 세션 삭제
        - list_tasks: 백그라운드 작업 목록
        - clear_completed_tasks: 완료된 작업 정리
        - cancel_task: 작업 취소
        - get_memory_stats: 메모리 통계
        - prune_memories: 저품질 기억 정리
        - delete_memory: 특정 기억 삭제
        - get_agent_stats: 에이전트 성능 통계
        - get_cache_stats: 캐시 통계 조회
        - clear_cache: 캐시 정리 (전체 또는 네임스페이스별)
    """

    name = "system_manager"
    description = "세션, 작업, 메모리 등 JINXUS 시스템을 관리합니다"
    allowed_agents = ["JX_OPS"]

    # 오케스트레이터가 초기화되지 않았을 때 사용하는 폴백 목록
    _FALLBACK_AGENTS = ["JX_CODER", "JX_RESEARCHER", "JX_WRITER", "JX_ANALYST", "JX_OPS", "JINXUS_CORE"]

    def __init__(self):
        super().__init__()
        self._memory = get_jinx_memory()

    def _get_all_agent_names(self, include_core: bool = True) -> list[str]:
        """오케스트레이터에서 동적으로 에이전트 목록 조회"""
        try:
            from jinxus.core.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            agents = orchestrator.get_agents() if orchestrator.is_initialized else []
            if agents:
                if include_core and "JINXUS_CORE" not in agents:
                    return ["JINXUS_CORE"] + agents
                if not include_core:
                    return [a for a in agents if a != "JINXUS_CORE"]
                return agents
        except Exception:
            pass
        if include_core:
            return self._FALLBACK_AGENTS[:]
        return [a for a in self._FALLBACK_AGENTS if a != "JINXUS_CORE"]

    async def run(self, input_data: dict) -> ToolResult:
        """시스템 관리 작업 실행

        Args:
            input_data: {
                "action": str,  # 작업 유형
                "session_id": str,  # 세션 ID (선택)
                "task_id": str,  # 작업 ID (선택)
                "agent_name": str,  # 에이전트 이름 (선택)
                "days": int,  # 기간 (선택, 기본 7일)
            }
        """
        self._start_timer()

        action = input_data.get("action")

        if not action:
            return ToolResult(
                success=False,
                output=None,
                error="action is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            if action == "list_sessions":
                return await self._list_sessions()

            elif action == "clear_session":
                session_id = input_data.get("session_id")
                if not session_id:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="session_id is required",
                        duration_ms=self._get_duration_ms(),
                    )
                return await self._clear_session(session_id)

            elif action == "clear_all_sessions":
                return await self._clear_all_sessions()

            elif action == "list_tasks":
                return await self._list_tasks()

            elif action == "clear_completed_tasks":
                return await self._clear_completed_tasks()

            elif action == "cancel_task":
                task_id = input_data.get("task_id")
                if not task_id:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="task_id is required",
                        duration_ms=self._get_duration_ms(),
                    )
                return await self._cancel_task(task_id)

            elif action == "get_memory_stats":
                agent_name = input_data.get("agent_name")
                return await self._get_memory_stats(agent_name)

            elif action == "prune_memories":
                agent_name = input_data.get("agent_name")
                return await self._prune_memories(agent_name)

            elif action == "delete_memory":
                task_id = input_data.get("task_id")
                agent_name = input_data.get("agent_name")
                if not task_id or not agent_name:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="task_id and agent_name are required",
                        duration_ms=self._get_duration_ms(),
                    )
                return await self._delete_memory(agent_name, task_id)

            elif action == "get_agent_stats":
                agent_name = input_data.get("agent_name")
                days = input_data.get("days", 7)
                return await self._get_agent_stats(agent_name, days)

            elif action == "get_system_status":
                return await self._get_system_status()

            elif action == "get_cache_stats":
                return await self._get_cache_stats()

            elif action == "clear_cache":
                namespace = input_data.get("namespace")  # None이면 전체 삭제
                return await self._clear_cache(namespace)

            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}",
                    duration_ms=self._get_duration_ms(),
                )

        except Exception as e:
            logger.error(f"SystemManager error: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ===== 세션 관리 =====

    async def _list_sessions(self) -> ToolResult:
        """세션 목록 조회"""
        sessions = await self._memory.list_sessions()

        return ToolResult(
            success=True,
            output={
                "sessions": sessions,
                "count": len(sessions),
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _clear_session(self, session_id: str) -> ToolResult:
        """특정 세션 삭제"""
        await self._memory.clear_session(session_id)

        return ToolResult(
            success=True,
            output={
                "session_id": session_id,
                "action": "cleared",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _clear_all_sessions(self) -> ToolResult:
        """모든 세션 삭제"""
        sessions = await self._memory.list_sessions()
        cleared_count = 0

        for session in sessions:
            try:
                await self._memory.clear_session(session.get("session_id", ""))
                cleared_count += 1
            except Exception:
                pass

        return ToolResult(
            success=True,
            output={
                "cleared_count": cleared_count,
                "action": "all_sessions_cleared",
            },
            duration_ms=self._get_duration_ms(),
        )

    # ===== 작업 관리 =====

    async def _list_tasks(self) -> ToolResult:
        """백그라운드 작업 목록"""
        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()
            tasks = worker.get_all_tasks()

            task_list = []
            for task in tasks:
                task_list.append({
                    "task_id": task.task_id[:8],
                    "full_id": task.task_id,
                    "status": task.status.value,
                    "description": task.description[:100],
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                })

            return ToolResult(
                success=True,
                output={
                    "tasks": task_list,
                    "count": len(task_list),
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to list tasks: {e}",
                duration_ms=self._get_duration_ms(),
            )

    async def _clear_completed_tasks(self) -> ToolResult:
        """완료된 작업 정리"""
        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()

            cleared_count = await worker.clear_completed_tasks()

            return ToolResult(
                success=True,
                output={
                    "cleared_count": cleared_count,
                    "action": "completed_tasks_cleared",
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to clear tasks: {e}",
                duration_ms=self._get_duration_ms(),
            )

    async def _cancel_task(self, task_id: str) -> ToolResult:
        """작업 취소"""
        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()

            # 짧은 ID로 검색
            all_tasks = worker.get_all_tasks()
            matched_task = None
            for task in all_tasks:
                if task.task_id.startswith(task_id):
                    matched_task = task
                    break

            if not matched_task:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Task not found: {task_id}",
                    duration_ms=self._get_duration_ms(),
                )

            success = await worker.cancel_task(matched_task.task_id)

            return ToolResult(
                success=success,
                output={
                    "task_id": task_id,
                    "action": "cancelled" if success else "cancel_failed",
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to cancel task: {e}",
                duration_ms=self._get_duration_ms(),
            )

    # ===== 메모리 관리 =====

    async def _get_memory_stats(self, agent_name: Optional[str] = None) -> ToolResult:
        """메모리 통계 조회"""
        if agent_name:
            stats = self._memory.get_memory_stats(agent_name)
            return ToolResult(
                success=True,
                output={
                    "agent_name": agent_name,
                    "stats": stats,
                },
                duration_ms=self._get_duration_ms(),
            )

        # 전체 에이전트 통계
        all_stats = {}

        for agent in self._get_all_agent_names(include_core=True):
            try:
                all_stats[agent] = self._memory.get_memory_stats(agent)
            except Exception:
                all_stats[agent] = {"error": "failed to get stats"}

        return ToolResult(
            success=True,
            output={
                "all_agents": all_stats,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _prune_memories(self, agent_name: Optional[str] = None) -> ToolResult:
        """저품질 기억 정리"""
        if agent_name:
            pruned_count = self._memory.prune_low_quality(agent_name)
            return ToolResult(
                success=True,
                output={
                    "agent_name": agent_name,
                    "pruned_count": pruned_count,
                    "action": "pruned",
                },
                duration_ms=self._get_duration_ms(),
            )

        # 전체 에이전트 정리
        total_pruned = 0
        results = {}

        for agent in self._get_all_agent_names(include_core=False):
            try:
                count = self._memory.prune_low_quality(agent)
                results[agent] = count
                total_pruned += count
            except Exception:
                results[agent] = 0

        return ToolResult(
            success=True,
            output={
                "total_pruned": total_pruned,
                "by_agent": results,
                "action": "all_pruned",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _delete_memory(self, agent_name: str, task_id: str) -> ToolResult:
        """특정 기억 삭제"""
        success = self._memory.delete_memory(agent_name, task_id)

        return ToolResult(
            success=success,
            output={
                "agent_name": agent_name,
                "task_id": task_id,
                "action": "deleted" if success else "not_found",
            },
            duration_ms=self._get_duration_ms(),
        )

    # ===== 에이전트 통계 =====

    async def _get_agent_stats(self, agent_name: Optional[str], days: int = 7) -> ToolResult:
        """에이전트 성능 통계"""
        if agent_name:
            stats = await self._memory.get_agent_performance(agent_name, days)
            return ToolResult(
                success=True,
                output={
                    "agent_name": agent_name,
                    "days": days,
                    "performance": stats,
                },
                duration_ms=self._get_duration_ms(),
            )

        # 전체 에이전트 통계
        all_stats = {}

        for agent in self._get_all_agent_names(include_core=False):
            try:
                all_stats[agent] = await self._memory.get_agent_performance(agent, days)
            except Exception:
                all_stats[agent] = {"error": "failed to get stats"}

        return ToolResult(
            success=True,
            output={
                "days": days,
                "all_agents": all_stats,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _get_system_status(self) -> ToolResult:
        """시스템 전체 상태"""
        try:
            from jinxus.core.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            status = await orchestrator.get_system_status()

            return ToolResult(
                success=True,
                output=status,
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to get system status: {e}",
                duration_ms=self._get_duration_ms(),
            )

    # ===== 캐시 관리 =====

    async def _get_cache_stats(self) -> ToolResult:
        """캐시 통계 조회

        GitHub, Brave Search, MCP 도구 등 모든 외부 API 캐시 통계
        """
        try:
            from .cache_manager import cache_stats
            stats = await cache_stats()

            return ToolResult(
                success=True,
                output={
                    "cache_stats": stats,
                    "description": {
                        "total_keys": "전체 캐시된 항목 수",
                        "namespaces": "서비스별 캐시 항목 (github, brave, mcp, web)",
                        "memory_mb": "Redis 메모리 사용량",
                        "hit_rate": "캐시 히트율 (%)",
                        "hits": "캐시 히트 횟수",
                        "misses": "캐시 미스 횟수",
                    },
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"캐시 통계 조회 실패: {e}",
                duration_ms=self._get_duration_ms(),
            )

    async def _clear_cache(self, namespace: Optional[str] = None) -> ToolResult:
        """캐시 정리

        Args:
            namespace: 정리할 네임스페이스 (None이면 전체 삭제)
                      - github: GitHub API 캐시
                      - brave: Brave Search 캐시
                      - mcp: MCP 도구 캐시
                      - web: 웹 페이지 캐시
        """
        try:
            from .cache_manager import cache_clear

            cleared_count = await cache_clear(namespace)

            action_desc = f"'{namespace}' 캐시 정리" if namespace else "전체 캐시 정리"

            return ToolResult(
                success=True,
                output={
                    "action": action_desc,
                    "cleared_count": cleared_count,
                    "namespace": namespace or "all",
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"캐시 정리 실패: {e}",
                duration_ms=self._get_duration_ms(),
            )
