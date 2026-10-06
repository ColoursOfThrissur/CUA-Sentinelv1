"""
Test LLM nesting behavior with the updated prompt.
Checks if the LLM generates proper nested structure for stacked objects.
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

PROMPT = "Build a multi-part desk fan. Start with a wide, flattened cylinder for the base. Attach a thin vertical rod to the exact center of the base. On top of this rod, place a thicker, horizontal cylinder to act as the motor housing. On the front circular face of the motor housing, attach a small spherical hub. Radially distribute exactly four flattened, elongated blades evenly around this hub. Twist each blade slightly on its own local lengthwise axis so they look angled to catch air. Finally, enclose the blades and hub completely inside a protective cage made of several thin, intersecting circular wireframe rings."

MODEL_ID = "qwen3:14b-q4_K_M"
OLLAMA_URL = "http://localhost:11434"

async def test_llm_nesting():
    """Test if LLM generates proper nested structure."""
    
    class SimpleModelManager:
        async def generate_async(self, prompt, model_id, task_id=None, temperature=0.1, system_prompt=None):
            """Call Ollama directly."""
            import httpx
            payload = {
                "model": model_id,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
            }
            if system_prompt:
                payload["system"] = system_prompt
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
    
    model_manager = SimpleModelManager()
    
    # Import the actual decomposer to get the system prompt
    from core.blender_pipeline.progressive_v2.decomposer import DECOMPOSITION_SYSTEM_PROMPT
    
    # Build the prompt exactly as the decomposer does
    from core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
    decomposer = RecursiveDecomposer()
    
    # Detect stacking words
    stacking_words = [w for w in
        ["base", "stand", "pole", "rod", "stem", "column", "neck",
         "top", "head", "housing", "mount", "tower", "pedestal"]
        if w in PROMPT.lower()]
    stacking_note = (
        f"Stacking cues detected ({', '.join(stacking_words[:6])}) — "
        f"use nested assemblies, one level per vertical transition.\n"
        if len(stacking_words) >= 2 else ""
    )
    
    enclosure_note = (
        "An enclosure/cage is mentioned — model it as a child assembly "
        "with torus rings as parts.\n"
        if any(w in PROMPT.lower() for w in ["cage", "enclosure", "guard", "grille", "cover"])
        else ""
    )
    
    user_prompt = (
        f"Decompose this object into a NESTED hierarchy:\n"
        f"{PROMPT}\n\n"
        f"{stacking_note}"
        f"{enclosure_note}"
        f"RULES:\n"
        f"- Use nested assemblies for every vertical level transition.\n"
        f"- Set is_simple: false.\n"
        f"- Do NOT flatten everything into one level.\n"
    )
    
    print("=" * 80)
    print("TESTING LLM NESTING BEHAVIOR")
    print("=" * 80)
    print(f"Prompt: {PROMPT[:100]}...")
    print(f"Model: {MODEL_ID}")
    print()
    print("Calling LLM...")
    
    try:
        response = await model_manager.generate_async(
            prompt=user_prompt,
            model_id=MODEL_ID,
            system_prompt=DECOMPOSITION_SYSTEM_PROMPT,
            temperature=0.4
        )
        
        print("\n" + "=" * 80)
        print("LLM RESPONSE")
        print("=" * 80)
        print(response)
        print()
        
        # Parse and check structure
        data = json.loads(response)
        
        print("=" * 80)
        print("CHECKING NESTING STRUCTURE")
        print("=" * 80)
        
        def check_structure(children, indent=0, path="root"):
            """Recursively check structure and detect flat siblings."""
            issues = []
            assembly_children = []
            
            for child in children:
                prefix = "  " * indent
                kind = child.get("kind", "?")
                label = child.get("label", "?")
                socket = child.get("socket_type", "?")
                current_path = f"{path} > {label}"
                
                print(f"{prefix}[{kind}] {label} (socket: {socket}) path: {current_path}")
                
                if kind == "assembly":
                    assembly_children.append((label, socket, current_path))
                    if "children" in child:
                        sub_issues = check_structure(child["children"], indent + 1, current_path)
                        issues.extend(sub_issues)
            
            # Check if there are multiple assemblies at the same level
            if len(assembly_children) > 1:
                assembly_info = "\n".join([f"  - {label} ({socket}) at {path}" for label, socket, path in assembly_children])
                issues.append(f"Multiple assemblies at same level (depth {indent}):\n{assembly_info}")
                print(f"\n⚠️  ISSUE: Multiple assemblies at depth {indent}:")
                for label, socket, path in assembly_children:
                    print(f"    - {label} ({socket}) at {path}")
            
            return issues
        
        if "children" in data:
            issues = check_structure(data["children"])
            
            if issues:
                print("\n" + "=" * 80)
                print("ISSUES FOUND:")
                print("=" * 80)
                for issue in issues:
                    print(issue)
            else:
                print("\n✅ NO ISSUES - Proper nested structure")
                print("All assemblies are correctly nested (depth increases with each level)")
        
        print()
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm_nesting())
