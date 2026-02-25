"""코드 실행 도구 - Claude Code CLI subprocess 기반"""
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from .base import JinxTool, ToolResult
from config import get_settings


class CodeExecutor(JinxTool):
    """Claude Code CLI를 통한 코드 실행 도구

    JX_CODER, JX_ANALYST 전용
    - 코드 작성 및 실행
    - 디버깅
    - 테스트 실행
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

    async def run(self, input_data: dict) -> ToolResult:
        """코드 실행

        Args:
            input_data: {
                "prompt": str,           # Claude Code에 전달할 프롬프트
                "timeout": int,          # 타임아웃 (초, 선택)
                "working_dir": str,      # 작업 디렉토리 (선택)
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

        # 작업 디렉토리 설정
        if working_dir:
            work_path = Path(working_dir)
        else:
            work_path = Path(tempfile.mkdtemp(dir=self._storage_path))

        work_path.mkdir(parents=True, exist_ok=True)

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

    async def _run_claude_code(
        self, prompt: str, working_dir: Path, timeout: int
    ) -> dict:
        """Claude Code CLI 실행"""
        settings = get_settings()

        # 환경 변수 설정
        env = os.environ.copy()
        if settings.claude_dangerously_skip_permissions:
            env["CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"] = "true"

        # claude 명령어 실행
        cmd = ["claude", "-p", prompt, "--yes"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": process.returncode or 0,
            }
        except asyncio.TimeoutError:
            process.kill()
            raise

    def _list_new_files(self, directory: Path) -> list[str]:
        """디렉토리 내 파일 목록"""
        files = []
        for item in directory.rglob("*"):
            if item.is_file():
                files.append(str(item.relative_to(directory)))
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

        try:
            process = await asyncio.create_subprocess_exec(
                "python3",
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
