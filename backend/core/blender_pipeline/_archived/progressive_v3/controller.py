"""V3 orchestration: bounded planning, typed scene, audited atomic commit."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from .audit import SceneAudit
from .compiler import IntentCompiler
from .executor import V3Executor
from .intent import IntentPlanner
from .normalize import IntentNormalizer
from .scene import BuildResult, BuildStatus, Scene
from .trace import record
from .verifier import V3Preflight, verify_committed_scene

logger = logging.getLogger(__name__)


class V3Controller:
    def __init__(self, model_manager: Any, mcp_manager: Optional[Any] = None) -> None:
        self.model_manager = model_manager
        self.mcp_manager = mcp_manager

    async def run(self, prompt: str, task_id: str, model_id: Optional[str] = None,
                  stage0_output: Optional[dict[str, Any]] = None) -> BuildResult:
        started = time.monotonic()
        planner = IntentPlanner(self.model_manager, model_id, task_id)
        scene = Scene.create(prompt, model_id)
        executor: Optional[V3Executor] = None
        committed = False
        try:
            intent = await planner.plan(prompt, stage0_output)
            for attempt in range(2):
                intent, inferred = IntentNormalizer.complete(intent)
                scene = IntentCompiler.compile(intent, scene.model_id)
                scene.stats.update({'planning_calls': planner.calls, 'v3_planner_attempts': planner.attempts,
                                    'stage0_output': stage0_output})
                record(scene, 'compiled', {'inferred_relations': inferred, 'attempt': attempt + 1})
                preflight = V3Preflight.run(scene)
                audit = SceneAudit.run(scene)
                record(scene, 'audited', {'preflight': preflight, 'scene': audit})
                errors = preflight['errors'] + audit['errors']
                if not errors:
                    break
                if attempt:
                    raise RuntimeError('V3_SCENE_AUDIT_FAILED: ' + '; '.join(errors[:8]))
                repaired = await planner.repair(prompt, intent, errors)
                if repaired is None:
                    raise RuntimeError('V3_SCENE_AUDIT_FAILED: ' + '; '.join(errors[:8]))
                intent = repaired
            if self.mcp_manager is None:
                raise RuntimeError('BLENDER_MCP_UNAVAILABLE: scene planned but not built')
            executor = V3Executor(self.mcp_manager, task_id)
            record(scene, 'transaction_starting', {'parts': len(scene.parts), 'collection': executor.collection_name})
            self._save(scene)
            receipt = await executor.execute(scene)
            committed = True
            record(scene, 'transaction_committed', {'parts': len(receipt['objects'])})
            readback = await verify_committed_scene(self.mcp_manager, scene, executor.collection_name)
            record(scene, 'readback', readback)
            if not readback['passed']:
                raise RuntimeError('V3_BLENDER_READBACK_FAILED: ' + '; '.join(readback['errors']))
            scene.status = BuildStatus.SUCCESS
            scene.stats['build_end_time'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            output = self._save(scene)
            logger.info('[task=%s] V3 verified %s/%s Blender meshes', task_id, readback['found_meshes'], len(scene.parts))
            return BuildResult(True, scene, BuildStatus.SUCCESS, total_nodes=len(scene.parts),
                               verified_nodes=readback['found_meshes'], llm_calls=planner.calls,
                               blender_ops=2, build_time_seconds=time.monotonic()-started,
                               blender_objects=[part.blender_name for part in scene.parts], output_file=str(output))
        except Exception as exc:
            logger.exception('[task=%s] V3 build failed', task_id)
            if committed and executor:
                try:
                    await executor.cleanup()
                    record(scene, 'rollback_complete', {'collection': executor.collection_name})
                except Exception as cleanup_exc:
                    record(scene, 'rollback_failed', {'error': str(cleanup_exc)})
            scene.stats.update({'planning_calls': planner.calls, 'v3_planner_attempts': planner.attempts})
            scene.status = BuildStatus.FAILED
            record(scene, 'failed', {'error': str(exc)})
            output = self._save(scene)
            return BuildResult(False, scene, BuildStatus.FAILED, total_nodes=len(scene.parts),
                               failed_nodes=max(1, len(scene.parts)), llm_calls=planner.calls,
                               build_time_seconds=time.monotonic()-started, errors=[str(exc)], output_file=str(output))

    @staticmethod
    def _save(scene: Scene) -> Path:
        path = Path(__file__).resolve().parents[3] / 'data' / 'builds_v3' / scene.model_id / 'manifest.json'
        return scene.save(path)


async def run_progressive_build(prompt: str, model_manager: Any, task_id: str,
                                mcp_manager: Optional[Any] = None, model_id: Optional[str] = None,
                                limits: Optional[Any] = None,
                                stage0_output: Optional[dict[str, Any]] = None) -> BuildResult:
    """Primary route. Explicit v2_legacy switch is an emergency rollback only."""
    if os.getenv('BLENDER_PIPELINE_MODE', 'v3').lower() == 'v2_legacy':
        from ..progressive_v2.controller import run_progressive_build as legacy
        return await legacy(prompt, model_manager, task_id, mcp_manager, model_id, limits, stage0_output)
    return await V3Controller(model_manager, mcp_manager).run(prompt, task_id, model_id, stage0_output)
