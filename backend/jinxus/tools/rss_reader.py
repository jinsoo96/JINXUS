"""RSS 피드 구독 및 집계 도구 - feedparser 기반"""
import logging
from datetime import datetime, timezone

import httpx

from .base import JinxTool, ToolResult

logger = logging.getLogger("jinxus.tools.rss_reader")

# 자주 쓰는 피드 단축키
PRESET_FEEDS: dict[str, str] = {
    "hacker_news": "https://news.ycombinator.com/rss",
    "hn": "https://news.ycombinator.com/rss",
    "techcrunch": "https://techcrunch.com/feed/",
    "the_verge": "https://www.theverge.com/rss/index.xml",
    "github_trending": "https://github.com/trending?since=daily",
    "naver_it": "https://rss.naver.com/main/rss/it/1",
    "etnews": "https://rss.etnews.com/Section901.xml",
    "zdnet_kr": "https://www.zdnet.co.kr/rss/news.xml",
    "reddit_programming": "https://www.reddit.com/r/programming/.rss",
    "reddit_ml": "https://www.reddit.com/r/MachineLearning/.rss",
    "reddit_python": "https://www.reddit.com/r/Python/.rss",
    "anthropic_blog": "https://www.anthropic.com/blog.rss",
    "openai_blog": "https://openai.com/blog/rss/",
}


class RSSReader(JinxTool):
    """RSS 피드 구독 및 집계 도구"""

    name = "rss_reader"
    description = "RSS/Atom 피드를 가져와 최신 글 목록을 반환합니다. 여러 피드 동시 집계 가능"
    allowed_agents = []  # 모든 에이전트 허용
    input_schema = {
        "type": "object",
        "properties": {
            "feeds": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "피드 URL 또는 단축키 목록 (예: ['hn', 'techcrunch', 'https://...']). "
                    f"단축키: {', '.join(PRESET_FEEDS.keys())}"
                )
            },
            "limit": {
                "type": "integer",
                "description": "피드당 최대 항목 수 (기본: 10)",
                "default": 10
            },
            "keyword": {
                "type": "string",
                "description": "제목/요약에서 필터링할 키워드 (선택)"
            }
        },
        "required": ["feeds"]
    }

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        try:
            import feedparser
        except ImportError:
            return ToolResult(
                success=False,
                output=None,
                error="feedparser 미설치 — pip install feedparser",
                duration_ms=self._get_duration_ms(),
            )

        feeds_input: list[str] = input_data.get("feeds", [])
        limit = int(input_data.get("limit", 10))
        keyword = input_data.get("keyword", "").lower()

        if not feeds_input:
            return ToolResult(
                success=False,
                output=None,
                error="feeds 목록이 필요합니다",
                duration_ms=self._get_duration_ms(),
            )

        results = []
        errors = []

        for feed_input in feeds_input:
            url = PRESET_FEEDS.get(feed_input, feed_input)
            try:
                feed_data = await self._fetch_feed(feedparser, url, limit, keyword)
                results.append(feed_data)
            except Exception as e:
                logger.warning(f"피드 로드 실패 ({url}): {e}")
                errors.append({"url": url, "error": str(e)})

        # 전체 합산 → 최신순 정렬
        all_items = []
        for fd in results:
            all_items.extend(fd["items"])
        all_items.sort(key=lambda x: x.get("published_ts", 0), reverse=True)

        return ToolResult(
            success=True,
            output={
                "feeds": results,
                "all_items_sorted": all_items[:limit * len(feeds_input)],
                "total": len(all_items),
                "errors": errors,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _fetch_feed(self, feedparser, url: str, limit: int, keyword: str) -> dict:
        """단일 피드 가져오기"""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JINXUS RSS reader)"}

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            content = resp.text

        parsed = feedparser.parse(content)
        feed_title = parsed.feed.get("title", url)

        items = []
        for entry in parsed.entries[:limit * 2]:  # 키워드 필터 후 limit 적용
            title = entry.get("title", "")
            summary = entry.get("summary", "")

            # 키워드 필터
            if keyword and keyword not in title.lower() and keyword not in summary.lower():
                continue

            # 날짜 파싱
            published_ts = 0
            published_str = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    published_ts = dt.timestamp()
                    published_str = dt.strftime("%Y-%m-%d %H:%M")
                except Exception as e:
                    logger.warning(f"[RSSReader] 날짜 파싱 실패 ({entry.get('link', '')}): {e}")

            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "summary": summary[:300] if summary else "",
                "published": published_str,
                "published_ts": published_ts,
                "author": entry.get("author", ""),
            })

            if len(items) >= limit:
                break

        return {
            "feed_url": url,
            "feed_title": feed_title,
            "item_count": len(items),
            "items": items,
        }
