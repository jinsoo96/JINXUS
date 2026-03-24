"""JINXUS 자기 수정 도구 (SelfModifier) v2.1

JINXUS가 자신의 소스코드를 읽고, 안전하게 수정하고, 백엔드를 재시작한다.

v2.1 변경:
- 다중 언어 문법 검증: Python(AST), TS/JS(esbuild), Rust(rustfmt), JSON
- write_files: 여러 파일 병렬 쓰기 (각 파일 독립 검증)
- 툴 미설치 시 검증 스킵 (graceful degradation)

사용 흐름:
    1. read_file / list_source → 현재 코드 파악
    2. write_file (단일) 또는 write_files (복수, 병렬) → 수정
    3. restart_backend → 변경사항 반영
"""
import ast
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from .base import JinxTool, ToolResult

logger = logging.getLogger(__name__)

# PROJECT_ROOT: JINXUS 자기 수정 기준 경로
# WORKSPACE_ROOT: 신규 프로젝트 개발 허용 경로 (기본 /home/jinsookim)
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/home/jinsookim/jinxus")).resolve()
_WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", "/home/jinsookim")).resolve()
_DOCKER_SOCK = "/var/run/docker.sock"
_CONTAINER_NAME = "jinxus-backend"


# ── 언어별 검증기 ─────────────────────────────────────────────────────────────

async def _run_cmd(
    *args: str,
    cwd: Optional[str] = None,
    timeout: float = 30.0,
) -> tuple[Optional[bool], str]:
    """외부 커맨드 비동기 실행.

    Returns:
        (True, "")      정상
        (False, "err")  오류
        (None,  "msg")  명령어 없음 (FileNotFoundError) → 검증 스킵
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "검증 타임아웃"
        output = stdout.decode(errors="replace")[:2000]
        return proc.returncode == 0, output
    except FileNotFoundError:
        return None, "명령어 없음"
    except Exception as e:
        return False, str(e)


def _check_python(content: str) -> tuple[bool, Optional[str]]:
    try:
        ast.parse(content)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


def _check_json(content: str) -> tuple[bool, Optional[str]]:
    try:
        json.loads(content)
        return True, None
    except json.JSONDecodeError as e:
        return False, f"JSONDecodeError line {e.lineno}: {e.msg}"


async def _check_ts_js(content: str, suffix: str) -> tuple[Optional[bool], Optional[str]]:
    """TypeScript/TSX/JS/JSX → esbuild 문법 검증 (타입 체크 제외, 순수 syntax only).

    frontend/node_modules/.bin/esbuild 우선, 없으면 npx esbuild 다운로드.
    """
    local_esbuild = _PROJECT_ROOT / "frontend" / "node_modules" / ".bin" / "esbuild"

    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = f.name

    try:
        base_args = ["--bundle=false", "--platform=node", "--log-level=error"]
        if suffix in (".tsx", ".jsx"):
            base_args += ["--loader=tsx"]

        if local_esbuild.exists():
            cmd = [str(local_esbuild), tmp] + base_args
            ok, output = await _run_cmd(*cmd, timeout=10.0)
        else:
            cmd = ["npx", "--yes", "esbuild", tmp] + base_args
            ok, output = await _run_cmd(*cmd, timeout=60.0)

        if ok is None:
            return None, "esbuild 없음, 검증 생략"
        return ok, output if not ok else None
    finally:
        Path(tmp).unlink(missing_ok=True)


async def _check_rust(content: str) -> tuple[Optional[bool], Optional[str]]:
    """Rust → rustfmt --check 문법 검증.

    rustfmt exit code:
        0 = 포맷 OK
        1 = 포맷 차이 있음 (syntax는 OK)
        2 = 파싱 오류 (syntax 오류)
    """
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "rustfmt", "--check", "--edition", "2021", tmp,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20.0)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "rustfmt 타임아웃"
        output = stdout.decode(errors="replace")[:1000]

        if proc.returncode == 2:
            return False, f"Rust 파싱 오류:\n{output}"
        return True, None  # 0 (OK) or 1 (format diff) 모두 syntax는 유효
    except FileNotFoundError:
        return None, "rustfmt 없음, 검증 생략"
    finally:
        Path(tmp).unlink(missing_ok=True)


async def _validate_content(path: str, content: str) -> tuple[Optional[bool], Optional[str]]:
    """파일 확장자에 따라 적합한 검증기 선택.

    Returns:
        (True, None)    → 검증 통과
        (False, "err")  → 오류 (쓰기 거부)
        (None, "msg")   → 검증 툴 없음 (쓰기 허용, 경고만)
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        ok, err = _check_python(content)
        return ok, err
    elif suffix in (".ts", ".tsx", ".js", ".jsx"):
        return await _check_ts_js(content, suffix)
    elif suffix == ".rs":
        return await _check_rust(content)
    elif suffix == ".json":
        ok, err = _check_json(content)
        return ok, err
    else:
        return True, None  # TOML, YAML, MD 등 — 검증 없이 통과


# ── SelfModifier 도구 ─────────────────────────────────────────────────────────

class SelfModifier(JinxTool):
    """JINXUS 자기 소스코드 수정 + 재시작 도구"""

    name = "self_modifier"
    description = (
        "JINXUS 소스코드 수정 및 신규 프로젝트 개발 도구. "
        "PROJECT_ROOT(JINXUS 자기 수정) 및 WORKSPACE_ROOT(/home/jinsookim) 내부 경로 허용. "
        "Python(AST)/TS·JS(esbuild)/Rust(rustfmt)/JSON 문법 검증 후 쓰기. "
        "여러 파일 병렬 쓰기 지원(write_files). "
        "업무 완료 후에는 반드시 docs/dev_notes/YYYY-MM-DD_제목.md 에 업무 노트를 작성할 것 (의존 시스템·영향 파일 포함). "
        "actions: list_source, read_file, write_file, write_files, "
        "validate_syntax, restart_backend, git_status, git_commit"
    )
    allowed_agents = ["JX_CODER", "JX_BACKEND", "JX_INFRA", "JX_OPS"]

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_source",
                    "read_file",
                    "write_file",
                    "write_files",
                    "validate_syntax",
                    "restart_backend",
                    "git_status",
                    "git_commit",
                ],
                "description": (
                    "list_source: 소스 파일 목록 | "
                    "read_file: 파일 읽기 | "
                    "write_file: 단일 파일 쓰기(언어별 검증) | "
                    "write_files: 복수 파일 병렬 쓰기(각각 검증) | "
                    "validate_syntax: 문법 검증만 | "
                    "restart_backend: Docker 컨테이너 재시작 | "
                    "git_status: 변경 파일 목록 | "
                    "git_commit: 변경사항 커밋"
                ),
            },
            "path": {
                "type": "string",
                "description": "파일 경로 (상대 또는 절대). write_file, read_file, validate_syntax 사용",
            },
            "content": {
                "type": "string",
                "description": "쓸 내용. write_file, validate_syntax 사용",
            },
            "files": {
                "type": "array",
                "description": "write_files 사용. [{path: string, content: string}, ...]",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            "pattern": {
                "type": "string",
                "description": "glob 패턴 (list_source 사용, 기본: '**/*.py')",
            },
            "root_dir": {
                "type": "string",
                "description": "list_source 기준 디렉토리. 기본 PROJECT_ROOT. 신규 프로젝트는 '/home/jinsookim/my_project' 같이 절대 경로 지정.",
            },
            "message": {
                "type": "string",
                "description": "커밋 메시지 (git_commit 사용)",
            },
        },
        "required": ["action"],
    }

    def _safe_path(self, path: str) -> Optional[Path]:
        """PROJECT_ROOT 또는 WORKSPACE_ROOT 내부 경로인지 검증.

        - 상대 경로: PROJECT_ROOT 기준으로 해석
        - PROJECT_ROOT 또는 WORKSPACE_ROOT 내부면 허용
        """
        p = Path(path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        p = p.resolve()
        if str(p).startswith(str(_PROJECT_ROOT)):
            return p
        if str(p).startswith(str(_WORKSPACE_ROOT)):
            return p
        return None

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()
        action = input_data.get("action", "")

        if action == "list_source":
            return self._list_source(
                input_data.get("pattern", "**/*.py"),
                input_data.get("root_dir"),
            )
        elif action == "read_file":
            return self._read_file(input_data.get("path", ""))
        elif action == "write_file":
            return await self._write_file(
                input_data.get("path", ""),
                input_data.get("content", ""),
            )
        elif action == "write_files":
            return await self._write_files(input_data.get("files", []))
        elif action == "validate_syntax":
            return await self._validate_syntax(
                input_data.get("path", ""),
                input_data.get("content"),
            )
        elif action == "restart_backend":
            return await self._restart_backend()
        elif action == "git_status":
            return await self._git_status()
        elif action == "git_commit":
            return await self._git_commit(
                input_data.get("message", "auto: JINXUS self-modification")
            )
        else:
            return ToolResult(
                success=False, output=None,
                error=f"Unknown action: {action}",
                duration_ms=self._get_duration_ms(),
            )

    # ── 파일 목록 ──────────────────────────────────────────────────────────────

    def _list_source(self, pattern: str, root_dir: Optional[str] = None) -> ToolResult:
        """파일 목록 조회.

        Args:
            pattern: glob 패턴 (기본: '**/*.py')
            root_dir: 탐색 기준 디렉토리. None이면 PROJECT_ROOT.
                      절대/상대 경로 모두 허용 (WORKSPACE_ROOT 내부여야 함).
        """
        if root_dir:
            base = self._safe_path(root_dir)
            if not base:
                return ToolResult(
                    success=False, output=None,
                    error=f"접근 불가 경로: {root_dir}",
                    duration_ms=self._get_duration_ms(),
                )
            if not base.is_dir():
                return ToolResult(
                    success=False, output=None,
                    error=f"디렉토리 아님: {root_dir}",
                    duration_ms=self._get_duration_ms(),
                )
        else:
            base = _PROJECT_ROOT

        try:
            files = sorted(base.glob(pattern))
            _SKIP = ("__pycache__", "/.git/", "/node_modules/", "/.next/", "tsconfig.tsbuildinfo")
            filtered = [
                str(f.relative_to(base))
                for f in files
                if f.is_file() and not any(s in str(f) for s in _SKIP)
            ]
            return ToolResult(
                success=True,
                output={"files": filtered, "count": len(filtered), "root": str(base)},
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"[SelfModifier] list_source 실패: {e}")
            return ToolResult(
                success=False, output=None, error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ── 파일 읽기 ──────────────────────────────────────────────────────────────

    def _read_file(self, path: str) -> ToolResult:
        safe = self._safe_path(path)
        if not safe:
            return ToolResult(
                success=False, output=None,
                error=f"접근 불가 경로 (프로젝트 루트 외부): {path}",
                duration_ms=self._get_duration_ms(),
            )
        if not safe.exists():
            return ToolResult(
                success=False, output=None, error=f"파일 없음: {path}",
                duration_ms=self._get_duration_ms(),
            )
        try:
            content = safe.read_text(encoding="utf-8")
            return ToolResult(
                success=True,
                output={
                    "path": str(safe.relative_to(_PROJECT_ROOT)),
                    "content": content,
                    "lines": content.count("\n") + 1,
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"[SelfModifier] read_file 실패: {e}")
            return ToolResult(
                success=False, output=None, error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ── 문법 검증 ──────────────────────────────────────────────────────────────

    async def _validate_syntax(self, path: str, content: Optional[str] = None) -> ToolResult:
        if content is None:
            safe = self._safe_path(path)
            if not safe:
                return ToolResult(
                    success=False, output=None,
                    error=f"접근 불가 경로: {path}",
                    duration_ms=self._get_duration_ms(),
                )
            try:
                content = safe.read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult(
                    success=False, output=None, error=str(e),
                    duration_ms=self._get_duration_ms(),
                )

        ok, err = await _validate_content(path, content)
        lang = Path(path).suffix.lower() or "(알 수 없음)"

        if ok is None:
            return ToolResult(
                success=True,
                output={"valid": None, "message": err, "lang": lang},
                duration_ms=self._get_duration_ms(),
            )
        elif ok:
            return ToolResult(
                success=True,
                output={"valid": True, "lang": lang},
                duration_ms=self._get_duration_ms(),
            )
        else:
            return ToolResult(
                success=False,
                output={"valid": False, "lang": lang},
                error=err,
                duration_ms=self._get_duration_ms(),
            )

    # ── 파일 쓰기 (단일) ───────────────────────────────────────────────────────

    async def _write_file(self, path: str, content: str) -> ToolResult:
        safe = self._safe_path(path)
        if not safe:
            return ToolResult(
                success=False, output=None,
                error=f"접근 불가 경로 (프로젝트 루트 외부): {path}",
                duration_ms=self._get_duration_ms(),
            )

        ok, err = await _validate_content(path, content)
        lang = Path(path).suffix.lower()

        if ok is False:
            return ToolResult(
                success=False, output=None,
                error=f"[{lang}] 문법 오류로 쓰기 중단 → {err}",
                duration_ms=self._get_duration_ms(),
            )

        try:
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            rel = str(safe.relative_to(_PROJECT_ROOT))
            logger.info(f"[SelfModifier] 쓰기 완료: {rel}")

            msg = f"[{lang}] 쓰기 완료"
            if ok is None:
                msg += f" (검증 스킵: {err})"

            return ToolResult(
                success=True,
                output={
                    "path": rel,
                    "lines": content.count("\n") + 1,
                    "validation": "skipped" if ok is None else "passed",
                    "note": err if ok is None else None,
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"[SelfModifier] write_file 실패: {e}")
            return ToolResult(
                success=False, output=None, error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ── 파일 쓰기 (병렬) ───────────────────────────────────────────────────────

    async def _write_files(self, files: list[dict]) -> ToolResult:
        """여러 파일을 병렬로 검증 후 쓰기.

        각 파일은 독립적으로 검증되고, 실패한 파일만 거부된다.
        """
        if not files:
            return ToolResult(
                success=False, output=None, error="files 목록이 비어있음",
                duration_ms=self._get_duration_ms(),
            )

        # 1단계: 병렬 검증
        validate_tasks = [
            _validate_content(f.get("path", ""), f.get("content", ""))
            for f in files
        ]
        validations = await asyncio.gather(*validate_tasks, return_exceptions=True)

        # 2단계: 검증 결과 분류
        results = []
        write_tasks = []

        for i, (file_spec, val_result) in enumerate(zip(files, validations)):
            path = file_spec.get("path", "")
            content = file_spec.get("content", "")

            if isinstance(val_result, Exception):
                results.append({"path": path, "success": False, "error": str(val_result)})
                continue

            ok, err = val_result
            if ok is False:
                results.append({
                    "path": path,
                    "success": False,
                    "error": f"문법 오류: {err}",
                    "validation": "failed",
                })
            else:
                # 통과 or 스킵 → 쓰기 예정
                write_tasks.append((i, path, content, ok, err))

        # 3단계: 통과된 파일들 병렬 쓰기
        async def _do_write(path: str, content: str, val_ok: Optional[bool], val_note: Optional[str]):
            safe = self._safe_path(path)
            if not safe:
                return {"path": path, "success": False, "error": "접근 불가 경로"}
            try:
                safe.parent.mkdir(parents=True, exist_ok=True)
                safe.write_text(content, encoding="utf-8")
                rel = str(safe.relative_to(_PROJECT_ROOT))
                logger.info(f"[SelfModifier] 병렬 쓰기 완료: {rel}")
                return {
                    "path": rel,
                    "success": True,
                    "lines": content.count("\n") + 1,
                    "validation": "skipped" if val_ok is None else "passed",
                    "note": val_note if val_ok is None else None,
                }
            except Exception as e:
                return {"path": path, "success": False, "error": str(e)}

        write_results = await asyncio.gather(*[
            _do_write(path, content, ok, err)
            for _, path, content, ok, err in write_tasks
        ])

        # 결과 삽입 (원래 순서 유지)
        write_idx = 0
        for i, path, content, ok, err in write_tasks:
            results.insert(i, write_results[write_idx])
            write_idx += 1

        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count

        return ToolResult(
            success=fail_count == 0,
            output={
                "total": len(files),
                "success": success_count,
                "failed": fail_count,
                "results": results,
            },
            error=f"{fail_count}개 파일 실패" if fail_count > 0 else None,
            duration_ms=self._get_duration_ms(),
        )

    # ── 백엔드 재시작 ──────────────────────────────────────────────────────────

    async def _restart_backend(self) -> ToolResult:
        """Docker 소켓 API로 백엔드 컨테이너 재시작"""
        if not Path(_DOCKER_SOCK).exists():
            return ToolResult(
                success=False, output=None,
                error="Docker 소켓 없음 (/var/run/docker.sock 마운트 필요)",
                duration_ms=self._get_duration_ms(),
            )
        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK),
                timeout=30.0,
            ) as client:
                resp = await client.post(
                    f"http://localhost/containers/{_CONTAINER_NAME}/restart",
                    params={"t": 5},
                )

            if resp.status_code in (204, 200):
                logger.info("[SelfModifier] 백엔드 재시작 요청 완료")
                return ToolResult(
                    success=True,
                    output={"message": "재시작 요청 완료. 약 30초 후 복구됩니다."},
                    duration_ms=self._get_duration_ms(),
                )
            else:
                return ToolResult(
                    success=False, output=None,
                    error=f"Docker API 오류: HTTP {resp.status_code}",
                    duration_ms=self._get_duration_ms(),
                )
        except Exception as e:
            logger.error(f"[SelfModifier] restart_backend 실패: {e}")
            return ToolResult(
                success=False, output=None, error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    # ── Git ────────────────────────────────────────────────────────────────────

    async def _git_status(self) -> ToolResult:
        ok, output = await _run_cmd("git", "status", "--short", cwd=str(_PROJECT_ROOT))
        if ok is None:
            return ToolResult(
                success=False, output=None, error="git 없음",
                duration_ms=self._get_duration_ms(),
            )
        return ToolResult(
            success=True,
            output={"status": output.strip(), "cwd": str(_PROJECT_ROOT)},
            duration_ms=self._get_duration_ms(),
        )

    async def _git_commit(self, message: str) -> ToolResult:
        ok_add, err_add = await _run_cmd("git", "add", "-A", cwd=str(_PROJECT_ROOT))
        if ok_add is None:
            return ToolResult(
                success=False, output=None, error="git 없음",
                duration_ms=self._get_duration_ms(),
            )
        if not ok_add:
            return ToolResult(
                success=False, output=None,
                error=f"git add 실패: {err_add}",
                duration_ms=self._get_duration_ms(),
            )

        ok_commit, out_commit = await _run_cmd(
            "git", "commit", "-m", message, cwd=str(_PROJECT_ROOT),
        )
        if not ok_commit:
            if "nothing to commit" in out_commit:
                return ToolResult(
                    success=True,
                    output={"message": "커밋할 변경사항 없음"},
                    duration_ms=self._get_duration_ms(),
                )
            return ToolResult(
                success=False, output=None,
                error=f"git commit 실패: {out_commit}",
                duration_ms=self._get_duration_ms(),
            )

        return ToolResult(
            success=True,
            output={"message": "커밋 완료", "output": out_commit.strip()},
            duration_ms=self._get_duration_ms(),
        )
