"""Subprocess Manager v1.0.0 — 장기 프로세스 관리

서버, 빌드, 테스트 실행기 등 장기 실행 프로세스를 관리한다.

기능:
- 프로세스 시작/중지/재시작
- 실시간 로그 스트리밍
- 헬스체크 (HTTP / 프로세스 존재)
- 자동 정리 (종료된 프로세스)
- 포트 충돌 감지

에이전트(JX_CODER, JX_OPS 등)가 도구를 통해 호출.
"""
import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ProcessStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class ManagedProcess:
    """관리되는 프로세스"""
    id: str
    name: str                         # 식별 이름 (예: "dev-server")
    command: str                      # 실행 명령
    cwd: str = ""                     # 작업 디렉토리
    env: dict = field(default_factory=dict)  # 추가 환경변수
    status: ProcessStatus = ProcessStatus.STOPPED
    pid: int | None = None
    port: int | None = None           # 사용 포트 (헬스체크용)
    started_at: str = ""
    stopped_at: str = ""
    exit_code: int | None = None
    error: str = ""
    restart_count: int = 0
    auto_restart: bool = False        # 비정상 종료 시 자동 재시작
    max_restarts: int = 3             # 최대 자동 재시작 횟수
    # 로그 버퍼 (최근 N줄)
    log_buffer: list[str] = field(default_factory=list)
    _log_buffer_max: int = 500


# 허용된 작업 디렉토리 (보안)
_ALLOWED_DIRS = [
    "/home/jinsookim/jinxus",
    "/tmp",
]

# 차단 명령어 패턴 (보안)
_BLOCKED_COMMANDS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "chmod 777 /",
]


class SubprocessManager:
    """장기 프로세스 관리자

    asyncio.subprocess로 프로세스를 관리하며,
    stdout/stderr를 비동기로 읽어 로그 버퍼에 저장.
    """

    def __init__(self, max_processes: int = 10):
        self._processes: dict[str, ManagedProcess] = {}
        self._async_processes: dict[str, asyncio.subprocess.Process] = {}
        self._log_tasks: dict[str, asyncio.Task] = {}
        self._max_processes = max_processes

    async def start_process(
        self,
        process_id: str,
        name: str,
        command: str,
        cwd: str = "",
        env: dict | None = None,
        port: int | None = None,
        auto_restart: bool = False,
    ) -> ManagedProcess:
        """프로세스 시작

        Args:
            process_id: 고유 ID
            name: 식별 이름
            command: 실행 명령
            cwd: 작업 디렉토리
            env: 추가 환경변수
            port: 사용 포트 (헬스체크용)
            auto_restart: 비정상 종료 시 자동 재시작

        Returns:
            ManagedProcess
        """
        # 보안 검증
        self._validate_command(command)
        if cwd:
            self._validate_cwd(cwd)

        # 동시 프로세스 수 제한
        running = sum(
            1 for p in self._processes.values()
            if p.status in (ProcessStatus.RUNNING, ProcessStatus.STARTING)
        )
        if running >= self._max_processes:
            raise RuntimeError(
                f"최대 동시 프로세스 수({self._max_processes})에 도달했습니다"
            )

        # 포트 충돌 확인
        if port:
            for p in self._processes.values():
                if p.port == port and p.status == ProcessStatus.RUNNING:
                    raise RuntimeError(f"포트 {port}이 이미 사용 중: {p.name}")

        # 기존 프로세스 정리
        if process_id in self._processes:
            await self.stop_process(process_id)

        managed = ManagedProcess(
            id=process_id,
            name=name,
            command=command,
            cwd=cwd or os.getcwd(),
            env=env or {},
            status=ProcessStatus.STARTING,
            port=port,
            auto_restart=auto_restart,
            started_at=datetime.now().isoformat(),
        )
        self._processes[process_id] = managed

        try:
            # 환경변수 병합
            process_env = os.environ.copy()
            process_env.update(managed.env)

            # 프로세스 시작
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=managed.cwd,
                env=process_env,
                preexec_fn=os.setsid,  # 새 프로세스 그룹 생성
            )

            self._async_processes[process_id] = proc
            managed.pid = proc.pid
            managed.status = ProcessStatus.RUNNING

            # 로그 수집 태스크 시작
            log_task = asyncio.create_task(
                self._collect_logs(process_id, proc)
            )
            self._log_tasks[process_id] = log_task

            logger.info(
                f"[SubprocessManager] 프로세스 시작: {name} "
                f"(PID={proc.pid}, port={port})"
            )
            return managed

        except Exception as e:
            managed.status = ProcessStatus.FAILED
            managed.error = str(e)
            logger.error(f"[SubprocessManager] 프로세스 시작 실패: {name} - {e}")
            raise

    async def stop_process(self, process_id: str, timeout: int = 10) -> bool:
        """프로세스 중지

        SIGTERM → timeout 대기 → SIGKILL
        """
        managed = self._processes.get(process_id)
        if not managed:
            return False

        proc = self._async_processes.get(process_id)
        if not proc or proc.returncode is not None:
            managed.status = ProcessStatus.STOPPED
            managed.stopped_at = datetime.now().isoformat()
            return True

        try:
            # SIGTERM으로 정상 종료 시도
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                # 이미 종료됨 — wait만 수행
                pass

            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                # 정상 종료 실패 → SIGKILL
                logger.warning(
                    f"[SubprocessManager] SIGTERM 타임아웃, SIGKILL: {managed.name}"
                )
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await proc.wait()

            managed.status = ProcessStatus.STOPPED
            managed.stopped_at = datetime.now().isoformat()
            managed.exit_code = proc.returncode

            # 로그 수집 태스크 정리
            log_task = self._log_tasks.pop(process_id, None)
            if log_task and not log_task.done():
                log_task.cancel()

            self._async_processes.pop(process_id, None)

            logger.info(
                f"[SubprocessManager] 프로세스 중지: {managed.name} "
                f"(exit_code={proc.returncode})"
            )
            return True

        except ProcessLookupError:
            managed.status = ProcessStatus.STOPPED
            managed.stopped_at = datetime.now().isoformat()
            return True
        except Exception as e:
            managed.error = str(e)
            logger.error(f"[SubprocessManager] 프로세스 중지 실패: {e}")
            return False

    async def restart_process(self, process_id: str) -> ManagedProcess:
        """프로세스 재시작"""
        managed = self._processes.get(process_id)
        if not managed:
            raise ValueError(f"프로세스를 찾을 수 없습니다: {process_id}")

        managed.status = ProcessStatus.RESTARTING
        managed.restart_count += 1

        await self.stop_process(process_id)

        return await self.start_process(
            process_id=process_id,
            name=managed.name,
            command=managed.command,
            cwd=managed.cwd,
            env=managed.env,
            port=managed.port,
            auto_restart=managed.auto_restart,
        )

    def get_process(self, process_id: str) -> Optional[ManagedProcess]:
        """프로세스 조회"""
        return self._processes.get(process_id)

    def get_all_processes(self) -> list[ManagedProcess]:
        """모든 프로세스 조회"""
        return list(self._processes.values())

    def get_logs(self, process_id: str, lines: int = 100) -> list[str]:
        """프로세스 로그 조회 (최근 N줄)"""
        managed = self._processes.get(process_id)
        if not managed:
            return []
        return managed.log_buffer[-lines:]

    async def health_check(self, process_id: str) -> dict:
        """프로세스 헬스체크

        1. 프로세스 존재 확인
        2. HTTP 포트 응답 확인 (port가 설정된 경우)
        """
        managed = self._processes.get(process_id)
        if not managed:
            return {"healthy": False, "reason": "프로세스 없음"}

        proc = self._async_processes.get(process_id)
        if not proc or proc.returncode is not None:
            return {"healthy": False, "reason": "프로세스 종료됨"}

        result = {
            "healthy": True,
            "pid": managed.pid,
            "status": managed.status.value,
            "uptime_s": 0,
        }

        # 업타임 계산
        if managed.started_at:
            try:
                started = datetime.fromisoformat(managed.started_at)
                result["uptime_s"] = round(
                    (datetime.now() - started).total_seconds(), 1
                )
            except ValueError:
                pass

        # HTTP 헬스체크
        if managed.port:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://localhost:{managed.port}/",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        result["http_status"] = resp.status
                        result["http_healthy"] = resp.status < 500
            except ImportError:
                # aiohttp 없으면 TCP 연결만 확인
                writer = None
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection("localhost", managed.port),
                        timeout=3,
                    )
                    result["http_healthy"] = True
                except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                    result["http_healthy"] = False
                except Exception:
                    result["http_healthy"] = False
                finally:
                    if writer:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception as e:
                            logger.debug(f"Writer close 실패: {e}")
            except Exception:
                result["http_healthy"] = False

        return result

    async def cleanup_stopped(self) -> int:
        """종료된 프로세스 정리"""
        to_remove = []
        for pid, managed in self._processes.items():
            if managed.status in (ProcessStatus.STOPPED, ProcessStatus.FAILED):
                to_remove.append(pid)

        for pid in to_remove:
            self._processes.pop(pid, None)
            self._async_processes.pop(pid, None)
            log_task = self._log_tasks.pop(pid, None)
            if log_task and not log_task.done():
                log_task.cancel()

        return len(to_remove)

    async def stop_all(self):
        """모든 프로세스 중지 (서버 종료 시 호출)"""
        for pid in list(self._processes.keys()):
            try:
                await self.stop_process(pid, timeout=5)
            except Exception as e:
                logger.warning(f"[SubprocessManager] 종료 실패: {pid} - {e}")

    async def _collect_logs(
        self,
        process_id: str,
        proc: asyncio.subprocess.Process,
    ):
        """프로세스 stdout을 비동기로 수집"""
        managed = self._processes.get(process_id)
        if not managed or not proc.stdout:
            return

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue

                managed.log_buffer.append(text)
                # 버퍼 크기 제한
                if len(managed.log_buffer) > managed._log_buffer_max:
                    managed.log_buffer = managed.log_buffer[-managed._log_buffer_max:]

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[SubprocessManager] 로그 수집 오류: {e}")
        finally:
            # 프로세스 종료 감지
            if proc.returncode is not None:
                managed.exit_code = proc.returncode
                managed.stopped_at = datetime.now().isoformat()

                if proc.returncode == 0:
                    managed.status = ProcessStatus.STOPPED
                else:
                    managed.status = ProcessStatus.FAILED
                    managed.error = f"exit code: {proc.returncode}"

                    # 자동 재시작
                    if (
                        managed.auto_restart
                        and managed.restart_count < managed.max_restarts
                    ):
                        logger.info(
                            f"[SubprocessManager] 자동 재시작: {managed.name} "
                            f"({managed.restart_count + 1}/{managed.max_restarts})"
                        )
                        try:
                            await self.restart_process(process_id)
                        except Exception as re_err:
                            logger.error(
                                f"[SubprocessManager] 자동 재시작 실패: {re_err}"
                            )

    @staticmethod
    def _validate_command(command: str):
        """명령어 보안 검증"""
        for blocked in _BLOCKED_COMMANDS:
            if blocked in command:
                raise ValueError(f"차단된 명령어: {blocked}")

    @staticmethod
    def _validate_cwd(cwd: str):
        """작업 디렉토리 보안 검증"""
        abs_cwd = os.path.abspath(cwd)
        if not any(abs_cwd.startswith(d) for d in _ALLOWED_DIRS):
            raise ValueError(
                f"허용되지 않는 작업 디렉토리: {cwd} "
                f"(허용: {_ALLOWED_DIRS})"
            )


# 싱글톤
_instance: SubprocessManager | None = None


def get_subprocess_manager() -> SubprocessManager:
    global _instance
    if _instance is None:
        _instance = SubprocessManager()
    return _instance
