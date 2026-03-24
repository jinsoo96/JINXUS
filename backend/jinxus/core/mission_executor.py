"""MissionExecutor v1.1.0 — 미션 실행 엔진

미션 상태 머신을 관리하고 오케스트레이터와 연동하여 미션을 실행한다.
에이전트 간 실시간 대화/인계/협업을 SSE로 프론트엔드에 전달.

미션 플로우:
1. BRIEFING: 미션 분석 → 회의 소집 → 에이전트 배정
2. IN_PROGRESS: 에이전트들이 서브태스크 수행 (DM으로 티키타카)
3. REVIEW: 결과 리뷰
4. COMPLETE / FAILED: 미션 종료
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, AsyncGenerator

from jinxus.core.mission import (
    Mission, MissionType, MissionStatus, get_mission_store,
)
from jinxus.core.agent_messenger import get_agent_messenger

logger = logging.getLogger(__name__)


# 오케스트레이터 thinking step → 한국어 라벨
_STEP_LABELS = {
    "cache": "캐시 확인",
    "intake": "입력 분석",
    "classify": "유형 분류",
    "decompose": "작업 분해",
    "web_search": "웹 검색",
    "thinking": "응답 생성",
    "agent_progress": "에이전트 진행",
    "aggregate": "결과 취합",
    "approval": "승인 처리",
}


class MissionExecutor:
    """미션 실행 엔진"""

    def __init__(self):
        self._store = get_mission_store()
        self._messenger = get_agent_messenger()
        self._active_missions: Dict[str, asyncio.Task] = {}

    async def execute_stream(self, mission: Mission) -> AsyncGenerator[dict, None]:
        """미션 실행 (SSE 스트리밍)"""
        # 현재 Task를 등록하여 cancel_mission()에서 취소 가능하게
        current_task = asyncio.current_task()
        if current_task:
            self._active_missions[mission.id] = current_task
        try:
            # === BRIEFING ===
            yield {"event": "mission_created", "data": mission.to_dict()}

            mission.status = MissionStatus.BRIEFING
            mission.started_at = datetime.now().isoformat()
            await self._store.save(mission)

            yield {"event": "mission_status", "data": {
                "id": mission.id, "status": "briefing",
                "message": "미션 브리핑 시작...",
            }}

            # QUICK 미션은 바로 JINXUS_CORE로 처리
            if mission.type == MissionType.QUICK:
                async for event in self._execute_with_conversations(mission):
                    yield event
                return

            # 회의 소집 (STANDARD / EPIC / RAID)
            async for event in self._run_briefing(mission):
                yield event

            # === IN_PROGRESS ===
            mission.status = MissionStatus.IN_PROGRESS
            await self._store.save(mission)

            yield {"event": "mission_status", "data": {
                "id": mission.id, "status": "in_progress",
                "message": "미션 수행 중...",
                "agents": mission.assigned_agents,
            }}

            async for event in self._execute_with_conversations(mission):
                yield event

            # === REVIEW ===
            mission.status = MissionStatus.REVIEW
            await self._store.save(mission)

            yield {"event": "mission_status", "data": {
                "id": mission.id, "status": "review",
                "message": "결과 리뷰 중...",
            }}

            await self._store.add_conversation(
                mission.id, "JINXUS_CORE", None,
                f"미션 '{mission.title}' 결과 취합 완료", "report"
            )

            # === COMPLETE ===
            mission.status = MissionStatus.COMPLETE
            mission.completed_at = datetime.now().isoformat()
            await self._store.save(mission)

            # 업무노트 자동 생성
            try:
                await self._create_work_note(mission)
            except Exception as e:
                logger.warning(f"[MissionExecutor] 업무노트 생성 실패: {e}")

            yield {"event": "mission_complete", "data": {
                "id": mission.id,
                "title": mission.title,
                "result": mission.result,
                "duration_ms": mission.duration_ms,
                "agents_used": mission.assigned_agents,
            }}

        except asyncio.CancelledError:
            mission.status = MissionStatus.CANCELLED
            mission.completed_at = datetime.now().isoformat()
            await self._store.save(mission)
            yield {"event": "mission_cancelled", "data": {"id": mission.id}}

        except Exception as e:
            logger.error(f"[MissionExecutor] 미션 실패 {mission.id}: {e}", exc_info=True)
            mission.status = MissionStatus.FAILED
            mission.error = str(e)[:500]
            mission.completed_at = datetime.now().isoformat()
            await self._store.save(mission)
            yield {"event": "mission_failed", "data": {
                "id": mission.id,
                "error": str(e)[:300],
            }}
        finally:
            # Task 등록 정리
            self._active_missions.pop(mission.id, None)

    async def _execute_with_conversations(self, mission: Mission) -> AsyncGenerator[dict, None]:
        """오케스트레이터 실행 + 모든 이벤트를 에이전트 대화로 변환"""
        from jinxus.api.deps import get_ready_orchestrator
        orchestrator = await get_ready_orchestrator()

        mission.status = MissionStatus.IN_PROGRESS
        await self._store.save(mission)

        final_response = ""
        agents_used = set()
        current_agent = "JINXUS_CORE"

        # QUICK 미션만 승인 스킵, 나머지는 승인 게이트 유지
        skip = mission.type == MissionType.QUICK

        async for event in orchestrator.run_task_stream(
            mission.original_input, mission.session_id, skip_approval=skip
        ):
            evt = event["event"]
            data = event["data"]

            if evt == "message":
                chunk = data.get("content", data.get("chunk", ""))
                if chunk:
                    final_response += chunk
                yield {"event": "mission_message", "data": {
                    "id": mission.id,
                    "chunk": chunk,
                }}

            elif evt == "manager_thinking":
                step = data.get("step", "")
                detail = data.get("detail", "")
                label = _STEP_LABELS.get(step, step)

                from_agent = "JINXUS_CORE"
                msg = detail or label

                if step == "agent_progress":
                    from_agent = current_agent

                # 기록용 (Redis 저장만, SSE emit 안 함)
                await self._store.add_conversation(
                    mission.id, from_agent, None, msg[:200], "huddle"
                )

                yield {"event": "mission_thinking", "data": {
                    "id": mission.id,
                    "step": step,
                    "detail": msg[:200],
                    "from": from_agent,
                    "timestamp": datetime.now().isoformat(),
                }}

            elif evt == "agent_started":
                agent = data.get("agent", "")
                instruction = data.get("instruction", "")
                if agent:
                    agents_used.add(agent)
                    current_agent = agent

                msg = instruction[:200] if instruction else f"{agent} 작업 시작"

                # 기록용 (Redis 저장만)
                await self._store.add_conversation(
                    mission.id, "JINXUS_CORE", agent, msg, "dm"
                )

                yield {"event": "agent_dm", "data": {
                    "id": mission.id,
                    "from": "JINXUS_CORE",
                    "to": agent,
                    "message": msg,
                    "timestamp": datetime.now().isoformat(),
                }}

                yield {"event": "mission_agent_activity", "data": {
                    "id": mission.id,
                    "agent": agent,
                    "action": "working",
                }}

            elif evt == "agent_done":
                agent = data.get("agent", "")
                output = data.get("output", "")
                score = data.get("score")
                success = data.get("success", True)
                tool_calls = data.get("tool_calls", [])

                # 도구 호출 이벤트 emit (OFFICE FEED용)
                if tool_calls:
                    yield {"event": "mission_tool_calls", "data": {
                        "id": mission.id,
                        "agent": agent,
                        "tools": tool_calls[:10],  # 최대 10개
                        "timestamp": datetime.now().isoformat(),
                    }}

                report_msg = output[:200] if output else ("작업 완료" if success else "작업 실패")

                # 기록용 (Redis 저장만)
                await self._store.add_conversation(
                    mission.id, agent, "JINXUS_CORE", report_msg, "report"
                )

                yield {"event": "agent_report", "data": {
                    "id": mission.id,
                    "from": agent,
                    "to": "JINXUS_CORE",
                    "message": report_msg,
                    "timestamp": datetime.now().isoformat(),
                }}

                yield {"event": "mission_agent_activity", "data": {
                    "id": mission.id,
                    "agent": agent,
                    "action": "done",
                }}

                current_agent = "JINXUS_CORE"

            elif evt == "approval_required":
                # 승인 요청을 미션 SSE로 릴레이 — 프론트에서 승인 UI 표시
                yield {"event": "mission_approval_required", "data": {
                    "id": mission.id,
                    "message": data.get("message", "작업 계획을 확인해 주세요"),
                    "subtasks_count": data.get("subtasks_count", 0),
                    "agents": data.get("agents", []),
                    "timestamp": datetime.now().isoformat(),
                }}

                yield {"event": "mission_status", "data": {
                    "id": mission.id, "status": "in_progress",
                    "message": "승인 대기 중...",
                }}

            elif evt == "decompose_done":
                count = data.get("subtasks_count", 0)
                mode = data.get("mode", "")
                if count > 0:
                    yield {"event": "huddle_message", "data": {
                        "id": mission.id,
                        "from": "JINXUS_CORE",
                        "message": f"📋 작업 {count}개 분해 완료 (모드: {mode})",
                        "timestamp": datetime.now().isoformat(),
                    }}

            elif evt == "start":
                yield {"event": "huddle_message", "data": {
                    "id": mission.id,
                    "from": "JINXUS_CORE",
                    "message": "미션 처리 시작합니다.",
                    "timestamp": datetime.now().isoformat(),
                }}

            elif evt == "done":
                agents_list = data.get("agents_used", [])
                if agents_list:
                    for a in agents_list:
                        agents_used.add(a)

        mission.result = final_response
        all_agents = list(agents_used) or ["JINXUS_CORE"]
        mission.assigned_agents = list(set(mission.assigned_agents + all_agents))

        # QUICK 미션은 여기서 완료 처리
        if mission.type == MissionType.QUICK:
            mission.status = MissionStatus.COMPLETE
            mission.completed_at = datetime.now().isoformat()
            await self._store.save(mission)
            yield {"event": "mission_complete", "data": {
                "id": mission.id,
                "title": mission.title,
                "result": mission.result,
                "duration_ms": mission.duration_ms,
                "agents_used": mission.assigned_agents,
            }}
        else:
            await self._store.save(mission)

    async def _run_briefing(self, mission: Mission) -> AsyncGenerator[dict, None]:
        """브리핑 단계 — 회의 소집 + 에이전트 배정"""
        agents = mission.assigned_agents or ["JINXUS_CORE"]

        if "JINXUS_CORE" not in agents:
            agents.insert(0, "JINXUS_CORE")
        mission.assigned_agents = agents

        yield {"event": "mission_huddle", "data": {
            "id": mission.id,
            "participants": agents,
            "topic": f"미션 브리핑: {mission.title}",
        }}

        # CORE 브리핑 메시지
        briefing_msg = f"미션: {mission.title}. {mission.description[:200]}"
        await self._store.add_conversation(
            mission.id, "JINXUS_CORE", None, briefing_msg, "huddle"
        )

        yield {"event": "mission_briefing_message", "data": {
            "id": mission.id,
            "from": "JINXUS_CORE",
            "message": briefing_msg,
            "timestamp": datetime.now().isoformat(),
        }}

        # 에이전트들 수락
        for agent in agents:
            if agent == "JINXUS_CORE":
                continue
            await self._store.add_conversation(
                mission.id, agent, "JINXUS_CORE", "네, 맡겠습니다.", "huddle"
            )
            yield {"event": "mission_briefing_message", "data": {
                "id": mission.id,
                "from": agent,
                "message": "네, 맡겠습니다.",
                "timestamp": datetime.now().isoformat(),
            }}

        await self._store.save(mission)

    async def cancel_mission(self, mission_id: str) -> bool:
        """미션 취소"""
        mission = await self._store.get(mission_id)
        if not mission:
            return False
        if mission.status in (MissionStatus.COMPLETE, MissionStatus.FAILED, MissionStatus.CANCELLED):
            return False

        # 실행 중인 Task 취소
        task = self._active_missions.get(mission_id)
        if task and not task.done():
            task.cancel()
            logger.info(f"[MissionExecutor] 미션 Task 취소 요청: {mission_id}")

        mission.status = MissionStatus.CANCELLED
        mission.completed_at = datetime.now().isoformat()
        await self._store.save(mission)

        # 메신저로 취소 이벤트 발행 → SSE 구독자에게 알림
        await self._messenger._emit(mission_id, {
            "event": "mission_cancelled",
            "data": {"id": mission_id, "message": "미션이 취소되었습니다"},
        })

        logger.info(f"[MissionExecutor] 미션 취소 완료: {mission_id}")
        return True

    async def _create_work_note(self, mission: Mission):
        """미션 완료 시 업무노트 자동 생성"""
        from jinxus.api.routers.dev_notes import create_work_note

        # 대화 로그 가져오기 (Mission 객체에서 직접 참조)
        conversations = mission.agent_conversations or []
        conv_lines = []
        for c in conversations[-20:]:  # 최근 20건
            conv_lines.append(f"- **{c.get('from', '?')}**: {c.get('message', '')[:200]}")
        conv_summary = "\n".join(conv_lines) if conv_lines else "(대화 없음)"

        # 소요 시간
        duration_str = ""
        if mission.duration_ms:
            secs = mission.duration_ms / 1000
            if secs < 60:
                duration_str = f"{secs:.1f}초"
            else:
                duration_str = f"{secs / 60:.1f}분"

        # 미션 타입 라벨
        type_labels = {
            "quick": "QUICK", "standard": "STANDARD",
            "epic": "EPIC", "raid": "RAID",
        }
        type_label = type_labels.get(mission.type.value if hasattr(mission.type, 'value') else str(mission.type), "STANDARD")

        content = f"""# {mission.title}

**날짜:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**미션 타입:** {type_label}
**상태:** 완료
**소요 시간:** {duration_str or '측정 안 됨'}
**참여 에이전트:** {', '.join(mission.assigned_agents) if mission.assigned_agents else '없음'}

## 미션 요청

{mission.original_input}

## 실행 결과

{mission.result or '(결과 없음)'}

## 에이전트 활동 로그

{conv_summary}
"""
        create_work_note(mission.title, content)
        logger.info(f"[MissionExecutor] 업무노트 생성 완료: {mission.title}")


# 싱글톤
_executor: Optional[MissionExecutor] = None


def get_mission_executor() -> MissionExecutor:
    global _executor
    if _executor is None:
        _executor = MissionExecutor()
    return _executor
