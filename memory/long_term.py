"""Qdrant 기반 장기기억 시스템 - 에이전트별 컬렉션 분리"""
import uuid
from typing import Optional
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from openai import OpenAI

from config import get_settings


# 에이전트별 컬렉션 이름
AGENT_COLLECTIONS = {
    "JINXUS_CORE": "jinxus_core_memory",
    "JX_CODER": "jinxus_coder_memory",
    "JX_RESEARCHER": "jinxus_researcher_memory",
    "JX_WRITER": "jinxus_writer_memory",
    "JX_ANALYST": "jinxus_analyst_memory",
    "JX_OPS": "jinxus_ops_memory",
}

VECTOR_SIZE = 1536  # text-embedding-3-small 차원


class LongTermMemory:
    """Qdrant 기반 에이전트별 장기기억 관리"""

    def __init__(self):
        settings = get_settings()
        self._client: Optional[QdrantClient] = None
        self._openai: Optional[OpenAI] = None
        self._host = settings.qdrant_host
        self._port = settings.qdrant_port
        self._openai_key = settings.openai_api_key or settings.gpt_emb_api_key

    def connect(self) -> None:
        """Qdrant 및 OpenAI 연결"""
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        if self._openai is None and self._openai_key:
            self._openai = OpenAI(api_key=self._openai_key)

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        if not self._client:
            return False
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def ensure_collections(self) -> None:
        """모든 에이전트 컬렉션 생성 (없으면)"""
        self.connect()

        existing = {c.name for c in self._client.get_collections().collections}

        for agent_name, collection_name in AGENT_COLLECTIONS.items():
            if collection_name not in existing:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=VECTOR_SIZE, distance=Distance.COSINE
                    ),
                )

    def _get_embedding(self, text: str) -> list[float]:
        """텍스트 임베딩 생성"""
        if not self._openai:
            raise RuntimeError("OpenAI client not initialized. Check OPENAI_API_KEY.")

        response = self._openai.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding

    def _collection_for_agent(self, agent_name: str) -> str:
        """에이전트 이름으로 컬렉션 이름 반환"""
        return AGENT_COLLECTIONS.get(agent_name, "jinxus_core_memory")

    def save(
        self,
        agent_name: str,
        task_id: str,
        instruction: str,
        summary: str,
        outcome: str,
        success_score: float,
        key_learnings: str,
        importance_score: float,
        prompt_version: str,
    ) -> str:
        """작업 결과를 에이전트 컬렉션에 저장"""
        self.connect()
        collection = self._collection_for_agent(agent_name)

        # 임베딩 생성 (summary 기반)
        embedding = self._get_embedding(summary)

        point_id = str(uuid.uuid4())
        payload = {
            "task_id": task_id,
            "agent_name": agent_name,
            "instruction": instruction,
            "summary": summary,
            "outcome": outcome,
            "success_score": success_score,
            "key_learnings": key_learnings,
            "importance_score": importance_score,
            "prompt_version": prompt_version,
            "created_at": datetime.utcnow().isoformat(),
        }

        self._client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
        )

        return point_id

    def search(
        self, agent_name: str, query: str, limit: int = 5
    ) -> list[dict]:
        """에이전트 컬렉션에서 유사 경험 검색"""
        self.connect()
        collection = self._collection_for_agent(agent_name)

        embedding = self._get_embedding(query)

        results = self._client.search(
            collection_name=collection, query_vector=embedding, limit=limit
        )

        return [
            {**hit.payload, "similarity_score": hit.score}
            for hit in results
        ]

    def search_all(self, query: str, limit: int = 5) -> list[dict]:
        """모든 컬렉션에서 검색 (JINXUS_CORE용)"""
        self.connect()
        all_results = []

        embedding = self._get_embedding(query)

        for collection in AGENT_COLLECTIONS.values():
            try:
                results = self._client.search(
                    collection_name=collection, query_vector=embedding, limit=limit
                )
                all_results.extend(
                    [{**hit.payload, "similarity_score": hit.score} for hit in results]
                )
            except Exception:
                continue

        # 유사도 순 정렬 후 상위 limit개 반환
        all_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return all_results[:limit]

    def delete_by_task_id(self, agent_name: str, task_id: str) -> bool:
        """특정 작업 기억 삭제"""
        self.connect()
        collection = self._collection_for_agent(agent_name)

        try:
            self._client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[FieldCondition(key="task_id", match=MatchValue(value=task_id))]
                ),
            )
            return True
        except Exception:
            return False

    def prune_low_quality(
        self, agent_name: str, importance_threshold: float = 0.3, max_days: int = 30
    ) -> int:
        """저품질 기억 정리"""
        self.connect()
        collection = self._collection_for_agent(agent_name)

        # Qdrant에서 importance_score가 낮은 포인트 조회 및 삭제
        # 실제 구현에서는 scroll API와 필터 조합 사용
        deleted_count = 0

        # TODO: 실제 pruning 로직 구현
        # - importance_score < threshold
        # - created_at > max_days ago

        return deleted_count

    def get_collection_stats(self, agent_name: str) -> dict:
        """컬렉션 통계 조회"""
        self.connect()
        collection = self._collection_for_agent(agent_name)

        try:
            info = self._client.get_collection(collection)
            return {
                "collection": collection,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
            }
        except Exception:
            return {"collection": collection, "points_count": 0, "vectors_count": 0}


# 싱글톤 인스턴스
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """장기기억 싱글톤 반환"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
