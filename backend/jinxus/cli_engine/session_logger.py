"""SessionLogger — 세션별 실시간 로그 시스템

3계층 저장: 인메모리 캐시 → DB → 파일
- 캐시: 200ms 폴링으로 실시간 UI 전달 (휘발)
- 파일: JSONL로 영속 저장 (세션별 로그 파일)
- DB: MetaStore에 실행 결과 저장 (agent_task_logs)

핵심 메서드: get_cache_entries_since(cursor) — 200ms 폴링용

사용 흐름:
    logger = get_session_logger(session_id)
    logger.log_tool_use("Bash", {"command": "npm test"})
    new_entries, cursor = logger.get_cache_entries_since(old_cursor)
"""
import json
import os
import re
import threading
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from jinxus.cli_engine.models import LogEntry, LogLevel, StreamEvent, StreamEventType

_logger = getLogger(__name__)

# 캐시 최대 엔트리 (Geny: 1000)
MAX_CACHE_SIZE = 1000

# 로그 파일 디렉토리
LOG_DIR = Path(os.environ.get("PROJECT_ROOT", "/app")) / "data" / "cli_logs"


class SessionLogger:

    def __init__(self, session_id: str, agent_name: str = "unknown"):
        self._session_id = session_id
        self._agent_name = agent_name
        self._cache: List[LogEntry] = []
        self._lock = threading.Lock()
        self._log_file: Optional[Path] = None
        self._init_log_file()

    @property
    def session_id(self) -> str:
        return self._session_id

    def _init_log_file(self):
        """세션별 JSONL 로그 파일 초기화"""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            self._log_file = LOG_DIR / f"{self._agent_name}_{date_str}_{self._session_id[:8]}.jsonl"
        except Exception as e:
            _logger.debug("Log file init failed: %s", e)

    # ── Core logging ──────────────────────────────────────────────

    def _append(self, level: LogLevel, message: str, metadata: Optional[dict] = None):
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            metadata=metadata,
        )
        with self._lock:
            self._cache.append(entry)
            if len(self._cache) > MAX_CACHE_SIZE:
                self._cache = self._cache[-MAX_CACHE_SIZE:]

        # 파일에도 기록 (비동기 아님, 경량 JSONL append)
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                pass  # 파일 쓰기 실패는 무시 (캐시가 주력)

    def info(self, message: str, metadata: dict = None):
        self._append(LogLevel.INFO, message, metadata)

    def error(self, message: str, metadata: dict = None):
        self._append(LogLevel.ERROR, message, metadata)

    def warning(self, message: str, metadata: dict = None):
        self._append(LogLevel.WARNING, message, metadata)

    # ── Command / Response logging ────────────────────────────────

    def log_command(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        system_prompt: Optional[str] = None,
        max_turns: Optional[int] = None,
    ):
        self._append(LogLevel.COMMAND, prompt[:500], {
            "timeout": timeout,
            "system_prompt_len": len(system_prompt) if system_prompt else 0,
            "max_turns": max_turns,
        })

    def log_response(
        self,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ):
        msg = output[:300] if output else (error[:300] if error else "")
        self._append(LogLevel.RESPONSE, msg, {
            "success": success,
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
        })

    # ── Tool logging (StreamParser 콜백에서 호출) ──────────────────

    def log_tool_use(
        self,
        tool_name: str,
        tool_input: Optional[dict] = None,
        tool_id: Optional[str] = None,
    ):
        detail = format_tool_detail(tool_name, tool_input or {})
        self._append(LogLevel.TOOL, f"{tool_name}: {detail}", {
            "tool_name": tool_name,
            "tool_input": _truncate_input(tool_input),
            "tool_id": tool_id,
        })

    def log_tool_result(
        self,
        tool_name: str,
        output: Optional[str] = None,
        is_error: bool = False,
    ):
        preview = (output or "")[:200]
        self._append(LogLevel.TOOL_RES, f"{tool_name}: {preview}", {
            "tool_name": tool_name,
            "is_error": is_error,
            "preview": preview,
        })

    # ── Stream event logging ──────────────────────────────────────

    def log_stream_event(self, event: StreamEvent):
        """StreamParser 콜백에서 호출 — 이벤트 타입별 분기"""
        if event.event_type == StreamEventType.SYSTEM_INIT:
            self._append(LogLevel.STREAM, "system_init", {
                "model": event.model,
                "tools_count": len(event.tools or []),
                "mcp_servers": event.mcp_servers,
            })
        elif event.event_type == StreamEventType.TOOL_USE:
            if event.tool_name:
                self.log_tool_use(event.tool_name, event.tool_input, event.tool_use_id)
        elif event.event_type == StreamEventType.ASSISTANT_MESSAGE:
            if event.tool_name:
                self.log_tool_use(event.tool_name, event.tool_input, event.tool_use_id)
            if event.text:
                self._append(LogLevel.STREAM, "assistant_text", {
                    "text_preview": event.text[:200],
                    "text_length": len(event.text),
                })
        elif event.event_type == StreamEventType.CONTENT_BLOCK_DELTA:
            # 텍스트 델타는 개별 로그하면 너무 많으므로 캐시만 기록
            if event.text and len(event.text) > 10:
                self._append(LogLevel.STREAM, "text_delta", {
                    "text_preview": event.text[:100],
                })
        elif event.event_type == StreamEventType.TOOL_RESULT:
            # 도구 실행 결과
            tool_output = event.tool_output or ""
            is_error = event.is_error or False
            tool_name = event.tool_name or "unknown"
            self.log_tool_result(tool_name, tool_output[:200], is_error)
        elif event.event_type == StreamEventType.RESULT:
            self._append(LogLevel.STREAM, "result", {
                "success": not event.is_error,
                "duration_ms": event.duration_ms,
                "cost_usd": event.total_cost_usd,
                "num_turns": event.num_turns,
            })

    # ── Session lifecycle ─────────────────────────────────────────

    def log_session_event(self, event_name: str, metadata: dict = None):
        self._append(LogLevel.INFO, f"session:{event_name}", metadata)

    # ── Cache query (실시간 폴링용) ──────────────────────────────

    def get_cache_length(self) -> int:
        with self._lock:
            return len(self._cache)

    def get_cache_entries_since(self, cursor: int) -> Tuple[List[LogEntry], int]:
        """cursor 위치 이후의 새 엔트리 반환.

        Returns:
            (new_entries, new_cursor)
        """
        with self._lock:
            current_len = len(self._cache)
            if cursor >= current_len:
                return [], current_len
            entries = self._cache[cursor:current_len]
            return entries, current_len

    def get_logs(
        self,
        limit: int = 100,
        level: Optional[Union[LogLevel, Set[LogLevel]]] = None,
        offset: int = 0,
        newest_first: bool = True,
    ) -> List[dict]:
        with self._lock:
            entries = list(self._cache)

        if level:
            if isinstance(level, set):
                entries = [e for e in entries if e.level in level]
            else:
                entries = [e for e in entries if e.level == level]

        if newest_first:
            entries = list(reversed(entries))

        entries = entries[offset:offset + limit]
        return [e.to_dict() for e in entries]

    # ── File change extraction ────────────────────────────────────

    def extract_file_changes_from_cache(self, since_cursor: int = 0) -> List[dict]:
        """도구 로그에서 파일 변경 추출.

        Returns:
            [{"file": "server.py", "op": "edit", "lines": 5}, ...]
        """
        with self._lock:
            entries = self._cache[since_cursor:]

        changes = []
        for entry in entries:
            if entry.level not in (LogLevel.TOOL, LogLevel.TOOL_RES):
                continue
            meta = entry.metadata or {}
            tool_name = meta.get("tool_name", "")
            tool_input = meta.get("tool_input", {})

            if not tool_name or not tool_input:
                continue

            change = _extract_file_change(tool_name, tool_input)
            if change:
                changes.append(change)

        # Deduplicate by file path
        seen = set()
        unique = []
        for c in changes:
            key = f"{c['file']}:{c['op']}"
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique


# ============================================================================
# Global registry
# ============================================================================

_loggers: Dict[str, SessionLogger] = {}
_registry_lock = threading.Lock()


def get_session_logger(
    session_id: str,
    agent_name: str = "unknown",
    create_if_missing: bool = True,
) -> Optional[SessionLogger]:
    with _registry_lock:
        sl = _loggers.get(session_id)
        if sl is None and create_if_missing:
            sl = SessionLogger(session_id, agent_name)
            _loggers[session_id] = sl
        return sl


def remove_session_logger(session_id: str):
    with _registry_lock:
        _loggers.pop(session_id, None)


def list_session_loggers() -> List[str]:
    with _registry_lock:
        return list(_loggers.keys())


# ============================================================================
# Helpers
# ============================================================================

def format_tool_detail(tool_name: str, tool_input: dict) -> str:
    """도구 입력을 1줄 프리뷰로 포맷"""
    if not tool_input:
        return "(no input)"

    name_lower = tool_name.lower()

    # Bash/Shell
    if name_lower in ("bash", "shell", "execute"):
        cmd = tool_input.get("command", tool_input.get("cmd", ""))
        if cmd:
            return f"`{cmd[:120]}`" if len(cmd) > 120 else f"`{cmd}`"

    # Read
    if name_lower in ("read", "readfile", "read_file", "view"):
        fp = tool_input.get("file_path", tool_input.get("path", ""))
        if fp:
            fname = fp.rsplit("/", 1)[-1]
            offset = tool_input.get("offset", tool_input.get("start_line", ""))
            limit = tool_input.get("limit", tool_input.get("end_line", ""))
            if offset and limit:
                return f"{fname} (lines {offset}-{int(offset)+int(limit)})"
            return fname

    # Write/Edit
    if name_lower in ("write", "edit", "edit_file", "write_file"):
        fp = tool_input.get("file_path", tool_input.get("path", ""))
        if fp:
            fname = fp.rsplit("/", 1)[-1]
            content = tool_input.get("content", tool_input.get("new_string", ""))
            if content:
                lines = content.count("\n") + 1
                return f"{fname} ({lines} lines)"
            return fname

    # Glob
    if name_lower in ("glob", "find", "list", "ls"):
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        if pattern:
            return f"`{pattern[:80]}`"

    # Grep
    if name_lower in ("grep", "ripgrep", "rg"):
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        result = f"`{pattern[:50]}`" if pattern else ""
        if path:
            result += f" in {path.rsplit('/', 1)[-1]}"
        return result

    # MCP tools
    if "__" in tool_name:
        for key in ("query", "path", "file_path", "command", "url", "content", "message"):
            if key in tool_input:
                val = str(tool_input[key])
                return f"{key}={val[:100]}" if len(val) > 100 else f"{key}={val}"

    # Fallback: first parameter
    for key, val in tool_input.items():
        if key.startswith("_"):
            continue
        val_str = str(val)
        return f"{key}={val_str[:100]}" if len(val_str) > 100 else f"{key}={val_str}"

    return "(empty)"


def extract_thinking_preview(entry: LogEntry) -> Optional[str]:
    """로그 엔트리에서 UI에 보여줄 1줄 프리뷰 추출.

    TOOL → "🔧 Bash: `npm test`"
    TOOL_RES → "🔧 Read: server.py (42 lines)"
    """
    level = entry.level
    meta = entry.metadata or {}

    if level == LogLevel.COMMAND or level == LogLevel.RESPONSE:
        return None

    if level == LogLevel.TOOL:
        tool_name = meta.get("tool_name", "")
        if tool_name:
            detail = format_tool_detail(tool_name, meta.get("tool_input", {}))
            return f"🔧 {tool_name}: {detail}"
        return None

    if level == LogLevel.TOOL_RES:
        tool_name = meta.get("tool_name", "")
        preview = meta.get("preview", "")[:60]
        if tool_name and preview:
            return f"✓ {tool_name}: {preview}"
        return None

    if level == LogLevel.STREAM:
        msg = entry.message or ""
        if msg == "assistant_text":
            text_preview = meta.get("text_preview", "")[:120]
            if text_preview:
                return f"\U0001f4ac {text_preview}"
        elif msg == "text_delta":
            text_preview = meta.get("text_preview", "")[:80]
            if text_preview:
                return f"\U0001f4ac {text_preview}"
        return None

    if level in (LogLevel.INFO, LogLevel.DEBUG):
        return entry.message[:100] if entry.message else None

    return None


def _truncate_input(tool_input: Optional[dict]) -> Optional[dict]:
    """도구 입력을 로그용으로 축약"""
    if not tool_input:
        return None
    truncated = {}
    for k, v in tool_input.items():
        if isinstance(v, str) and len(v) > 300:
            truncated[k] = v[:300] + "..."
        else:
            truncated[k] = v
    return truncated


def _extract_file_change(tool_name: str, tool_input: dict) -> Optional[dict]:
    """도구 호출에서 파일 변경 정보 추출"""
    name_lower = tool_name.lower()

    if name_lower in ("write", "write_file"):
        fp = tool_input.get("file_path", tool_input.get("path", ""))
        content = tool_input.get("content", "")
        if fp:
            return {
                "file": fp.rsplit("/", 1)[-1],
                "path": fp,
                "op": "create",
                "lines": content.count("\n") + 1 if content else 0,
            }

    if name_lower in ("edit", "edit_file"):
        fp = tool_input.get("file_path", tool_input.get("path", ""))
        new = tool_input.get("new_string", tool_input.get("content", ""))
        if fp:
            return {
                "file": fp.rsplit("/", 1)[-1],
                "path": fp,
                "op": "edit",
                "lines": new.count("\n") + 1 if new else 0,
            }

    if name_lower in ("bash", "shell"):
        cmd = tool_input.get("command", "")
        # Detect file writes in bash (echo > file, cat > file, etc.)
        m = re.search(r'>\s*(\S+)', cmd)
        if m:
            fp = m.group(1).strip("'\"")
            return {
                "file": fp.rsplit("/", 1)[-1],
                "path": fp,
                "op": "bash_write",
                "lines": 0,
            }

    return None
