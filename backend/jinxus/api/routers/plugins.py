"""플러그인 관리 API — TOOL_REGISTRY 기반 런타임 도구 활성화/비활성화"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginToggleRequest(BaseModel):
    name: str


@router.get("")
async def list_plugins():
    """등록된 네이티브 도구 목록 (MCP 제외)"""
    from jinxus.tools import get_all_tools_info
    tools = get_all_tools_info()
    native = [t for t in tools if not t.get("is_mcp")]
    return {"plugins": native, "total": len(native)}


@router.get("/{name}")
async def get_plugin(name: str):
    """플러그인 상세 정보"""
    from jinxus.tools import get_all_tools_info
    tools = {t["name"]: t for t in get_all_tools_info()}
    if name not in tools:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {name}")
    return tools[name]


@router.post("/enable")
async def enable_plugin(req: PluginToggleRequest):
    """플러그인 활성화 (런타임, 재시작 시 초기화)"""
    from jinxus.tools import set_tool_enabled
    set_tool_enabled(req.name, True)
    return {"success": True, "name": req.name, "enabled": True}


@router.post("/disable")
async def disable_plugin(req: PluginToggleRequest):
    """플러그인 비활성화 (런타임, 재시작 시 초기화)"""
    from jinxus.tools import set_tool_enabled
    set_tool_enabled(req.name, False)
    return {"success": True, "name": req.name, "enabled": False}


@router.post("/reload")
async def reload_plugins():
    """도구 목록 새로고침 (현재 등록된 도구 수 반환)"""
    from jinxus.tools import get_all_tools_info
    tools = get_all_tools_info()
    native = [t for t in tools if not t.get("is_mcp")]
    return {"success": True, "loaded_count": len(native)}
