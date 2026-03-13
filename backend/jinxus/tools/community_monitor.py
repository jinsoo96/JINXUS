"""커뮤니티 댓글/게시물 모니터링 도구 - Reddit / Hacker News / 국내 커뮤니티"""
import logging
from datetime import datetime, timezone

import httpx

from .base import JinxTool, ToolResult

logger = logging.getLogger("jinxus.tools.community_monitor")

REDDIT_HEADERS = {
    "User-Agent": "JINXUS:community-monitor:v1.0 (personal assistant)",
    "Accept": "application/json",
}

# 자주 쓰는 서브레딧 단축키
SUBREDDIT_ALIASES: dict[str, str] = {
    "programming": "programming",
    "ml": "MachineLearning",
    "ai": "artificial",
    "python": "Python",
    "webdev": "webdev",
    "node": "node",
    "react": "reactjs",
    "devops": "devops",
    "security": "netsec",
    "startup": "startups",
    "tech": "technology",
    "korea": "korea",
    "korean": "korea",
}


class CommunityMonitor(JinxTool):
    """Reddit/Hacker News 댓글·게시물 수집 도구"""

    name = "community_monitor"
    description = (
        "Reddit 서브레딧 또는 Hacker News에서 최신 게시물/댓글을 가져옵니다. "
        "특정 키워드로 검색하거나 핫 게시물 목록을 조회할 수 있습니다"
    )
    allowed_agents = []  # 모든 에이전트 허용
    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "소스 타입: 'hn'(Hacker News), 'reddit:서브레딧명'(예: 'reddit:python'), 'hn_search'",
                "enum": ["hn", "hn_top", "hn_search", "reddit", "reddit_search"]
            },
            "subreddit": {
                "type": "string",
                "description": "Reddit 서브레딧 이름 (source가 reddit일 때). 단축키: programming, ml, ai, python, webdev 등"
            },
            "query": {
                "type": "string",
                "description": "검색 키워드 (source가 hn_search / reddit_search일 때)"
            },
            "limit": {
                "type": "integer",
                "description": "가져올 최대 항목 수 (기본: 15)",
                "default": 15
            },
            "include_comments": {
                "type": "boolean",
                "description": "상위 댓글 포함 여부 (기본: false, true면 느려짐)",
                "default": False
            }
        },
        "required": ["source"]
    }

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        source = input_data.get("source", "hn")
        limit = int(input_data.get("limit", 15))
        query = input_data.get("query", "")
        subreddit = input_data.get("subreddit", "programming")
        include_comments = input_data.get("include_comments", False)

        # 서브레딧 단축키 변환
        subreddit = SUBREDDIT_ALIASES.get(subreddit.lower(), subreddit)

        try:
            if source in ("hn", "hn_top"):
                result = await self._fetch_hn_top(limit, include_comments)
            elif source == "hn_search":
                if not query:
                    return ToolResult(
                        success=False, output=None,
                        error="hn_search는 query가 필요합니다",
                        duration_ms=self._get_duration_ms(),
                    )
                result = await self._fetch_hn_search(query, limit)
            elif source == "reddit":
                result = await self._fetch_reddit_hot(subreddit, limit)
            elif source == "reddit_search":
                if not query:
                    return ToolResult(
                        success=False, output=None,
                        error="reddit_search는 query가 필요합니다",
                        duration_ms=self._get_duration_ms(),
                    )
                result = await self._fetch_reddit_search(query, subreddit, limit)
            else:
                return ToolResult(
                    success=False, output=None,
                    error=f"지원하지 않는 source: {source}",
                    duration_ms=self._get_duration_ms(),
                )

            return ToolResult(
                success=True,
                output=result,
                duration_ms=self._get_duration_ms(),
            )

        except Exception as e:
            logger.error(f"커뮤니티 모니터링 실패 ({source}): {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ── Hacker News ──────────────────────────────────────────────────────

    async def _fetch_hn_top(self, limit: int, include_comments: bool) -> dict:
        """HN 탑 스토리"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            resp.raise_for_status()
            ids = resp.json()[:limit]

            items = []
            for story_id in ids:
                try:
                    item_resp = await client.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    )
                    item = item_resp.json()
                    if not item or item.get("type") != "story":
                        continue

                    entry = {
                        "id": story_id,
                        "title": item.get("title", ""),
                        "url": item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "score": item.get("score", 0),
                        "comments": item.get("descendants", 0),
                        "author": item.get("by", ""),
                        "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                        "time": datetime.fromtimestamp(
                            item.get("time", 0), tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M"),
                    }

                    if include_comments and item.get("kids"):
                        entry["top_comments"] = await self._fetch_hn_comments(
                            client, item["kids"][:3]
                        )

                    items.append(entry)
                except Exception as e:
                    logger.debug(f"HN item {story_id} 로드 실패: {e}")

        return {
            "source": "Hacker News Top Stories",
            "count": len(items),
            "items": items,
        }

    async def _fetch_hn_search(self, query: str, limit: int) -> dict:
        """Algolia HN Search API"""
        url = "https://hn.algolia.com/api/v1/search"
        params = {"query": query, "tags": "story", "hitsPerPage": limit}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = []
        for hit in data.get("hits", []):
            items.append({
                "id": hit.get("objectID"),
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "score": hit.get("points", 0),
                "comments": hit.get("num_comments", 0),
                "author": hit.get("author", ""),
                "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "time": hit.get("created_at", "")[:16],
            })

        return {
            "source": f"Hacker News Search: '{query}'",
            "count": len(items),
            "items": items,
        }

    async def _fetch_hn_comments(self, client: httpx.AsyncClient, ids: list[int]) -> list[dict]:
        comments = []
        for cid in ids:
            try:
                r = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{cid}.json")
                c = r.json()
                if c and c.get("text"):
                    # HTML 태그 간단 제거
                    import re
                    text = re.sub(r"<[^>]+>", "", c["text"])[:300]
                    comments.append({"author": c.get("by", ""), "text": text})
            except Exception as e:
                logger.warning(f"[CommunityMonitor] HN 댓글 아이템 {cid} 조회 실패: {e}")
        return comments

    # ── Reddit ───────────────────────────────────────────────────────────

    async def _fetch_reddit_hot(self, subreddit: str, limit: int) -> dict:
        """Reddit 서브레딧 핫 게시물"""
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        params = {"limit": limit}

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=REDDIT_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        items = self._parse_reddit_listing(data)
        return {
            "source": f"Reddit r/{subreddit} (Hot)",
            "subreddit": subreddit,
            "count": len(items),
            "items": items,
        }

    async def _fetch_reddit_search(self, query: str, subreddit: str, limit: int) -> dict:
        """Reddit 검색"""
        if subreddit:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
        else:
            url = "https://www.reddit.com/search.json"

        params = {"q": query, "limit": limit, "sort": "relevance", "restrict_sr": bool(subreddit)}

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=REDDIT_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        items = self._parse_reddit_listing(data)
        return {
            "source": f"Reddit Search: '{query}'" + (f" in r/{subreddit}" if subreddit else ""),
            "count": len(items),
            "items": items,
        }

    def _parse_reddit_listing(self, data: dict) -> list[dict]:
        items = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied"):
                continue
            items.append({
                "id": post.get("id"),
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "reddit_url": f"https://reddit.com{post.get('permalink', '')}",
                "score": post.get("score", 0),
                "upvote_ratio": round(post.get("upvote_ratio", 0) * 100),
                "comments": post.get("num_comments", 0),
                "author": post.get("author", ""),
                "subreddit": post.get("subreddit", ""),
                "flair": post.get("link_flair_text", ""),
                "selftext": post.get("selftext", "")[:300] if post.get("selftext") else "",
                "time": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M"),
            })
        return items
