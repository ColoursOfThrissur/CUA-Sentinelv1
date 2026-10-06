import asyncio
import json
from core.mcp_manager import MCPManager
from core.blender_ops import parse_op_output

async def check():
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    code = """
import bpy, json
objs = [o.name for o in bpy.data.objects]
colls = [c.name for c in bpy.data.collections]
result = {"ok": True, "objects": objs, "collections": colls, "obj_count": len(objs)}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": code})
    print("Raw MCP response:", res)
    parsed = parse_op_output(res.get("output", ""))
    print(f"Live Blender has {parsed.get('obj_count')} objects:")
    print("Objects:", parsed.get("objects"))
    print("Collections:", parsed.get("collections"))
    await mcp.shutdown()

if __name__ == "__main__":
    asyncio.run(check())
