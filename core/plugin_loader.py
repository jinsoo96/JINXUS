"""플러그인 자동 로더 — tools/ 폴더 스캔해서 자동 등록

설계 원칙: 파일 하나 = 플러그인 하나

tools/
├── code_executor.py     [ON] 기본
├── web_searcher.py      [ON] 기본
├── github_agent.py      [ON] 기본
├── scheduler.py         [ON] 기본
├── file_manager.py      [ON] 기본
│
├── notion_agent.py      [OFF → 파일 넣으면 ON]
├── arxiv_searcher.py    [OFF → 파일 넣으면 ON]
└── custom_anything.py   [직접 만들어서 넣으면 됨]

플러그인 작성 규칙:
    - name: str 속성 필수
    - description: str 속성 필수
    - allowed_agents: list[str] 속성 (선택)
    - async run(input_data: dict) -> ToolResult 메서드 필수
"""
import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Optional

from config import get_settings

logger = logging.getLogger(__name__)


class PluginLoader:
    """플러그인 자동 로더

    tools/ 폴더를 스캔하여 도구 클래스를 자동으로 찾아 등록.
    """

    def __init__(self, tools_dir: str = "tools"):
        settings = get_settings()
        self._tools_dir = settings.project_root / tools_dir
        self._loaded_tools: dict[str, Any] = {}
        self._disabled_tools: set[str] = set()

    def scan_and_load(self) -> dict[str, Any]:
        """tools/ 폴더 스캔하여 모든 도구 로드

        Returns:
            {tool_name: tool_instance} 딕셔너리
        """
        self._loaded_tools = {}

        if not self._tools_dir.exists():
            logger.warning(f"Tools directory not found: {self._tools_dir}")
            return self._loaded_tools

        for py_file in self._tools_dir.glob("*.py"):
            # __init__.py, base.py 등은 스킵
            if py_file.stem.startswith("_") or py_file.stem == "base":
                continue

            self._load_tool(py_file)

        logger.info(f"Loaded {len(self._loaded_tools)} tools")
        return self._loaded_tools

    def _load_tool(self, py_file: Path) -> Optional[Any]:
        """단일 파일에서 도구 로드"""
        module_name = f"tools.{py_file.stem}"

        try:
            module = importlib.import_module(module_name)

            # 모듈에서 도구 클래스 찾기
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # name, run 속성이 있으면 도구로 간주
                if hasattr(obj, "name") and hasattr(obj, "run"):
                    # base 클래스는 스킵
                    if name in ("JinxTool", "ToolResult"):
                        continue

                    try:
                        instance = obj()
                        tool_name = getattr(instance, "name", py_file.stem)

                        # 비활성화된 도구면 스킵
                        if tool_name in self._disabled_tools:
                            logger.info(f"  - {tool_name}: disabled")
                            continue

                        self._loaded_tools[tool_name] = instance
                        logger.info(f"  + {tool_name}: loaded")
                        return instance

                    except Exception as e:
                        logger.warning(f"  ! {name}: failed to instantiate - {e}")

        except Exception as e:
            logger.warning(f"  ! {py_file.name}: failed to import - {e}")

        return None

    def get_tool(self, name: str) -> Optional[Any]:
        """이름으로 도구 조회"""
        return self._loaded_tools.get(name)

    def get_all_tools(self) -> dict[str, Any]:
        """모든 로드된 도구 반환"""
        return self._loaded_tools.copy()

    def get_tools_for_agent(self, agent_name: str) -> dict[str, Any]:
        """특정 에이전트가 사용할 수 있는 도구 반환

        Args:
            agent_name: 에이전트 이름

        Returns:
            에이전트가 사용 가능한 도구 딕셔너리
        """
        result = {}

        for tool_name, tool in self._loaded_tools.items():
            # allowed_agents 속성이 없으면 모든 에이전트 허용
            allowed = getattr(tool, "allowed_agents", None)
            if allowed is None or agent_name in allowed:
                result[tool_name] = tool

        return result

    def enable_tool(self, name: str) -> bool:
        """도구 활성화"""
        self._disabled_tools.discard(name)
        return True

    def disable_tool(self, name: str) -> bool:
        """도구 비활성화"""
        self._disabled_tools.add(name)
        # 로드된 도구에서도 제거
        self._loaded_tools.pop(name, None)
        return True

    def reload(self) -> dict[str, Any]:
        """재시작 없이 런타임 중 재스캔"""
        logger.info("Reloading tools...")
        return self.scan_and_load()

    def get_tool_info(self, name: str) -> Optional[dict]:
        """도구 정보 조회"""
        tool = self._loaded_tools.get(name)
        if not tool:
            return None

        return {
            "name": getattr(tool, "name", name),
            "description": getattr(tool, "description", ""),
            "allowed_agents": getattr(tool, "allowed_agents", []),
            "enabled": name not in self._disabled_tools,
        }

    def list_tools(self) -> list[dict]:
        """모든 도구 정보 목록"""
        return [
            self.get_tool_info(name)
            for name in self._loaded_tools
        ]


# 싱글톤 인스턴스
_plugin_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    """플러그인 로더 싱글톤"""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader
