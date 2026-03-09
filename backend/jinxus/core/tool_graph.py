"""그래프 기반 도구 탐색 엔진

도구 간 관계를 그래프로 모델링하고, 사용자 쿼리에서
관련 도구 워크플로우를 자동으로 구성한다.

v2: BM25 + 그래프 BFS + wRRF 퓨전, 히스토리 디모션, JSON 영속화
참고: https://github.com/SonAIengine/graph-tool-call
"""
import json
import logging
import math
import os
import re
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "allowed_agents": self.allowed_agents,
            "actions": self.actions,
            "keywords": self.keywords,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolNode":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolEdge:
    """도구 간 관계 엣지"""
    source: str       # 출발 노드 이름
    target: str       # 도착 노드 이름
    edge_type: EdgeType
    weight: float = 1.0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolEdge":
        d = dict(data)
        d["edge_type"] = EdgeType(d["edge_type"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


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


# ═══════════════════════════════════════════════════
# BM25 스코어러 (자체 구현, graph-tool-call 패턴)
# ═══════════════════════════════════════════════════

# 한국어 불용어
_KO_STOPWORDS = {"은", "는", "이", "가", "을", "를", "에", "에서", "의", "와", "과", "로", "으로", "도", "만", "좀", "해줘", "알려줘", "해", "줘"}

# 영어 불용어
_EN_STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
                 "at", "by", "from", "it", "this", "that", "and", "or", "but", "not", "no",
                 "so", "if", "me", "my", "i", "you", "your", "we", "our", "they", "their"}

# CRUD 관련 단어는 보호 (stopword에서 제외)
_PROTECTED_TERMS = {"list", "get", "create", "delete", "read", "write", "search", "find",
                    "run", "execute", "push", "pull", "commit", "fetch", "send", "check"}


def _tokenize(text: str) -> list[str]:
    """텍스트 토큰화 (한국어 bigram + 영어 단어 분리 + camelCase 분리)"""
    tokens = []
    text = text.lower().strip()

    # camelCase/snake_case 분리
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = text.replace("_", " ").replace("-", " ").replace(":", " ")

    # 영어 단어 추출
    en_words = re.findall(r'[a-z]{2,}', text)
    for w in en_words:
        if w not in _EN_STOPWORDS or w in _PROTECTED_TERMS:
            tokens.append(w)

    # 한국어 문자 추출 → bigram
    ko_chars = re.findall(r'[\uac00-\ud7a3]+', text)
    for word in ko_chars:
        if word in _KO_STOPWORDS:
            continue
        if len(word) == 1:
            tokens.append(word)
        elif len(word) == 2:
            # 2글자는 bigram = 전체 단어이므로 한 번만
            tokens.append(word)
        else:
            # 3글자 이상: bigram + 전체 단어
            for i in range(len(word) - 1):
                tokens.append(word[i:i+2])
            tokens.append(word)

    return tokens


class BM25Scorer:
    """BM25 기반 도구 검색 스코어러

    도구의 이름, 설명, 키워드를 문서로 취급하여
    쿼리와의 BM25 점수를 계산한다.
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._docs: dict[str, list[str]] = {}  # tool_name -> tokens
        self._doc_lens: dict[str, int] = {}
        self._avg_dl: float = 0.0
        self._idf: dict[str, float] = {}
        self._n_docs: int = 0

    def index(self, nodes: dict[str, "ToolNode"]) -> None:
        """노드 목록으로 인덱스 구축"""
        self._docs.clear()
        self._doc_lens.clear()

        for name, node in nodes.items():
            # 도구의 텍스트 구성: 이름 + 설명 + 키워드
            text = f"{node.name} {node.description} {' '.join(node.keywords)} {node.category}"
            tokens = _tokenize(text)
            self._docs[name] = tokens
            self._doc_lens[name] = len(tokens)

        self._n_docs = len(self._docs)
        if self._n_docs > 0:
            self._avg_dl = sum(self._doc_lens.values()) / self._n_docs
        else:
            self._avg_dl = 1.0

        # IDF 계산
        self._compute_idf()

    def _compute_idf(self) -> None:
        """역문서빈도(IDF) 계산"""
        df: dict[str, int] = {}
        for tokens in self._docs.values():
            unique_tokens = set(tokens)
            for t in unique_tokens:
                df[t] = df.get(t, 0) + 1

        self._idf = {}
        for term, n_qi in df.items():
            self._idf[term] = math.log((self._n_docs - n_qi + 0.5) / (n_qi + 0.5) + 1.0)

    def score(self, query: str) -> dict[str, float]:
        """쿼리에 대한 각 도구의 BM25 점수 계산"""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return {}

        scores: dict[str, float] = {}
        for name, doc_tokens in self._docs.items():
            score = 0.0
            dl = self._doc_lens[name]
            # term frequency 계산
            tf_map: dict[str, int] = {}
            for t in doc_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            for q_token in query_tokens:
                if q_token not in self._idf:
                    continue
                idf = self._idf[q_token]
                tf = tf_map.get(q_token, 0)
                if tf == 0:
                    continue
                # BM25 공식
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * dl / self._avg_dl)
                score += idf * numerator / denominator

            if score > 0:
                scores[name] = score

        return scores


# ═══════════════════════════════════════════════════
# ToolGraph 본체
# ═══════════════════════════════════════════════════

class ToolGraph:
    """그래프 기반 도구 탐색 엔진

    v2: BM25 + BFS 그래프 확장 + wRRF 랭크 퓨전
    """

    # wRRF 가중치
    _WEIGHT_BM25 = 0.35
    _WEIGHT_GRAPH = 0.65
    _WRRF_K = 60  # RRF 상수

    def __init__(self):
        self._nodes: dict[str, ToolNode] = {}
        self._edges: list[ToolEdge] = []
        self._adj: dict[str, list[ToolEdge]] = {}
        self._bm25 = BM25Scorer()
        self._bm25_dirty = True  # 인덱스 재빌드 필요 여부

    def add_node(self, node: ToolNode) -> None:
        """노드 추가"""
        self._nodes[node.name] = node
        if node.name not in self._adj:
            self._adj[node.name] = []
        self._bm25_dirty = True

    def add_edge(self, edge: ToolEdge) -> None:
        """엣지 추가"""
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

    def _ensure_bm25_index(self) -> None:
        """BM25 인덱스가 최신인지 확인하고 필요시 재빌드"""
        if self._bm25_dirty:
            self._bm25.index(self._nodes)
            self._bm25_dirty = False

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        max_depth: int = 2,
        agent_name: Optional[str] = None,
        history: Optional[list[str]] = None,
    ) -> Workflow:
        """쿼리에서 관련 도구 워크플로우 탐색 (wRRF 퓨전)

        1. BM25로 키워드 기반 점수 계산
        2. BFS로 그래프 기반 점수 계산 (BM25 상위를 seed로)
        3. wRRF로 두 소스 랭크 퓨전
        4. history 디모션 (최근 사용 도구 점수 감쇠)
        5. 위상 정렬로 실행 순서 결정
        """
        self._ensure_bm25_index()

        # ── 1단계: BM25 점수 ──
        bm25_scores = self._bm25.score(query)

        # 에이전트 권한 필터
        if agent_name:
            bm25_scores = {
                name: score for name, score in bm25_scores.items()
                if not self._nodes[name].allowed_agents or agent_name in self._nodes[name].allowed_agents
            }

        # ── 2단계: 그래프 BFS 점수 ──
        # BM25 상위 3개를 seed로 사용
        bm25_sorted = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
        seed_names = [name for name, _ in bm25_sorted[:3]]

        # history에 있는 도구도 추가 seed로 사용 (쿼리 확장 효과)
        if history:
            for h in history:
                if h in self._nodes and h not in seed_names:
                    seed_names.append(h)

        graph_scores: dict[str, float] = {}
        workflow_edges: list[ToolEdge] = []

        if seed_names:
            graph_scores, workflow_edges = self._bfs_expand(
                seed_names, max_depth, agent_name
            )

        # ── 3단계: wRRF 퓨전 ──
        final_scores = self._wrrf_fuse([
            (bm25_scores, self._WEIGHT_BM25),
            (graph_scores, self._WEIGHT_GRAPH),
        ])

        # BM25에만 있는 도구도 포함 (seed 노드)
        for name, score in bm25_scores.items():
            if name not in final_scores:
                final_scores[name] = score * self._WEIGHT_BM25 / (self._WRRF_K + 1)

        # ── 4단계: history 디모션 ──
        if history:
            for tool_name in history:
                if tool_name in final_scores:
                    final_scores[tool_name] *= 0.8  # 20% 감쇠

        # 노드 가중치 반영
        for name in final_scores:
            node = self._nodes.get(name)
            if node:
                final_scores[name] *= node.weight

        if not final_scores:
            return Workflow(nodes=[], edges=[], score=0.0, query=query)

        # ── 5단계: top_k 선택 + 위상 정렬 ──
        sorted_nodes = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        result_names = {name for name, _ in sorted_nodes}

        result_nodes = [self._nodes[name] for name, _ in sorted_nodes if name in self._nodes]
        result_edges = [e for e in workflow_edges if e.source in result_names and e.target in result_names]

        result_nodes = self._topological_sort(result_nodes, result_edges)

        total_score = sum(s for _, s in sorted_nodes)
        return Workflow(
            nodes=result_nodes,
            edges=result_edges,
            score=total_score,
            query=query,
        )

    def _bfs_expand(
        self,
        seed_names: list[str],
        max_depth: int,
        agent_name: Optional[str],
    ) -> tuple[dict[str, float], list[ToolEdge]]:
        """BFS로 seed 노드에서 그래프 확장하여 점수 계산"""
        visited = set(seed_names)
        # seed 노드에 초기 점수 부여
        scores: dict[str, float] = {name: 1.0 for name in seed_names if name in self._nodes}
        queue: deque[tuple[str, int]] = deque((name, 0) for name in seed_names)
        edges: list[ToolEdge] = []

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

                # 거리 감쇠: 1 / (depth + 1)
                neighbor_score = edge.weight / (depth + 1)

                if neighbor not in visited:
                    visited.add(neighbor)
                    scores[neighbor] = neighbor_score
                    queue.append((neighbor, depth + 1))
                elif neighbor in scores:
                    # 더 높은 점수로 업데이트
                    scores[neighbor] = max(scores[neighbor], neighbor_score)

                edges.append(edge)

        return scores, edges

    @staticmethod
    def _wrrf_fuse(
        weighted_sources: list[tuple[dict[str, float], float]],
        k: int = 60,
    ) -> dict[str, float]:
        """Weighted Reciprocal Rank Fusion

        wRRF_score(d) = Σ(weight_i / (k + rank_i(d)))
        """
        fused: dict[str, float] = {}
        for scores, weight in weighted_sources:
            if not scores:
                continue
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            for rank, (name, _) in enumerate(ranked, start=1):
                fused[name] = fused.get(name, 0.0) + weight / (k + rank)
        return fused

    def _topological_sort(self, nodes: list[ToolNode], edges: list[ToolEdge]) -> list[ToolNode]:
        """엣지 관계에 따른 위상 정렬 (REQUIRES, PRECEDES 기반)"""
        name_set = {n.name for n in nodes}
        node_map = {n.name: n for n in nodes}

        order_edges = [
            e for e in edges
            if e.edge_type in (EdgeType.REQUIRES, EdgeType.PRECEDES)
            and e.source in name_set and e.target in name_set
        ]

        if not order_edges:
            return nodes

        in_degree: dict[str, int] = {n.name: 0 for n in nodes}
        adj: dict[str, list[str]] = {n.name: [] for n in nodes}

        for edge in order_edges:
            if edge.edge_type == EdgeType.REQUIRES:
                adj[edge.target].append(edge.source)
                in_degree[edge.source] += 1
            elif edge.edge_type == EdgeType.PRECEDES:
                adj[edge.source].append(edge.target)
                in_degree[edge.target] += 1

        queue = deque(name for name in in_degree if in_degree[name] == 0)
        sorted_names: list[str] = []

        while queue:
            current = queue.popleft()
            sorted_names.append(current)
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

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
        history_tools: list[str] = []
        try:
            from jinxus.memory.meta_store import get_meta_store
            meta = get_meta_store()
            patterns = await meta.find_similar_workflows(query, limit=3)

            if patterns:
                best = patterns[0]
                for tool_name in best["tool_sequence"]:
                    node = self._nodes.get(tool_name)
                    if node:
                        node.weight = min(node.weight + 0.3, 5.0)
                        history_tools.append(tool_name)
        except Exception:
            pass

        return self.retrieve(query, top_k=top_k, agent_name=agent_name, history=history_tools)

    # ── 영속화 ──

    def save(self, filepath: str) -> None:
        """그래프 상태를 JSON으로 저장 (학습된 가중치 포함)"""
        data = {
            "version": 2,
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
        }
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"ToolGraph saved: {filepath} ({len(self._nodes)} nodes, {len(self._edges)} edges)")

    def load_weights(self, filepath: str) -> bool:
        """저장된 가중치만 로드 (노드/엣지 구조는 유지, 가중치만 업데이트)"""
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") != 2:
                logger.warning(f"ToolGraph version mismatch, skipping weight load")
                return False

            # 노드 가중치 복원
            weight_map: dict[str, float] = {}
            for nd in data.get("nodes", []):
                weight_map[nd["name"]] = nd.get("weight", 1.0)

            updated = 0
            for name, node in self._nodes.items():
                if name in weight_map and weight_map[name] != 1.0:
                    node.weight = weight_map[name]
                    updated += 1

            # 엣지 가중치 복원
            edge_weight_map: dict[str, float] = {}
            for ed in data.get("edges", []):
                key = f"{ed['source']}→{ed['target']}"
                edge_weight_map[key] = ed.get("weight", 1.0)

            for edge in self._edges:
                key = f"{edge.source}→{edge.target}"
                if key in edge_weight_map and edge_weight_map[key] != 1.0:
                    edge.weight = edge_weight_map[key]
                    updated += 1

            if updated:
                logger.info(f"ToolGraph weights loaded: {updated} updates from {filepath}")
            return True

        except Exception as e:
            logger.warning(f"ToolGraph weight load failed: {e}")
            return False

    def get_node(self, name: str) -> Optional[ToolNode]:
        return self._nodes.get(name)

    def get_all_nodes(self) -> list[ToolNode]:
        return list(self._nodes.values())

    def get_all_edges(self) -> list[ToolEdge]:
        return list(self._edges)

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"name": n.name, "description": n.description, "category": n.category, "keywords": n.keywords, "weight": n.weight}
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

# 가중치 저장 경로
_WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tool_graph_weights.json")


def build_jinxus_tool_graph() -> ToolGraph:
    """JINXUS의 기존 도구 + MCP 도구를 그래프로 구축

    노드는 TOOL_REGISTRY에서 자동 추출하고,
    키워드/카테고리 등 그래프 전용 메타데이터는 수동 매핑으로 보완한다.
    시작 시 이전에 저장된 학습 가중치를 복원한다.
    """
    from jinxus.tools import TOOL_REGISTRY, register_tools

    if not TOOL_REGISTRY:
        register_tools()

    graph = ToolGraph()

    # ── 그래프 전용 메타데이터 ──
    _NODE_META: dict[str, dict] = {
        "code_executor": {
            "category": "development",
            "keywords": ["코드", "실행", "프로그래밍", "개발", "디버깅", "code", "execute", "run", "debug", "python", "스크립트"],
        },
        "web_searcher": {
            "category": "research",
            "keywords": ["검색", "웹", "찾기", "조사", "search", "web", "find", "research", "뉴스", "news", "tavily"],
        },
        "naver_searcher": {
            "category": "research",
            "keywords": ["네이버", "검색", "뉴스", "블로그", "지식인", "naver", "한국", "로컬"],
        },
        "weather": {
            "category": "research",
            "keywords": ["날씨", "기온", "온도", "비", "눈", "미세먼지", "weather", "temperature", "forecast", "서울"],
        },
        "file_manager": {
            "category": "filesystem",
            "keywords": ["파일", "읽기", "쓰기", "저장", "삭제", "file", "read", "write", "save", "delete", "디렉토리"],
        },
        "github_agent": {
            "category": "github",
            "keywords": ["깃허브", "GitHub", "레포", "PR", "커밋", "이슈", "브랜치",
                          "repo", "commit", "pull request", "issue", "branch", "push"],
        },
        "github_graphql": {
            "category": "github",
            "keywords": ["깃허브", "GitHub", "코드검색", "레포", "repo", "search_code", "graphql"],
        },
        "scheduler": {
            "category": "automation",
            "keywords": ["스케줄", "예약", "반복", "cron", "schedule", "recurring", "자동", "알림", "매일", "매주"],
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

    # ── 노드 등록 ──
    for tool_name, tool in TOOL_REGISTRY.items():
        meta = _NODE_META.get(tool_name, {})
        graph.add_node(ToolNode(
            name=tool.name,
            description=tool.description,
            category=meta.get("category", "general"),
            allowed_agents=list(tool.allowed_agents) if tool.allowed_agents else [],
            keywords=meta.get("keywords", []),
        ))

    # ── 엣지 등록 ──

    # GitHub 워크플로우
    graph.add_edge(ToolEdge("github_graphql", "github_agent", EdgeType.PRECEDES,
                            description="GraphQL로 조회 후 REST로 수정 작업"))
    graph.add_edge(ToolEdge("code_executor", "github_agent", EdgeType.PRECEDES,
                            description="코드 작성 후 GitHub에 커밋/PR"))
    graph.add_edge(ToolEdge("github_agent", "code_executor", EdgeType.REQUIRES,
                            weight=0.7, description="레포 정보가 코드 작업에 필요할 수 있음"))
    graph.add_edge(ToolEdge("github_agent", "github_graphql", EdgeType.SIMILAR_TO,
                            description="둘 다 GitHub 데이터 접근"))

    # 리서치 워크플로우
    graph.add_edge(ToolEdge("web_searcher", "code_executor", EdgeType.PRECEDES,
                            weight=0.8, description="조사 후 코드 작성"))
    graph.add_edge(ToolEdge("web_searcher", "naver_searcher", EdgeType.SIMILAR_TO,
                            description="둘 다 웹 검색 도구"))
    graph.add_edge(ToolEdge("naver_searcher", "weather", EdgeType.COMPLEMENTARY,
                            weight=0.6, description="네이버 검색과 날씨 보완"))

    # 파일 관련
    graph.add_edge(ToolEdge("code_executor", "file_manager", EdgeType.COMPLEMENTARY,
                            description="코드 실행과 파일 관리는 보완 관계"))
    graph.add_edge(ToolEdge("file_manager", "github_agent", EdgeType.PRECEDES,
                            weight=0.6, description="파일 작성 후 GitHub 커밋"))
    graph.add_edge(ToolEdge("web_searcher", "file_manager", EdgeType.PRECEDES,
                            weight=0.7, description="검색 결과를 파일로 저장"))

    # 시스템 관리
    graph.add_edge(ToolEdge("system_manager", "scheduler", EdgeType.COMPLEMENTARY,
                            description="시스템 관리와 스케줄 관리는 보완"))
    graph.add_edge(ToolEdge("hr_tool", "system_manager", EdgeType.COMPLEMENTARY,
                            description="에이전트 관리와 시스템 관리는 보완"))
    graph.add_edge(ToolEdge("hr_tool", "prompt_version_manager", EdgeType.PRECEDES,
                            weight=0.5, description="에이전트 생성 후 프롬프트 설정"))

    # 충돌 관계
    graph.add_edge(ToolEdge("github_agent", "github_graphql", EdgeType.CONFLICTS_WITH,
                            weight=0.3, description="같은 API rate limit 공유"))

    # ── 저장된 가중치 복원 ──
    graph.load_weights(_WEIGHTS_FILE)

    logger.info(f"ToolGraph built: {len(graph._nodes)} nodes, {len(graph._edges)} edges")
    return graph


def save_tool_graph() -> None:
    """현재 ToolGraph의 학습된 가중치를 저장"""
    global _tool_graph
    if _tool_graph:
        _tool_graph.save(_WEIGHTS_FILE)


# ── 싱글톤 ──

_tool_graph: Optional[ToolGraph] = None


def get_tool_graph() -> ToolGraph:
    """ToolGraph 싱글톤"""
    global _tool_graph
    if _tool_graph is None:
        _tool_graph = build_jinxus_tool_graph()
    return _tool_graph
