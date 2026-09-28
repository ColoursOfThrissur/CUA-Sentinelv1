"""Run just Case E."""
import sys
import asyncio
import json
import aiohttp
sys.path.insert(0, '.')

from tests.run_checkpoint3 import (
    CASE_E_NODES, CASE_E_EXPECTED,
    run_case_in_blender,
)

async def main():
    async with aiohttp.ClientSession() as session:
        readback, errors = await run_case_in_blender(
            session, CASE_E_NODES, "Case_E", CASE_E_EXPECTED
        )
        print("\nFinal result:")
        print(f"  Errors: {errors}")
        print(f"  dome aabb: {readback.get('dome', {}).get('aabb')}")

if __name__ == "__main__":
    asyncio.run(main())
