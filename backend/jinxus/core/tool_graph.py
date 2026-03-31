"""그래프 기반 도구 탐색 엔진

도구 간 관계를 그래프로 모델링하고, 사용자 쿼리에서
관련 도구 워크플로우를 자동으로 구성한다.

v4: BM25 + 그래프 BFS + 임베딩 시맨틱 + wRRF 퓨전 + 어노테이션 정렬
    + 대화 컨텍스트 인식 + 이름 기반 자동 의존성 탐지 + MCP 자동 메타데이터
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

# graph-tool-call 패턴: 어노테이션 및 의도 분류기
try:
    from jinxus.core.tool_annotation import (
        ToolAnnotations,
        infer_annotations_from_name,
        compute_annotation_scores,
    )
    from jinxus.core.tool_intent import classify_intent
    _ANNOTATION_AVAILABLE = True
except ImportError:
    _ANNOTATION_AVAILABLE = False
    # fallback stub — ToolNode의 타입 힌트용
    class ToolAnnotations:  # type: ignore[no-redef]
        pass

    def infer_annotations_from_name(name: str) -> None:  # type: ignore[misc]
        return None

    def compute_annotation_scores(*args, **kwargs) -> dict:  # type: ignore[misc]
        return {}

    def classify_intent(query: str):  # type: ignore[misc]
        return None

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
    annotations: Optional["ToolAnnotations"] = field(default=None, repr=False)  # graph-tool-call 어노테이션

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "allowed_agents": self.allowed_agents,
            "actions": self.actions,
            "keywords": self.keywords,
            "weight": self.weight,
        }
        if self.annotations is not None:
            d["annotations"] = self.annotations.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ToolNode":
        d = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "annotations"}
        node = cls(**d)
        if "annotations" in data and _ANNOTATION_AVAILABLE:
            node.annotations = ToolAnnotations.from_dict(data["annotations"])
        return node


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

    v4: BM25 + BFS 그래프 확장 + 임베딩 시맨틱 + wRRF 랭크 퓨전 + 어노테이션 정렬
    """

    # v4: wRRF 가중치 (임베딩 소스 추가)
    _WEIGHT_BM25 = 0.25
    _WEIGHT_GRAPH = 0.40
    _WEIGHT_EMBEDDING = 0.20  # v4 신규: 시맨틱 유사도
    _WEIGHT_ANNOTATION = 0.15
    _WRRF_K = 60

    # 쿼리 확장 매핑 — 한국어 키워드 → 관련 영어 키워드 추가
    _QUERY_EXPANSIONS: dict[str, str] = {
        '파일': 'file read write filesystem directory',
        '검색': 'search web brave google find query',
        '코드': 'code execute bash terminal python script',
        '이미지': 'image screenshot playwright analyze vision',
        '메모리': 'memory store save cache redis qdrant',
        '깃': 'git github commit push pull branch',
        '깃허브': 'git github commit push pull branch repo',
        '문서': 'document pdf read docx write generate',
        '브라우저': 'browser playwright navigate click screenshot',
        '데이터': 'data sqlite database query csv excel json',
        '웹': 'web fetch crawl scrape firecrawl url',
        '암호화폐': 'crypto price bitcoin ethereum coingecko',
        '코인': 'crypto price bitcoin ethereum coingecko',
        '도커': 'docker container image deploy',
        '날씨': 'weather forecast temperature rain',
        '뉴스': 'news rss feed article headline',
        '주식': 'stock price market ticker yahoo',
        '스크린샷': 'screenshot playwright browser capture',
        '노션': 'notion page database block',
        '슬랙': 'slack message channel send',
        '분석': 'analyze analysis data process statistics',
        '크롤링': 'crawl scrape firecrawl playwright web',
        '스케줄': 'schedule cron recurring timer job',
        '에이전트': 'agent hire fire spawn hr manage',
        '프롬프트': 'prompt version rollback sync',
    }

    def __init__(self):
        self._nodes: dict[str, ToolNode] = {}
        self._edges: list[ToolEdge] = []
        self._adj: dict[str, list[ToolEdge]] = {}
        self._bm25 = BM25Scorer()
        self._bm25_dirty = True  # 인덱스 재빌드 필요 여부
        # v4: 임베딩 기반 검색 소스
        self._embeddings: dict[str, list[float]] = {}  # tool_name -> embedding vector
        self._embedding_fn = None  # embedding 함수 (lazy init)

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

    def _expand_query(self, query: str) -> str:
        """쿼리 확장 — 한국어 키워드에 대응하는 영어 동의어/관련어 추가.

        BM25 검색 전 호출하여 한국어 쿼리의 영어 도구명 매칭률을 높인다.
        원본 쿼리를 변경하지 않고 뒤에 확장 키워드만 추가한다.
        """
        expanded = query
        for ko, en in self._QUERY_EXPANSIONS.items():
            if ko in query:
                expanded += ' ' + en
        return expanded

    def _ensure_bm25_index(self) -> None:
        """BM25 인덱스가 최신인지 확인하고 필요시 재빌드"""
        if self._bm25_dirty:
            self._bm25.index(self._nodes)
            self._bm25_dirty = False

    def _ensure_embeddings(self) -> None:
        """도구 설명의 임베딩 벡터를 미리 계산 (lazy, 한 번만)"""
        if self._embeddings or not self._nodes:
            return
        try:
            if self._embedding_fn is None:
                from jinxus.config import get_settings
                from openai import OpenAI
                settings = get_settings()
                api_key = settings.openai_api_key or settings.gpt_emb_api_key
                if not api_key:
                    logger.debug("[ToolGraph] OpenAI API 키 없음 — 임베딩 검색 비활성화")
                    return
                client = OpenAI(api_key=api_key)
                model = settings.embedding_model

                def embed_fn(text: str) -> list[float]:
                    resp = client.embeddings.create(model=model, input=text)
                    return resp.data[0].embedding

                self._embedding_fn = embed_fn

            # 모든 도구 설명을 배치 임베딩
            texts = []
            names = []
            for name, node in self._nodes.items():
                text = f"{node.name}: {node.description}. Keywords: {', '.join(node.keywords[:5])}"
                texts.append(text)
                names.append(name)

            if not texts:
                return

            # 배치로 임베딩 생성 (최대 2048개씩)
            from jinxus.config import get_settings
            from openai import OpenAI
            settings = get_settings()
            api_key = settings.openai_api_key or settings.gpt_emb_api_key
            client = OpenAI(api_key=api_key)
            model = settings.embedding_model

            batch_size = 100
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                batch_names = names[i:i+batch_size]
                resp = client.embeddings.create(model=model, input=batch_texts)
                for j, emb_data in enumerate(resp.data):
                    self._embeddings[batch_names[j]] = emb_data.embedding

            logger.info(f"[ToolGraph] 임베딩 {len(self._embeddings)}개 생성 완료")
        except Exception as e:
            logger.warning(f"[ToolGraph] 임베딩 생성 실패 (BM25+그래프로 fallback): {e}")

    def _embedding_search(self, query: str, top_k: int = 20) -> dict[str, float]:
        """쿼리 임베딩과 도구 임베딩 간 코사인 유사도 계산"""
        if not self._embeddings or not self._embedding_fn:
            return {}
        try:
            query_vec = self._embedding_fn(query)

            # 코사인 유사도 계산 (numpy 없이)
            scores: dict[str, float] = {}
            for name, tool_vec in self._embeddings.items():
                dot = sum(a * b for a, b in zip(query_vec, tool_vec))
                norm_q = sum(a * a for a in query_vec) ** 0.5
                norm_t = sum(b * b for b in tool_vec) ** 0.5
                if norm_q > 0 and norm_t > 0:
                    sim = dot / (norm_q * norm_t)
                    if sim > 0.1:  # 노이즈 필터
                        scores[name] = sim

            # 상위 top_k만 반환
            if len(scores) > top_k:
                sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
                scores = dict(sorted_items)

            return scores
        except Exception as e:
            logger.debug(f"[ToolGraph] 임베딩 검색 실패: {e}")
            return {}

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
        3. 어노테이션-의도 정렬 점수 (graph-tool-call 패턴)
        4. wRRF로 세 소스 랭크 퓨전
        5. history 디모션 (최근 사용 도구 점수 감쇠)
        6. 위상 정렬로 실행 순서 결정
        """
        self._ensure_bm25_index()

        # ── 1단계: BM25 점수 (쿼리 확장 적용) ──
        expanded_query = self._expand_query(query)
        bm25_scores = self._bm25.score(expanded_query)

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

        # ── 2.5단계: 임베딩 기반 시맨틱 검색 (v4) ──
        embedding_scores: dict[str, float] = {}
        self._ensure_embeddings()
        if self._embeddings:
            embedding_scores = self._embedding_search(query, top_k=20)
            # 에이전트 권한 필터
            if agent_name:
                embedding_scores = {
                    name: score for name, score in embedding_scores.items()
                    if not self._nodes.get(name, ToolNode("", "")).allowed_agents
                    or agent_name in self._nodes.get(name, ToolNode("", "")).allowed_agents
                }

        # ── 3단계: 어노테이션-의도 정렬 점수 (graph-tool-call 패턴) ──
        annotation_scores: dict[str, float] = {}
        if _ANNOTATION_AVAILABLE:
            try:
                intent = classify_intent(query)
                if not intent.is_neutral:
                    tool_annotations = {
                        name: node.annotations
                        for name, node in self._nodes.items()
                    }
                    annotation_scores = compute_annotation_scores(intent, tool_annotations)
                    # [0,1] → wRRF용 점수로 정규화 (0.5 중립 제외)
                    annotation_scores = {
                        k: v for k, v in annotation_scores.items() if v != 0.5
                    }
            except Exception as e:
                logger.debug(f"[ToolGraph] 어노테이션 점수 계산 실패 (무시): {e}")

        # ── 4단계: wRRF 퓨전 ──
        fusion_sources: list[tuple[dict[str, float], float]] = [
            (bm25_scores, self._WEIGHT_BM25),
            (graph_scores, self._WEIGHT_GRAPH),
        ]
        if embedding_scores:
            fusion_sources.append((embedding_scores, self._WEIGHT_EMBEDDING))
        if annotation_scores:
            fusion_sources.append((annotation_scores, self._WEIGHT_ANNOTATION))

        final_scores = self._wrrf_fuse(fusion_sources)

        # BM25에만 있는 도구도 포함 (seed 노드)
        for name, score in bm25_scores.items():
            if name not in final_scores:
                final_scores[name] = score * self._WEIGHT_BM25 / (self._WRRF_K + 1)

        # ── 5단계: history 디모션 + 다음 단계 부스트 (v4) ──
        if history:
            for tool_name in history:
                if tool_name in final_scores:
                    final_scores[tool_name] *= 0.8  # 이미 사용한 도구 20% 감쇠

                # v4: 이전 도구의 PRECEDES 이웃에 보너스 (다음 단계 도구 부스트)
                for edge in self._adj.get(tool_name, []):
                    if edge.edge_type == EdgeType.PRECEDES and edge.target in final_scores:
                        final_scores[edge.target] *= 1.3  # 30% 부스트

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
        except Exception as e:
            logger.warning(f"[ToolGraph] 메타 스토어 히스토리 조회 실패, 히스토리 없이 진행: {e}")

        return self.retrieve(query, top_k=top_k, agent_name=agent_name, history=history_tools)

    async def retrieve_with_context(
        self,
        query: str,
        conversation_history: list[dict],
        top_k: int = 5,
        agent_name: Optional[str] = None,
    ) -> Workflow:
        """대화 컨텍스트를 고려한 도구 탐색 (v4)

        "그거 취소해줘" 같은 모호한 쿼리를 이전 대화에서 해석하여
        구체적인 도구 검색 쿼리로 확장한다.

        Args:
            query: 현재 쿼리
            conversation_history: 이전 대화 히스토리 [{role, content}, ...]
            top_k: 반환할 도구 수
            agent_name: 에이전트 이름 (권한 필터)
        """
        # 1. 최근 대화에서 도구 관련 컨텍스트 추출
        context_keywords = self._extract_context_keywords(conversation_history)

        # 2. 쿼리에 대명사/모호한 참조가 있으면 컨텍스트로 보강
        enriched_query = query
        if context_keywords and self._is_ambiguous_query(query):
            enriched_query = f"{query} {' '.join(context_keywords)}"
            logger.info(f"[ToolGraph] 쿼리 컨텍스트 보강: '{query}' → '{enriched_query}'")

        # 3. 최근 사용 도구를 히스토리로 전달 (디모션)
        recent_tools = self._extract_recent_tools(conversation_history)

        return self.retrieve(
            enriched_query, top_k=top_k, agent_name=agent_name, history=recent_tools
        )

    def _extract_context_keywords(self, history: list[dict]) -> list[str]:
        """대화 히스토리에서 도구 관련 키워드 추출"""
        keywords = []
        # 최근 5개 메시지만 (너무 오래된 것은 노이즈)
        recent = history[-5:] if len(history) > 5 else history

        for msg in recent:
            content = msg.get("content", "")
            if not content:
                continue
            # 도구/작업 관련 명사 추출 (한국어+영어)
            for ko, en in self._QUERY_EXPANSIONS.items():
                if ko in content:
                    keywords.extend(en.split()[:2])  # 상위 2개만
            # 영어 키워드 추출
            en_words = re.findall(r'[a-z]{3,}', content.lower())
            for w in en_words:
                if w in _PROTECTED_TERMS:
                    keywords.append(w)

        return list(set(keywords))[:10]  # 최대 10개

    def _is_ambiguous_query(self, query: str) -> bool:
        """쿼리가 모호한지 판별 (대명사, 짧은 참조 등)"""
        ambiguous_markers = {
            "그거", "그것", "이거", "이것", "저거", "저것",
            "아까", "방금", "위에", "그", "이", "저",
            "다시", "또", "계속", "마저", "나머지",
            "it", "that", "this", "same", "again",
        }
        tokens = set(query.lower().split())
        return bool(tokens & ambiguous_markers) or len(query) < 10

    def _extract_recent_tools(self, history: list[dict]) -> list[str]:
        """대화 히스토리에서 최근 사용된 도구명 추출"""
        tools = []
        for msg in reversed(history[-10:]):
            content = msg.get("content", "")
            # 도구명 패턴 매칭 (도구명은 snake_case 또는 mcp:xxx:xxx 형태)
            found = re.findall(r'(?:mcp:[a-z_-]+:[a-z_]+|[a-z]+_[a-z_]+)', content.lower())
            for f in found:
                if f in self._nodes and f not in tools:
                    tools.append(f)
        return tools[:5]

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


def _resolve_annotation_for_tool(tool_name: str) -> Optional["ToolAnnotations"]:
    """도구 이름에서 어노테이션을 추론한다.

    MCP 동적 로드 도구는 이름이 ``mcp:서버:실제도구명`` 형식이므로,
    맨 앞의 ``mcp:서버:`` 접두어를 제거하고 실제 도구명으로 추론한다.

    예)
        "mcp:brave-search:brave_web_search" → "brave_web_search" → read_only=True
        "mcp:filesystem:list_directory"     → "list_directory"    → read_only=True
        "mcp:github:create_issue"           → "create_issue"      → read_only=False
        "code_executor"                     → "code_executor"     → open_world=True

    _ANNOTATION_AVAILABLE 이 False 인 환경에서는 None 을 반환한다 (graceful fallback).
    """
    if not _ANNOTATION_AVAILABLE:
        return None
    try:
        # MCP 도구: "mcp:<server>:<tool_name>" → 마지막 세그먼트만 사용
        if tool_name.startswith("mcp:"):
            parts = tool_name.split(":")
            # parts = ["mcp", "server", "tool_name"] — 최소 3개 필요
            if len(parts) >= 3:
                actual_tool_name = parts[-1]  # 실제 도구 이름만 추출
                return infer_annotations_from_name(actual_tool_name)
            # 세그먼트 부족 시 그대로 시도
        return infer_annotations_from_name(tool_name)
    except Exception:
        return None


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

        # graph-tool-call 패턴: 어노테이션 성정 우선순위
        # 1순위: MCPToolAdapter 에 이미 주입된 어노테이션 (등록 시점에 _annotation_hook 적용됨)
        # 2순위: 없으면 이름 기반 작업 (_resolve_annotation_for_tool)
        adapter_annotations = getattr(tool, "annotations", None)
        if adapter_annotations is not None:
            # 어댑터에 이미 어노테이션 있음 → 재추론 불필요
            auto_annotations = adapter_annotations
        else:
            # MCP 동적 로드 도구(mcp:server:tool)는 _resolve_annotation_for_tool() 로
            # 실제 도구명 세그먼트만 추출하여 추론 — 기존 정적 도구와 동일한 파이프라인 적용
            auto_annotations = _resolve_annotation_for_tool(tool_name)

        # MCP 도구: 서버명을 카테고리로 자동 설정 (메타 없는 경우)
        if not meta and tool_name.startswith("mcp:"):
            parts = tool_name.split(":")
            mcp_category = f"mcp:{parts[1]}" if len(parts) >= 2 else "mcp"
            meta = {"category": mcp_category, "keywords": []}

        graph.add_node(ToolNode(
            name=tool.name,
            description=tool.description,
            category=meta.get("category", "general"),
            allowed_agents=list(tool.allowed_agents) if tool.allowed_agents else [],
            keywords=meta.get("keywords", []),
            annotations=auto_annotations,
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

    # ── 이름 기반 자동 의존성 탐지 (graph-tool-call 패턴) ──
    # 도구 이름의 접두어 패턴으로 CRUD 관계 자동 탐지
    _auto_detect_name_based_edges(graph)

    # ── 저장된 가중치 복원 ──
    graph.load_weights(_WEIGHTS_FILE)

    logger.info(f"ToolGraph built: {len(graph._nodes)} nodes, {len(graph._edges)} edges")
    return graph


def _auto_detect_name_based_edges(graph: ToolGraph) -> None:
    """graph-tool-call dependency.py 패턴: 도구 이름 기반 CRUD 자동 의존성 탐지.

    동일 리소스를 다루는 도구 식별 후 CRUD 순서 기반으로
    PRECEDES / REQUIRES 엓지를 자동으로 추가한다.

    - list_*/get_* 시리즈는 SIMILAR_TO
    - create_*/list_* 시리즈는 PRECEDES (create 머저, list로 확인)
    - delete_* 도구는 대응 get_* 에 REQUIRES
    """
    if not _ANNOTATION_AVAILABLE:
        return

    import re as _re

    # CRUD 동사 접두어 순서 (graph-tool-call _CRUD_ORDER 패턴)
    _CRUD_ORDER = {"create": 0, "add": 0, "post": 0, "list": 1, "get": 1,
                   "fetch": 1, "search": 1, "update": 2, "edit": 2, "set": 2,
                   "delete": 3, "remove": 3, "clear": 3}

    def _split_name(name: str) -> tuple[str, str]:
        """(동사, 리소스) 분리. 'github_agent' 스타일 스킵."""
        n = _re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()
        parts = [p for p in n.replace("-", "_").split("_") if p]
        if not parts:
            return "", name
        verb = parts[0]
        resource = "_".join(parts[1:]) if len(parts) > 1 else ""
        return verb, resource

    # 제외할 이미 명시된 엓지 파어
    existing_pairs: set[tuple[str, str]] = {
        (e.source, e.target) for e in graph.get_all_edges()
    }

    nodes = graph.get_all_nodes()
    added = 0

    for i, a in enumerate(nodes):
        verb_a, res_a = _split_name(a.name)
        if not res_a or verb_a not in _CRUD_ORDER:
            continue
        order_a = _CRUD_ORDER[verb_a]
        annot_a = infer_annotations_from_name(a.name)

        for b in nodes[i + 1:]:
            if a.name == b.name:
                continue
            verb_b, res_b = _split_name(b.name)
            if not res_b or verb_b not in _CRUD_ORDER:
                continue

            # 동일 리소스인 경우만 적용
            if res_a != res_b:
                continue

            order_b = _CRUD_ORDER[verb_b]
            annot_b = infer_annotations_from_name(b.name)

            # list_X ⇔ get_X 두 개는 SIMILAR_TO
            if annot_a and annot_b and annot_a.read_only_hint and annot_b.read_only_hint:
                pair = (a.name, b.name)
                if pair not in existing_pairs:
                    graph.add_edge(ToolEdge(
                        source=a.name, target=b.name,
                        edge_type=EdgeType.SIMILAR_TO,
                        weight=0.85,
                        description=f"자동 탐지: 동일 리소스 읽기 도구",
                    ))
                    existing_pairs.add(pair)
                    added += 1
                continue

            # CRUD 순서대로 PRECEDES (a 먹저 b 나중)
            if order_a < order_b:
                pair = (a.name, b.name)
                if pair not in existing_pairs:
                    graph.add_edge(ToolEdge(
                        source=a.name, target=b.name,
                        edge_type=EdgeType.PRECEDES,
                        weight=0.75,
                        description=f"자동 탐지: CRUD 순서 ({verb_a}→{verb_b})",
                    ))
                    existing_pairs.add(pair)
                    added += 1

    if added:
        logger.info(f"[ToolGraph] 이름 기반 자동 엳지 {added}개 추가")


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
