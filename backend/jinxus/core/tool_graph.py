"""그래프 기반 도구 탐색 엔진

도구 간 관계를 그래프로 모델링하고, 사용자 쿼리에서
관련 도구 워크플로우를 자동으로 구성한다.

참고: https://github.com/SonAIengine/graph-tool-call
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

logger = logging.getLogger(__name__)


class EdgeType(str, Enum):
    """도구 간 관계 유형"""
    REQUIRES = "requires"           # A 실행 시 B의 결과가 필요
    PRECEDES = "precedes"           # A 다음에 B가 실행되어야 함
    COMPLEMENTARY = "complementary" # 함께 사용하면 좋은 보완 관계
    SIMILAR_TO = "similar_to"       # 기능이 유사한 대체 도구
    CONFLICTS_WITH = "conflicts"    # 동시 실행 불가
    BELONGS_TO = "belongs_to"       # 카테고리 분류


@dataclass
class ToolNode:
    """도구 노드"""
    name: str
    description: str
    category: str = ""
    allowed_agents: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    weight: float = 1.0  # 기본 가중치 (학습으로 변동)

    def matches_query(self, query: str) -> float:
        """쿼리와의 매칭 점수 (0~1)"""
        query_lower = query.lower()
        score = 0.0

        # 이름 매칭
        if self.name.lower() in query_lower:
            score += 0.5

        # 키워드 매칭
        matched_keywords = sum(
            1 for kw in self.keywords if kw.lower() in query_lower
        )
        if self.keywords:
            score += 0.3 * (matched_keywords / len(self.keywords))

        # 설명 매칭 (단어 단위)
        query_words = set(query_lower.split())
        desc_words = set(self.description.lower().split())
        overlap = len(query_words & desc_words)
        if query_words:
            score += 0.2 * min(overlap / len(query_words), 1.0)

        return min(score * self.weight, 1.0)


@dataclass
class ToolEdge:
    """도구 간 관계 엣지"""
    source: str       # 출발 노드 이름
    target: str       # 도착 노드 이름
    edge_type: EdgeType
    weight: float = 1.0
    description: str = ""


@dataclass
class Workflow:
    """탐색된 워크플로우"""
    nodes: list[ToolNode]
    edges: list[ToolEdge]
    score: float = 0.0
    query: str = ""

    @property
    def tool_names(self) -> list[str]:
        return [n.name for n in self.nodes]

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "score": self.score,
            "tools": [
                {"name": n.name, "description": n.description, "category": n.category}
                for n in self.nodes
            ],
            "edges": [
                {"from": e.source, "to": e.target, "type": e.edge_type.value}
                for e in self.edges
            ],
        }


class ToolGraph:
    """그래프 기반 도구 탐색 엔진

    도구들을 노드로, 관계를 엣지로 모델링하여
    쿼리에 맞는 도구 워크플로우를 자동으로 구성한다.
    """

    def __init__(self):
        self._nodes: dict[str, ToolNode] = {}
        self._edges: list[ToolEdge] = []
        # 인접 리스트 (양방향)
        self._adj: dict[str, list[ToolEdge]] = {}

    def add_node(self, node: ToolNode) -> None:
        """노드 추가"""
        self._nodes[node.name] = node
        if node.name not in self._adj:
            self._adj[node.name] = []

    def add_edge(self, edge: ToolEdge) -> None:
        """엣지 추가"""
        # 노드가 없으면 무시
        if edge.source not in self._nodes or edge.target not in self._nodes:
            logger.warning(f"Edge skipped: {edge.source} -> {edge.target} (node not found)")
            return

        self._edges.append(edge)

        if edge.source not in self._adj:
            self._adj[edge.source] = []
        self._adj[edge.source].append(edge)

        # 양방향 탐색을 위한 역방향 (SIMILAR_TO, COMPLEMENTARY)
        if edge.edge_type in (EdgeType.SIMILAR_TO, EdgeType.COMPLEMENTARY):
            reverse = ToolEdge(
                source=edge.target,
                target=edge.source,
                edge_type=edge.edge_type,
                weight=edge.weight,
                description=edge.description,
            )
            if edge.target not in self._adj:
                self._adj[edge.target] = []
            self._adj[edge.target].append(reverse)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        max_depth: int = 2,
        agent_name: Optional[str] = None,
    ) -> Workflow:
        """쿼리에서 관련 도구 워크플로우 탐색

        1. 키워드 매칭으로 seed 노드 탐색
        2. BFS로 관련 노드 확장
        3. 엣지 관계에 따라 실행 순서 결정
        """
        # 1단계: seed 노드 (상위 매칭)
        scores = []
        for name, node in self._nodes.items():
            # 에이전트 권한 필터
            if agent_name and node.allowed_agents and agent_name not in node.allowed_agents:
                continue
            score = node.matches_query(query)
            if score > 0:
                scores.append((name, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        seed_names = [name for name, _ in scores[:3]]  # 상위 3개 seed

        if not seed_names:
            return Workflow(nodes=[], edges=[], score=0.0, query=query)

        # 2단계: BFS 확장
        visited = set(seed_names)
        discovered: dict[str, float] = {name: score for name, score in scores[:3]}
        queue: deque[tuple[str, int]] = deque((name, 0) for name in seed_names)
        workflow_edges: list[ToolEdge] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for edge in self._adj.get(current, []):
                neighbor = edge.target
                # 에이전트 권한 필터
                if agent_name:
                    neighbor_node = self._nodes.get(neighbor)
                    if neighbor_node and neighbor_node.allowed_agents and agent_name not in neighbor_node.allowed_agents:
                        continue

                # CONFLICTS_WITH는 제외
                if edge.edge_type == EdgeType.CONFLICTS_WITH:
                    continue

                # 점수 감쇠 (깊이에 따라)
                decay = 0.6 ** (depth + 1)
                neighbor_score = edge.weight * decay

                if neighbor not in visited:
                    visited.add(neighbor)
                    discovered[neighbor] = neighbor_score
                    queue.append((neighbor, depth + 1))

                workflow_edges.append(edge)

        # 3단계: 점수 순 정렬 후 top_k
        sorted_nodes = sorted(discovered.items(), key=lambda x: x[1], reverse=True)[:top_k]
        result_names = {name for name, _ in sorted_nodes}

        # 결과 노드와 관련 엣지만 필터
        result_nodes = [self._nodes[name] for name, _ in sorted_nodes if name in self._nodes]
        result_edges = [e for e in workflow_edges if e.source in result_names and e.target in result_names]

        # 4단계: 실행 순서 정렬 (위상 정렬)
        result_nodes = self._topological_sort(result_nodes, result_edges)

        total_score = sum(s for _, s in sorted_nodes)
        return Workflow(
            nodes=result_nodes,
            edges=result_edges,
            score=total_score,
            query=query,
        )

    def _topological_sort(self, nodes: list[ToolNode], edges: list[ToolEdge]) -> list[ToolNode]:
        """엣지 관계에 따른 위상 정렬 (REQUIRES, PRECEDES 기반)"""
        name_set = {n.name for n in nodes}
        node_map = {n.name: n for n in nodes}

        # 순서 엣지만 필터
        order_edges = [
            e for e in edges
            if e.edge_type in (EdgeType.REQUIRES, EdgeType.PRECEDES)
            and e.source in name_set and e.target in name_set
        ]

        if not order_edges:
            return nodes

        # in-degree 계산
        in_degree: dict[str, int] = {n.name: 0 for n in nodes}
        adj: dict[str, list[str]] = {n.name: [] for n in nodes}

        for edge in order_edges:
            # REQUIRES: target이 먼저 실행 → target → source
            # PRECEDES: source가 먼저 실행 → source → target
            if edge.edge_type == EdgeType.REQUIRES:
                adj[edge.target].append(edge.source)
                in_degree[edge.source] += 1
            elif edge.edge_type == EdgeType.PRECEDES:
                adj[edge.source].append(edge.target)
                in_degree[edge.target] += 1

        # Kahn's algorithm
        queue = deque(name for name in in_degree if in_degree[name] == 0)
        sorted_names: list[str] = []

        while queue:
            current = queue.popleft()
            sorted_names.append(current)
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 순환이 있으면 남은 노드 추가
        remaining = [n.name for n in nodes if n.name not in sorted_names]
        sorted_names.extend(remaining)

        return [node_map[name] for name in sorted_names if name in node_map]

    def get_neighbors(self, tool_name: str, edge_type: Optional[EdgeType] = None) -> list[tuple[str, EdgeType]]:
        """특정 노드의 이웃 조회"""
        result = []
        for edge in self._adj.get(tool_name, []):
            if edge_type is None or edge.edge_type == edge_type:
                result.append((edge.target, edge.edge_type))
        return result

    def update_edge_weight(self, source: str, target: str, delta: float) -> None:
        """엣지 가중치 업데이트 (학습용)"""
        for edge in self._edges:
            if edge.source == source and edge.target == target:
                edge.weight = max(0.1, min(edge.weight + delta, 5.0))
                break

    def update_node_weight(self, name: str, delta: float) -> None:
        """노드 가중치 업데이트 (학습용)"""
        node = self._nodes.get(name)
        if node:
            node.weight = max(0.1, min(node.weight + delta, 5.0))

    async def retrieve_with_history(
        self,
        query: str,
        top_k: int = 5,
        agent_name: Optional[str] = None,
    ) -> Workflow:
        """메타 스토어의 과거 성공 패턴을 참고하여 워크플로우 탐색"""
        try:
            from jinxus.memory.meta_store import get_meta_store
            meta = get_meta_store()
            patterns = await meta.find_similar_workflows(query, limit=3)

            if patterns:
                # 가장 많이 사용된 성공 패턴의 도구 가중치 일시 부스트
                best = patterns[0]
                for tool_name in best["tool_sequence"]:
                    node = self._nodes.get(tool_name)
                    if node:
                        node.weight = min(node.weight + 0.3, 5.0)
        except Exception:
            pass

        return self.retrieve(query, top_k=top_k, agent_name=agent_name)

    def get_node(self, name: str) -> Optional[ToolNode]:
        return self._nodes.get(name)

    def get_all_nodes(self) -> list[ToolNode]:
        return list(self._nodes.values())

    def get_all_edges(self) -> list[ToolEdge]:
        return list(self._edges)

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"name": n.name, "description": n.description, "category": n.category, "keywords": n.keywords}
                for n in self._nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.edge_type.value, "weight": e.weight}
                for e in self._edges
            ],
        }


# ═══════════════════════════════════════════════════
# 기존 JINXUS 도구에서 ToolGraph 자동 구축
# ═══════════════════════════════════════════════════

def build_jinxus_tool_graph() -> ToolGraph:
    """JINXUS의 기존 도구 + MCP 도구를 그래프로 구축

    노드는 TOOL_REGISTRY에서 자동 추출하고,
    키워드/카테고리 등 그래프 전용 메타데이터는 수동 매핑으로 보완한다.
    """
    from jinxus.tools import TOOL_REGISTRY, register_tools

    # TOOL_REGISTRY가 비어있으면 초기화
    if not TOOL_REGISTRY:
        register_tools()

    graph = ToolGraph()

    # ── 그래프 전용 메타데이터 (키워드, 카테고리 등) ──
    # TOOL_REGISTRY에 없는 그래프 탐색용 정보를 수동 매핑
    _NODE_META: dict[str, dict] = {
        "code_executor": {
            "category": "development",
            "keywords": ["코드", "실행", "프로그래밍", "개발", "디버깅", "code", "execute", "run", "debug"],
        },
        "web_searcher": {
            "category": "research",
            "keywords": ["검색", "웹", "찾기", "조사", "search", "web", "find", "research", "뉴스", "news"],
        },
        "file_manager": {
            "category": "filesystem",
            "keywords": ["파일", "읽기", "쓰기", "저장", "삭제", "file", "read", "write", "save", "delete"],
        },
        "github_agent": {
            "category": "github",
            "keywords": ["깃허브", "GitHub", "레포", "PR", "커밋", "이슈", "브랜치",
                          "repo", "commit", "pull request", "issue", "branch", "push"],
        },
        "github_graphql": {
            "category": "github",
            "keywords": ["깃허브", "GitHub", "코드검색", "레포", "repo", "search_code"],
        },
        "scheduler": {
            "category": "automation",
            "keywords": ["스케줄", "예약", "반복", "cron", "schedule", "recurring", "자동"],
        },
        "system_manager": {
            "category": "system",
            "keywords": ["시스템", "세션", "메모리", "캐시", "정리", "상태", "system", "session", "memory", "cache", "cleanup"],
        },
        "hr_tool": {
            "category": "management",
            "keywords": ["고용", "해고", "에이전트", "생성", "hire", "fire", "agent", "spawn"],
        },
        "prompt_version_manager": {
            "category": "management",
            "keywords": ["프롬프트", "버전", "동기화", "롤백", "prompt", "version", "sync", "rollback"],
        },
    }

    # ── 노드 등록: TOOL_REGISTRY에서 자동 추출 + 메타데이터 보완 ──
    for tool_name, tool in TOOL_REGISTRY.items():
        meta = _NODE_META.get(tool_name, {})
        graph.add_node(ToolNode(
            name=tool.name,
            description=tool.description,
            category=meta.get("category", "general"),
            allowed_agents=list(tool.allowed_agents) if tool.allowed_agents else [],
            keywords=meta.get("keywords", []),
        ))

    # ── 엣지 등록 (도구 간 관계) ──

    # GitHub 워크플로우: 조회 → 분기 생성 → 코드 작성 → 커밋 → PR
    graph.add_edge(ToolEdge("github_graphql", "github_agent", EdgeType.PRECEDES,
                            description="GraphQL로 조회 후 REST로 수정 작업"))
    graph.add_edge(ToolEdge("code_executor", "github_agent", EdgeType.PRECEDES,
                            description="코드 작성 후 GitHub에 커밋/PR"))
    graph.add_edge(ToolEdge("github_agent", "code_executor", EdgeType.REQUIRES,
                            weight=0.7, description="레포 정보가 코드 작업에 필요할 수 있음"))

    # GitHub 도구 간 유사성
    graph.add_edge(ToolEdge("github_agent", "github_graphql", EdgeType.SIMILAR_TO,
                            description="둘 다 GitHub 데이터 접근"))

    # 리서치 → 코드 작성 워크플로우
    graph.add_edge(ToolEdge("web_searcher", "code_executor", EdgeType.PRECEDES,
                            weight=0.8, description="조사 후 코드 작성"))

    # 파일 관련 워크플로우
    graph.add_edge(ToolEdge("code_executor", "file_manager", EdgeType.COMPLEMENTARY,
                            description="코드 실행과 파일 관리는 보완 관계"))
    graph.add_edge(ToolEdge("file_manager", "github_agent", EdgeType.PRECEDES,
                            weight=0.6, description="파일 작성 후 GitHub 커밋"))

    # 리서치 → 문서 작성
    graph.add_edge(ToolEdge("web_searcher", "file_manager", EdgeType.PRECEDES,
                            weight=0.7, description="검색 결과를 파일로 저장"))

    # 시스템 관리 관계
    graph.add_edge(ToolEdge("system_manager", "scheduler", EdgeType.COMPLEMENTARY,
                            description="시스템 관리와 스케줄 관리는 보완"))
    graph.add_edge(ToolEdge("hr_tool", "system_manager", EdgeType.COMPLEMENTARY,
                            description="에이전트 관리와 시스템 관리는 보완"))
    graph.add_edge(ToolEdge("hr_tool", "prompt_version_manager", EdgeType.PRECEDES,
                            weight=0.5, description="에이전트 생성 후 프롬프트 설정"))

    # 충돌 관계
    graph.add_edge(ToolEdge("github_agent", "github_graphql", EdgeType.CONFLICTS_WITH,
                            weight=0.3, description="같은 API rate limit 공유"))

    logger.info(f"ToolGraph built: {len(graph._nodes)} nodes, {len(graph._edges)} edges")
    return graph


# ── 싱글톤 ──

_tool_graph: Optional[ToolGraph] = None


def get_tool_graph() -> ToolGraph:
    """ToolGraph 싱글톤"""
    global _tool_graph
    if _tool_graph is None:
        _tool_graph = build_jinxus_tool_graph()
    return _tool_graph
