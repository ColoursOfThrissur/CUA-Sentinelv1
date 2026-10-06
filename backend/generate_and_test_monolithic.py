import httpx
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PROMPT = (
    "Build a detailed tabletop retro-futuristic surveillance drone, approximately 0.45 meters wide. "
    "Use a rounded rectangular dark charcoal chassis with beveled edges and a shallow metallic silver top panel. "
    "Center a small blue-glass hemispherical status dome on top. Attach four identical horizontal cylindrical "
    "arms radiating outward in the X-Y plane at 90-degree intervals from the chassis. Each arm must be equal "
    "length and thickness, with a small silver collar at its inner connection. At the outer end of every arm, "
    "attach a flat horizontal circular torus rotor guard larger than the arm diameter. Inside each guard, "
    "add a central hub and three thin tapered propeller blades. Under the chassis, attach a brushed-steel "
    "U-shaped bracket facing downward. The bracket must be wider than the camera module. Inside the U-bracket, "
    "suspend a small dark-glass spherical camera lens between the two forks, with visible clearance on both sides. "
    "On the front of the chassis, add a short horizontal cylindrical sensor barrel with a recessed blue lens. "
    "On the rear, add a small rectangular battery module with rounded edges and two red indicator LEDs. "
    "Add four small black rubber landing feet below the chassis, evenly spaced and touching the ground plane. "
    "Maintain strict symmetry for the four arm, guard, hub, and propeller assemblies. Keep all parts physically "
    "connected, avoid overlapping geometry except intentional joints, and make sure every component fits within "
    "the overall 0.45-meter width. Use realistic materials: matte painted metal chassis, brushed steel bracket "
    "and collars, black rubber feet, dark glass camera lens, blue emissive LEDs, and slightly glossy propeller blades. "
    "Also setup a camera and light, and render 4 views (front, side, top, isometric) to ./data/renders_llm_direct/."
)

SYSTEM_PROMPT = (
    "You are an expert 3D Blender Python developer and 3D artist. "
    "Generate a complete, production-ready, standalone Blender 4.5 Python script that creates the 3D model "
    "described in the user prompt from scratch using bpy. "
    "Rules:\n"
    "1. Only output executable Python code. Do not include markdown codeblocks or conversational text.\n"
    "2. Use bpy.ops or bmesh to create geometry accurately according to dimensions in the prompt.\n"
    "3. Set up Principled BSDF materials with realistic colors, metallic, roughness, and emission.\n"
    "4. Add a camera, lighting, and code to render 4 camera angles (front, side, top, isometric) to './data/renders_llm_direct/'.\n"
    "5. Ensure proper object hierarchy, parenting, and clean manifold meshes.\n"
)

def query_ollama(model="qwen2.5-coder:14b"):
    print(f"Querying Ollama model '{model}' to generate monolithic Blender script for prompt...")
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": PROMPT}
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
        }
    }
    t0 = time.time()
    resp = httpx.post(url, json=payload, timeout=180.0)
    resp.raise_for_status()
    data = resp.json()
    duration = time.time() - t0
    content = data["message"]["content"]
    print(f"Ollama response received in {duration:.2f}s ({len(content)} chars)")
    return content

def clean_script(raw: str) -> str:
    # Strip markdown code fences if present
    match = re.search(r"```python\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw.strip()

def run_blender(script_path: Path):
    blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
    cmd = [blender_exe, "--background", "--python", str(script_path)]
    print(f"\nRunning Blender headless: {' '.join(cmd)}")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    duration = time.time() - t0
    print(f"Blender completed in {duration:.2f}s with returncode {proc.returncode}")
    print("\n--- Blender STDOUT (truncated to last 40 lines) ---")
    stdout_lines = proc.stdout.splitlines()
    print("\n".join(stdout_lines[-40:] if len(stdout_lines) > 40 else stdout_lines))
    if proc.stderr:
        print("\n--- Blender STDERR ---")
        stderr_lines = proc.stderr.splitlines()
        print("\n".join(stderr_lines[-20:] if len(stderr_lines) > 20 else stderr_lines))
    return proc.returncode, proc.stdout, proc.stderr

def main():
    raw_code = query_ollama("qwen2.5-coder:14b")
    clean_code = clean_script(raw_code)
    
    script_file = Path("llm_direct_drone_script.py")
    script_file.write_text(clean_code, encoding="utf-8")
    print(f"Saved generated script to {script_file.resolve()} ({len(clean_code.splitlines())} lines)")
    
    # Ensure render dir exists
    Path("data/renders_llm_direct").mkdir(parents=True, exist_ok=True)
    
    code, stdout, stderr = run_blender(script_file)
    print(f"\nExecution finished. Exit code: {code}")

if __name__ == "__main__":
    main()
