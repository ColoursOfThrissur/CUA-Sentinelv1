import base64
from pathlib import Path

art_path = Path("data/renders_tabletop_drone/isometric.png")
pipe_path = Path("data/renders_pipeline_compiled/isometric.png")

with open(art_path, "rb") as f:
    b64_art = base64.b64encode(f.read()).decode("utf-8")

with open(pipe_path, "rb") as f:
    b64_pipe = base64.b64encode(f.read()).decode("utf-8")

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Render Comparison</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #eee; padding: 24px; }}
  .container {{ display: flex; gap: 24px; justify-content: center; }}
  .card {{ background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 18px; width: 48%; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
  img {{ max-width: 100%; border-radius: 6px; background: #ffffff; display: block; margin: 0 auto; }}
  h2 {{ margin-top: 0; color: #fff; border-bottom: 1px solid #333; padding-bottom: 8px; }}
  .desc {{ text-align: left; font-size: 0.95em; line-height: 1.5; color: #ccc; margin-top: 14px; }}
  .desc li {{ margin-bottom: 6px; }}
  .badge-pass {{ background: #1b5e20; color: #a5d6a7; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .badge-fail {{ background: #b71c1c; color: #ffcdd2; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
</style>
</head>
<body>
  <h1 style="text-align: center; margin-bottom: 24px;">Blender 4.5.3 LTS Visual Comparison</h1>
  <div class="container">
    <div class="card">
      <h2>1. Artist Reference Script <span class="badge-pass">COHESIVE</span></h2>
      <img src="data:image/png;base64,{b64_art}" alt="Artist Reference Drone" />
      <div class="desc">
        <ul>
          <li><strong>Chassis & Top Panel:</strong> Beveled rounded rectangular body with metallic silver top plate.</li>
          <li><strong>Status Dome:</strong> Blue glass hemisphere resting flush on top face ($Z = 0.045\\text{{m}}$).</li>
          <li><strong>Rotors:</strong> 4 symmetrical arms with collars, guards, hubs, and 3 horizontal tapered blades.</li>
          <li><strong>Underside:</strong> Brushed steel U-bracket, dark camera lens, 4 black rubber feet touching $Z = 0.000\\text{{m}}$.</li>
          <li><strong>Shading:</strong> 100% 2-manifold, smooth angle-limited normals, realistic PBR materials.</li>
        </ul>
      </div>
    </div>
    <div class="card">
      <h2>2. Pipeline V2 Compiled Output <span class="badge-fail">DEFECTS VISIBLE</span></h2>
      <img src="data:image/png;base64,{b64_pipe}" alt="Pipeline V2 Drone" />
      <div class="desc">
        <ul>
          <li><strong>Floating Dome:</strong> Sits at $Z = 0.0254\\text{{m}}$; chassis top is at $Z = 0.0200\\text{{m}}$, leaving a <strong>5.4 mm gap in mid-air</strong>.</li>
          <li><strong>Vertical Blades:</strong> Cones pointing along $+Z$ with rotation $[0,0,0]$ instead of lying horizontal in the rotor disk.</li>
          <li><strong>Floating Extra Guards:</strong> 5 duplicate torus rings hanging at $Z = -0.105\\text{{m}}$ from redundant <code>arm_assembly</code>.</li>
          <li><strong>Material Fallback:</strong> Generic grey PBR assigned to all arm components.</li>
        </ul>
      </div>
    </div>
  </div>
</body>
</html>"""

out_file = Path("data/render_comparison.html")
out_file.write_text(html, encoding="utf-8")
print(f"Generated {out_file.resolve()} ({len(html)} chars).")
