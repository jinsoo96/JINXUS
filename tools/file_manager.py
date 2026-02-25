"""파일 관리 도구 - 로컬 파일시스템 CRUD"""
import os
import shutil
from pathlib import Path
from typing import Optional

from .base import JinxTool, ToolResult
from config import get_settings


class FileManager(JinxTool):
    """로컬 파일시스템 관리 도구

    JX_WRITER, JX_ANALYST, JX_OPS 사용 가능
    - 파일 읽기/쓰기/삭제
    - 디렉토리 관리
    - 허용 경로 화이트리스트 기반 보안
    """

    name = "file_manager"
    description = "로컬 파일시스템의 파일을 읽고 쓰고 관리합니다"
    allowed_agents = ["JX_WRITER", "JX_ANALYST", "JX_OPS"]

    def __init__(self):
        super().__init__()
        settings = get_settings()
        # 기본 허용 경로: 프로젝트 디렉토리 및 하위
        self._allowed_paths = [
            settings.project_root,
            settings.data_dir,
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path("/tmp"),
        ]

    def _is_path_allowed(self, path: Path) -> bool:
        """경로가 허용된 범위 내인지 확인"""
        path = path.resolve()
        for allowed in self._allowed_paths:
            try:
                path.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False

    async def run(self, input_data: dict) -> ToolResult:
        """파일 작업 실행

        Args:
            input_data: {
                "action": str,    # "read" | "write" | "append" | "delete" | "list" | "move" | "mkdir"
                "path": str,      # 대상 경로
                "content": str,   # write/append 시 내용
                "dest": str,      # move 시 목적지
            }
        """
        self._start_timer()

        action = input_data.get("action")
        path_str = input_data.get("path")

        if not action or not path_str:
            return ToolResult(
                success=False,
                output=None,
                error="action and path are required",
                duration_ms=self._get_duration_ms(),
            )

        path = Path(path_str).expanduser()

        # 경로 검증
        if not self._is_path_allowed(path):
            return ToolResult(
                success=False,
                output=None,
                error=f"Path not allowed: {path}",
                duration_ms=self._get_duration_ms(),
            )

        try:
            if action == "read":
                return await self._read(path)
            elif action == "write":
                content = input_data.get("content", "")
                return await self._write(path, content)
            elif action == "append":
                content = input_data.get("content", "")
                return await self._append(path, content)
            elif action == "delete":
                return await self._delete(path)
            elif action == "list":
                return await self._list_dir(path)
            elif action == "move":
                dest = input_data.get("dest") or input_data.get("destination")
                if not dest:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="dest is required for move action",
                        duration_ms=self._get_duration_ms(),
                    )
                return await self._move(path, Path(dest).expanduser())
            elif action == "copy":
                dest = input_data.get("dest") or input_data.get("destination")
                if not dest:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="dest is required for copy action",
                        duration_ms=self._get_duration_ms(),
                    )
                return await self._copy(path, Path(dest).expanduser())
            elif action == "mkdir":
                return await self._mkdir(path)
            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}",
                    duration_ms=self._get_duration_ms(),
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _read(self, path: Path) -> ToolResult:
        """파일 읽기"""
        if not path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"File not found: {path}",
                duration_ms=self._get_duration_ms(),
            )

        if not path.is_file():
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a file: {path}",
                duration_ms=self._get_duration_ms(),
            )

        content = path.read_text(encoding="utf-8")
        return ToolResult(
            success=True,
            output={
                "content": content,
                "path": str(path),
                "size": path.stat().st_size,
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _write(self, path: Path, content: str) -> ToolResult:
        """파일 쓰기 (덮어쓰기)"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "size": path.stat().st_size,
                "action": "written",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _append(self, path: Path, content: str) -> ToolResult:
        """파일 추가"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(content)

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "size": path.stat().st_size,
                "action": "appended",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _delete(self, path: Path) -> ToolResult:
        """파일/디렉토리 삭제"""
        if not path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"Path not found: {path}",
                duration_ms=self._get_duration_ms(),
            )

        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "action": "deleted",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _list_dir(self, path: Path) -> ToolResult:
        """디렉토리 내용 조회"""
        if not path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"Directory not found: {path}",
                duration_ms=self._get_duration_ms(),
            )

        if not path.is_dir():
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a directory: {path}",
                duration_ms=self._get_duration_ms(),
            )

        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "items": items,
                "count": len(items),
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _move(self, src: Path, dest: Path) -> ToolResult:
        """파일/디렉토리 이동"""
        if not src.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"Source not found: {src}",
                duration_ms=self._get_duration_ms(),
            )

        if not self._is_path_allowed(dest):
            return ToolResult(
                success=False,
                output=None,
                error=f"Destination not allowed: {dest}",
                duration_ms=self._get_duration_ms(),
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

        return ToolResult(
            success=True,
            output={
                "source": str(src),
                "destination": str(dest),
                "action": "moved",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _mkdir(self, path: Path) -> ToolResult:
        """디렉토리 생성"""
        path.mkdir(parents=True, exist_ok=True)

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "action": "created",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _copy(self, src: Path, dest: Path) -> ToolResult:
        """파일/디렉토리 복사"""
        if not src.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"Source not found: {src}",
                duration_ms=self._get_duration_ms(),
            )

        if not self._is_path_allowed(dest):
            return ToolResult(
                success=False,
                output=None,
                error=f"Destination not allowed: {dest}",
                duration_ms=self._get_duration_ms(),
            )

        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.is_file():
            shutil.copy2(str(src), str(dest))
        else:
            shutil.copytree(str(src), str(dest))

        return ToolResult(
            success=True,
            output={
                "source": str(src),
                "destination": str(dest),
                "action": "copied",
            },
            duration_ms=self._get_duration_ms(),
        )
