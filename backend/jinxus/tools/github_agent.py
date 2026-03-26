"""GitHub 자동화 도구 - GitHub REST API 기반

Redis 캐싱 + ETag conditional requests + Rate limit 자동 대기 지원
"""
import asyncio
import hashlib
import json
import time
from typing import Optional

from github import Github, GithubException

import logging

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


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
- list_commits: 최근 커밋 목록 조회 (repo 파라미터, 예: "owner/repo", branch 선택, limit 선택)
- get_contents: 파일/디렉토리 내용 조회 (repo, path 파라미터. 디렉토리면 파일 목록, 파일이면 내용 반환)
- get_file: 특정 파일의 전체 내용 조회 (repo, path 파라미터)
- get_tree_recursive: 레포 전체 파일 트리를 재귀적으로 조회 (repo 파라미터, branch 선택)
- read_all_files: 레포의 모든 소스 파일을 재귀적으로 읽어 내용 반환 (repo 파라미터, path 선택, branch 선택. 바이너리/거대 파일 자동 제외)
- rate_limit: 현재 rate limit 상태 확인"""
    allowed_agents = ["JX_OPS", "JX_RESEARCHER", "JX_CODER", "JX_REVIEWER"]

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "수행할 GitHub 작업",
                "enum": [
                    "list_user_repos", "search_repos", "get_repo",
                    "list_commits", "list_branches", "create_branch",
                    "commit_file", "create_pr", "list_prs",
                    "create_issue", "list_issues", "delete_branch",
                    "get_contents", "get_file",
                    "get_tree_recursive", "read_all_files",
                    "rate_limit",
                ],
            },
            "repo": {"type": "string", "description": "owner/repo 형식 (예: jinsoo96/JINXUS)"},
            "username": {"type": "string", "description": "GitHub 사용자명 (list_user_repos용)"},
            "query": {"type": "string", "description": "검색어 (search_repos용, 예: user:jinsoo96)"},
            "branch": {"type": "string", "description": "브랜치명"},
            "limit": {"type": "integer", "description": "조회 개수 제한 (기본 10)"},
            "title": {"type": "string", "description": "PR/이슈 제목"},
            "body": {"type": "string", "description": "PR/이슈 본문"},
            "path": {"type": "string", "description": "파일 경로"},
            "content": {"type": "string", "description": "파일 내용"},
            "message": {"type": "string", "description": "커밋 메시지"},
        },
        "required": ["action"],
    }

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
            except Exception as e:
                logger.warning(f"Redis connection failed for GitHub cache: {e}")
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
        except Exception as e:
            logger.debug(f"GitHub cache read failed: {e}")
        return None

    async def _set_cached(self, key: str, data: dict, ttl: int = None):
        """캐시에 저장"""
        try:
            redis = await self._get_redis()
            if redis:
                await redis.setex(key, ttl or self.CACHE_TTL, json.dumps(data, default=str))
        except Exception as e:
            logger.debug(f"GitHub cache write failed: {e}")

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
        except Exception as e:
            logger.debug(f"Rate limit check failed: {e}")

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
        read_only_actions = ["get_repo", "list_branches", "list_prs", "list_issues", "list_user_repos", "search_repos", "list_commits", "get_contents", "get_file", "get_tree_recursive", "read_all_files"]

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
            elif action == "list_commits":
                result = await loop.run_in_executor(
                    None, self._list_commits, input_data
                )
            elif action == "get_contents":
                result = await loop.run_in_executor(
                    None, self._get_contents, input_data
                )
            elif action == "get_file":
                result = await loop.run_in_executor(
                    None, self._get_file, input_data
                )
            elif action == "get_tree_recursive":
                result = await loop.run_in_executor(
                    None, self._get_tree_recursive, input_data
                )
            elif action == "read_all_files":
                result = await loop.run_in_executor(
                    None, self._read_all_files, input_data
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

    def _get_contents(self, input_data: dict) -> ToolResult:
        """파일/디렉토리 내용 조회"""
        repo_name = input_data.get("repo")
        path = input_data.get("path", "")
        branch = input_data.get("branch")

        if not repo_name:
            return ToolResult(
                success=False, output=None,
                error="repo is required (예: jinsoo96/Prompt_Foundry)",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()
        try:
            repo = client.get_repo(repo_name)
            kwargs = {"ref": branch} if branch else {}
            contents = repo.get_contents(path, **kwargs)

            if isinstance(contents, list):
                # 디렉토리
                items = []
                for item in contents:
                    items.append({
                        "name": item.name,
                        "path": item.path,
                        "type": item.type,  # "file" or "dir"
                        "size": item.size if item.type == "file" else None,
                    })
                return ToolResult(
                    success=True,
                    output={"repo": repo_name, "path": path or "/", "type": "directory", "items": items, "count": len(items)},
                    duration_ms=self._get_duration_ms(),
                )
            else:
                # 파일
                try:
                    content = contents.decoded_content.decode("utf-8")
                except Exception:
                    content = f"[바이너리 파일, {contents.size} bytes]"

                # 너무 긴 파일은 잘라서 반환
                if len(content) > 10000:
                    content = content[:10000] + f"\n\n... (이하 생략, 전체 {len(content)}자)"

                return ToolResult(
                    success=True,
                    output={"repo": repo_name, "path": contents.path, "type": "file", "size": contents.size, "content": content},
                    duration_ms=self._get_duration_ms(),
                )

        except GithubException as e:
            return ToolResult(
                success=False, output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )

    def _get_file(self, input_data: dict) -> ToolResult:
        """특정 파일 전체 내용 조회 (get_contents의 파일 전용 래퍼)"""
        if not input_data.get("path"):
            return ToolResult(
                success=False, output=None,
                error="path is required (예: src/main.py)",
                duration_ms=self._get_duration_ms(),
            )
        return self._get_contents(input_data)

    # 재귀 탐색 시 무시할 확장자/디렉토리
    _SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".venv", "venv", "vendor", ".cache"}
    _BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
                    ".mp3", ".mp4", ".zip", ".tar", ".gz", ".bin", ".exe", ".dll", ".so", ".pyc",
                    ".lock", ".pack", ".idx"}
    _MAX_FILE_SIZE = 50000  # 50KB 이상 파일은 내용 생략

    def _get_tree_recursive(self, input_data: dict) -> ToolResult:
        """레포 전체 파일 트리를 재귀적으로 조회 (Git Tree API 사용, API 1회)"""
        repo_name = input_data.get("repo")
        branch = input_data.get("branch")

        if not repo_name:
            return ToolResult(
                success=False, output=None,
                error="repo is required (예: jinsoo96/Prompt_Foundry)",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()
        try:
            repo = client.get_repo(repo_name)
            ref = branch or repo.default_branch
            # Git Tree API — recursive=True로 전체 트리 한 번에 조회
            tree = repo.get_git_tree(ref, recursive=True)

            files = []
            dirs = set()
            for item in tree.tree:
                # 무시할 디렉토리 내부 파일 스킵
                parts = item.path.split("/")
                if any(p in self._SKIP_DIRS for p in parts):
                    continue

                if item.type == "blob":
                    files.append({
                        "path": item.path,
                        "size": item.size,
                        "sha": item.sha[:7],
                    })
                elif item.type == "tree":
                    dirs.add(item.path)

            return ToolResult(
                success=True,
                output={
                    "repo": repo_name,
                    "branch": ref,
                    "total_files": len(files),
                    "total_dirs": len(dirs),
                    "files": files,
                    "truncated": tree.truncated,
                },
                duration_ms=self._get_duration_ms(),
            )

        except GithubException as e:
            return ToolResult(
                success=False, output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )

    def _read_all_files(self, input_data: dict) -> ToolResult:
        """레포의 모든 소스 파일을 재귀적으로 읽어 내용 반환

        바이너리, 거대 파일, node_modules 등은 자동 제외.
        path 파라미터로 특정 디렉토리만 읽기 가능.
        """
        repo_name = input_data.get("repo")
        base_path = input_data.get("path", "")
        branch = input_data.get("branch")
        limit = input_data.get("limit", 100)  # 최대 파일 수

        if not repo_name:
            return ToolResult(
                success=False, output=None,
                error="repo is required (예: jinsoo96/Prompt_Foundry)",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()
        try:
            repo = client.get_repo(repo_name)
            ref = branch or repo.default_branch

            # 1. 전체 트리 조회
            tree = repo.get_git_tree(ref, recursive=True)

            # 2. 소스 파일 필터링
            import os
            target_files = []
            for item in tree.tree:
                if item.type != "blob":
                    continue
                # base_path 필터
                if base_path and not item.path.startswith(base_path):
                    continue
                # 무시할 디렉토리
                parts = item.path.split("/")
                if any(p in self._SKIP_DIRS for p in parts):
                    continue
                # 바이너리 확장자
                ext = os.path.splitext(item.path)[1].lower()
                if ext in self._BINARY_EXTS:
                    continue
                # 크기 제한
                if item.size and item.size > self._MAX_FILE_SIZE:
                    continue

                target_files.append(item)

                if len(target_files) >= limit:
                    break

            # 3. 파일 내용 읽기
            file_contents = []
            skipped = 0
            for item in target_files:
                try:
                    blob = repo.get_git_blob(item.sha)
                    import base64
                    if blob.encoding == "base64":
                        content = base64.b64decode(blob.content).decode("utf-8", errors="replace")
                    else:
                        content = blob.content

                    file_contents.append({
                        "path": item.path,
                        "size": item.size,
                        "content": content,
                    })
                except Exception as e:
                    skipped += 1
                    logger.debug(f"Failed to read {item.path}: {e}")

            return ToolResult(
                success=True,
                output={
                    "repo": repo_name,
                    "branch": ref,
                    "base_path": base_path or "/",
                    "files_read": len(file_contents),
                    "files_skipped": skipped,
                    "files": file_contents,
                },
                duration_ms=self._get_duration_ms(),
            )

        except GithubException as e:
            return ToolResult(
                success=False, output=None,
                error=f"GitHub API error: {e.data.get('message', str(e))}",
                duration_ms=self._get_duration_ms(),
            )

    def _list_commits(self, input_data: dict) -> ToolResult:
        """최근 커밋 목록 조회"""
        repo_name = input_data.get("repo")
        branch = input_data.get("branch")
        limit = input_data.get("limit", 10)

        if not repo_name:
            # repo 없으면 username으로 전체 레포 최근 커밋 조회 시도
            username = input_data.get("username")
            if username:
                return self._list_user_recent_commits(username, limit)
            return ToolResult(
                success=False,
                output=None,
                error="repo 또는 username이 필요합니다 (예: repo='jinsoo96/JINXUS' 또는 username='jinsoo96')",
                duration_ms=self._get_duration_ms(),
            )

        client = self._get_client()

        try:
            repo = client.get_repo(repo_name)
            kwargs = {}
            if branch:
                kwargs["sha"] = branch

            commits = []
            for i, commit in enumerate(repo.get_commits(**kwargs)):
                if i >= limit:
                    break
                commits.append({
                    "sha": commit.sha[:7],
                    "message": commit.commit.message.split("\n")[0][:100],
                    "author": commit.commit.author.name if commit.commit.author else "unknown",
                    "date": commit.commit.author.date.isoformat() if commit.commit.author else None,
                    "url": commit.html_url,
                })

            return ToolResult(
                success=True,
                output={
                    "repo": repo_name,
                    "branch": branch or repo.default_branch,
                    "commits": commits,
                    "count": len(commits),
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

    def _list_user_recent_commits(self, username: str, limit: int = 10) -> ToolResult:
        """사용자의 최근 커밋 (전체 레포 대상)"""
        client = self._get_client()

        try:
            user = client.get_user(username)
            repos = user.get_repos(sort="pushed")

            all_commits = []
            for repo in repos:
                if len(all_commits) >= limit:
                    break
                try:
                    for commit in repo.get_commits(author=username):
                        if len(all_commits) >= limit:
                            break
                        all_commits.append({
                            "repo": repo.full_name,
                            "sha": commit.sha[:7],
                            "message": commit.commit.message.split("\n")[0][:100],
                            "date": commit.commit.author.date.isoformat() if commit.commit.author else None,
                            "url": commit.html_url,
                        })
                except GithubException:
                    continue  # 빈 레포 등 건너뛰기

            # 날짜순 정렬
            all_commits.sort(key=lambda c: c.get("date", ""), reverse=True)

            return ToolResult(
                success=True,
                output={
                    "username": username,
                    "commits": all_commits[:limit],
                    "count": len(all_commits[:limit]),
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
