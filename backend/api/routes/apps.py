from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from core.mcp_manager import MCPManager

router = APIRouter()

class AppConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    icon: Optional[str] = None
    transport: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    security: Optional[Dict[str, Any]] = None

class NewAppConfig(AppConfigUpdate):
    app_id: str
    display_name: str
    transport: str


def _get_mcp_manager(request: Request) -> MCPManager:
    manager = getattr(request.app.state, "mcp_manager", None)
    if manager is None:
        manager = MCPManager()
        manager.initialize_from_config()
        request.app.state.mcp_manager = manager
    return manager


@router.get("")
@router.get("/")
async def list_apps(request: Request):
    """List all configured apps with their current status."""
    try:
        manager = _get_mcp_manager(request)
        return {"apps": manager.list_connections()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{app_id}")
async def get_app(request: Request, app_id: str):
    """Get details of a single app."""
    try:
        manager = _get_mcp_manager(request)
        conn = manager.get_connection(app_id)
        if not conn:
            raise HTTPException(status_code=404, detail="App not found")
        
        return {
            "app_id": conn.app_id,
            "display_name": conn.display_name,
            "icon": conn.icon,
            "transport": conn.transport,
            "status": conn.status,
            "enabled": conn.enabled,
            "description": conn.description,
            "error_message": conn.error_message,
            "tools_count": len(conn.discovered_tools),
            "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in conn.discovered_tools],
            "security": conn.security,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/connect")
async def connect_app(request: Request, app_id: str):
    """Connect to an MCP app."""
    try:
        manager = _get_mcp_manager(request)
        await manager.connect_app(app_id)
        # Inject MCP tool entries into ToolGateway for runtime resolution
        from core.tool_gateway import ToolGateway
        ToolGateway._active_mcp_manager = manager
        return {"status": "success", "message": f"Connected to {app_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {e}")


@router.post("/{app_id}/disconnect")
async def disconnect_app(request: Request, app_id: str):
    """Disconnect from an MCP app."""
    try:
        manager = _get_mcp_manager(request)
        await manager.disconnect_app(app_id)
        return {"status": "success", "message": f"Disconnected from {app_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{app_id}/test")
async def test_app(request: Request, app_id: str):
    """Test connection to an MCP app."""
    try:
        manager = _get_mcp_manager(request)
        result = await manager.test_connection(app_id)
        if not result["ok"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error during test"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{app_id}")
async def update_app(request: Request, app_id: str, updates: AppConfigUpdate):
    """Update an app's configuration."""
    try:
        manager = _get_mcp_manager(request)
        update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
        manager.update_app_config(app_id, update_data)
        return {"status": "success", "message": f"Updated {app_id}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
@router.post("/")
async def add_app(request: Request, new_app: NewAppConfig):
    """Add a new custom MCP app."""
    try:
        manager = _get_mcp_manager(request)
        app_data = new_app.model_dump()
        app_id = app_data.pop("app_id")
        
        if manager.get_connection(app_id):
            raise HTTPException(status_code=409, detail=f"App {app_id} already exists")
            
        manager.add_custom_app(app_id, app_data)
        return {"status": "success", "message": f"Added app {app_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{app_id}")
async def remove_app(request: Request, app_id: str):
    """Remove an app."""
    try:
        manager = _get_mcp_manager(request)
        await manager.disconnect_app(app_id)
        manager.remove_app(app_id)
        return {"status": "success", "message": f"Removed app {app_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
