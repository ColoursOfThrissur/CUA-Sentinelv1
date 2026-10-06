import asyncio
from core.mcp_manager import MCPManager

async def test():
    mcp = MCPManager()
    mcp.initialize_from_config()
    print("Connecting...")
    await mcp.connect_app("blender")
    print("Connected.")
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": "import bpy\nprint('HELLO_FROM_BLENDER', len(bpy.data.objects))"})
    print("Result:", res)
    await mcp.shutdown()

asyncio.run(test())
