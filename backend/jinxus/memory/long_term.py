"""Qdrant 기반 장기기억 시스템 - 에이전트별 컬렉션 분리

v2.8.0: 메모리 최적화
- 시간 감쇠 기반 자동 정리 (prune_with_time_decay)
- 중복 메모리 제거 (deduplicate_memories)
- 컨텍스트 주입 예산 제한 (search with budget)
"""
import logging
import uuid
from typing import Optional
from datetime import datetime, timedelta

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

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


def _get_collection_name(agent_name: str) -> str:
    """에이전트 이름으로 컬렉션 이름 동적 생성"""
    return f"jinxus_{agent_name.lower()}_memory"


# 기본 에이전트 목록 (ensure_collections / search_all / optimize_all 용)
_DEFAULT_AGENTS = [
    "JINXUS_CORE", "JX_CODER", "JX_RESEARCHER", "JX_WRITER",
    "JX_ANALYST", "JX_OPS", "JS_PERSONA", "JX_MARKETING",
    "JX_PRODUCT", "JX_CTO", "JX_FRONTEND", "JX_BACKEND",
    "JX_INFRA", "JX_REVIEWER", "JX_TESTER",
    "JX_WEB_SEARCHER", "JX_DEEP_READER", "JX_FACT_CHECKER",
]

# settings에서 임베딩 차원 가져오기
VECTOR_SIZE = get_settings().embedding_dimensions


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
        """Qdrant 및 OpenAI 연결 (연결 상태 검증 포함)"""
        if self._client is None:
            try:
                self._client = QdrantClient(host=self._host, port=self._port)
                # 연결 검증
                self._client.get_collections()
                logger.info(f"[LongTermMemory] Qdrant 연결 성공: {self._host}:{self._port}")
            except Exception as e:
                logger.error(f"[LongTermMemory] Qdrant 연결 실패: {self._host}:{self._port} — {e}")
                self._client = None
                raise

        if self._openai is None and self._openai_key:
            self._openai = OpenAI(api_key=self._openai_key)
            logger.info("[LongTermMemory] OpenAI 임베딩 클라이언트 초기화 완료")
        elif not self._openai_key:
            logger.warning("[LongTermMemory] OpenAI API 키 미설정 — 임베딩 생성 불가")

    def is_connected(self) -> bool:
        """연결 상태 확인 (실패 원인 로깅)"""
        if not self._client:
            logger.debug("[LongTermMemory] Qdrant 클라이언트 미초기화")
            return False
        try:
            self._client.get_collections()
            return True
        except Exception as e:
            logger.warning(f"[LongTermMemory] Qdrant 연결 확인 실패: {e}")
            return False

    def ensure_collections(self) -> None:
        """모든 에이전트 컬렉션 생성 (없으면)"""
        self.connect()

        existing = {c.name for c in self._client.get_collections().collections}

        for agent_name in _DEFAULT_AGENTS:
            collection_name = _get_collection_name(agent_name)
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

        settings = get_settings()
        response = self._openai.embeddings.create(
            model=settings.embedding_model, input=text
        )
        return response.data[0].embedding

    def _collection_for_agent(self, agent_name: str) -> str:
        """에이전트 이름으로 컬렉션 이름 반환"""
        return _get_collection_name(agent_name)

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
            "created_at": datetime.now().isoformat(),
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

        for collection in [_get_collection_name(a) for a in _DEFAULT_AGENTS]:
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
        """저품질 기억 정리

        조건:
        1. importance_score < threshold
        2. created_at이 max_days보다 오래됨

        Args:
            agent_name: 에이전트 이름
            importance_threshold: 이 점수 미만은 삭제 대상
            max_days: 이 일수보다 오래된 것만 삭제

        Returns:
            삭제된 포인트 수
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)
        deleted_count = 0

        try:
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=max_days)).isoformat()

            # scroll API로 모든 포인트 조회 후 조건에 맞는 것 삭제
            offset = None
            points_to_delete = []

            while True:
                result = self._client.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                points, next_offset = result

                if not points:
                    break

                for point in points:
                    payload = point.payload
                    importance = payload.get("importance_score", 1.0)
                    created_at = payload.get("created_at", "")

                    # 조건 1: 중요도 낮음 + 오래됨
                    if importance < importance_threshold and created_at < cutoff_date:
                        points_to_delete.append(point.id)

                    # 조건 2: 성공한 단순 작업 + 매우 낮은 중요도
                    elif importance < 0.15 and payload.get("outcome") == "success":
                        points_to_delete.append(point.id)

                if next_offset is None:
                    break
                offset = next_offset

            # 일괄 삭제
            if points_to_delete:
                self._client.delete(
                    collection_name=collection,
                    points_selector=points_to_delete,
                )
                deleted_count = len(points_to_delete)

        except Exception as e:
            print(f"Pruning failed for {collection}: {e}")

        return deleted_count

    def get_failure_patterns(self, agent_name: str, limit: int = 10) -> list[dict]:
        """에이전트의 실패 패턴 분석용 데이터 조회

        JinxLoop이 프롬프트 개선 시 사용
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)

        try:
            results = self._client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="outcome", match=MatchValue(value="failure"))]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            points, _ = results
            return [
                {
                    "task_id": p.payload.get("task_id"),
                    "instruction": p.payload.get("instruction"),
                    "key_learnings": p.payload.get("key_learnings"),
                    "success_score": p.payload.get("success_score"),
                    "created_at": p.payload.get("created_at"),
                }
                for p in points
            ]
        except Exception:
            return []

    def get_success_patterns(self, agent_name: str, min_score: float = 0.8, limit: int = 10) -> list[dict]:
        """에이전트의 성공 패턴 분석용 데이터 조회

        좋은 패턴을 학습하는 데 사용
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)

        try:
            results = self._client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="outcome", match=MatchValue(value="success"))]
                ),
                limit=limit * 2,  # 필터링 위해 더 많이 가져옴
                with_payload=True,
                with_vectors=False,
            )

            points, _ = results

            # success_score 기준 필터링 및 정렬
            filtered = [
                {
                    "task_id": p.payload.get("task_id"),
                    "instruction": p.payload.get("instruction"),
                    "summary": p.payload.get("summary"),
                    "key_learnings": p.payload.get("key_learnings"),
                    "success_score": p.payload.get("success_score"),
                }
                for p in points
                if p.payload.get("success_score", 0) >= min_score
            ]

            # 점수 높은 순 정렬
            filtered.sort(key=lambda x: x["success_score"], reverse=True)
            return filtered[:limit]

        except Exception:
            return []

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

    # ===== 메모리 최적화 (v2.8.0) =====

    def prune_with_time_decay(
        self,
        agent_name: str,
        min_score: float = 0.1,
        halflife_days: int = 30,
        pin_threshold: float = 0.8,
    ) -> int:
        """시간 감쇠 기반 메모리 정리

        Geny 패턴 참고: final_score = importance * 0.5^(days/halflife)
        final_score < min_score 이고 importance < pin_threshold 인 메모리 삭제.

        Args:
            agent_name: 에이전트 이름
            min_score: 감쇠 적용 후 최소 점수 임계값
            halflife_days: 반감기 (일)
            pin_threshold: 이 이상의 importance는 삭제 면제 (고정)

        Returns:
            삭제된 포인트 수
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)
        now = datetime.now()
        points_to_delete = []

        try:
            offset = None
            while True:
                result = self._client.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result

                if not points:
                    break

                for point in points:
                    payload = point.payload
                    importance = payload.get("importance_score", 0.5)

                    # 고정 메모리는 삭제 면제
                    if importance >= pin_threshold:
                        continue

                    # 생성일 파싱
                    created_str = payload.get("created_at", "")
                    if not created_str:
                        continue

                    try:
                        created_at = datetime.fromisoformat(created_str)
                    except (ValueError, TypeError):
                        continue

                    days_old = (now - created_at).total_seconds() / 86400
                    time_decay = 0.5 ** (days_old / halflife_days)
                    final_score = importance * time_decay

                    if final_score < min_score:
                        points_to_delete.append(point.id)

                if next_offset is None:
                    break
                offset = next_offset

            # 일괄 삭제
            if points_to_delete:
                self._client.delete(
                    collection_name=collection,
                    points_selector=points_to_delete,
                )

            logger.info(
                f"[MemoryOptim] prune_with_time_decay: {collection} — "
                f"{len(points_to_delete)}개 삭제 (halflife={halflife_days}일, min_score={min_score})"
            )

        except Exception as e:
            logger.error(f"[MemoryOptim] prune_with_time_decay 실패 ({collection}): {e}")

        return len(points_to_delete)

    def deduplicate_memories(
        self,
        agent_name: str,
        similarity_threshold: float = 0.95,
    ) -> int:
        """중복 메모리 제거

        각 메모리에 대해 유사도 검색 수행, 임계값 이상이면 중복으로 판정.
        importance_score가 낮은 쪽을 삭제.

        Args:
            agent_name: 에이전트 이름
            similarity_threshold: 코사인 유사도 임계값

        Returns:
            삭제된 포인트 수
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)
        deleted_ids: set[str] = set()

        try:
            # 모든 포인트를 벡터 포함해서 조회
            all_points = []
            offset = None
            while True:
                result = self._client.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                points, next_offset = result

                if not points:
                    break

                all_points.extend(points)

                if next_offset is None:
                    break
                offset = next_offset

            if len(all_points) < 2:
                return 0

            # 각 포인트에 대해 유사한 것 찾기
            for point in all_points:
                if point.id in deleted_ids:
                    continue

                # 해당 포인트의 벡터로 유사 검색
                vector = point.vector
                if not vector:
                    continue

                results = self._client.search(
                    collection_name=collection,
                    query_vector=vector,
                    limit=10,  # 상위 10개만 확인
                    score_threshold=similarity_threshold,
                )

                for hit in results:
                    # 자기 자신은 스킵
                    if hit.id == point.id:
                        continue
                    # 이미 삭제 예정이면 스킵
                    if hit.id in deleted_ids:
                        continue

                    # importance 비교: 낮은 쪽 삭제
                    point_importance = point.payload.get("importance_score", 0.5)
                    hit_importance = hit.payload.get("importance_score", 0.5)

                    if hit_importance <= point_importance:
                        deleted_ids.add(hit.id)
                    else:
                        deleted_ids.add(point.id)
                        break  # 자신이 삭제 대상이면 더 이상 비교 불필요

            # 일괄 삭제
            if deleted_ids:
                self._client.delete(
                    collection_name=collection,
                    points_selector=list(deleted_ids),
                )

            logger.info(
                f"[MemoryOptim] deduplicate_memories: {collection} — "
                f"{len(deleted_ids)}개 중복 삭제 (threshold={similarity_threshold})"
            )

        except Exception as e:
            logger.error(f"[MemoryOptim] deduplicate_memories 실패 ({collection}): {e}")

        return len(deleted_ids)

    def search_with_budget(
        self, agent_name: str, query: str, limit: int = 5, max_chars: int = 8000
    ) -> list[dict]:
        """컨텍스트 예산 제한 검색

        유사도 검색 후 max_chars까지만 결과를 반환.
        예산 초과 시 나머지는 잘림.

        Args:
            agent_name: 에이전트 이름
            query: 검색 쿼리
            limit: 최대 검색 결과 수
            max_chars: 컨텍스트 최대 글자수

        Returns:
            예산 내 결과 리스트
        """
        results = self.search(agent_name, query, limit)
        budgeted = []
        total_chars = 0

        for r in results:
            # 각 결과의 주요 텍스트 길이 계산
            entry_chars = len(r.get("summary", "")) + len(r.get("key_learnings", ""))
            if total_chars + entry_chars > max_chars and budgeted:
                break
            budgeted.append(r)
            total_chars += entry_chars

        return budgeted

    def search_all_with_budget(
        self, query: str, limit: int = 5, max_chars: int = 8000
    ) -> list[dict]:
        """모든 컬렉션에서 예산 제한 검색"""
        results = self.search_all(query, limit)
        budgeted = []
        total_chars = 0

        for r in results:
            entry_chars = len(r.get("summary", "")) + len(r.get("key_learnings", ""))
            if total_chars + entry_chars > max_chars and budgeted:
                break
            budgeted.append(r)
            total_chars += entry_chars

        return budgeted

    def enforce_collection_cap(
        self,
        agent_name: str,
        max_points: int = 10000,
    ) -> int:
        """컬렉션 포인트 수 상한 강제 — 초과 시 가장 오래되고 중요도 낮은 포인트 삭제

        Args:
            agent_name: 에이전트 이름
            max_points: 컬렉션당 최대 포인트 수

        Returns:
            삭제된 포인트 수
        """
        self.connect()
        collection = self._collection_for_agent(agent_name)

        try:
            info = self._client.get_collection(collection)
            current = info.points_count
            if current <= max_points:
                return 0

            excess = current - max_points
            # importance 낮은 순 + 오래된 순으로 삭제 대상 수집
            candidates = []
            offset = None
            while True:
                result = self._client.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result
                if not points:
                    break
                for p in points:
                    importance = p.payload.get("importance_score", 0.5)
                    created = p.payload.get("created_at", "")
                    candidates.append((p.id, importance, created))
                if next_offset is None:
                    break
                offset = next_offset

            # importance 오름차순, 생성일 오름차순 (낮고 오래된 것 우선 삭제)
            candidates.sort(key=lambda x: (x[1], x[2]))
            to_delete = [c[0] for c in candidates[:excess]]

            if to_delete:
                self._client.delete(
                    collection_name=collection,
                    points_selector=to_delete,
                )

            logger.info(
                f"[MemoryOptim] enforce_cap: {collection} — "
                f"{len(to_delete)}개 삭제 ({current} → {current - len(to_delete)}, cap={max_points})"
            )
            return len(to_delete)

        except Exception as e:
            logger.error(f"[MemoryOptim] enforce_cap 실패 ({collection}): {e}")
            return 0

    def optimize_all_collections(self) -> dict:
        """모든 컬렉션에 대해 사이즈 가드 + 정리 + 중복 제거 실행

        Returns:
            {agent_name: {"pruned": N, "deduped": M, "capped": K}} 형태의 결과
        """
        settings = get_settings()
        results = {}

        for agent_name in _DEFAULT_AGENTS:
            capped = self.enforce_collection_cap(
                agent_name=agent_name,
                max_points=getattr(settings, "memory_max_points_per_collection", 10000),
            )
            pruned = self.prune_with_time_decay(
                agent_name=agent_name,
                min_score=settings.memory_prune_min_score,
                halflife_days=settings.memory_prune_halflife_days,
            )
            deduped = self.deduplicate_memories(
                agent_name=agent_name,
                similarity_threshold=settings.memory_dedup_threshold,
            )
            results[agent_name] = {"pruned": pruned, "deduped": deduped, "capped": capped}

        total_pruned = sum(r["pruned"] for r in results.values())
        total_deduped = sum(r["deduped"] for r in results.values())
        total_capped = sum(r["capped"] for r in results.values())
        logger.info(
            f"[MemoryOptim] 전체 최적화 완료: {total_capped}개 상한초과삭제, "
            f"{total_pruned}개 감쇠정리, {total_deduped}개 중복 제거"
        )

        return results


# 싱글톤 인스턴스
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """장기기억 싱글톤 반환"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
