"""StreamParser — Claude CLI stream-json 출력 파서

Claude Code CLI의 --output-format stream-json 출력을 실시간으로 파싱.
각 JSON 라인을 StreamEvent로 변환하고 ExecutionSummary를 누적.

사용 흐름:
    parser = StreamParser(on_event=callback)
    for line in stdout_lines:
        parser.parse_line(line)
    summary = parser.get_summary()
"""
import json
from datetime import datetime
from logging import getLogger
from typing import Callable, Optional

from jinxus.cli_engine.models import (
    StreamEvent,
    StreamEventType,
    ExecutionSummary,
)

logger = getLogger(__name__)


class StreamParser:

    def __init__(
        self,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        session_id: Optional[str] = None,
    ):
        self.on_event = on_event
        self.session_id = session_id
        self.summary = ExecutionSummary()
        self._current_tool_use: Optional[dict] = None

    def parse_line(self, line: str) -> Optional[StreamEvent]:
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("[%s] Non-JSON line: %s", self.session_id, line[:100])
            return None

        event = self._parse_event(data)
        if event:
            self._update_summary(event)
            if self.on_event:
                try:
                    self.on_event(event)
                except Exception as e:
                    logger.warning("[%s] Event callback error: %s", self.session_id, e)

        return event

    def get_summary(self) -> ExecutionSummary:
        return self.summary

    def reset(self):
        self.summary = ExecutionSummary()
        self._current_tool_use = None

    # ── Event parsing ─────────────────────────────────────────────

    def _parse_event(self, data: dict) -> Optional[StreamEvent]:
        event_type = data.get("type", "unknown")
        subtype = data.get("subtype")
        ts = datetime.now()

        if event_type == "system" and subtype == "init":
            return self._parse_system_init(data, ts)
        elif event_type == "assistant":
            return self._parse_assistant(data, ts)
        elif event_type == "content_block_start":
            return self._parse_content_start(data, ts)
        elif event_type == "content_block_delta":
            return self._parse_content_delta(data, ts)
        elif event_type == "content_block_stop":
            return self._parse_content_stop(data, ts)
        elif event_type == "tool_result":
            return self._parse_tool_result(data, ts)
        elif event_type == "result":
            return self._parse_result(data, ts)
        else:
            return StreamEvent(
                event_type=StreamEventType.UNKNOWN,
                timestamp=ts,
                raw_data=data,
            )

    def _parse_system_init(self, data: dict, ts: datetime) -> StreamEvent:
        return StreamEvent(
            event_type=StreamEventType.SYSTEM_INIT,
            timestamp=ts,
            raw_data=data,
            session_id=data.get("session_id"),
            tools=data.get("tools", []),
            mcp_servers=data.get("mcp_servers", []),
            model=data.get("model"),
        )

    def _parse_assistant(self, data: dict, ts: datetime) -> StreamEvent:
        message = data.get("message", {})
        content = message.get("content", [])

        text_parts = []
        tool_uses = []

        for block in content:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_uses.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })

        text = "\n".join(text_parts) if text_parts else None

        event = StreamEvent(
            event_type=StreamEventType.ASSISTANT_MESSAGE,
            timestamp=ts,
            raw_data=data,
            session_id=data.get("session_id"),
            message_id=message.get("id"),
            text=text,
            stop_reason=message.get("stop_reason"),
        )

        if tool_uses:
            event.tool_name = tool_uses[0].get("name")
            event.tool_input = tool_uses[0].get("input")
            event.tool_use_id = tool_uses[0].get("id")
            if len(tool_uses) > 1:
                event.raw_data["_parsed_tool_uses"] = tool_uses

        return event

    def _parse_content_start(self, data: dict, ts: datetime) -> StreamEvent:
        block = data.get("content_block", {})
        btype = block.get("type")

        event = StreamEvent(
            event_type=StreamEventType.CONTENT_BLOCK_START,
            timestamp=ts,
            raw_data=data,
        )

        if btype == "tool_use":
            event.event_type = StreamEventType.TOOL_USE
            event.tool_name = block.get("name")
            event.tool_use_id = block.get("id")
            self._current_tool_use = {
                "id": block.get("id"),
                "name": block.get("name"),
                "input": {},
            }

        return event

    def _parse_content_delta(self, data: dict, ts: datetime) -> StreamEvent:
        delta = data.get("delta", {})
        event = StreamEvent(
            event_type=StreamEventType.CONTENT_BLOCK_DELTA,
            timestamp=ts,
            raw_data=data,
        )
        if delta.get("type") == "text_delta":
            event.text = delta.get("text", "")
        return event

    def _parse_content_stop(self, data: dict, ts: datetime) -> StreamEvent:
        event = StreamEvent(
            event_type=StreamEventType.CONTENT_BLOCK_STOP,
            timestamp=ts,
            raw_data=data,
        )
        if self._current_tool_use:
            event.event_type = StreamEventType.TOOL_USE
            event.tool_name = self._current_tool_use.get("name")
            event.tool_use_id = self._current_tool_use.get("id")
            self._current_tool_use = None
        return event

    def _parse_tool_result(self, data: dict, ts: datetime) -> StreamEvent:
        """tool_result 이벤트 파싱 — 도구 실행 결과"""
        content = data.get("content", "")
        # content가 리스트인 경우 텍스트 추출
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        tool_use_id = data.get("tool_use_id")
        is_error = data.get("is_error", False)

        return StreamEvent(
            event_type=StreamEventType.TOOL_RESULT,
            timestamp=ts,
            raw_data=data,
            tool_use_id=tool_use_id,
            tool_output=str(content)[:500] if content else None,
            is_error=is_error,
        )

    def _parse_result(self, data: dict, ts: datetime) -> StreamEvent:
        return StreamEvent(
            event_type=StreamEventType.RESULT,
            timestamp=ts,
            raw_data=data,
            session_id=data.get("session_id"),
            duration_ms=data.get("duration_ms"),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            num_turns=data.get("num_turns"),
            result_text=data.get("result"),
            usage=data.get("usage"),
            is_error=data.get("is_error", False),
            stop_reason=data.get("stop_reason"),
        )

    # ── Summary accumulation ──────────────────────────────────────

    def _update_summary(self, event: StreamEvent):
        s = self.summary

        if event.event_type == StreamEventType.SYSTEM_INIT:
            s.session_id = event.session_id
            s.model = event.model
            s.available_tools = event.tools or []
            s.mcp_servers = event.mcp_servers or []

        elif event.event_type == StreamEventType.ASSISTANT_MESSAGE:
            if event.text:
                s.assistant_messages.append(event.text)
            if event.tool_name:
                s.tool_calls.append({
                    "id": event.tool_use_id,
                    "name": event.tool_name,
                    "input": event.tool_input,
                    "timestamp": event.timestamp.isoformat(),
                })
            for tool in event.raw_data.get("_parsed_tool_uses", [])[1:]:
                s.tool_calls.append({
                    "id": tool.get("id"),
                    "name": tool.get("name"),
                    "input": tool.get("input"),
                    "timestamp": event.timestamp.isoformat(),
                })

        elif event.event_type == StreamEventType.TOOL_USE:
            if event.tool_name:
                s.tool_calls.append({
                    "id": event.tool_use_id,
                    "name": event.tool_name,
                    "input": event.tool_input,
                    "timestamp": event.timestamp.isoformat(),
                })

        elif event.event_type == StreamEventType.TOOL_RESULT:
            # 도구 결과는 summary에 별도 누적하지 않음 (tool_calls에 이미 기록)
            pass

        elif event.event_type == StreamEventType.RESULT:
            s.success = not event.is_error
            s.is_error = event.is_error or False
            s.duration_ms = event.duration_ms or 0
            s.total_cost_usd = event.total_cost_usd or 0.0
            s.num_turns = event.num_turns or 0
            s.final_output = event.result_text or ""
            s.usage = event.usage
            s.stop_reason = event.stop_reason
            if event.is_error and event.result_text:
                s.error_message = event.result_text
