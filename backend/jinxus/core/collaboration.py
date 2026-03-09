"""Agent Collaboration System — 에이전트 간 협업 인프라

회사처럼 에이전트가 서로 돕는 구조:
1. 공유 워크스페이스 (Redis Blackboard): 에이전트가 중간 결과를 게시, 다른 에이전트가 참조
2. 에이전트 간 직접 위임: 실행 중 다른 에이전트에게 도움 요청
3. 협업 세션: 여러 에이전트가 하나의 목표를 향해 병렬로 작업하며 결과 공유
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Any
from uuid import uuid4

import redis.asyncio as redis

from jinxus.config import get_settings
from jinxus.hr import get_communicator, MessageType

logger = logging.getLogger(__name__)

# Redis 키 접두사
WS_PREFIX = "jinxus:workspace:"


class SharedWorkspace:
    """공유 워크스페이스 — Redis 기반 에이전트 간 정보 공유 보드

    에이전트가 작업 중 발견한 정보를 게시하면,
    같은 협업 세션의 다른 에이전트가 참조할 수 있다.

    예시:
        JX_RESEARCHER가 "AI 트렌드" 검색 결과를 게시
        → JX_WRITER가 이를 참조하여 보고서 작성
    """

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password
        self._ttl = 3600  # 1시간

    async def _ensure_connection(self):
        if self._redis is None:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )

    async def post(
        self,
        session_id: str,
        agent_name: str,
        content: str,
        content_type: str = "finding",
        metadata: Optional[dict] = None,
    ) -> str:
        """워크스페이스에 정보 게시

        Args:
            session_id: 협업 세션 ID
            agent_name: 게시하는 에이전트
            content: 게시 내용
            content_type: finding | request | result | note
            metadata: 추가 메타데이터

        Returns:
            게시물 ID
        """
        await self._ensure_connection()
        post_id = str(uuid4())[:8]
        entry = {
            "id": post_id,
            "agent": agent_name,
            "type": content_type,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        key = f"{WS_PREFIX}{session_id}"
        await self._redis.rpush(key, json.dumps(entry, ensure_ascii=False))
        await self._redis.expire(key, self._ttl)

        logger.debug(f"[Workspace] {agent_name} 게시 ({content_type}): {content[:50]}...")
        return post_id

    async def read_all(self, session_id: str) -> list[dict]:
        """워크스페이스의 모든 게시물 조회"""
        await self._ensure_connection()
        key = f"{WS_PREFIX}{session_id}"
        entries = await self._redis.lrange(key, 0, -1)
        return [json.loads(e) for e in entries]

    async def read_by_agent(self, session_id: str, agent_name: str) -> list[dict]:
        """특정 에이전트의 게시물만 조회"""
        all_entries = await self.read_all(session_id)
        return [e for e in all_entries if e["agent"] == agent_name]

    async def read_others(self, session_id: str, exclude_agent: str) -> list[dict]:
        """다른 에이전트의 게시물 조회 (자기 것 제외)"""
        all_entries = await self.read_all(session_id)
        return [e for e in all_entries if e["agent"] != exclude_agent]

    async def get_summary(self, session_id: str) -> str:
        """워크스페이스 요약 (컨텍스트로 주입용)"""
        entries = await self.read_all(session_id)
        if not entries:
            return ""

        lines = []
        for e in entries[-10:]:  # 최근 10개만
            lines.append(f"[{e['agent']}] ({e['type']}): {e['content'][:200]}")
        return "\n".join(lines)

    async def clear(self, session_id: str):
        """워크스페이스 초기화"""
        await self._ensure_connection()
        await self._redis.delete(f"{WS_PREFIX}{session_id}")


class AgentCollaborator:
    """에이전트 협업 매니저 — 위임, 협업 세션 관리

    사용법 (에이전트 내부에서):
        collab = get_collaborator()
        # 다른 에이전트에게 도움 요청
        result = await collab.request_help("JX_CODER", "이 코드 작성해줘", my_context)
        # 워크스페이스에 결과 공유
        await collab.share_finding(session_id, "JX_RESEARCHER", "검색 결과: ...")
    """

    def __init__(self):
        self._workspace = SharedWorkspace()
        self._agents: dict = {}  # name → agent instance (run() 호출용)

    def register_agents(self, agents: dict):
        """사용 가능한 에이전트 인스턴스 등록"""
        self._agents = agents
        # Communicator에도 등록
        comm = get_communicator()
        for name in agents:
            comm.register_agent(name)

    async def request_help(
        self,
        from_agent: str,
        to_agent: str,
        instruction: str,
        context: list = None,
        collab_session_id: Optional[str] = None,
    ) -> dict:
        """다른 에이전트에게 직접 도움 요청

        Args:
            from_agent: 요청하는 에이전트
            to_agent: 도움을 줄 에이전트
            instruction: 요청 내용
            context: 추가 컨텍스트
            collab_session_id: 협업 세션 ID (워크스페이스 공유용)

        Returns:
            AgentResult 딕셔너리
        """
        if to_agent not in self._agents:
            logger.warning(f"[Collab] {to_agent} 에이전트를 찾을 수 없음")
            return {
                "success": False,
                "output": f"에이전트 {to_agent}을(를) 찾을 수 없습니다",
                "agent_name": to_agent,
            }

        logger.info(f"[Collab] {from_agent} → {to_agent}: {instruction[:50]}...")

        # 워크스페이스의 다른 에이전트 결과를 컨텍스트에 추가
        enriched_context = list(context or [])
        if collab_session_id:
            workspace_summary = await self._workspace.get_summary(collab_session_id)
            if workspace_summary:
                enriched_context.append({
                    "from_task": "workspace",
                    "summary": f"[다른 에이전트 작업 결과]\n{workspace_summary}",
                })

        # Communicator로 위임 기록
        comm = get_communicator()
        await comm.send(
            from_agent=from_agent,
            to_agent=to_agent,
            content={"instruction": instruction},
            message_type=MessageType.TASK_DELEGATE,
        )

        # 에이전트 직접 실행
        agent = self._agents[to_agent]
        try:
            result = await agent.run(instruction, enriched_context)

            # 결과를 워크스페이스에 공유
            if collab_session_id and result.get("success"):
                await self._workspace.post(
                    session_id=collab_session_id,
                    agent_name=to_agent,
                    content=result.get("output", "")[:500],
                    content_type="result",
                    metadata={"requested_by": from_agent},
                )

            # 완료 메시지 전송
            await comm.send(
                from_agent=to_agent,
                to_agent=from_agent,
                content={"result": result.get("output", "")[:200], "success": result.get("success")},
                message_type=MessageType.TASK_RESULT,
            )

            return result

        except Exception as e:
            logger.error(f"[Collab] {to_agent} 실행 실패: {e}")
            return {
                "task_id": str(uuid4()),
                "agent_name": to_agent,
                "success": False,
                "success_score": 0.0,
                "output": "",
                "failure_reason": str(e),
                "duration_ms": 0,
            }

    async def share_finding(
        self,
        session_id: str,
        agent_name: str,
        content: str,
        content_type: str = "finding",
    ):
        """워크스페이스에 발견 사항 공유"""
        await self._workspace.post(session_id, agent_name, content, content_type)

    async def get_peer_findings(
        self,
        session_id: str,
        agent_name: str,
    ) -> str:
        """다른 에이전트가 공유한 결과 조회 (컨텍스트 주입용)"""
        return await self._workspace.get_summary(session_id)

    async def run_collaborative(
        self,
        subtasks: list[dict],
        collab_session_id: str,
        progress_callback=None,
    ) -> list[dict]:
        """협업 모드 실행 — 에이전트들이 워크스페이스를 통해 결과를 공유하며 작업

        병렬 실행이되, 각 에이전트가 다른 에이전트의 중간 결과를 참조 가능.
        빠른 에이전트가 먼저 끝나면 그 결과를 느린 에이전트가 참조할 수 있음.

        Args:
            subtasks: 서브태스크 목록
            collab_session_id: 협업 세션 ID
            progress_callback: 진행 보고 콜백

        Returns:
            에이전트 결과 목록
        """
        results = []
        tasks = []

        for subtask in subtasks:
            agent_name = subtask["assigned_agent"]
            if agent_name not in self._agents:
                continue

            async def _run_with_collab(st=subtask, name=agent_name):
                # 워크스페이스에서 다른 에이전트 결과 가져오기
                peer_context = await self._workspace.get_summary(collab_session_id)
                context = []
                if peer_context:
                    context.append({
                        "from_task": "peer_agents",
                        "summary": peer_context,
                    })

                if progress_callback:
                    await progress_callback(f"🤝 {name} 협업 모드 실행 시작")

                agent = self._agents[name]
                result = await agent.run(st["instruction"], context)

                # 결과를 워크스페이스에 즉시 공유 (다른 에이전트가 참조 가능)
                if result.get("success") and result.get("output"):
                    await self._workspace.post(
                        session_id=collab_session_id,
                        agent_name=name,
                        content=result["output"][:500],
                        content_type="result",
                    )

                if progress_callback:
                    status = "✓" if result["success"] else "✗"
                    await progress_callback(f"   {status} {name} 완료 (점수: {result.get('success_score', 0):.1f})")

                return {
                    "task_id": st["task_id"],
                    "agent_name": name,
                    **result,
                }

            tasks.append(_run_with_collab())

        if progress_callback and len(tasks) > 1:
            agent_names = [st["assigned_agent"] for st in subtasks if st["assigned_agent"] in self._agents]
            await progress_callback(f"🤝 협업 실행: {', '.join(agent_names)} (워크스페이스 공유)")

        # 병렬 실행 — 먼저 끝난 에이전트의 결과가 워크스페이스에 올라감
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                results.append({
                    "task_id": subtasks[i]["task_id"],
                    "agent_name": subtasks[i]["assigned_agent"],
                    "success": False,
                    "success_score": 0.0,
                    "output": "",
                    "failure_reason": str(result),
                    "duration_ms": 0,
                })
            else:
                results.append(result)

        # 협업 세션 정리
        await self._workspace.clear(collab_session_id)

        return results


# 싱글톤
_collaborator: Optional[AgentCollaborator] = None


def get_collaborator() -> AgentCollaborator:
    """AgentCollaborator 싱글톤 반환"""
    global _collaborator
    if _collaborator is None:
        _collaborator = AgentCollaborator()
    return _collaborator
