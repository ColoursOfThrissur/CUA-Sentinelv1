"""Live Blender cleanup proof for attempt-tagged hostile names and datablocks."""

from __future__ import annotations

import asyncio
import json

from core.blender_ops import parse_op_output
from core.blender_pipeline.progressive_v2.attempt_ledger import AttemptLedger, AttemptState
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, CompletionStatus
from core.mcp_manager import MCPManager


async def _call(mcp, code: str) -> dict:
    result = await mcp.call_locked("blender", "execute_blender_code", {"code": code})
    return parse_op_output(result.get("output", ""))


async def run() -> None:
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    executor = BlenderExecutor(mcp, task_id="ledger_live_cleanup")
    manifest = BuildManifest.create("ledger live cleanup")
    ledger = AttemptLedger(manifest)
    ledger.register(executor)
    ledger.mark_committing(executor._attempt_id)
    hostile_name = "hostile_\\\"_name_" + ("x" * 100)
    tag = executor._collection_name
    setup = f'''
import bpy, json
_tag={tag!r}; _name={hostile_name!r}
_coll=bpy.data.collections.new(_tag); bpy.context.scene.collection.children.link(_coll)
_mesh=bpy.data.meshes.new(_name); _mesh['sentinel_build_id']=_tag
_obj=bpy.data.objects.new(_name,_mesh); _obj['sentinel_build_id']=_tag; _coll.objects.link(_obj)
_mat=bpy.data.materials.new(_name); _mat['sentinel_build_id']=_tag; _obj.data.materials.append(_mat)
print('SENTINEL_OUTPUT_START'+json.dumps({{'ok': True, 'name': _obj.name}})+'SENTINEL_OUTPUT_END')
'''
    assert (await _call(mcp, setup)).get("ok") is True
    ledger.mark_committed(executor._attempt_id)
    assert await ledger.rollback_all() is True
    assert ledger.records[executor._attempt_id].state == AttemptState.CLEANED
    absent = await executor.verify_attempt_absent()
    assert absent == {"ok": True, "remaining": []}, absent
    # Restart sweep: a terminal failed manifest is swept, while an active
    # manifest's tagged attempt is deliberately excluded.
    orphan = BlenderExecutor(mcp, task_id="ledger_live_orphan")
    orphan_setup = setup.replace(tag, orphan._collection_name)
    assert (await _call(mcp, orphan_setup)).get("ok") is True
    dead = BuildManifest.create("dead build")
    dead.completion_status = CompletionStatus.FAILED
    dead.stats["attempt_ledger"] = [{
        "attempt_id": orphan._attempt_id, "collection": orphan._collection_name,
        "state": AttemptState.CLEANUP_FAILED.value,
    }]
    active = BuildManifest.create("active build")
    active.completion_status = CompletionStatus.IN_PROGRESS
    active.stats["attempt_ledger"] = [{
        "attempt_id": "active", "collection": "must-not-sweep", "state": AttemptState.COMMITTING.value,
    }]
    sweep = await AttemptLedger.sweep_orphans(mcp, [dead, active])
    assert sweep == [{"attempt_id": orphan._attempt_id, "collection": orphan._collection_name, "ok": True, "removed": sweep[0]["removed"]}]
    assert (await orphan.verify_attempt_absent())["ok"] is True
    # Shared material safety: cleaning the superseded collection must retain a
    # material still used by the keeper, then remove it once the keeper is gone.
    old = BlenderExecutor(mcp, task_id="ledger_shared_material")
    keeper = BlenderExecutor(mcp, task_id="ledger_shared_material")
    shared_setup = f'''
import bpy, json
_old={old._collection_name!r}; _keeper={keeper._collection_name!r}; _mat_name='sentinel_shared_live'
for _name in (_old, _keeper):
    _coll=bpy.data.collections.new(_name); bpy.context.scene.collection.children.link(_coll)
    _coll['sentinel_build_id']=_name
_mat=bpy.data.materials.new(_mat_name); _mat['sentinel_build_id']=_old
for _index,_name in enumerate((_old, _keeper)):
    _mesh=bpy.data.meshes.new('shared_mesh_'+str(_index)); _mesh['sentinel_build_id']=_name
    _obj=bpy.data.objects.new('shared_obj_'+str(_index), _mesh); _obj['sentinel_build_id']=_name
    bpy.data.collections[_name].objects.link(_obj); _obj.data.materials.append(_mat)
print('SENTINEL_OUTPUT_START'+json.dumps({{'ok': True}})+'SENTINEL_OUTPUT_END')
'''
    assert (await _call(mcp, shared_setup))["ok"] is True
    await old.cleanup_all()
    shared_after_old = await _call(mcp, "import bpy,json\nprint('SENTINEL_OUTPUT_START'+json.dumps({'ok': bpy.data.materials.get('sentinel_shared_live') is not None})+'SENTINEL_OUTPUT_END')")
    assert shared_after_old["ok"] is True
    await keeper.cleanup_all()
    shared_after_keeper = await _call(mcp, "import bpy,json\nprint('SENTINEL_OUTPUT_START'+json.dumps({'ok': bpy.data.materials.get('sentinel_shared_live') is None})+'SENTINEL_OUTPUT_END')")
    assert shared_after_keeper["ok"] is True
    print("LIVE_LEDGER_CLEANUP_PASS", json.dumps({"attempt": executor._attempt_id, "hostile_name_length": len(hostile_name)}))
    await mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
