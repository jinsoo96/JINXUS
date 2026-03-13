"""실시간 로그 스트리머 — Python 로거 출력을 SSE로 전달

사용법:
    queue = asyncio.Queue()
    handler = TaskLogHandler(queue, event_wrap=True)
    handler.attach()

    # 큐에서 꺼내면 바로 SSE yield 가능:
    # {"event": "log", "data": {"line": "[15:23:01] INFO ..."}}

    handler.detach()
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TaskLogHandler(logging.Handler):
    """asyncio.Queue에 로그 레코드를 전달하는 핸들러

    jinxus 네임스페이스의 모든 로그를 캡처하여
    터미널 형식으로 포맷팅 후 큐에 전송.
    """

    # 포맷: [시간] LEVEL module:line | 메시지
    FORMAT = "[%(asctime)s] %(levelname)-5s %(name)s:%(lineno)d | %(message)s"

    def __init__(self, queue: asyncio.Queue, level: int = logging.DEBUG, event_wrap: bool = False):
        super().__init__(level)
        self._queue = queue
        self._event_wrap = event_wrap  # True면 {"event":"log","data":{...}} 형태로
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._formatter = logging.Formatter(self.FORMAT, datefmt="%H:%M:%S")
        self._attached_loggers: list[logging.Logger] = []

    def attach(self):
        """jinxus.* 로거 전체에 핸들러 부착"""
        self._loop = asyncio.get_event_loop()

        # 핵심 로거 목록
        logger_names = [
            "jinxus.agents.jinxus_core",
            "jinxus.agents.base_agent",
            "jinxus.agents.jx_coder",
            "jinxus.agents.jx_researcher",
            "jinxus.agents.jx_writer",
            "jinxus.agents.jx_analyst",
            "jinxus.agents.jx_ops",
            "jinxus.tools.dynamic_executor",
            "jinxus.core.orchestrator",
            "jinxus.core.model_router",
            "jinxus.core.tool_graph",
            "jinxus.core.workflow_executor",
            "jinxus.core.collaboration",
            "jinxus.core.context_guard",
            "jinxus.core.response_cache",
            "jinxus.core.session_freshness",
            "jinxus.memory",
            "jinxus.memory.short_term",
            "jinxus.memory.long_term",
        ]

        for name in logger_names:
            lg = logging.getLogger(name)
            lg.addHandler(self)
            if lg.level > logging.DEBUG or lg.level == logging.NOTSET:
                lg.setLevel(logging.DEBUG)
            self._attached_loggers.append(lg)

    def detach(self):
        """모든 로거에서 핸들러 제거"""
        for lg in self._attached_loggers:
            lg.removeHandler(self)
        self._attached_loggers.clear()

    def emit(self, record: logging.LogRecord):
        try:
            line = self._formatter.format(record)
            if self._event_wrap:
                item = {"event": "log", "data": {"line": line}}
            else:
                item = line
            # 큐에 비동기 전달
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(
                    self._queue.put_nowait, item
                )
        except Exception as e:
            logger.debug(f"[TaskLogHandler] SSE 큐 전달 실패 (무시): {e}")
