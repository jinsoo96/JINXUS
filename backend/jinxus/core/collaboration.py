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

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._redis:
            await self._redis.close()
            self._redis = None


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

    @property
    def trust(self) -> 'TrustLevel':
        """Trust level manager (lazy init)"""
        if not hasattr(self, '_trust') or self._trust is None:
            self._trust = TrustLevel()
        return self._trust

    @property
    def debate(self) -> 'DebateSession':
        """Debate session factory (lazy init)"""
        if not hasattr(self, '_debate') or self._debate is None:
            self._debate = DebateSession(self)
        return self._debate

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


# ═══════════════════════════════════════════════════════════════════════
# Debate Model — 다중 관점 토론으로 최적 결정 도출
# 논문 참고: Agentic LLM Survey — Multi-Agent Debate
# ═══════════════════════════════════════════════════════════════════════

class DebateSession:
    """다중 에이전트 토론 세션

    핵심 결정이 필요할 때, 여러 에이전트가 각자 주장을 펼치고
    라운드별로 반박/수정하여 최적 결론에 수렴한다.

    사용 예시:
        debate = DebateSession(collaborator)
        result = await debate.run(
            topic="Redis vs PostgreSQL for session storage",
            participants=["JX_CODER", "JX_ANALYST", "JX_OPS"],
            rounds=2,
        )
    """

    def __init__(self, collaborator: AgentCollaborator):
        self._collaborator = collaborator
        self._workspace = collaborator._workspace

    async def run(
        self,
        topic: str,
        participants: list[str],
        rounds: int = 2,
        session_id: Optional[str] = None,
    ) -> dict:
        """토론 실행

        Args:
            topic: 토론 주제
            participants: 참여 에이전트 목록 (최소 2명)
            rounds: 토론 라운드 수 (기본 2)
            session_id: 협업 세션 ID

        Returns:
            {"conclusion": str, "arguments": list, "consensus_score": float}
        """
        if len(participants) < 2:
            return {"conclusion": "", "arguments": [], "consensus_score": 0.0, "error": "최소 2명 필요"}

        sid = session_id or str(uuid4())[:8]
        all_arguments = []

        for round_num in range(1, rounds + 1):
            round_args = []

            for agent_name in participants:
                if agent_name not in self._collaborator._agents:
                    continue

                # 이전 라운드 의견 수집
                prev_opinions = ""
                if round_num > 1:
                    prev_entries = await self._workspace.read_all(f"debate:{sid}")
                    prev_opinions = "\n".join(
                        f"[{e['agent']}] {e['content']}"
                        for e in prev_entries[-len(participants)*2:]
                    )

                # 에이전트에게 의견 요청
                if round_num == 1:
                    instruction = (
                        f"다음 주제에 대해 너의 전문적 의견을 제시해줘.\n"
                        f"주제: {topic}\n\n"
                        f"너의 관점에서 장단점을 분석하고 결론을 내려줘. 200자 이내로."
                    )
                else:
                    instruction = (
                        f"다음 주제에 대한 토론 라운드 {round_num}이다.\n"
                        f"주제: {topic}\n\n"
                        f"## 이전 의견들:\n{prev_opinions}\n\n"
                        f"다른 에이전트의 의견을 고려하여 너의 입장을 수정하거나 강화해줘. 200자 이내로."
                    )

                agent = self._collaborator._agents[agent_name]
                try:
                    result = await agent.run(instruction, [])
                    opinion = result.get("output", "")[:500]
                except Exception as e:
                    opinion = f"(의견 제시 실패: {str(e)[:50]})"

                round_args.append({
                    "agent": agent_name,
                    "round": round_num,
                    "opinion": opinion,
                })

                # 워크스페이스에 게시
                await self._workspace.post(
                    session_id=f"debate:{sid}",
                    agent_name=agent_name,
                    content=opinion,
                    content_type="debate_opinion",
                    metadata={"round": round_num, "topic": topic[:100]},
                )

            all_arguments.extend(round_args)

        # 최종 합의 평가 (마지막 라운드 의견들의 유사도)
        last_round = [a for a in all_arguments if a["round"] == rounds]
        consensus_score = self._calc_consensus(last_round)

        # 종합 결론 도출
        conclusion = self._synthesize_conclusion(topic, last_round)

        # 정리
        await self._workspace.clear(f"debate:{sid}")

        logger.info(
            f"[Debate] '{topic[:50]}...' 완료: {len(participants)}명, "
            f"{rounds}라운드, 합의도 {consensus_score:.2f}"
        )

        return {
            "conclusion": conclusion,
            "arguments": all_arguments,
            "consensus_score": consensus_score,
            "participants": participants,
            "rounds": rounds,
        }

    def _calc_consensus(self, last_round_args: list[dict]) -> float:
        """마지막 라운드 의견들의 합의도 추정 (0-1)

        키워드 겹침 기반 간이 측정 (LLM 호출 없이 빠르게).
        """
        if len(last_round_args) < 2:
            return 1.0

        opinions = [set(a["opinion"].split()) for a in last_round_args]
        overlaps = []
        for i in range(len(opinions)):
            for j in range(i + 1, len(opinions)):
                if opinions[i] and opinions[j]:
                    overlap = len(opinions[i] & opinions[j]) / len(opinions[i] | opinions[j])
                    overlaps.append(overlap)

        return sum(overlaps) / len(overlaps) if overlaps else 0.0

    def _synthesize_conclusion(self, topic: str, last_round: list[dict]) -> str:
        """마지막 라운드 의견을 종합하여 결론 생성 (간이)"""
        if not last_round:
            return "토론 결과 없음"

        parts = [f"[{a['agent']}] {a['opinion'][:200]}" for a in last_round]
        return f"주제: {topic}\n\n" + "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# Trust Level — 에이전트 간 신뢰 수준 기반 정보 공개 제어
# 논문 참고: SOTOPIA — Partial Observability (Dec-POMDP)
# ═══════════════════════════════════════════════════════════════════════

class TrustLevel:
    """에이전트 간 신뢰 수준 관리

    협업 이력에 따라 동적으로 신뢰 수준이 변하며,
    신뢰 수준에 따라 공유되는 컨텍스트의 범위가 달라진다.

    레벨:
    - 0 (stranger): 기본 정보만 공유 (에이전트 이름, 역할)
    - 1 (colleague): 작업 결과 요약 공유
    - 2 (trusted): 상세 결과 + 중간 과정 공유
    - 3 (partner): 전체 컨텍스트 공유 (메모리, 실패 이력 포함)
    """

    STRANGER = 0
    COLLEAGUE = 1
    TRUSTED = 2
    PARTNER = 3

    def __init__(self):
        # (agent_a, agent_b) -> trust_score (0.0 ~ 3.0)
        self._trust_scores: dict[tuple[str, str], float] = {}
        self._collab_history: dict[tuple[str, str], list[dict]] = {}

    def _key(self, a: str, b: str) -> tuple[str, str]:
        """정렬된 키 (방향 무관)"""
        return (min(a, b), max(a, b))

    def get_level(self, agent_a: str, agent_b: str) -> int:
        """두 에이전트 간 신뢰 수준 조회"""
        score = self._trust_scores.get(self._key(agent_a, agent_b), 0.0)
        return min(int(score), self.PARTNER)

    def record_collaboration(
        self,
        agent_a: str,
        agent_b: str,
        success: bool,
        quality_score: float = 0.5,
    ) -> None:
        """협업 결과 기록 -> 신뢰 수준 업데이트

        성공적 협업: +0.3, 실패: -0.2 (비대칭 -- 신뢰는 쌓기 어렵고 잃기 쉬움)
        """
        key = self._key(agent_a, agent_b)
        current = self._trust_scores.get(key, 0.0)

        if success:
            delta = 0.2 + (quality_score * 0.1)  # 0.2 ~ 0.3
        else:
            delta = -0.2

        new_score = max(0.0, min(3.0, current + delta))
        self._trust_scores[key] = new_score

        # 이력 기록
        history = self._collab_history.setdefault(key, [])
        history.append({
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "quality": quality_score,
            "trust_after": new_score,
        })
        # 최근 20건만 유지
        if len(history) > 20:
            self._collab_history[key] = history[-20:]

        logger.debug(
            f"[Trust] {agent_a} <-> {agent_b}: {current:.1f} -> {new_score:.1f} "
            f"({'OK' if success else 'FAIL'})"
        )

    def filter_context_by_trust(
        self,
        from_agent: str,
        to_agent: str,
        full_context: dict,
    ) -> dict:
        """신뢰 수준에 따라 공유할 컨텍스트를 필터링

        Args:
            from_agent: 정보를 제공하는 에이전트
            to_agent: 정보를 받는 에이전트
            full_context: 전체 컨텍스트

        Returns:
            필터링된 컨텍스트
        """
        level = self.get_level(from_agent, to_agent)

        if level >= self.PARTNER:
            # 전체 공유
            return full_context

        filtered = {}

        # STRANGER: 기본 정보만
        if level >= self.STRANGER:
            filtered["agent_name"] = full_context.get("agent_name", from_agent)
            filtered["role"] = full_context.get("role", "")
            filtered["status"] = full_context.get("status", "")

        # COLLEAGUE: 결과 요약 추가
        if level >= self.COLLEAGUE:
            filtered["output_summary"] = full_context.get("output", "")[:200]
            filtered["success"] = full_context.get("success")

        # TRUSTED: 상세 결과 + 중간 과정
        if level >= self.TRUSTED:
            filtered["output"] = full_context.get("output", "")
            filtered["tools_used"] = full_context.get("tools_used", [])
            filtered["reasoning"] = full_context.get("reasoning", "")

        return filtered

    def get_all_trust_scores(self) -> dict:
        """전체 신뢰 점수 맵 반환 (디버깅/모니터링용)"""
        return {
            f"{a}<->{b}": round(score, 2)
            for (a, b), score in self._trust_scores.items()
        }


# ═══════════════════════════════════════════════════════════════════════
# Cross-Validation — 에이전트 결과 교차 검증
# ═══════════════════════════════════════════════════════════════════════

async def cross_validate(
    results: list[dict],
    validator_agent: Optional[str] = None,
    collaborator: Optional[AgentCollaborator] = None,
) -> list[dict]:
    """복수 에이전트 결과를 교차 검증

    각 결과를 다른 에이전트의 결과와 비교하여 일관성 체크.
    불일치가 크면 경고 플래그를 추가한다.

    Args:
        results: 에이전트 결과 리스트
        validator_agent: 검증 전담 에이전트 (없으면 키워드 기반 간이 검증)
        collaborator: AgentCollaborator (validator 사용 시)

    Returns:
        검증 정보가 추가된 결과 리스트
    """
    if len(results) < 2:
        for r in results:
            r["cross_validation"] = {"status": "skip", "reason": "단일 결과"}
        return results

    # 성공한 결과만 교차 검증
    successful = [r for r in results if r.get("success")]
    if len(successful) < 2:
        for r in results:
            r["cross_validation"] = {"status": "skip", "reason": "비교 대상 부족"}
        return results

    # 키워드 기반 간이 교차 검증
    outputs = [set(r.get("output", "").split()) for r in successful]

    for i, result in enumerate(successful):
        other_outputs = [outputs[j] for j in range(len(outputs)) if j != i]

        # 다른 결과들과의 키워드 겹침 비율
        overlaps = []
        for other in other_outputs:
            if outputs[i] and other:
                overlap = len(outputs[i] & other) / len(outputs[i] | other)
                overlaps.append(overlap)

        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0

        result["cross_validation"] = {
            "status": "validated",
            "consistency_score": round(avg_overlap, 3),
            "flag": "low_consistency" if avg_overlap < 0.1 else "ok",
            "compared_with": [r.get("agent_name", "unknown") for r in successful if r is not result],
        }

    # 실패한 결과에는 skip 표시
    for r in results:
        if "cross_validation" not in r:
            r["cross_validation"] = {"status": "skip", "reason": "실행 실패"}

    flagged = sum(1 for r in results if r.get("cross_validation", {}).get("flag") == "low_consistency")
    if flagged > 0:
        logger.warning(f"[CrossValidation] {flagged}건 낮은 일관성 감지")

    return results


# 싱글톤
_collaborator: Optional[AgentCollaborator] = None


def get_collaborator() -> AgentCollaborator:
    """AgentCollaborator 싱글톤 반환"""
    global _collaborator
    if _collaborator is None:
        _collaborator = AgentCollaborator()
    return _collaborator
