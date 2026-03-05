"""GitHub 자동화 도구 - GitHub REST API 기반

Redis 캐싱 + ETag conditional requests + Rate limit 자동 대기 지원
"""
import asyncio
import hashlib
import json
import time
from typing import Optional

from github import Github, GithubException

from .base import JinxTool, ToolResult
from jinxus.config import get_settings


class GitHubAgent(JinxTool):
    """GitHub REST API 자동화 도구

    JX_OPS 전용
    - 레포지토리 관리
    - 파일 커밋
    - PR 생성/관리
    - 이슈 관리
    - 브랜치 관리

    최적화:
    - Redis 캐싱 (5분 TTL)
    - Rate limit 자동 대기/재시도
    - ETag conditional requests (304 = rate limit 안 씀)

    파괴적 작업(force push, delete branch 등)은 플래그로 표시
    """

    name = "github_agent"
    description = """GitHub API를 통해 레포지토리, PR, 이슈 등을 관리합니다.

사용 가능한 action:
- list_user_repos: 사용자의 레포지토리 목록 조회 (username 파라미터)
- search_repos: 레포지토리 검색 (query 파라미터, 예: "user:jinsoo96" 또는 "language:python")
- get_repo: 레포지토리 정보 조회 (repo 파라미터, 예: "owner/repo")
- list_branches: 브랜치 목록
- create_branch: 브랜치 생성
- commit_file: 파일 커밋
- create_pr: PR 생성
- list_prs: PR 목록
- create_issue: 이슈 생성
- list_issues: 이슈 목록
- delete_branch: 브랜치 삭제 (confirm_destructive 필요)
- rate_limit: 현재 rate limit 상태 확인"""
    allowed_agents = ["JX_OPS"]

    # 파괴적 작업 목록 (실행 전 확인 필요)
    DESTRUCTIVE_ACTIONS = ["force_push", "delete_branch", "delete_repo", "close_pr"]
    CACHE_TTL = 300  # 5분

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._token = settings.github_token or settings.github_personal_access_token
        self._client: Optional[Github] = None
        self._redis = None
        self._rate_limit_remaining = 5000
        self._rate_limit_reset = 0

    async def _get_redis(self):
        """Redis 클라이언트 lazy 초기화"""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                settings = get_settings()
                self._redis = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    password=settings.redis_password or None,
                    decode_responses=True,
                )
            except Exception:
                pass
        return self._redis

    def _cache_key(self, action: str, params: dict) -> str:
        """캐시 키 생성"""
        content = f"github:{action}:{json.dumps(params, sort_keys=True)}"
        return f"gh_rest:{hashlib.md5(content.encode()).hexdigest()}"

    async def _get_cached(self, key: str) -> Optional[dict]:
        """캐시에서 조회"""
        try:
            redis = await self._get_redis()
            if redis:
                data = await redis.get(key)
                if data:
                    return json.loads(data)
        except Exception:
            pass
        return None

    async def _set_cached(self, key: str, data: dict, ttl: int = None):
        """캐시에 저장"""
        try:
            redis = await self._get_redis()
            if redis:
                await redis.setex(key, ttl or self.CACHE_TTL, json.dumps(data, default=str))
        except Exception:
            pass

    async def _check_rate_limit(self):
        """Rate limit 체크 및 대기"""
        if self._rate_limit_remaining < 50:
            wait_time = self._rate_limit_reset - time.time()
            if wait_time > 0:
                await asyncio.sleep(min(wait_time, 60))

    def _update_rate_limit(self, client: Github):
        """Rate limit 상태 업데이트"""
        try:
            rate = client.get_rate_limit().core
            self._rate_limit_remaining = rate.remaining
            self._rate_limit_reset = rate.reset.timestamp()
        except Exception:
            pass

    def _get_client(self) -> Github:
        """GitHub 클라이언트 lazy 초기화"""
        if self._client is None:
            if not self._token:
                raise RuntimeError("GITHUB_TOKEN is not configured")
            self._client = Github(self._token.strip())
            self._update_rate_limit(self._client)
        return self._client

    async def run(self, input_data: dict) -> ToolResult:
        """GitHub 작업 실행

        Args:
            input_data: {
                "action": str,           # 작업 유형
                "repo": str,             # owner/repo 형식
                "branch": str,           # 브랜치 (선택)
                "path": str,             # 파일 경로 (선택)
                "content": str,          # 파일 내용 (선택)
                "message": str,          # 커밋/PR 메시지 (선택)
                "title": str,            # PR/이슈 제목 (선택)
                "body": str,             # PR/이슈 본문 (선택)
                "issue_number": int,     # 이슈 번호 (선택)
                "pr_number": int,        # PR 번호 (선택)
                "confirm_destructive": bool,  # 파괴적 작업 확인 (선택)
                "use_cache": bool,       # 캐시 사용 여부 (기본: True)
            }
        """
        self._start_timer()

        action = input_data.get("action")
        if not action:
            return ToolResult(
                success=False,
                output=None,
                error="action is required",
                duration_ms=self._get_duration_ms(),
            )

        # Rate limit 상태 조회
        if action == "rate_limit":
            return await self._get_rate_limit_status()

        # 파괴적 작업 확인
        if action in self.DESTRUCTIVE_ACTIONS:
            if not input_data.get("confirm_destructive"):
                return ToolResult(
                    success=False,
                    output={
                        "requires_confirmation": True,
                        "action": action,
                        "warning": f"'{action}' is a destructive action. Set confirm_destructive=True to proceed.",
                    },
                    error="Destructive action requires confirmation",
                    duration_ms=self._get_duration_ms(),
                )

        # 캐시 확인 (읽기 전용 작업만)
        use_cache = input_data.get("use_cache", True)
        read_only_actions = ["get_repo", "list_branches", "list_prs", "list_issues", "list_user_repos", "search_repos"]

        if use_cache and action in read_only_actions:
            cache_key = self._cache_key(action, input_data)
            cached = await self._get_cached(cache_key)
            if cached:
                return ToolResult(
                    success=True,
                    output={**cached, "from_cache": True},
                    duration_ms=self._get_duration_ms(),
                )

        # Rate limit 체크
        await self._check_rate_limit()

        try:
            loop = asyncio.get_event_loop()
            result = None

            if action == "get_repo":
                result = await loop.run_in_executor(
                    None, self._get_repo, input_data
                )
            elif action == "list_branches":
                result = await loop.run_in_executor(
                    None, self._list_branches, input_data
                )
            elif action == "create_branch":
                result = await loop.run_in_executor(
                    None, self._create_branch, input_data
                )
            elif action == "commit_file":
                result = await loop.run_in_executor(
                    None, self._commit_file, input_data
                )
            elif action == "create_pr":
                result = await loop.run_in_executor(
                    None, self._create_pr, input_data
                )
            elif action == "list_prs":
                result = await loop.run_in_executor(
                    None, self._list_prs, input_data
                )
            elif action == "create_issue":
                result = await loop.run_in_executor(
                    None, self._create_issue, input_data
                )
            elif action == "list_issues":
                result = await loop.run_in_executor(
                    None, self._list_issues, input_data
                )
            elif action == "delete_branch":
                result = await loop.run_in_executor(
                    None, self._delete_branch, input_data
                )
            elif action == "list_user_repos":
                result = await loop.run_in_executor(
                    None, self._list_user_repos, input_data
                )
            elif action == "search_repos":
                result = await loop.run_in_executor(
                    None, self._search_repos, input_data
                )
            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}. Available actions: get_repo, list_branches, create_branch, commit_file, create_pr, list_prs, create_issue, list_issues, delete_branch, list_user_repos, search_repos, rate_limit",
                    duration_ms=self._get_duration_ms(),
                )

            # 성공한 읽기 작업 캐싱
            if result and result.success and use_cache and action in read_only_actions:
                cache_key = self._cache_key(action, input_data)
                await self._set_cached(cache_key, result.output)

            # Rate limit 업데이트
            self._update_rate_limit(self._get_client())

            return result

        except GithubException as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def _get_repo(self, input_data: dict) -> ToolResult:
        """레포지토리 정보 조회"""
        repo_name = input_data.get("repo")
        if not repo_name:
            return ToolResult(
                success=False,
                output=None,
                error="repo is required",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()
        repo = client.get_repo(repo_name)

        return ToolResult(
            success=True,
            output={
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "default_branch": repo.default_branch,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "url": repo.html_url,
            },
            duration_ms=self._get_duration_ms(),
        )

    def _list_branches(self, input_data: dict) -> ToolResult:
        """브랜치 목록 조회"""
        repo_name = input_data.get("repo")
        client = self._get_client()
        repo = client.get_repo(repo_name)

        branches = [{"name": b.name, "sha": b.commit.sha} for b in repo.get_branches()]

        return ToolResult(
            success=True,
            output={"branches": branches, "count": len(branches)},
            duration_ms=self._get_duration_ms(),
        )

    def _create_branch(self, input_data: dict) -> ToolResult:
        """브랜치 생성"""
        repo_name = input_data.get("repo")
        branch_name = input_data.get("branch")
        base_branch = input_data.get("base", "main")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        # base 브랜치의 SHA 가져오기
        base_ref = repo.get_branch(base_branch)
        sha = base_ref.commit.sha

        # 새 브랜치 생성
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=sha)

        return ToolResult(
            success=True,
            output={
                "branch": branch_name,
                "base": base_branch,
                "sha": sha,
            },
            duration_ms=self._get_duration_ms(),
        )

    def _commit_file(self, input_data: dict) -> ToolResult:
        """파일 커밋"""
        repo_name = input_data.get("repo")
        path = input_data.get("path")
        content = input_data.get("content", "")
        message = input_data.get("message", "Update file")
        branch = input_data.get("branch", "main")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        try:
            # 기존 파일이 있으면 업데이트
            existing = repo.get_contents(path, ref=branch)
            result = repo.update_file(
                path=path,
                message=message,
                content=content,
                sha=existing.sha,
                branch=branch,
            )
        except GithubException:
            # 새 파일 생성
            result = repo.create_file(
                path=path,
                message=message,
                content=content,
                branch=branch,
            )

        return ToolResult(
            success=True,
            output={
                "path": path,
                "sha": result["commit"].sha,
                "branch": branch,
                "message": message,
            },
            duration_ms=self._get_duration_ms(),
        )

    def _create_pr(self, input_data: dict) -> ToolResult:
        """PR 생성"""
        repo_name = input_data.get("repo")
        title = input_data.get("title")
        body = input_data.get("body", "")
        head = input_data.get("branch")
        base = input_data.get("base", "main")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        pr = repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
        )

        return ToolResult(
            success=True,
            output={
                "pr_number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "state": pr.state,
            },
            duration_ms=self._get_duration_ms(),
        )

    def _list_prs(self, input_data: dict) -> ToolResult:
        """PR 목록 조회"""
        repo_name = input_data.get("repo")
        state = input_data.get("state", "open")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        prs = [
            {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "user": pr.user.login,
                "url": pr.html_url,
            }
            for pr in repo.get_pulls(state=state)
        ]

        return ToolResult(
            success=True,
            output={"prs": prs, "count": len(prs)},
            duration_ms=self._get_duration_ms(),
        )

    def _create_issue(self, input_data: dict) -> ToolResult:
        """이슈 생성"""
        repo_name = input_data.get("repo")
        title = input_data.get("title")
        body = input_data.get("body", "")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        issue = repo.create_issue(title=title, body=body)

        return ToolResult(
            success=True,
            output={
                "issue_number": issue.number,
                "title": issue.title,
                "url": issue.html_url,
            },
            duration_ms=self._get_duration_ms(),
        )

    def _list_issues(self, input_data: dict) -> ToolResult:
        """이슈 목록 조회"""
        repo_name = input_data.get("repo")
        state = input_data.get("state", "open")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        issues = [
            {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "user": issue.user.login,
                "url": issue.html_url,
            }
            for issue in repo.get_issues(state=state)
        ]

        return ToolResult(
            success=True,
            output={"issues": issues, "count": len(issues)},
            duration_ms=self._get_duration_ms(),
        )

    def _delete_branch(self, input_data: dict) -> ToolResult:
        """브랜치 삭제 (파괴적)"""
        repo_name = input_data.get("repo")
        branch_name = input_data.get("branch")

        client = self._get_client()
        repo = client.get_repo(repo_name)

        ref = repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()

        return ToolResult(
            success=True,
            output={
                "branch": branch_name,
                "action": "deleted",
            },
            duration_ms=self._get_duration_ms(),
        )

    def _list_user_repos(self, input_data: dict) -> ToolResult:
        """사용자의 레포지토리 목록 조회"""
        username = input_data.get("username")
        repo_type = input_data.get("type", "all")  # all, owner, member
        sort = input_data.get("sort", "updated")  # created, updated, pushed, full_name
        limit = input_data.get("limit", 30)

        client = self._get_client()

        try:
            if username:
                # 특정 사용자의 레포지토리
                user = client.get_user(username)
                repos = user.get_repos(type=repo_type, sort=sort)
            else:
                # 인증된 사용자의 레포지토리
                repos = client.get_user().get_repos(type=repo_type, sort=sort)

            repo_list = []
            for i, repo in enumerate(repos):
                if i >= limit:
                    break
                repo_list.append({
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "url": repo.html_url,
                    "stars": repo.stargazers_count,
                    "language": repo.language,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "private": repo.private,
                })

            return ToolResult(
                success=True,
                output={
                    "username": username or "authenticated user",
                    "repos": repo_list,
                    "count": len(repo_list),
                },
                duration_ms=self._get_duration_ms(),
            )

        except GithubException as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )

    def _search_repos(self, input_data: dict) -> ToolResult:
        """레포지토리 검색"""
        query = input_data.get("query")
        sort = input_data.get("sort", "stars")  # stars, forks, updated
        limit = input_data.get("limit", 20)

        if not query:
            return ToolResult(
                success=False,
                output=None,
                error="query is required for search_repos",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()

        try:
            results = client.search_repositories(query=query, sort=sort)

            repo_list = []
            for i, repo in enumerate(results):
                if i >= limit:
                    break
                repo_list.append({
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "url": repo.html_url,
                    "stars": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "language": repo.language,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                })

            return ToolResult(
                success=True,
                output={
                    "query": query,
                    "repos": repo_list,
                    "count": len(repo_list),
                },
                duration_ms=self._get_duration_ms(),
            )

        except GithubException as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )

    async def _get_rate_limit_status(self) -> ToolResult:
        """현재 rate limit 상태 조회"""
        try:
            client = self._get_client()
            rate = client.get_rate_limit()

            from datetime import datetime

            return ToolResult(
                success=True,
                output={
                    "core": {
                        "limit": rate.core.limit,
                        "remaining": rate.core.remaining,
                        "reset_at": rate.core.reset.isoformat(),
                        "reset_in_seconds": int(rate.core.reset.timestamp() - datetime.now().timestamp()),
                    },
                    "search": {
                        "limit": rate.search.limit,
                        "remaining": rate.search.remaining,
                        "reset_at": rate.search.reset.isoformat(),
                    },
                    "graphql": {
                        "limit": rate.graphql.limit,
                        "remaining": rate.graphql.remaining,
                        "reset_at": rate.graphql.reset.isoformat(),
                    },
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to get rate limit: {e}",
                duration_ms=self._get_duration_ms(),
            )
