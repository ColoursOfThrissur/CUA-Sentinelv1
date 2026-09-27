import os
import sys
import pytest
from unittest.mock import MagicMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.reflection import ReflectionEngine


@pytest.fixture
def mock_memory_tool():
    tool = MagicMock()
    tool.ingest.return_value = "doc_test_123"
    tool.retrieve.return_value = (
        "<untrusted_retrieved_context>\n"
        "<snippet index=\"0\" score=\"0.95\">When handling tasks related to 'blender 3d cube', using execute_blender_code produced completed outcome.</snippet>\n"
        "</untrusted_retrieved_context>"
    )
    return tool


@pytest.mark.asyncio
async def test_reflection_engine_crystallizes_lesson(mock_memory_tool):
    engine = ReflectionEngine(memory_tool=mock_memory_tool)
    doc_id = await engine.reflect_on_task(
        task_id="task_reflect_test",
        workflow_type="ENDPOINT",
        prompt="in blender, create a 3d cube with 2m size",
        result_payload={"response": "Successfully created cube via Blender Python API."},
        status="COMPLETED",
    )
    assert doc_id == "doc_test_123"
    assert mock_memory_tool.ingest.called
    call_kwargs = mock_memory_tool.ingest.call_args[1]
    assert call_kwargs["domain"] == "AI"
    assert "blender" in call_kwargs["raw_content"]
    assert "COMPLETED" in call_kwargs["raw_content"]


def test_reflection_engine_recalls_lessons(mock_memory_tool):
    engine = ReflectionEngine(memory_tool=mock_memory_tool)
    recalled = engine.recall_lessons("how do I create a cube in blender?")
    assert recalled is not None
    assert "•" in recalled
    assert "blender 3d cube" in recalled


def test_reflection_engine_ignores_empty_or_short_prompts(mock_memory_tool):
    engine = ReflectionEngine(memory_tool=mock_memory_tool)
    assert engine.recall_lessons("") is None
    assert engine.recall_lessons("hi") is None
