"""플러그인 관리 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jinxus.core.plugin_loader import get_plugin_loader

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginToggleRequest(BaseModel):
    name: str


@router.get("")
async def list_plugins():
    """로드된 플러그인 목록"""
    loader = get_plugin_loader()
    return {"plugins": loader.list_tools()}


@router.get("/{name}")
async def get_plugin(name: str):
    """플러그인 상세 정보"""
    loader = get_plugin_loader()
    info = loader.get_tool_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {name}")
    return info


@router.post("/enable")
async def enable_plugin(req: PluginToggleRequest):
    """플러그인 활성화"""
    loader = get_plugin_loader()
    loader.enable_tool(req.name)
    # 재스캔하여 비활성화됐던 도구를 다시 로드
    loader.reload()
    return {"success": True, "name": req.name, "enabled": True}


@router.post("/disable")
async def disable_plugin(req: PluginToggleRequest):
    """플러그인 비활성화"""
    loader = get_plugin_loader()
    loader.disable_tool(req.name)
    return {"success": True, "name": req.name, "enabled": False}


@router.post("/reload")
async def reload_plugins():
    """플러그인 전체 재스캔"""
    loader = get_plugin_loader()
    tools = loader.reload()
    return {"success": True, "loaded_count": len(tools)}
