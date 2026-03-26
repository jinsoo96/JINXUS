"""DAGScheduler — depends_on 기반 서브태스크 DAG 실행 엔진

서브태스크의 depends_on 필드를 분석하여 진짜 DAG(Directed Acyclic Graph)로 실행한다.
- 의존성 없는 태스크는 asyncio.gather로 병렬 실행
- 의존성 있는 태스크는 asyncio.Event로 선행 완료 대기
- 순환 참조 감지 → CycleDetectedError 발생
- 실패한 태스크의 후속 태스크는 자동 스킵 (cascade failure 방지)
- 진행률 콜백 지원
"""

import asyncio
import logging
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class CycleDetectedError(Exception):
    """DAG에 순환 참조가 존재할 때 발생"""


class TaskNode(TypedDict, total=False):
    """DAG 노드 (SubTask 호환)"""
    task_id: str
    assigned_agent: str
    instruction: str
    depends_on: List[str]
    priority: str


class TaskResult(TypedDict, total=False):
    """태스크 실행 결과"""
    task_id: str
    agent_name: str
    success: bool
    success_score: float
    output: str
    failure_reason: Optional[str]
    duration_ms: int
    skipped: bool
    skip_reason: Optional[str]


# executor_fn 타입: 서브태스크 + 선행 결과 dict → TaskResult
ExecutorFn = Callable[[TaskNode, Dict[str, TaskResult]], Awaitable[TaskResult]]
ProgressFn = Callable[[int, int, str], Awaitable[None]]


class DAGScheduler:
    """depends_on 기반 DAG 스케줄러

    Usage:
        scheduler = DAGScheduler(subtasks)
        results = await scheduler.execute(executor_fn, on_progress=callback)
    """

    def __init__(self, subtasks: List[TaskNode]):
        self._subtasks = {st["task_id"]: st for st in subtasks}
        self._validate_and_build()

    def _validate_and_build(self):
        """DAG 구성 + 순환 참조 검증"""
        # 인접 리스트 (task_id -> 이 태스크에 의존하는 태스크들)
        self._dependents: Dict[str, List[str]] = defaultdict(list)
        # 각 태스크의 선행 의존 수
        self._in_degree: Dict[str, int] = {}
        # 각 태스크의 선행 의존 목록
        self._dependencies: Dict[str, List[str]] = {}

        for task_id, task in self._subtasks.items():
            deps = task.get("depends_on", [])
            # 존재하지 않는 의존성은 무시
            valid_deps = [d for d in deps if d in self._subtasks]
            self._dependencies[task_id] = valid_deps
            self._in_degree[task_id] = len(valid_deps)
            for dep in valid_deps:
                self._dependents[dep].append(task_id)

        # 순환 참조 검증 (Kahn's algorithm으로 토폴로지컬 정렬)
        self._topo_order = self._topological_sort()

    def _topological_sort(self) -> List[str]:
        """Kahn's algorithm으로 토폴로지컬 정렬. 순환 시 CycleDetectedError."""
        in_degree = dict(self._in_degree)
        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        order = []

        while queue:
            tid = queue.popleft()
            order.append(tid)
            for dependent in self._dependents.get(tid, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(self._subtasks):
            remaining = set(self._subtasks.keys()) - set(order)
            raise CycleDetectedError(
                f"DAG에 순환 참조 발견: {remaining}"
            )

        return order

    @property
    def execution_order(self) -> List[str]:
        """토폴로지컬 정렬 순서 반환 (디버깅용)"""
        return list(self._topo_order)

    @property
    def parallelism_levels(self) -> List[List[str]]:
        """병렬 실행 가능한 레벨별 태스크 그룹 반환 (디버깅용)"""
        levels = []
        remaining_in_degree = dict(self._in_degree)
        done = set()

        while len(done) < len(self._subtasks):
            # in_degree가 0인 것들이 현재 레벨
            level = [
                tid for tid, deg in remaining_in_degree.items()
                if deg == 0 and tid not in done
            ]
            if not level:
                break
            levels.append(level)
            for tid in level:
                done.add(tid)
                for dep in self._dependents.get(tid, []):
                    remaining_in_degree[dep] -= 1

        return levels

    async def execute(
        self,
        executor_fn: ExecutorFn,
        on_progress: Optional[ProgressFn] = None,
    ) -> List[TaskResult]:
        """DAG 기반 실행

        Args:
            executor_fn: async (subtask, dep_results) -> TaskResult
            on_progress: async (completed, total, current_task_id) -> None

        Returns:
            모든 태스크의 결과 리스트 (토폴로지컬 순서)
        """
        total = len(self._subtasks)
        completed_count = 0

        # 태스크별 완료 이벤트
        events: Dict[str, asyncio.Event] = {
            tid: asyncio.Event() for tid in self._subtasks
        }
        # 태스크별 결과 저장
        results: Dict[str, TaskResult] = {}
        # 실패한 태스크 ID 집합 (cascade skip용)
        failed: set = set()

        async def _run_task(task_id: str):
            nonlocal completed_count

            task = self._subtasks[task_id]
            deps = self._dependencies.get(task_id, [])

            # 선행 태스크 완료 대기
            for dep_id in deps:
                await events[dep_id].wait()

            # 선행 태스크 중 실패한 것이 있으면 스킵
            failed_deps = [d for d in deps if d in failed]
            if failed_deps:
                result: TaskResult = {
                    "task_id": task_id,
                    "agent_name": task.get("assigned_agent", "?"),
                    "success": False,
                    "success_score": 0.0,
                    "output": "",
                    "failure_reason": None,
                    "duration_ms": 0,
                    "skipped": True,
                    "skip_reason": f"선행 태스크 실패: {', '.join(failed_deps)}",
                }
                failed.add(task_id)
                results[task_id] = result
                events[task_id].set()
                completed_count += 1
                if on_progress:
                    await on_progress(completed_count, total, task_id)
                return

            # 선행 태스크 결과 수집
            dep_results = {d: results[d] for d in deps if d in results}

            # 실행
            try:
                result = await executor_fn(task, dep_results)
                result["task_id"] = task_id
                if not result.get("success", False):
                    failed.add(task_id)
            except Exception as e:
                logger.error("[DAGScheduler] Task %s failed: %s", task_id, e)
                result = {
                    "task_id": task_id,
                    "agent_name": task.get("assigned_agent", "?"),
                    "success": False,
                    "success_score": 0.0,
                    "output": "",
                    "failure_reason": str(e),
                    "duration_ms": 0,
                    "skipped": False,
                    "skip_reason": None,
                }
                failed.add(task_id)

            results[task_id] = result
            events[task_id].set()
            completed_count += 1

            if on_progress:
                await on_progress(completed_count, total, task_id)

        # 모든 태스크를 동시에 시작 — 각자 자기 의존성을 Event로 대기
        tasks = [asyncio.create_task(_run_task(tid)) for tid in self._subtasks]
        await asyncio.gather(*tasks)

        # 토폴로지컬 순서로 결과 정렬
        return [results[tid] for tid in self._topo_order if tid in results]
