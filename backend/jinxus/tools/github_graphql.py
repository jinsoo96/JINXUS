"""GitHub GraphQL API 클라이언트 - Rate Limit 최적화

REST API 여러 번 호출 대신 GraphQL 한 번으로 필요한 데이터만 가져온다.
Redis 캐싱 + ETag로 추가 최적화.
"""
import asyncio
import hashlib
import json
import time
from typing import Any, Optional

import logging

import httpx

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


class GitHubGraphQL(JinxTool):
    """GitHub GraphQL API 도구

    장점:
    - REST API 여러 번 대신 한 번 호출
    - 필요한 필드만 선택해서 가져옴
    - Redis 캐싱으로 중복 요청 제거
    - Rate limit 자동 대기/재시도
    """

    name = "github_graphql"
    description = """GitHub GraphQL API로 효율적인 데이터 조회.

사용 가능한 action:
- repo_overview: 레포 + 브랜치 + 최근 커밋 + 이슈 + PR 한 번에 조회
- user_repos: 사용자 레포 목록 (한 번에 100개)
- repo_files: 레포 파일 트리 조회 (경로 지정 가능)
- search_code: 코드 검색
- raw_query: 직접 GraphQL 쿼리 실행
"""
    allowed_agents = ["JX_OPS", "JX_CODER", "JX_RESEARCHER", "JX_REVIEWER"]

    GRAPHQL_URL = "https://api.github.com/graphql"
    CACHE_TTL = 300  # 5분 캐시

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._token = settings.github_token or settings.github_personal_access_token
        self._redis = None
        self._rate_limit_remaining = 5000
        self._rate_limit_reset = 0

    async def _get_redis(self):
        """Redis 클라이언트 lazy 초기화"""
        if self._redis is None:
            import redis.asyncio as redis
            settings = get_settings()
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                decode_responses=True,
            )
        return self._redis

    def _cache_key(self, query: str, variables: dict) -> str:
        """캐시 키 생성"""
        content = f"{query}:{json.dumps(variables, sort_keys=True)}"
        return f"github_gql:{hashlib.md5(content.encode()).hexdigest()}"

    async def _get_cached(self, key: str) -> Optional[dict]:
        """캐시에서 조회"""
        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"GraphQL cache read failed: {e}")
        return None

    async def _set_cached(self, key: str, data: dict, ttl: int = None):
        """캐시에 저장"""
        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl or self.CACHE_TTL, json.dumps(data))
        except Exception as e:
            logger.debug(f"GraphQL cache write failed: {e}")

    async def _execute_graphql(
        self, query: str, variables: dict = None, use_cache: bool = True
    ) -> dict:
        """GraphQL 쿼리 실행 (캐싱 + rate limit 처리)"""
        variables = variables or {}
        cache_key = self._cache_key(query, variables)

        # 캐시 확인
        if use_cache:
            cached = await self._get_cached(cache_key)
            if cached:
                return {"data": cached, "from_cache": True}

        # Rate limit 체크
        if self._rate_limit_remaining < 10:
            wait_time = self._rate_limit_reset - time.time()
            if wait_time > 0:
                await asyncio.sleep(min(wait_time, 60))  # 최대 60초 대기

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GRAPHQL_URL,
                headers=headers,
                json={"query": query, "variables": variables},
                timeout=30,
            )

            # Rate limit 헤더 파싱
            self._rate_limit_remaining = int(
                response.headers.get("X-RateLimit-Remaining", 5000)
            )
            self._rate_limit_reset = int(
                response.headers.get("X-RateLimit-Reset", 0)
            )

            if response.status_code == 200:
                result = response.json()
                if "data" in result and use_cache:
                    await self._set_cached(cache_key, result["data"])
                return result
            elif response.status_code == 403:
                # Rate limit 초과
                reset_time = self._rate_limit_reset - time.time()
                raise Exception(
                    f"Rate limit exceeded. Resets in {int(reset_time)}s. "
                    f"Remaining: {self._rate_limit_remaining}"
                )
            else:
                raise Exception(f"GraphQL error: {response.status_code} - {response.text}")

    async def run(self, input_data: dict) -> ToolResult:
        """GraphQL 작업 실행"""
        self._start_timer()

        action = input_data.get("action")
        if not action:
            return ToolResult(
                success=False,
                output=None,
                error="action is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            if action == "repo_overview":
                return await self._repo_overview(input_data)
            elif action == "user_repos":
                return await self._user_repos(input_data)
            elif action == "repo_files":
                return await self._repo_files(input_data)
            elif action == "search_code":
                return await self._search_code(input_data)
            elif action == "raw_query":
                return await self._raw_query(input_data)
            elif action == "rate_limit":
                return await self._get_rate_limit()
            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}",
                    duration_ms=self._get_duration_ms(),
                )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _repo_overview(self, input_data: dict) -> ToolResult:
        """레포 전체 개요 한 번에 조회"""
        owner, repo = input_data.get("repo", "/").split("/")

        query = """
        query RepoOverview($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            name
            description
            url
            stargazerCount
            forkCount
            primaryLanguage { name }
            defaultBranchRef {
              name
              target {
                ... on Commit {
                  history(first: 5) {
                    nodes {
                      message
                      committedDate
                      author { name }
                    }
                  }
                }
              }
            }
            issues(first: 10, states: OPEN, orderBy: {field: UPDATED_AT, direction: DESC}) {
              totalCount
              nodes {
                number
                title
                state
                createdAt
              }
            }
            pullRequests(first: 10, states: OPEN, orderBy: {field: UPDATED_AT, direction: DESC}) {
              totalCount
              nodes {
                number
                title
                state
                createdAt
              }
            }
            refs(refPrefix: "refs/heads/", first: 20) {
              nodes {
                name
              }
            }
          }
        }
        """

        result = await self._execute_graphql(query, {"owner": owner, "repo": repo})

        if "errors" in result:
            return ToolResult(
                success=False,
                output=None,
                error=str(result["errors"]),
                duration_ms=self._get_duration_ms(),
            )

        data = result.get("data", {}).get("repository", {})
        from_cache = result.get("from_cache", False)

        return ToolResult(
            success=True,
            output={
                "repo": data,
                "from_cache": from_cache,
                "rate_limit_remaining": self._rate_limit_remaining,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _user_repos(self, input_data: dict) -> ToolResult:
        """사용자 레포 목록 (최대 100개 한 번에)"""
        username = input_data.get("username")
        limit = min(input_data.get("limit", 30), 100)

        query = """
        query UserRepos($username: String!, $limit: Int!) {
          user(login: $username) {
            repositories(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
              totalCount
              nodes {
                name
                description
                url
                stargazerCount
                primaryLanguage { name }
                updatedAt
                isPrivate
              }
            }
          }
        }
        """

        result = await self._execute_graphql(
            query, {"username": username, "limit": limit}
        )

        if "errors" in result:
            return ToolResult(
                success=False,
                output=None,
                error=str(result["errors"]),
                duration_ms=self._get_duration_ms(),
            )

        repos = result.get("data", {}).get("user", {}).get("repositories", {})

        return ToolResult(
            success=True,
            output={
                "repos": repos.get("nodes", []),
                "total": repos.get("totalCount", 0),
                "from_cache": result.get("from_cache", False),
                "rate_limit_remaining": self._rate_limit_remaining,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _repo_files(self, input_data: dict) -> ToolResult:
        """레포 파일 트리 조회"""
        owner, repo = input_data.get("repo", "/").split("/")
        path = input_data.get("path", "")
        branch = input_data.get("branch", "HEAD")

        expression = f"{branch}:{path}" if path else f"{branch}:"

        query = """
        query RepoFiles($owner: String!, $repo: String!, $expression: String!) {
          repository(owner: $owner, name: $repo) {
            object(expression: $expression) {
              ... on Tree {
                entries {
                  name
                  type
                  path
                  object {
                    ... on Blob {
                      byteSize
                    }
                  }
                }
              }
            }
          }
        }
        """

        result = await self._execute_graphql(
            query, {"owner": owner, "repo": repo, "expression": expression}
        )

        if "errors" in result:
            return ToolResult(
                success=False,
                output=None,
                error=str(result["errors"]),
                duration_ms=self._get_duration_ms(),
            )

        obj = result.get("data", {}).get("repository", {}).get("object", {})
        entries = obj.get("entries", []) if obj else []

        return ToolResult(
            success=True,
            output={
                "path": path or "/",
                "files": entries,
                "count": len(entries),
                "from_cache": result.get("from_cache", False),
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _search_code(self, input_data: dict) -> ToolResult:
        """코드 검색"""
        query_str = input_data.get("query")
        limit = min(input_data.get("limit", 20), 100)

        query = """
        query SearchCode($query: String!, $limit: Int!) {
          search(query: $query, type: CODE, first: $limit) {
            codeCount
            edges {
              node {
                ... on Blob {
                  path
                  repository {
                    nameWithOwner
                  }
                }
              }
            }
          }
        }
        """

        # 코드 검색은 캐시 안 함 (실시간 결과 필요)
        result = await self._execute_graphql(
            query, {"query": query_str, "limit": limit}, use_cache=False
        )

        if "errors" in result:
            return ToolResult(
                success=False,
                output=None,
                error=str(result["errors"]),
                duration_ms=self._get_duration_ms(),
            )

        search = result.get("data", {}).get("search", {})

        return ToolResult(
            success=True,
            output={
                "query": query_str,
                "total": search.get("codeCount", 0),
                "results": search.get("edges", []),
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _raw_query(self, input_data: dict) -> ToolResult:
        """직접 GraphQL 쿼리 실행"""
        query = input_data.get("query")
        variables = input_data.get("variables", {})
        use_cache = input_data.get("use_cache", True)

        if not query:
            return ToolResult(
                success=False,
                output=None,
                error="query is required",
                duration_ms=self._get_duration_ms(),
            )

        result = await self._execute_graphql(query, variables, use_cache)

        return ToolResult(
            success=True,
            output={
                "data": result.get("data"),
                "errors": result.get("errors"),
                "from_cache": result.get("from_cache", False),
                "rate_limit_remaining": self._rate_limit_remaining,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _get_rate_limit(self) -> ToolResult:
        """현재 rate limit 상태 조회"""
        query = """
        query {
          rateLimit {
            limit
            remaining
            resetAt
            used
          }
        }
        """

        result = await self._execute_graphql(query, use_cache=False)

        return ToolResult(
            success=True,
            output=result.get("data", {}).get("rateLimit", {}),
            duration_ms=self._get_duration_ms(),
        )
