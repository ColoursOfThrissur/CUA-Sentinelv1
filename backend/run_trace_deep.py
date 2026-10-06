"""Run trace_pipeline with a deep model (depth >2) using live Ollama."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.blender_pipeline.progressive_v2.trace_pipeline as tp

tp.PROMPT = (
    "a floor lamp with a heavy circular base, "
    "a 3-section telescoping pole, "
    "and a shade assembly containing a bulb socket and a conical shade"
)
tp.MODEL_ID = "qwen3:14b-q4_K_M"

asyncio.run(tp.main())
