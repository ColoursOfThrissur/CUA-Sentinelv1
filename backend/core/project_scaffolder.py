"""
Project Scaffolder Engine for CUA-Sentinel.

Scaffolds new projects from scratch on target D:\\ drive locations with UI/UX Pro Max design tokens,
FastAPI / React / Python CLI boilerplate files, requirements.txt, package.json, and README.md.
"""

import os
import json
import logging
from typing import Dict, Any
from core.path_security import path_security
from core.ui_ux_pro_max import ui_ux_pro_max

logger = logging.getLogger(__name__)

class ProjectScaffolder:
    def create_project_structure(
        self,
        project_name: str,
        target_path: str,
        tech_stack: str = "FastAPI + React",
        ui_style: str = "Glassmorphism",
        description: str = "",
        blueprint_content: str = "",
        blueprint_filename: str = ""
    ) -> Dict[str, Any]:
        """
        Scaffolds a new project directory on D:\\ with tech stack boilerplate, UI/UX design tokens, and optional architectural blueprint document.
        """
        # Enforce D:\ Drive Write Permission Security
        path_security.validate_write_permission(target_path)

        os.makedirs(target_path, exist_ok=True)
        created_files = []

        # If custom blueprint/directive document was provided, write ARCHITECTURE_SPEC.md
        if blueprint_content and blueprint_content.strip():
            spec_path = os.path.join(target_path, "ARCHITECTURE_SPEC.md")
            spec_header = f"# Architectural Spec Blueprint: {blueprint_filename or 'Directive Spec'}\n\n> Custom blueprint uploaded by user.\n\n"
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(spec_header + blueprint_content)
            created_files.append("ARCHITECTURE_SPEC.md")

        # Generate UI/UX Pro Max CSS tokens
        css_tokens = ui_ux_pro_max.generate_css_variables(ui_style)

        # 1. Write README.md
        readme_content = f"""# {project_name}

> {description or 'Generated autonomously by CUA-Sentinel AI Developer Engine.'}

## Architecture & Tech Stack
- **Stack:** {tech_stack}
- **UI/UX Design Style:** {ui_style} (UI/UX Pro Max Engine)
- **Target Drive:** `{target_path}`
{"- **Architectural Spec Directive:** `ARCHITECTURE_SPEC.md` attached" if blueprint_content else ""}

## Getting Started
```bash
# Backend setup
pip install -r requirements.txt
python main.py

# Frontend setup (if applicable)
npm install
npm run dev
```
"""
        readme_path = os.path.join(target_path, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        created_files.append("README.md")

        # 2. Write requirements.txt
        reqs_content = "fastapi>=0.100.0\nuvicorn>=0.22.0\npydantic>=2.0.0\nrequests>=2.31.0\npytest>=7.4.0\n"
        reqs_path = os.path.join(target_path, "requirements.txt")
        with open(reqs_path, "w", encoding="utf-8") as f:
            f.write(reqs_content)
        created_files.append("requirements.txt")

        # 3. Write package.json
        pkg_content = {
            "name": project_name.lower().replace(" ", "-"),
            "version": "1.0.0",
            "private": True,
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build"
            },
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "lucide-react": "^0.300.0"
            },
            "devDependencies": {
                "vite": "^5.4.0",
                "@vitejs/plugin-react": "^4.3.0",
                "typescript": "^5.2.0",
                "@types/react": "^18.2.0",
                "@types/react-dom": "^18.2.0"
            }
        }
        pkg_path = os.path.join(target_path, "package.json")
        with open(pkg_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(pkg_content, indent=2))
        created_files.append("package.json")

        # 3b. Scaffold vite.config.ts
        vite_config_content = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8001,
    host: true
  }
});
"""
        vite_config_path = os.path.join(target_path, "vite.config.ts")
        if not os.path.exists(vite_config_path):
            with open(vite_config_path, "w", encoding="utf-8") as f:
                f.write(vite_config_content)
            created_files.append("vite.config.ts")

        # 3c. Scaffold tsconfig.json
        tsconfig_content = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": false
  },
  "include": ["src"]
}
"""
        tsconfig_path = os.path.join(target_path, "tsconfig.json")
        if not os.path.exists(tsconfig_path):
            with open(tsconfig_path, "w", encoding="utf-8") as f:
                f.write(tsconfig_content)
            created_files.append("tsconfig.json")

        # 4. Write .gitignore
        git_content = "node_modules/\n.venv/\nvenv/\ndist/\n__pycache__/\n*.pyc\n.env\n.sentinel_backup/\n"
        git_path = os.path.join(target_path, ".gitignore")
        with open(git_path, "w", encoding="utf-8") as f:
            f.write(git_content)
        created_files.append(".gitignore")

        # 5. Scaffold backend/ and main.py
        backend_dir = os.path.join(target_path, "backend")
        os.makedirs(backend_dir, exist_ok=True)
        main_py_content = f"""\"\"\"
{project_name} - Main Entry Point
Generated by CUA-Sentinel AI Developer Engine
\"\"\"

import sys
from fastapi import FastAPI
from starlette.middleware import Middleware

def _middleware_smart_iter(self):
    try:
        frame = sys._getframe(1)
        code = frame.f_code.co_code
        lasti = frame.f_lasti
        oparg = code[lasti + 1] if lasti < len(code) - 1 else 3
        if oparg == 2:
            return iter((self.cls, self.kwargs))
    except Exception:
        pass
    return iter((self.cls, self.args, self.kwargs))

Middleware.__iter__ = _middleware_smart_iter

app = FastAPI(title="{project_name}", version="1.0.0")

@app.get("/")
def root():
    return {{"message": "Welcome to {project_name}", "status": "online"}}

@app.get("/health")
def health():
    return {{"status": "ok", "service": "{project_name}"}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
        main_py_path = os.path.join(backend_dir, "main.py")
        with open(main_py_path, "w", encoding="utf-8") as f:
            f.write(main_py_content)
        created_files.append("backend/main.py")

        # 6. Scaffold root index.html
        html_content = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{project_name}</title>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
      body {{ margin: 0; background-color: #0b0f19; color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif; }}
      .preview-container {{ padding: 2rem; max-width: 1200px; margin: 0 auto; }}
      .card {{ background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 1.5rem; backdrop-filter: blur(12px); }}
      .badge {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 0.25rem 0.6rem; border-radius: 12px; font-size: 0.8rem; border: 1px solid rgba(56, 189, 248, 0.3); }}
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="text/babel">
      function FallbackApp() {{
        return (
          <div className="preview-container">
            <div className="card">
              <span className="badge">LIVE SOLUTION READY</span>
              <h1 style={{{{ color: '#38bdf8', marginTop: '1rem' }}}}>✨ {project_name}</h1>
              <p style={{{{ color: '#94a3b8' }}}}>{description or 'Autonomously scaffolded by CUA-Sentinel AI Engine.'}</p>
              <p>Target Location: <code>{target_path}</code></p>
            </div>
          </div>
        );
      }}
      if (!window.__VITE_ACTIVE__) {{
        ReactDOM.createRoot(document.getElementById('root')).render(<FallbackApp />);
      }}
    </script>
    <script>window.__VITE_ACTIVE__ = true;</script>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""
        html_path = os.path.join(target_path, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        created_files.append("index.html")

        # 7. Scaffold frontend/src/ and App.tsx, App.css, main.tsx + index.css
        src_dir = os.path.join(target_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        css_path = os.path.join(src_dir, "index.css")
        with open(css_path, "w", encoding="utf-8") as f:
            f.write(css_tokens)
        created_files.append("src/index.css")

        app_css_path = os.path.join(src_dir, "App.css")
        with open(app_css_path, "w", encoding="utf-8") as f:
            f.write("/* App.css - Auto-scaffolded by CUA-Sentinel */\n")
        created_files.append("src/App.css")

        main_tsx_content = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
"""
        main_tsx_path = os.path.join(src_dir, "main.tsx")
        with open(main_tsx_path, "w", encoding="utf-8") as f:
            f.write(main_tsx_content)
        created_files.append("src/main.tsx")

        app_tsx_content = f"""import React from 'react'
import './index.css'
import './App.css'

export default function App() {{
  return (
    <div style={{{{ padding: '2rem', fontFamily: 'var(--font-body)', background: 'var(--bg-color)', color: 'var(--text-main)', minHeight: '100vh' }}}}>
      <header style={{{{ borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}}}>
        <h1 style={{{{ fontFamily: 'var(--font-heading)', color: 'var(--primary-color)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}}}>
          ✨ {project_name}
        </h1>
        <p style={{{{ color: 'var(--text-muted)' }}}}>{description or 'Autonomously scaffolded with UI/UX Pro Max Design Intelligence.'}</p>
      </header>

      <main style={{{{ marginTop: '2rem' }}}}>
        <div style={{{{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '0.75rem', padding: '1.5rem' }}}}>
          <h2 style={{{{ color: 'var(--cta-color)' }}}}>
            ✅ Solution Ready
          </h2>
          <p>Scaffolded at <code>{target_path}</code></p>
        </div>
      </main>
    </div>
  )
}}
"""
        app_tsx_path = os.path.join(src_dir, "App.tsx")
        with open(app_tsx_path, "w", encoding="utf-8") as f:
            f.write(app_tsx_content)
        created_files.append("src/App.tsx")

        logger.info(f"Successfully scaffolded project '{project_name}' at {target_path} ({len(created_files)} files created)")
        return {
            "project_name": project_name,
            "target_path": target_path,
            "tech_stack": tech_stack,
            "ui_style": ui_style,
            "created_files": created_files
        }

project_scaffolder = ProjectScaffolder()
