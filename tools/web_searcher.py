"""웹 검색 도구 - Tavily API 기반"""
import asyncio
from typing import Optional

from tavily import TavilyClient

from .base import JinxTool, ToolResult
from config import get_settings


class WebSearcher(JinxTool):
    """Tavily API 기반 웹 검색 도구

    JX_RESEARCHER 전용
    - 웹 검색
    - 쿼리 자동 변형 (넓게 → 좁게)
    - 결과 중복 제거 및 병합
    """

    name = "web_searcher"
    description = "Tavily API를 통해 웹을 검색하고 결과를 분석합니다"
    allowed_agents = ["JX_RESEARCHER"]

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._api_key = settings.tavily_api_key
        self._client: Optional[TavilyClient] = None

    def _get_client(self) -> TavilyClient:
        """Tavily 클라이언트 lazy 초기화"""
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("TAVILY_API_KEY is not configured")
            self._client = TavilyClient(api_key=self._api_key)
        return self._client

    async def run(self, input_data: dict) -> ToolResult:
        """웹 검색 실행

        Args:
            input_data: {
                "query": str,            # 검색 쿼리
                "max_results": int,      # 최대 결과 수 (기본 5)
                "search_depth": str,     # "basic" | "advanced" (기본 basic)
                "auto_expand": bool,     # 쿼리 자동 변형 (기본 True)
            }

        Returns:
            ToolResult: {
                "results": [
                    {
                        "title": str,
                        "url": str,
                        "content": str,
                        "published_date": str,
                        "score": float,
                    }
                ],
                "total": int,
            }
        """
        self._start_timer()

        query = input_data.get("query")
        if not query:
            return ToolResult(
                success=False,
                output=None,
                error="query is required",
                duration_ms=self._get_duration_ms(),
            )

        max_results = input_data.get("max_results", 5)
        search_depth = input_data.get("search_depth", "basic")
        auto_expand = input_data.get("auto_expand", True)

        try:
            if auto_expand:
                results = await self._search_with_expansion(query, max_results, search_depth)
            else:
                results = await self._single_search(query, max_results, search_depth)

            return ToolResult(
                success=True,
                output={
                    "results": results,
                    "total": len(results),
                    "query": query,
                },
                duration_ms=self._get_duration_ms(),
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _single_search(
        self, query: str, max_results: int, search_depth: str
    ) -> list[dict]:
        """단일 쿼리 검색"""
        client = self._get_client()

        # Tavily는 동기 API이므로 executor에서 실행
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            ),
        )

        return self._parse_results(response)

    async def _search_with_expansion(
        self, query: str, max_results: int, search_depth: str
    ) -> list[dict]:
        """쿼리 변형으로 3번 검색 후 병합"""
        queries = self._expand_query(query)

        # 병렬 검색
        tasks = [
            self._single_search(q, max_results, search_depth)
            for q in queries
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 병합 및 중복 제거
        merged = {}
        for result_list in all_results:
            if isinstance(result_list, Exception):
                continue
            for item in result_list:
                url = item.get("url")
                if url and url not in merged:
                    merged[url] = item

        # 점수 기준 정렬 후 상위 반환
        sorted_results = sorted(
            merged.values(),
            key=lambda x: x.get("score", 0),
            reverse=True,
        )
        return sorted_results[:max_results]

    def _expand_query(self, query: str) -> list[str]:
        """쿼리 변형 (넓게 → 좁게)"""
        queries = [query]

        # 더 구체적인 쿼리
        queries.append(f"{query} tutorial guide")

        # 더 넓은 쿼리
        words = query.split()
        if len(words) > 2:
            queries.append(" ".join(words[:2]))

        return queries[:3]

    def _parse_results(self, response: dict) -> list[dict]:
        """Tavily 응답 파싱"""
        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "published_date": item.get("published_date"),
                "score": item.get("score", 0.0),
            })
        return results

    async def search_news(self, query: str, days: int = 7) -> ToolResult:
        """뉴스 검색 (최근 N일)"""
        self._start_timer()

        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    max_results=10,
                    search_depth="advanced",
                    include_domains=["news.google.com", "reuters.com", "bbc.com"],
                ),
            )

            return ToolResult(
                success=True,
                output={"results": self._parse_results(response)},
                duration_ms=self._get_duration_ms(),
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )
