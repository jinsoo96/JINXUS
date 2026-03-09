"""네이버 검색 도구 - Naver Open API 기반"""
import asyncio
import logging
from typing import Optional

import httpx

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger("jinxus.tools.naver_searcher")


class NaverSearcher(JinxTool):
    """네이버 검색 API 기반 웹 검색 도구

    한국어 검색에 최적화.
    카테고리: webkr(웹), news(뉴스), blog(블로그), kin(지식iN), encyc(백과사전), local(지역)
    """

    name = "naver_searcher"
    description = "네이버 검색 API로 웹/뉴스/블로그를 검색합니다. 한국어 검색에 최적화."
    allowed_agents = []  # 모든 에이전트 사용 가능
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색 쿼리"
            },
            "category": {
                "type": "string",
                "description": "검색 카테고리: webkr(웹), news(뉴스), blog(블로그), kin(지식iN), encyc(백과사전), local(지역)",
                "enum": ["webkr", "news", "blog", "kin", "encyc", "local"],
                "default": "webkr"
            },
            "display": {
                "type": "integer",
                "description": "결과 수 (최대 100, 기본 10)",
                "default": 10
            },
            "sort": {
                "type": "string",
                "description": "정렬: sim(정확도) 또는 date(날짜순)",
                "enum": ["sim", "date"],
                "default": "sim"
            }
        },
        "required": ["query"]
    }

    BASE_URL = "https://openapi.naver.com/v1/search"

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._client_id = settings.naver_client_id
        self._client_secret = settings.naver_client_secret

    async def run(self, input_data: dict) -> ToolResult:
        """네이버 검색 실행"""
        self._start_timer()

        query = input_data.get("query")
        if not query:
            return ToolResult(
                success=False,
                output=None,
                error="query is required",
                duration_ms=self._get_duration_ms(),
            )

        if not self._client_id or not self._client_secret:
            return ToolResult(
                success=False,
                output=None,
                error="NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되지 않았습니다",
                duration_ms=self._get_duration_ms(),
            )

        category = input_data.get("category", "webkr")
        display = min(input_data.get("display", 10), 100)
        sort = input_data.get("sort", "sim")

        try:
            results = await self._search(query, category, display, sort)

            return ToolResult(
                success=True,
                output={
                    "results": results,
                    "total": len(results),
                    "query": query,
                    "category": category,
                },
                duration_ms=self._get_duration_ms(),
            )

        except Exception as e:
            logger.error(f"네이버 검색 실패: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _search(self, query: str, category: str, display: int, sort: str) -> list[dict]:
        """네이버 검색 API 호출"""
        url = f"{self.BASE_URL}/{category}"
        headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }
        params = {
            "query": query,
            "display": display,
            "start": 1,
            "sort": sort,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        return self._parse_results(data, category)

    def _parse_results(self, data: dict, category: str) -> list[dict]:
        """응답 파싱 - 카테고리별 통일된 형식으로 변환"""
        results = []
        for item in data.get("items", []):
            # HTML 태그 제거
            title = self._strip_html(item.get("title", ""))
            description = self._strip_html(item.get("description", ""))

            result = {
                "title": title,
                "url": item.get("originallink") or item.get("link", ""),
                "content": description,
                "score": 1.0,  # 네이버는 점수 미제공, 기본값
            }

            # 카테고리별 추가 필드
            if category == "news":
                result["published_date"] = item.get("pubDate", "")
            elif category == "blog":
                result["blogger_name"] = item.get("bloggername", "")
                result["published_date"] = item.get("postdate", "")
            elif category == "local":
                result["address"] = item.get("address", "")
                result["telephone"] = item.get("telephone", "")

            results.append(result)

        return results

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거"""
        import re
        return re.sub(r"<[^>]+>", "", text)
