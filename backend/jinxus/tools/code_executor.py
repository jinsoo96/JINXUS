"""코드 실행 도구 - Claude Code CLI subprocess 기반

claude_company 참고: 크로스 플랫폼 지원 + MCP 설정 자동 로딩 + 우아한 종료
"""
import asyncio
import json
import os
import platform
import signal
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# 플랫폼 감지
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# 버퍼 제한 (16MB)
STDIO_BUFFER_LIMIT = 16 * 1024 * 1024

# 긴 프롬프트 임계값 (stdin으로 전송)
LONG_PROMPT_THRESHOLD_WINDOWS = 2000
LONG_PROMPT_THRESHOLD_UNIX = 8000


def find_claude_executable() -> Optional[str]:
    """Claude CLI 실행 파일 경로 찾기

    Windows: .cmd, .bat 파일 명시적 검색
    Unix: PATH 탐색
    """
    if IS_WINDOWS:
        # Windows: npm global 경로 확인
        possible_paths = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.environ.get("LOCALAPPDATA", "")) / "npm" / "claude.cmd",
        ]
        for path in possible_paths:
            if path.exists():
                return str(path)

        # PATH에서 찾기
        return shutil.which("claude") or shutil.which("claude.cmd")
    else:
        # Unix: PATH 탐색
        return shutil.which("claude")


class CodeExecutor(JinxTool):
    """Claude Code CLI를 통한 코드 실행 도구

    JX_CODER, JX_ANALYST 전용
    - 코드 작성 및 실행
    - 디버깅
    - 테스트 실행
    - 크로스 플랫폼 지원 (Windows/macOS/Linux)
    - MCP 설정 자동 로딩
    """

    name = "code_executor"
    description = "Claude Code CLI를 통해 코드를 작성하고 실행합니다"
    allowed_agents = ["JX_CODER", "JX_ANALYST"]

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._storage_path = Path(settings.claude_code_storage)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._timeout = 300  # 기본 5분
        self._claude_path = find_claude_executable()
        self._current_process: Optional[asyncio.subprocess.Process] = None

    async def run(self, input_data: dict) -> ToolResult:
        """코드 실행

        Args:
            input_data: {
                "prompt": str,           # Claude Code에 전달할 프롬프트
                "timeout": int,          # 타임아웃 (초, 선택)
                "working_dir": str,      # 작업 디렉토리 (선택)
                "mcp_config": dict,      # MCP 설정 (선택)
            }

        Returns:
            ToolResult: {
                "code_output": str,      # 실행 결과
                "files_created": list,   # 생성된 파일 목록
                "exit_code": int,        # 종료 코드
            }
        """
        self._start_timer()

        prompt = input_data.get("prompt")
        if not prompt:
            return ToolResult(
                success=False,
                output=None,
                error="prompt is required",
                duration_ms=self._get_duration_ms(),
            )

        timeout = input_data.get("timeout", self._timeout)
        working_dir = input_data.get("working_dir")
        mcp_config = input_data.get("mcp_config")

        # 작업 디렉토리 설정
        if working_dir:
            work_path = Path(working_dir)
            # 경로 검증 (디렉토리 순회 공격 방지)
            if not self._validate_path(work_path):
                return ToolResult(
                    success=False,
                    output=None,
                    error="Invalid working directory path",
                    duration_ms=self._get_duration_ms(),
                )
        else:
            work_path = Path(tempfile.mkdtemp(dir=self._storage_path))

        work_path.mkdir(parents=True, exist_ok=True)

        # MCP 설정 파일 생성
        if mcp_config:
            self._write_mcp_config(work_path, mcp_config)

        try:
            # Claude Code CLI 실행
            result = await self._run_claude_code(prompt, work_path, timeout)

            # 생성된 파일 목록
            files_created = self._list_new_files(work_path)

            return ToolResult(
                success=result["exit_code"] == 0,
                output={
                    "code_output": result["stdout"],
                    "stderr": result["stderr"],
                    "files_created": files_created,
                    "exit_code": result["exit_code"],
                    "working_dir": str(work_path),
                },
                error=result["stderr"] if result["exit_code"] != 0 else None,
                duration_ms=self._get_duration_ms(),
            )

        except asyncio.TimeoutError:
            await self._kill_current_process()
            return ToolResult(
                success=False,
                output=None,
                error=f"Timeout after {timeout} seconds",
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def _validate_path(self, path: Path) -> bool:
        """경로 검증 (디렉토리 순회 공격 방지)"""
        try:
            # 절대 경로로 변환
            abs_path = path.resolve()
            # storage 경로 내부인지 확인
            return str(abs_path).startswith(str(self._storage_path.resolve()))
        except Exception:
            return False

    def _write_mcp_config(self, working_dir: Path, config: dict) -> None:
        """MCP 설정 파일 생성"""
        mcp_file = working_dir / ".mcp.json"
        mcp_file.write_text(json.dumps(config, indent=2))
        logger.debug(f"MCP config written to {mcp_file}")

    async def _run_claude_code(
        self, prompt: str, working_dir: Path, timeout: int
    ) -> dict:
        """Claude Code CLI 실행 (크로스 플랫폼)"""
        settings = get_settings()

        # 환경 변수 설정
        env = os.environ.copy()
        if settings.claude_dangerously_skip_permissions:
            env["CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"] = "true"

        # Claude CLI 경로 확인
        claude_cmd = self._claude_path or "claude"

        # 명령어 구성
        cmd = [claude_cmd, "-p", prompt, "--yes"]

        # 긴 프롬프트는 stdin으로 전송
        use_stdin = False
        threshold = LONG_PROMPT_THRESHOLD_WINDOWS if IS_WINDOWS else LONG_PROMPT_THRESHOLD_UNIX
        if len(prompt) > threshold:
            cmd = [claude_cmd, "--yes"]  # -p 제거
            use_stdin = True

        # 플랫폼별 프로세스 생성
        if IS_WINDOWS:
            # Windows: cmd.exe 래퍼
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(working_dir),
                stdin=asyncio.subprocess.PIPE if use_stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=STDIO_BUFFER_LIMIT,
                # Windows 전용
                # startupinfo=startupinfo,
                # creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            # Unix (macOS, Linux)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(working_dir),
                stdin=asyncio.subprocess.PIPE if use_stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=STDIO_BUFFER_LIMIT,
            )

        self._current_process = process

        try:
            # stdin으로 프롬프트 전송
            stdin_data = prompt.encode("utf-8") if use_stdin else None

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=stdin_data),
                timeout=timeout,
            )

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": process.returncode or 0,
            }
        except asyncio.TimeoutError:
            await self._kill_current_process()
            raise
        finally:
            self._current_process = None

    async def _kill_current_process(self) -> None:
        """현재 프로세스 우아한 종료

        1. terminate() (SIGTERM)
        2. 5초 대기
        3. kill() (SIGKILL)
        """
        if self._current_process is None:
            return

        process = self._current_process

        try:
            # 1단계: 우아한 종료 시도
            process.terminate()

            try:
                # 5초 대기
                await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.debug("Process terminated gracefully")
            except asyncio.TimeoutError:
                # 2단계: 강제 종료
                process.kill()
                await process.wait()
                logger.warning("Process killed forcefully")

        except Exception as e:
            logger.error(f"Failed to kill process: {e}")

    def _list_new_files(self, directory: Path) -> list[str]:
        """디렉토리 내 파일 목록"""
        files = []
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    files.append(str(item.relative_to(directory)))
        except Exception as e:
            logger.warning(f"Failed to list files: {e}")
        return files

    async def execute_python(self, code: str, working_dir: Optional[Path] = None) -> ToolResult:
        """Python 코드 직접 실행 (간단한 케이스용)"""
        self._start_timer()

        if working_dir is None:
            working_dir = Path(tempfile.mkdtemp(dir=self._storage_path))

        working_dir.mkdir(parents=True, exist_ok=True)

        # 코드 파일 생성
        code_file = working_dir / "script.py"
        code_file.write_text(code)

        # Python 실행 파일 찾기
        python_cmd = "python3" if not IS_WINDOWS else "python"

        try:
            process = await asyncio.create_subprocess_exec(
                python_cmd,
                str(code_file),
                cwd=str(working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )

            return ToolResult(
                success=process.returncode == 0,
                output={
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "exit_code": process.returncode,
                },
                error=stderr.decode("utf-8") if process.returncode != 0 else None,
                duration_ms=self._get_duration_ms(),
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output=None,
                error="Python execution timeout",
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def cleanup_session(self, working_dir: Path) -> None:
        """세션 디렉토리 정리"""
        if working_dir.exists() and working_dir.is_dir():
            shutil.rmtree(working_dir)

    def list_storage_files(self) -> list[dict]:
        """스토리지 내 모든 세션 파일 목록"""
        sessions = []
        for session_dir in self._storage_path.iterdir():
            if session_dir.is_dir():
                files = self._list_new_files(session_dir)
                sessions.append({
                    "session_id": session_dir.name,
                    "files": files,
                    "path": str(session_dir),
                })
        return sessions

    def read_storage_file(self, session_id: str, file_path: str) -> Optional[str]:
        """스토리지 파일 읽기 (경로 검증 포함)"""
        session_path = self._storage_path / session_id
        file_full_path = session_path / file_path

        # 경로 검증 (디렉토리 순회 공격 방지)
        try:
            resolved = file_full_path.resolve()
            if not str(resolved).startswith(str(session_path.resolve())):
                logger.warning(f"Path traversal attempt: {file_path}")
                return None
        except Exception:
            return None

        if file_full_path.exists() and file_full_path.is_file():
            return file_full_path.read_text(encoding="utf-8", errors="replace")
        return None

    def cleanup_all_sessions(self) -> int:
        """모든 세션 정리"""
        count = 0
        for session_dir in self._storage_path.iterdir():
            if session_dir.is_dir():
                shutil.rmtree(session_dir)
                count += 1
        return count
