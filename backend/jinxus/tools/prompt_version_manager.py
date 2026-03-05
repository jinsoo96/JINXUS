"""프롬프트 버전 관리자 - 파일과 DB 동기화"""
import logging
from pathlib import Path
from typing import Optional

from .base import JinxTool, ToolResult
from jinxus.config import get_settings
from jinxus.memory.meta_store import get_meta_store

logger = logging.getLogger(__name__)


class PromptVersionManager(JinxTool):
    """프롬프트 버전 관리

    JX_OPS 전용
    - 프롬프트 파일과 SQLite DB 동기화
    - 버전 히스토리 관리
    - 롤백 지원
    """

    name = "prompt_version_manager"
    description = "프롬프트 버전을 관리하고 파일/DB 동기화를 수행합니다"
    allowed_agents = ["JX_OPS"]

    def __init__(self):
        super().__init__()
        self._prompts_dir = Path(get_settings().prompts_dir)
        self._meta_store = get_meta_store()

    async def run(self, input_data: dict) -> ToolResult:
        """프롬프트 버전 관리

        Args:
            input_data: {
                "action": str,        # "sync" | "list" | "get" | "rollback" | "save"
                "agent_name": str,    # 에이전트 이름
                "version": str,       # 버전 (rollback/get 시)
                "prompt_content": str, # 내용 (save 시)
                "change_reason": str,  # 변경 사유 (save 시)
            }
        """
        self._start_timer()

        action = input_data.get("action")
        if not action:
            return ToolResult(
                success=False,
                output=None,
                error="action is required",
                duration_ms=self._get_duration_ms(),
            )

        try:
            if action == "sync":
                return await self._sync_all()
            elif action == "list":
                return await self._list_versions(input_data)
            elif action == "get":
                return await self._get_version(input_data)
            elif action == "rollback":
                return await self._rollback(input_data)
            elif action == "save":
                return await self._save_version(input_data)
            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown action: {action}",
                    duration_ms=self._get_duration_ms(),
                )

        except Exception as e:
            logger.error(f"PromptVersionManager error: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    async def _sync_all(self) -> ToolResult:
        """모든 에이전트 프롬프트를 DB와 동기화"""
        synced = []

        # 모든 프롬프트 디렉토리 순회
        for agent_dir in self._prompts_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            agent_name = agent_dir.name.upper()
            system_file = agent_dir / "system.md"

            if not system_file.exists():
                continue

            try:
                # 현재 파일 내용 읽기
                current_content = system_file.read_text(encoding="utf-8")

                # DB에서 활성 버전 확인
                active_prompt = await self._meta_store.get_active_prompt(agent_name)

                if active_prompt:
                    # 내용이 다르면 새 버전 저장
                    if active_prompt["prompt_content"] != current_content:
                        new_version = self._increment_version(active_prompt["version"])
                        await self._meta_store.save_prompt_version(
                            agent_name=agent_name,
                            version=new_version,
                            prompt_content=current_content,
                            change_reason="File sync - content changed",
                            is_active=True,
                        )
                        synced.append({
                            "agent": agent_name,
                            "action": "updated",
                            "version": new_version,
                        })
                    else:
                        synced.append({
                            "agent": agent_name,
                            "action": "unchanged",
                            "version": active_prompt["version"],
                        })
                else:
                    # 첫 동기화 - v1.0으로 저장
                    await self._meta_store.save_prompt_version(
                        agent_name=agent_name,
                        version="1.0",
                        prompt_content=current_content,
                        change_reason="Initial sync",
                        is_active=True,
                    )
                    synced.append({
                        "agent": agent_name,
                        "action": "created",
                        "version": "1.0",
                    })

                # versions 디렉토리 생성 및 백업
                await self._backup_to_versions_dir(agent_dir, agent_name, current_content)

            except Exception as e:
                logger.error(f"Failed to sync {agent_name}: {e}")
                synced.append({
                    "agent": agent_name,
                    "action": "error",
                    "error": str(e),
                })

        return ToolResult(
            success=True,
            output={"synced": synced, "count": len(synced)},
            duration_ms=self._get_duration_ms(),
        )

    async def _backup_to_versions_dir(
        self, agent_dir: Path, agent_name: str, content: str
    ) -> None:
        """versions 디렉토리에 백업 파일 생성"""
        versions_dir = agent_dir / "versions"
        versions_dir.mkdir(exist_ok=True)

        # 현재 활성 버전 가져오기
        active_prompt = await self._meta_store.get_active_prompt(agent_name)
        if not active_prompt:
            return

        version = active_prompt["version"]
        version_file = versions_dir / f"v{version}.md"

        if not version_file.exists():
            version_file.write_text(content, encoding="utf-8")
            logger.info(f"Backup created: {version_file}")

    def _increment_version(self, version: str) -> str:
        """버전 증가 (1.0 -> 1.1, 1.9 -> 2.0)"""
        try:
            major, minor = map(int, version.split("."))
            if minor >= 9:
                return f"{major + 1}.0"
            return f"{major}.{minor + 1}"
        except ValueError:
            return "1.0"

    async def _list_versions(self, input_data: dict) -> ToolResult:
        """에이전트 프롬프트 버전 목록 조회"""
        agent_name = input_data.get("agent_name")
        if not agent_name:
            return ToolResult(
                success=False,
                output=None,
                error="agent_name is required",
                duration_ms=self._get_duration_ms(),
            )

        versions = await self._meta_store.get_prompt_history(agent_name.upper())

        return ToolResult(
            success=True,
            output={
                "agent_name": agent_name,
                "versions": [
                    {
                        "version": v["version"],
                        "is_active": v["is_active"],
                        "change_reason": v["change_reason"],
                        "avg_score": v["avg_score"],
                        "task_count": v["task_count"],
                        "created_at": v["created_at"],
                    }
                    for v in versions
                ],
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _get_version(self, input_data: dict) -> ToolResult:
        """특정 버전 프롬프트 내용 조회"""
        agent_name = input_data.get("agent_name")
        version = input_data.get("version")

        if not agent_name:
            return ToolResult(
                success=False,
                output=None,
                error="agent_name is required",
                duration_ms=self._get_duration_ms(),
            )

        agent_name = agent_name.upper()

        if version:
            # 특정 버전 조회
            versions = await self._meta_store.get_prompt_history(agent_name)
            for v in versions:
                if v["version"] == version:
                    return ToolResult(
                        success=True,
                        output={
                            "agent_name": agent_name,
                            "version": v["version"],
                            "content": v["prompt_content"],
                            "is_active": v["is_active"],
                        },
                        duration_ms=self._get_duration_ms(),
                    )
            return ToolResult(
                success=False,
                output=None,
                error=f"Version {version} not found",
                duration_ms=self._get_duration_ms(),
            )
        else:
            # 활성 버전 조회
            active = await self._meta_store.get_active_prompt(agent_name)
            if active:
                return ToolResult(
                    success=True,
                    output={
                        "agent_name": agent_name,
                        "version": active["version"],
                        "content": active["prompt_content"],
                        "is_active": True,
                    },
                    duration_ms=self._get_duration_ms(),
                )
            return ToolResult(
                success=False,
                output=None,
                error=f"No active version for {agent_name}",
                duration_ms=self._get_duration_ms(),
            )

    async def _rollback(self, input_data: dict) -> ToolResult:
        """특정 버전으로 롤백"""
        agent_name = input_data.get("agent_name")
        version = input_data.get("version")

        if not agent_name or not version:
            return ToolResult(
                success=False,
                output=None,
                error="agent_name and version are required",
                duration_ms=self._get_duration_ms(),
            )

        agent_name = agent_name.upper()

        # 해당 버전 찾기
        versions = await self._meta_store.get_prompt_history(agent_name)
        target_version = None
        for v in versions:
            if v["version"] == version:
                target_version = v
                break

        if not target_version:
            return ToolResult(
                success=False,
                output=None,
                error=f"Version {version} not found",
                duration_ms=self._get_duration_ms(),
            )

        # DB에서 해당 버전 활성화
        success = await self._meta_store.activate_prompt_version(agent_name, version)
        if not success:
            return ToolResult(
                success=False,
                output=None,
                error="Failed to activate version",
                duration_ms=self._get_duration_ms(),
            )

        # 파일에도 반영
        agent_dir = self._prompts_dir / agent_name.lower()
        system_file = agent_dir / "system.md"

        if system_file.exists():
            system_file.write_text(target_version["prompt_content"], encoding="utf-8")
            logger.info(f"Rolled back {agent_name} to v{version}")

        return ToolResult(
            success=True,
            output={
                "agent_name": agent_name,
                "version": version,
                "action": "rolled_back",
            },
            duration_ms=self._get_duration_ms(),
        )

    async def _save_version(self, input_data: dict) -> ToolResult:
        """새 프롬프트 버전 저장"""
        agent_name = input_data.get("agent_name")
        prompt_content = input_data.get("prompt_content")
        change_reason = input_data.get("change_reason", "Manual update")

        if not agent_name or not prompt_content:
            return ToolResult(
                success=False,
                output=None,
                error="agent_name and prompt_content are required",
                duration_ms=self._get_duration_ms(),
            )

        agent_name = agent_name.upper()

        # 현재 버전 확인
        active = await self._meta_store.get_active_prompt(agent_name)
        if active:
            new_version = self._increment_version(active["version"])
        else:
            new_version = "1.0"

        # DB에 저장
        await self._meta_store.save_prompt_version(
            agent_name=agent_name,
            version=new_version,
            prompt_content=prompt_content,
            change_reason=change_reason,
            is_active=True,
        )

        # 파일에도 반영
        agent_dir = self._prompts_dir / agent_name.lower()
        agent_dir.mkdir(parents=True, exist_ok=True)
        system_file = agent_dir / "system.md"
        system_file.write_text(prompt_content, encoding="utf-8")

        # 백업
        await self._backup_to_versions_dir(agent_dir, agent_name, prompt_content)

        return ToolResult(
            success=True,
            output={
                "agent_name": agent_name,
                "version": new_version,
                "action": "saved",
            },
            duration_ms=self._get_duration_ms(),
        )


# 싱글톤
_prompt_version_manager: Optional[PromptVersionManager] = None


def get_prompt_version_manager() -> PromptVersionManager:
    global _prompt_version_manager
    if _prompt_version_manager is None:
        _prompt_version_manager = PromptVersionManager()
    return _prompt_version_manager


async def sync_all_prompts() -> dict:
    """모든 프롬프트 동기화 (서버 시작 시 호출)"""
    manager = get_prompt_version_manager()
    result = await manager.run({"action": "sync"})
    return result.output if result.success else {}
