"""ClaudeProcess — Claude Code CLI subprocess 관리

에이전트 하나 = ClaudeProcess 하나.
claude --print --output-format stream-json 으로 실행하고
stdout을 StreamParser로 실시간 파싱.

사용:
    process = ClaudeProcess(session_id="...", agent_name="JX_CODER", ...)
    await process.initialize()
    result = await process.execute("회원가입 API 만들어")
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jinxus.cli_engine.models import (
    ExecutionResult,
    ExecutionSummary,
    SessionStatus,
    StreamEvent,
    StreamEventType,
)
from jinxus.cli_engine.stream_parser import StreamParser
from jinxus.cli_engine.session_logger import (
    SessionLogger,
    get_session_logger,
    format_tool_detail,
)

logger = getLogger(__name__)

# Claude CLI 기본값
CLAUDE_DEFAULT_TIMEOUT = 21600.0  # 6시간
STDIO_BUFFER_LIMIT = 10 * 1024 * 1024  # 10MB


def find_claude_cli() -> Optional[str]:
    """Claude Code CLI 경로 탐색"""
    # npx 경로
    npx = shutil.which("npx")
    if npx:
        return npx
    # 직접 설치된 claude
    claude = shutil.which("claude")
    if claude:
        return claude
    return None


def build_claude_command(args: List[str]) -> List[str]:
    """Claude CLI 실행 커맨드 빌드"""
    cli_path = find_claude_cli()
    if not cli_path:
        raise RuntimeError(
            "Claude Code CLI not found. "
            "Install: npm install -g @anthropic-ai/claude-code"
        )
    if cli_path.endswith("npx"):
        return [cli_path, "-y", "@anthropic-ai/claude-code", *args]
    return [cli_path, *args]


class ClaudeProcess:

    def __init__(
        self,
        session_id: str,
        agent_name: str,
        working_dir: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        max_turns: int = 50,
        timeout: float = CLAUDE_DEFAULT_TIMEOUT,
        mcp_config: Optional[dict] = None,
        env_vars: Optional[dict] = None,
    ):
        self.session_id = session_id
        self.agent_name = agent_name
        self.working_dir = working_dir
        self.system_prompt = system_prompt
        self.model = model
        self.max_turns = max_turns
        self.timeout = timeout
        self.mcp_config = mcp_config
        self.env_vars = env_vars or {}

        self.status = SessionStatus.STARTING
        self.created_at = datetime.now()
        self.error_message: Optional[str] = None
        self.pid: Optional[int] = None

        self._conversation_id: Optional[str] = None
        self._execution_count: int = 0
        self._execution_lock = asyncio.Lock()
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._storage_path: Optional[str] = None

    @property
    def storage_path(self) -> Optional[str]:
        return self._storage_path

    def is_alive(self) -> bool:
        return self.status in (SessionStatus.RUNNING, SessionStatus.IDLE, SessionStatus.EXECUTING)

    async def initialize(self) -> bool:
        """세션 초기화 — 작업 디렉토리 + MCP 설정"""
        try:
            # 작업 디렉토리 확인/생성
            wd = Path(self.working_dir)
            wd.mkdir(parents=True, exist_ok=True)

            # 세션 스토리지 (로그, 작업 기록)
            self._storage_path = str(wd / ".jinxus_sessions" / self.session_id)
            Path(self._storage_path).mkdir(parents=True, exist_ok=True)

            # MCP 설정 파일 생성
            if self.mcp_config:
                mcp_path = wd / ".mcp.json"
                # 기존 설정이 있으면 병합
                existing = {}
                if mcp_path.exists():
                    try:
                        existing = json.loads(mcp_path.read_text())
                    except Exception:
                        pass
                merged = {**existing, **self.mcp_config}
                mcp_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))

            # CLI 존재 확인
            if not find_claude_cli():
                self.error_message = "Claude Code CLI not found"
                self.status = SessionStatus.ERROR
                return False

            self.status = SessionStatus.RUNNING
            logger.info(
                "[%s] ClaudeProcess initialized (agent=%s, dir=%s)",
                self.session_id, self.agent_name, self.working_dir,
            )
            return True

        except Exception as e:
            self.error_message = str(e)
            self.status = SessionStatus.ERROR
            logger.error("[%s] Initialize failed: %s", self.session_id, e)
            return False

    async def execute(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        resume: Optional[bool] = None,
        system_prompt: Optional[str] = None,
        max_turns: Optional[int] = None,
    ) -> ExecutionResult:
        """프롬프트 실행 — 핵심 메서드

        1. Claude CLI를 stream-json 모드로 실행
        2. stdin으로 프롬프트 전달
        3. stdout에서 실시간 파싱 (StreamParser)
        4. SessionLogger에 자동 기록
        5. ExecutionResult 반환
        """
        async with self._execution_lock:
            if self.status not in (SessionStatus.RUNNING, SessionStatus.IDLE):
                return ExecutionResult(
                    success=False,
                    session_id=self.session_id,
                    error=f"Session not running (status: {self.status.value})",
                )

            prev_status = self.status
            self.status = SessionStatus.EXECUTING
            start_time = time.time()

            # 세션 로거
            session_logger = get_session_logger(
                self.session_id, self.agent_name, create_if_missing=True
            )

            # 실시간 로깅 콜백
            def _realtime_log(event: StreamEvent):
                if on_event:
                    on_event(event)
                if session_logger:
                    session_logger.log_stream_event(event)

            parser = StreamParser(on_event=_realtime_log, session_id=self.session_id)

            try:
                # 커맨드 빌드
                args = [
                    "--print", "--verbose",
                    "--output-format", "stream-json",
                ]

                # Resume 판단
                should_resume = resume if resume is not None else (
                    self._execution_count > 0 and self._conversation_id is not None
                )
                if should_resume and self._conversation_id:
                    args.extend(["--resume", self._conversation_id])

                # Permission bypass (자율 실행)
                # --print 모드에서는 permission dialog가 자동 스킵되므로
                # root에서 --dangerously-skip-permissions 사용 불가 문제를 회피
                is_root = os.getuid() == 0 if hasattr(os, 'getuid') else False
                if not is_root:
                    skip_env = os.environ.get("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", "true")
                    if skip_env.lower() in ("true", "1", "yes"):
                        args.append("--dangerously-skip-permissions")

                # 모델
                effective_model = self.model or os.environ.get("ANTHROPIC_MODEL")
                if effective_model:
                    args.extend(["--model", effective_model])

                # Max turns
                effective_turns = max_turns or self.max_turns
                if effective_turns:
                    args.extend(["--max-turns", str(effective_turns)])

                # 시스템 프롬프트
                effective_prompt = system_prompt or self.system_prompt
                if effective_prompt:
                    args.extend(["--append-system-prompt", effective_prompt])

                cmd = build_claude_command(args)

                logger.info(
                    "[%s] Executing (agent=%s, prompt=%d chars, resume=%s)",
                    self.session_id, self.agent_name, len(prompt), should_resume,
                )

                if session_logger:
                    session_logger.log_command(prompt=prompt, max_turns=effective_turns)

                # 환경변수
                env = os.environ.copy()
                env.update(self.env_vars)
                # root에서 CLI 실행 시 이 환경변수가 있으면 에러 발생
                if is_root:
                    env.pop("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", None)

                # 프로세스 실행
                self._current_process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.working_dir,
                    env=env,
                    limit=STDIO_BUFFER_LIMIT,
                )
                self.pid = self._current_process.pid

                # 스트리밍 실행
                result = await self._stream_execute(
                    self._current_process,
                    prompt,
                    timeout or self.timeout,
                    parser,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                summary = parser.get_summary()

                # conversation_id 캡처 (다음 resume용)
                if summary.session_id:
                    self._conversation_id = summary.session_id

                if result["success"]:
                    self._execution_count += 1
                    logger.info(
                        "[%s] ✅ Execution #%d done (%dms, %d tools, $%.6f)",
                        self.session_id, self._execution_count,
                        duration_ms, len(summary.tool_calls), summary.total_cost_usd,
                    )

                exec_result = ExecutionResult(
                    success=result["success"],
                    session_id=self.session_id,
                    output=summary.final_output,
                    error=result.get("error") or summary.error_message,
                    duration_ms=duration_ms,
                    cost_usd=summary.total_cost_usd,
                    tool_calls=summary.tool_calls,
                    num_turns=summary.num_turns,
                    model=summary.model,
                )

                if session_logger:
                    session_logger.log_response(
                        success=exec_result.success,
                        output=exec_result.output,
                        error=exec_result.error,
                        duration_ms=duration_ms,
                        cost_usd=summary.total_cost_usd,
                    )
                    exec_result.file_changes = session_logger.extract_file_changes_from_cache()

                # Context Guard에 토큰 사용량 보고
                if summary.usage:
                    try:
                        from jinxus.core.context_guard import get_context_guard
                        guard = get_context_guard(summary.model or "default")
                        input_tokens = summary.usage.get("input_tokens", 0)
                        output_tokens = summary.usage.get("output_tokens", 0)
                        total_tokens = input_tokens + output_tokens
                        if total_tokens > 0:
                            guard.report_token_usage(total_tokens)
                    except Exception as e:
                        logger.warning(
                            "[%s] Context Guard 토큰 보고 실패: %s",
                            self.session_id, e,
                        )

                return exec_result

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error("[%s] Execution error: %s", self.session_id, e, exc_info=True)
                if session_logger:
                    session_logger.log_response(
                        success=False, error=str(e), duration_ms=duration_ms,
                    )
                return ExecutionResult(
                    success=False,
                    session_id=self.session_id,
                    error=str(e),
                    duration_ms=duration_ms,
                )
            finally:
                self._current_process = None
                self.status = SessionStatus.RUNNING if prev_status != SessionStatus.IDLE else SessionStatus.IDLE

    async def _stream_execute(
        self,
        process: asyncio.subprocess.Process,
        prompt: str,
        timeout: float,
        parser: StreamParser,
    ) -> dict:
        """stdin에 프롬프트 전달 + stdout 실시간 파싱"""
        stderr_lines: List[str] = []

        async def _read_stdout():
            while True:
                try:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str:
                        parser.parse_line(line_str)
                except Exception as e:
                    logger.warning("[%s] stdout read error: %s", self.session_id, e)
                    break

        async def _read_stderr():
            while True:
                try:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str:
                        stderr_lines.append(line_str)
                except Exception as e:
                    logger.warning("[%s] stderr read error: %s", self.session_id, e)
                    break

        try:
            # stdin에 프롬프트 쓰기
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()

            # stdout/stderr 동시 읽기 (타임아웃)
            await asyncio.wait_for(
                asyncio.gather(_read_stdout(), _read_stderr()),
                timeout=timeout,
            )

            # 프로세스 완료 대기
            await asyncio.wait_for(process.wait(), timeout=10.0)

        except asyncio.TimeoutError:
            logger.error("[%s] Execution timed out after %ss", self.session_id, timeout)
            await self._kill_process()
            return {"success": False, "error": f"Timeout after {timeout}s"}

        success = process.returncode == 0
        error = "\n".join(stderr_lines) if not success and stderr_lines else None

        return {"success": success, "error": error}

    async def _kill_process(self):
        """현재 실행 중인 프로세스 강제 종료"""
        if self._current_process:
            try:
                self._current_process.terminate()
                try:
                    await asyncio.wait_for(self._current_process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._current_process.kill()
                    await self._current_process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("[%s] Kill process error: %s", self.session_id, e)

    async def stop(self):
        """세션 종료"""
        await self._kill_process()
        self.status = SessionStatus.STOPPED
        logger.info("[%s] Session stopped", self.session_id)
