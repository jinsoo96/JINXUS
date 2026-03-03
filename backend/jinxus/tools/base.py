"""JINXUS 도구 기반 클래스"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import time


@dataclass
class ToolResult:
    """도구 실행 결과"""
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class JinxTool(ABC):
    """JINXUS 도구 추상 기반 클래스

    모든 도구는 이 클래스를 상속받아 구현한다.
    """

    name: str = "base_tool"
    description: str = "기본 도구"
    allowed_agents: list[str] = field(default_factory=list)
    # Claude tool_use용 input schema (서브클래스에서 오버라이드)
    input_schema: dict = None

    def __init__(self):
        self._start_time: Optional[float] = None
        # 기본 input_schema (서브클래스에서 정의 안 하면 이것 사용)
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "도구 입력값"
                    }
                },
                "required": ["input"]
            }

    def _start_timer(self) -> None:
        """타이머 시작"""
        self._start_time = time.time()

    def _get_duration_ms(self) -> int:
        """경과 시간 (ms)"""
        if self._start_time is None:
            return 0
        return int((time.time() - self._start_time) * 1000)

    def is_allowed(self, agent_name: str) -> bool:
        """에이전트가 이 도구를 사용할 수 있는지 확인"""
        if not self.allowed_agents:
            return True  # 빈 리스트면 모든 에이전트 허용
        return agent_name in self.allowed_agents

    @abstractmethod
    async def run(self, input_data: dict) -> ToolResult:
        """도구 실행 (비동기)

        Args:
            input_data: 도구별 입력 파라미터

        Returns:
            ToolResult: 실행 결과
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
