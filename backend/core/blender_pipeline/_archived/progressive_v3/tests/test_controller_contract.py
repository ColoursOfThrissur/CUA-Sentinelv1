"""Trace the V3 controller without substituting V2 runtime objects."""
import json
import re
import ast

import pytest

from core.blender_pipeline.progressive_v3.controller import V3Controller
from core.blender_pipeline.progressive_v3.scene import BuildStatus


class Model:
    def get_model_for_workflow(self, name):
        return 'mock-model'

    async def generate_async(self, **kwargs):
        return json.dumps({'overall_extent_m': .45, 'components': [
            {'key': 'body', 'primitive': 'box', 'parameters': {'size': [.15,.1,.05]}},
            {'key': 'arm', 'primitive': 'cylinder', 'count': 4, 'parameters': {'radius': .01, 'depth': .12}},
        ], 'relations': [{'subject':'arm','target':'body','kind':'radial','parameters':{'radius':.14}}]})


class MCP:
    def __init__(self, missing=False):
        self.calls = []
        self.missing = missing
        self.parts = []

    async def call_locked(self, server, tool, args):
        assert (server, tool) == ('blender', 'execute_blender_code')
        code = args['code']
        self.calls.append(code)
        if 'plan = json.loads(' in code:
            line = next(line for line in code.splitlines() if line.startswith('plan = json.loads('))
            self.parts = json.loads(ast.literal_eval(line[len('plan = json.loads('):-1]))['parts']
            mapping = {part['id']: part['blender_name'] for part in self.parts}
            assert len(mapping) == 5
            payload = {'ok': True, 'objects': mapping}
        elif '_found = {}' in code:
            names = ast.literal_eval(next(line.split('=', 1)[1].strip() for line in code.splitlines() if line.startswith('_names =')))
            if self.missing:
                names = names[:-1]
            by_id = {part['id']: part for part in self.parts}
            info = {}
            for part in self.parts:
                name = part['blender_name']
                if name not in names:
                    continue
                parent_id = part['parent_id']
                info[name] = {'min': [-.1,-.1,-.02], 'max': [.1,.1,.02], 'vertices': 8,
                              'part_id': part['id'], 'parent': by_id[parent_id]['blender_name'] if parent_id else next(re.finditer(r"_collection = bpy.data.collections.get\('([^']+)'\)", code)).group(1) + '_Root',
                              'location': part['transform']['position'], 'materials': 1, 'modifiers': []}
            payload = {'ok': True, 'objects': info}
        else:
            payload = {'ok': True}
        return {'output': 'SENTINEL_OUTPUT_START' + json.dumps(payload) + 'SENTINEL_OUTPUT_END'}


@pytest.mark.asyncio
async def test_v3_success_requires_readback(tmp_path, monkeypatch):
    monkeypatch.setattr(V3Controller, '_save', staticmethod(lambda scene: scene.save(tmp_path / 'manifest.json')))
    mcp = MCP()
    result = await V3Controller(Model(), mcp).run('Make a 0.45 meter body with four radial arms', 'task-v3-test')
    assert result.success and result.completion_status is BuildStatus.SUCCESS
    assert result.verified_nodes == result.total_nodes == 5
    assert result.manifest.stats['pipeline'] == 'progressive_v3'
    assert len(mcp.calls) == 2


@pytest.mark.asyncio
async def test_v3_missing_readback_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(V3Controller, '_save', staticmethod(lambda scene: scene.save(tmp_path / 'manifest.json')))
    mcp = MCP(missing=True)
    result = await V3Controller(Model(), mcp).run('Make a 0.45 meter body with four radial arms', 'task-v3-fail')
    assert not result.success and result.completion_status is BuildStatus.FAILED
    assert 'V3_BLENDER_READBACK_FAILED' in result.errors[0]
    assert len(mcp.calls) == 3
    assert result.manifest.events[-2]['type'] == 'v3_rollback_complete'
