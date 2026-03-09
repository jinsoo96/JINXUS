"""워크플로우 실행 엔진

ToolGraph에서 탐색된 워크플로우를 순차 실행한다.
각 노드(도구)의 실행 결과를 다음 노드에 컨텍스트로 전달하여
자율적인 멀티스텝 작업을 수행한다.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from jinxus.core.tool_graph import ToolGraph, Workflow, ToolNode, EdgeType, get_tool_graph, save_tool_graph

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """워크플로우 단일 스텝 결과"""
    tool_name: str
    success: bool
    output: str
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    """워크플로우 전체 실행 결과"""
    success: bool
    query: str
    steps: list[StepResult] = field(default_factory=list)
    final_output: str = ""
    total_duration_ms: int = 0
    workflow_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "query": self.query,
            "steps": [
                {"tool": s.tool_name, "success": s.success, "duration_ms": s.duration_ms}
                for s in self.steps
            ],
            "final_output": self.final_output,
            "total_duration_ms": self.total_duration_ms,
        }


class WorkflowExecutor:
    """워크플로우 순차 실행 엔진

    ToolGraph.retrieve()로 탐색된 워크플로우를 받아서
    각 노드의 도구를 순서대로 실행한다.

    사용 예:
        graph = get_tool_graph()
        workflow = graph.retrieve("코드 분석하고 PR 올려줘")
        executor = WorkflowExecutor(agent_name="JX_OPS")
        result = await executor.execute(workflow, instruction="...")
    """

    def __init__(self, agent_name: str):
        self._agent_name = agent_name
        self._graph = get_tool_graph()

    async def execute(
        self,
        workflow: Workflow,
        instruction: str,
        context: Optional[str] = None,
    ) -> WorkflowResult:
        """워크플로우 실행

        Args:
            workflow: ToolGraph.retrieve()로 생성된 워크플로우
            instruction: 원본 사용자 지시
            context: 추가 컨텍스트

        Returns:
            WorkflowResult: 전체 실행 결과
        """
        start_time = time.time()
        steps: list[StepResult] = []
        accumulated_context = context or ""

        if not workflow.nodes:
            return WorkflowResult(
                success=False,
                query=workflow.query,
                final_output="관련 도구를 찾을 수 없습니다.",
                total_duration_ms=0,
            )

        logger.info(
            f"[WorkflowExecutor] 워크플로우 시작: {workflow.query} "
            f"→ {[n.name for n in workflow.nodes]}"
        )

        for i, node in enumerate(workflow.nodes):
            step_start = time.time()

            # 이전 스텝 결과를 컨텍스트에 누적
            step_context = self._build_step_context(
                instruction=instruction,
                node=node,
                step_index=i,
                total_steps=len(workflow.nodes),
                accumulated_context=accumulated_context,
                previous_steps=steps,
            )

            # 도구 실행
            step_result = await self._execute_step(node, step_context)
            step_result.duration_ms = int((time.time() - step_start) * 1000)
            steps.append(step_result)

            logger.info(
                f"[WorkflowExecutor] Step {i+1}/{len(workflow.nodes)}: "
                f"{node.name} → {'성공' if step_result.success else '실패'} "
                f"({step_result.duration_ms}ms)"
            )

            # 결과를 누적 컨텍스트에 추가
            if step_result.success and step_result.output:
                accumulated_context += f"\n\n## {node.name} 결과:\n{step_result.output[:2000]}"

            # 실패 시 대체 경로 탐색
            if not step_result.success:
                alt_node = self._find_alternative(node, workflow)
                if alt_node:
                    logger.info(f"[WorkflowExecutor] 대체 도구 시도: {alt_node.name}")
                    alt_result = await self._execute_step(alt_node, step_context)
                    alt_result.duration_ms = int((time.time() - step_start) * 1000)
                    steps.append(alt_result)

                    if alt_result.success and alt_result.output:
                        accumulated_context += f"\n\n## {alt_node.name} 결과:\n{alt_result.output[:2000]}"

        total_ms = int((time.time() - start_time) * 1000)
        all_success = all(s.success for s in steps)

        # 최종 출력: 마지막 성공 스텝의 결과
        final_output = ""
        for step in reversed(steps):
            if step.success and step.output:
                final_output = step.output
                break

        result = WorkflowResult(
            success=all_success,
            query=workflow.query,
            steps=steps,
            final_output=final_output,
            total_duration_ms=total_ms,
            workflow_score=workflow.score,
        )

        # 워크플로우 결과 기반 그래프 학습
        self._learn_from_result(workflow, result)

        return result

    def _build_step_context(
        self,
        instruction: str,
        node: ToolNode,
        step_index: int,
        total_steps: int,
        accumulated_context: str,
        previous_steps: list[StepResult],
    ) -> str:
        """각 스텝에 전달할 컨텍스트 구성"""
        parts = [f"## 원본 지시\n{instruction}"]

        if step_index > 0 and previous_steps:
            parts.append(f"\n## 워크플로우 진행 ({step_index}/{total_steps})")
            for prev in previous_steps[-3:]:  # 최근 3개만
                status = "성공" if prev.success else "실패"
                output_preview = (prev.output[:500] + "...") if len(prev.output) > 500 else prev.output
                parts.append(f"- [{status}] {prev.tool_name}: {output_preview}")

        parts.append(f"\n## 현재 단계: {node.name}")
        parts.append(f"설명: {node.description}")

        if node.actions:
            parts.append(f"가능한 액션: {', '.join(node.actions)}")

        if accumulated_context:
            parts.append(f"\n## 이전 컨텍스트\n{accumulated_context[-3000:]}")

        return "\n".join(parts)

    async def _execute_step(self, node: ToolNode, context: str) -> StepResult:
        """단일 스텝 실행"""
        from jinxus.tools import get_tool

        tool = get_tool(node.name)
        if not tool:
            return StepResult(
                tool_name=node.name,
                success=False,
                output="",
                error=f"도구를 찾을 수 없음: {node.name}",
            )

        try:
            # 도구에 컨텍스트 기반 입력 구성
            input_data = self._build_tool_input(node, context)
            result = await tool.run(input_data)

            output = ""
            if hasattr(result, 'output'):
                output = json.dumps(result.output, ensure_ascii=False) if isinstance(result.output, dict) else str(result.output or "")

            return StepResult(
                tool_name=node.name,
                success=getattr(result, 'success', True),
                output=output,
                error=getattr(result, 'error', None),
            )

        except Exception as e:
            logger.error(f"[WorkflowExecutor] Step 실행 실패 [{node.name}]: {e}")
            return StepResult(
                tool_name=node.name,
                success=False,
                output="",
                error=str(e),
            )

    def _build_tool_input(self, node: ToolNode, context: str) -> dict:
        """도구별 입력 데이터 구성"""
        # 기본: 컨텍스트를 query/instruction으로 전달
        if node.name == "web_searcher":
            # 웹 검색: 컨텍스트에서 검색어 추출 (첫 줄)
            first_line = context.split("\n")[0].replace("## 원본 지시", "").strip()
            return {"query": first_line, "max_results": 5}

        if node.name == "code_executor":
            return {"prompt": context, "timeout": 300}

        if node.name in ("github_agent", "github_graphql"):
            return {"action": "get_repo", "input": context}

        if node.name == "file_manager":
            return {"action": "list", "path": ".", "input": context}

        if node.name == "system_manager":
            return {"action": "get_system_status"}

        # 기타 도구: 범용 입력
        return {"input": context}

    def _find_alternative(self, failed_node: ToolNode, workflow: Workflow) -> Optional[ToolNode]:
        """실패한 노드의 대체 도구 탐색 (SIMILAR_TO 엣지)"""
        neighbors = self._graph.get_neighbors(failed_node.name, EdgeType.SIMILAR_TO)
        used_names = {n.name for n in workflow.nodes}

        for neighbor_name, _ in neighbors:
            if neighbor_name not in used_names:
                node = self._graph.get_node(neighbor_name)
                if node:
                    # 에이전트 권한 확인
                    if not node.allowed_agents or self._agent_name in node.allowed_agents:
                        return node
        return None

    def _learn_from_result(self, workflow: Workflow, result: WorkflowResult) -> None:
        """워크플로우 결과에서 그래프 가중치 학습 + 메타 스토어 저장"""
        if not result.steps:
            return

        delta = 0.1 if result.success else -0.05

        # 성공한 노드의 가중치 강화
        for step in result.steps:
            if step.success:
                self._graph.update_node_weight(step.tool_name, delta)

        # 성공한 워크플로우의 엣지 가중치 강화
        if result.success:
            for edge in workflow.edges:
                if edge.edge_type in (EdgeType.PRECEDES, EdgeType.REQUIRES):
                    self._graph.update_edge_weight(edge.source, edge.target, delta)

        # 워크플로우 패턴을 메타 스토어에 비동기 저장
        import asyncio
        try:
            from jinxus.memory.meta_store import get_meta_store
            meta = get_meta_store()
            tool_seq = [s.tool_name for s in result.steps if s.success]
            if tool_seq:
                asyncio.create_task(meta.save_workflow_pattern(
                    query=result.query,
                    tool_sequence=tool_seq,
                    success=result.success,
                    score=result.workflow_score,
                    duration_ms=result.total_duration_ms,
                ))
        except Exception as e:
            logger.debug(f"워크플로우 패턴 저장 실패: {e}")

        # 학습된 가중치를 디스크에 저장
        try:
            save_tool_graph()
        except Exception as e:
            logger.debug(f"ToolGraph 가중치 저장 실패: {e}")
