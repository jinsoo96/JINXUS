"""HR Tool - JINXUS_CORE 전용 에이전트 관리 도구"""
import logging
from typing import Any, Dict, Optional

from jinxus.tools.base import JinxTool, ToolResult

logger = logging.getLogger(__name__)


class HRTool(JinxTool):
    """에이전트 고용/해고/스폰 관리 도구

    JINXUS_CORE만 사용 가능.
    동적으로 에이전트를 생성/삭제하고 조직 구조를 관리.
    """

    name = "hr_tool"
    description = """에이전트 고용/해고/스폰 관리 도구.

사용 가능한 action:
- hire: 새 에이전트 고용
- fire: 에이전트 해고
- spawn: 새끼 에이전트 스폰 (부모 에이전트의 하위)
- list: 에이전트 목록 조회
- org_chart: 조직도 조회

예시:
- action="hire", specialty="coder", name="JX_CUSTOM_CODER"
- action="fire", agent_id="agent_123"
- action="spawn", parent_id="JX_CODER", specialty="coder", task_focus="Python 최적화"
- action="list", active_only=True
- action="org_chart"
"""

    # JINXUS_CORE만 사용 가능
    allowed_agents = ["JINXUS_CORE"]

    def __init__(self):
        super().__init__()
        self._hr_manager = None

    def _get_hr_manager(self):
        """Lazy load HR manager to avoid circular imports"""
        if self._hr_manager is None:
            from jinxus.hr import get_hr_manager
            self._hr_manager = get_hr_manager()
        return self._hr_manager

    async def run(self, input_data: dict) -> ToolResult:
        """JinxTool 인터페이스 구현"""
        self._start_timer()
        try:
            result = await self.execute(**input_data)
            return ToolResult(
                success=result.get("success", False),
                output=result,
                error=result.get("error"),
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def execute(
        self,
        action: str,
        specialty: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        task_focus: Optional[str] = None,
        temporary: bool = False,
        active_only: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """HR 작업 실행

        Args:
            action: 수행할 작업 (hire, fire, spawn, list, org_chart)
            specialty: 에이전트 전문 분야 (hire, spawn)
            name: 에이전트 이름 (hire)
            description: 에이전트 설명 (hire)
            agent_id: 에이전트 ID (fire)
            parent_id: 부모 에이전트 ID (spawn)
            task_focus: 작업 집중 영역 (spawn)
            temporary: 임시 에이전트 여부 (spawn)
            active_only: 활성 에이전트만 조회 (list)

        Returns:
            작업 결과 딕셔너리
        """
        hr = self._get_hr_manager()

        try:
            if action == "hire":
                return await self._hire(hr, specialty, name, description)
            elif action == "fire":
                return await self._fire(hr, agent_id)
            elif action == "spawn":
                return await self._spawn(hr, parent_id, specialty, task_focus, temporary)
            elif action == "list":
                return self._list(hr, active_only)
            elif action == "org_chart":
                return self._org_chart(hr)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "available_actions": ["hire", "fire", "spawn", "list", "org_chart"],
                }

        except Exception as e:
            logger.error(f"HR Tool error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _hire(
        self,
        hr,
        specialty: Optional[str],
        name: Optional[str],
        description: Optional[str],
    ) -> Dict[str, Any]:
        """새 에이전트 고용"""
        if not specialty:
            return {
                "success": False,
                "error": "specialty is required for hire action",
            }

        from jinxus.hr import HireSpec, AgentRole

        spec = HireSpec(
            specialty=specialty,
            role=AgentRole.SENIOR,
            name=name,
            description=description,
        )

        record = await hr.hire(spec)

        return {
            "success": True,
            "action": "hire",
            "agent": record.to_dict(),
            "message": f"에이전트 '{record.name}' 고용 완료",
        }

    async def _fire(self, hr, agent_id: Optional[str]) -> Dict[str, Any]:
        """에이전트 해고"""
        if not agent_id:
            return {
                "success": False,
                "error": "agent_id is required for fire action",
            }

        success = await hr.fire(agent_id)

        if success:
            return {
                "success": True,
                "action": "fire",
                "agent_id": agent_id,
                "message": "에이전트 해고 완료",
            }
        else:
            return {
                "success": False,
                "error": "에이전트를 해고할 수 없습니다 (존재하지 않거나 해고 불가)",
            }

    async def _spawn(
        self,
        hr,
        parent_id: Optional[str],
        specialty: Optional[str],
        task_focus: Optional[str],
        temporary: bool,
    ) -> Dict[str, Any]:
        """새끼 에이전트 스폰"""
        if not parent_id:
            return {
                "success": False,
                "error": "parent_id is required for spawn action",
            }
        if not specialty:
            return {
                "success": False,
                "error": "specialty is required for spawn action",
            }
        if not task_focus:
            return {
                "success": False,
                "error": "task_focus is required for spawn action",
            }

        from jinxus.hr import SpawnSpec

        spec = SpawnSpec(
            parent_id=parent_id,
            specialty=specialty,
            task_focus=task_focus,
            temporary=temporary,
        )

        record = await hr.spawn_child(spec)

        return {
            "success": True,
            "action": "spawn",
            "agent": record.to_dict(),
            "message": f"새끼 에이전트 '{record.name}' 스폰 완료",
        }

    def _list(self, hr, active_only: bool) -> Dict[str, Any]:
        """에이전트 목록 조회"""
        if active_only:
            records = hr.get_active_records()
        else:
            records = hr.get_all_records()

        return {
            "success": True,
            "action": "list",
            "agents": [r.to_dict() for r in records],
            "total": len(records),
        }

    def _org_chart(self, hr) -> Dict[str, Any]:
        """조직도 조회"""
        org_chart = hr.get_org_chart()

        return {
            "success": True,
            "action": "org_chart",
            "org_chart": org_chart.to_dict(),
        }
