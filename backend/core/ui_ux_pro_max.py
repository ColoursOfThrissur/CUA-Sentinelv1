"""
UI/UX Pro Max Design Intelligence Engine for CUA-Sentinel.

Inspired by nextlevelbuilder/ui-ux-pro-max-skill.
Provides design intelligence, curated color palettes, Google Fonts pairings,
CSS design token generators, and pre-delivery UI quality checklists.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

DESIGN_STYLES = {
    "Glassmorphism": {
        "name": "Glassmorphism Dark",
        "primary": "#3b82f6",
        "secondary": "#8b5cf6",
        "accent": "#ec4899",
        "cta": "#10b981",
        "background": "#0f172a",
        "card_bg": "rgba(30, 41, 59, 0.7)",
        "text": "#f8fafc",
        "text_muted": "#94a3b8",
        "border": "rgba(255, 255, 255, 0.12)",
        "font_heading": "Inter, sans-serif",
        "font_body": "Inter, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap"
    },
    "Soft UI": {
        "name": "Soft UI Evolution",
        "primary": "#e8b4b8",
        "secondary": "#a8d5ba",
        "accent": "#d4af37",
        "cta": "#d4af37",
        "background": "#fff5f5",
        "card_bg": "#ffffff",
        "text": "#2d3436",
        "text_muted": "#636e72",
        "border": "rgba(0, 0, 0, 0.06)",
        "font_heading": "Cormorant Garamond, serif",
        "font_body": "Montserrat, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Montserrat:wght@400;500&display=swap"
    },
    "Clean SaaS Dark": {
        "name": "Clean SaaS Dark",
        "primary": "#6366f1",
        "secondary": "#06b6d4",
        "accent": "#f59e0b",
        "cta": "#10b981",
        "background": "#111827",
        "card_bg": "#1f2937",
        "text": "#f9fafb",
        "text_muted": "#9ca3af",
        "border": "rgba(255, 255, 255, 0.08)",
        "font_heading": "Plus Jakarta Sans, sans-serif",
        "font_body": "Inter, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;800&family=Inter:wght@400;500&display=swap"
    },
    "Developer Dark": {
        "name": "Developer IDE Dark",
        "primary": "#38bdf8",
        "secondary": "#a855f7",
        "accent": "#f43f5e",
        "cta": "#22c55e",
        "background": "#090d16",
        "card_bg": "#131b2e",
        "text": "#f1f5f9",
        "text_muted": "#64748b",
        "border": "rgba(56, 189, 248, 0.2)",
        "font_heading": "JetBrains Mono, monospace",
        "font_body": "Inter, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&family=Inter:wght@400;500&display=swap"
    },
    "Light": {
        "name": "Clean Light",
        "primary": "#2563eb",
        "secondary": "#7c3aed",
        "accent": "#db2777",
        "cta": "#059669",
        "background": "#f8fafc",
        "card_bg": "#ffffff",
        "text": "#0f172a",
        "text_muted": "#64748b",
        "border": "rgba(0, 0, 0, 0.09)",
        "font_heading": "Plus Jakarta Sans, sans-serif",
        "font_body": "Inter, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;800&family=Inter:wght@400;500&display=swap"
    },
    "Corporate": {
        "name": "Corporate Pro",
        "primary": "#1d4ed8",
        "secondary": "#0369a1",
        "accent": "#b45309",
        "cta": "#15803d",
        "background": "#f1f5f9",
        "card_bg": "#ffffff",
        "text": "#1e293b",
        "text_muted": "#475569",
        "border": "rgba(0, 0, 0, 0.1)",
        "font_heading": "Montserrat, sans-serif",
        "font_body": "Open Sans, sans-serif",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Open+Sans:wght@400;500&display=swap"
    },
    "Neon": {
        "name": "Neon Cyberpunk",
        "primary": "#00fff5",
        "secondary": "#ff00aa",
        "accent": "#ffe600",
        "cta": "#00ff88",
        "background": "#050510",
        "card_bg": "rgba(0, 255, 245, 0.04)",
        "text": "#e2e8f0",
        "text_muted": "#64748b",
        "border": "rgba(0, 255, 245, 0.2)",
        "font_heading": "Orbitron, monospace",
        "font_body": "Share Tech Mono, monospace",
        "font_google_url": "https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&display=swap"
    },
    "Terminal": {
        "name": "Hacker Terminal",
        "primary": "#22c55e",
        "secondary": "#4ade80",
        "accent": "#fbbf24",
        "cta": "#22c55e",
        "background": "#0a0a0a",
        "card_bg": "#111111",
        "text": "#d4d4d4",
        "text_muted": "#737373",
        "border": "rgba(34, 197, 94, 0.25)",
        "font_heading": "JetBrains Mono, monospace",
        "font_body": "JetBrains Mono, monospace",
        "font_google_url": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap"
    },
}

class UIUXProMaxEngine:
    def get_design_system(self, style_name: str = "Glassmorphism") -> Dict[str, Any]:
        """
        Returns design system tokens matching selected visual style.
        """
        style = DESIGN_STYLES.get(style_name, DESIGN_STYLES["Glassmorphism"])
        return {
            "style_name": style["name"],
            "colors": {
                "primary": style["primary"],
                "secondary": style["secondary"],
                "accent": style["accent"],
                "cta": style["cta"],
                "background": style["background"],
                "card_bg": style["card_bg"],
                "text": style["text"],
                "text_muted": style["text_muted"],
                "border": style["border"]
            },
            "typography": {
                "font_heading": style["font_heading"],
                "font_body": style["font_body"],
                "google_fonts_import": style["font_google_url"]
            },
            "checklist": [
                "Use Lucide SVG icons instead of raw emojis for UI buttons.",
                "Enforce cursor: pointer on all clickable elements.",
                "Ensure WCAG text contrast ratio >= 4.5:1.",
                "Support responsive breakpoints (375px, 768px, 1024px, 1440px)."
            ]
        }

    def generate_css_variables(self, style_name: str = "Glassmorphism") -> str:
        """
        Generates a complete, production-grade Pure Vanilla CSS Design System for inclusion in src/index.css.
        Includes CSS resets, design tokens, responsive layout shells, cards, typography, grids, buttons, badges, tables, and form elements.
        """
        ds = self.get_design_system(style_name)
        c = ds["colors"]
        t = ds["typography"]
        return f"""/* UI/UX Pro Max Generated Pure Vanilla CSS Design System */
@import url('{t["google_fonts_import"]}');

:root {{
  --primary-color: {c["primary"]};
  --secondary-color: {c["secondary"]};
  --accent-color: {c["accent"]};
  --cta-color: {c["cta"]};
  --bg-color: {c["background"]};
  --card-bg: {c["card_bg"]};
  --text-main: {c["text"]};
  --text-muted: {c["text_muted"]};
  --border-color: {c["border"]};
  --font-heading: {t["font_heading"]};
  --font-body: {t["font_body"]};
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
  --shadow-md: 0 4px 14px -2px rgba(0,0,0,0.25);
  --shadow-lg: 0 10px 30px -4px rgba(0,0,0,0.35);
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}}

/* 1. Global Reset & Typography Defaults */
* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

html, body {{
  height: 100%;
  background-color: var(--bg-color);
  color: var(--text-main);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}

h1, h2, h3, h4, h5, h6 {{
  font-family: var(--font-heading);
  color: var(--text-main);
  font-weight: 700;
  line-height: 1.25;
}}

h1 {{ font-size: 1.75rem; }}
h2 {{ font-size: 1.4rem; }}
h3 {{ font-size: 1.15rem; }}
h4 {{ font-size: 1rem; }}

p {{
  color: var(--text-muted);
  font-size: 0.9rem;
}}

a {{
  color: var(--primary-color);
  text-decoration: none;
  transition: var(--transition);
}}
a:hover {{ text-decoration: underline; }}

/* 2. Layout & Shell Architecture */
.app-shell {{
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: var(--bg-color);
}}

.sidebar {{
  width: 260px;
  background-color: var(--card-bg);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(12px);
  z-index: 20;
  flex-shrink: 0;
}}

.sidebar-header {{
  height: 64px;
  padding: 0 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}}

.sidebar-nav {{
  flex: 1;
  padding: 1.25rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  overflow-y: auto;
}}

.nav-item {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-weight: 500;
  font-size: 0.9rem;
  cursor: pointer;
  background: transparent;
  border: none;
  width: 100%;
  text-align: left;
  transition: var(--transition);
}}

.nav-item:hover, .nav-item.active {{
  color: var(--text-main);
  background-color: rgba(255, 255, 255, 0.08);
}}

.nav-item.active {{
  border-left: 3px solid var(--primary-color);
  color: var(--primary-color);
}}

.main-content {{
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}}

.header {{
  height: 64px;
  padding: 0 1.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--card-bg);
  backdrop-filter: blur(12px);
  z-index: 10;
}}

.workspace-area {{
  flex: 1;
  padding: 1.75rem;
  overflow-y: auto;
}}

/* 3. Surface Cards & Elevators */
.card {{
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(12px);
  transition: var(--transition);
}}

.card-interactive:hover {{
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.2);
}}

.card-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}}

.card-title {{
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-main);
}}

.card-body {{
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}}

/* 4. Grid System & Flex Utilities */
.grid-layout {{
  display: grid;
  gap: 1.25rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}}

.grid-2 {{
  display: grid;
  gap: 1.25rem;
  grid-template-columns: repeat(2, 1fr);
}}

.grid-3 {{
  display: grid;
  gap: 1.25rem;
  grid-template-columns: repeat(3, 1fr);
}}

.grid-4 {{
  display: grid;
  gap: 1.25rem;
  grid-template-columns: repeat(4, 1fr);
}}

@media (max-width: 1024px) {{
  .grid-3, .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
}}

@media (max-width: 640px) {{
  .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr; }}
  .sidebar {{ display: none; }}
}}

.flex {{ display: flex; }}
.flex-col {{ flex-direction: column; }}
.flex-between {{ justify-content: space-between; }}
.items-center {{ align-items: center; }}
.gap-1 {{ gap: 0.25rem; }}
.gap-2 {{ gap: 0.5rem; }}
.gap-3 {{ gap: 0.75rem; }}
.gap-4 {{ gap: 1rem; }}
.p-1 {{ padding: 0.25rem; }}
.p-2 {{ padding: 0.5rem; }}
.p-3 {{ padding: 0.75rem; }}
.p-4 {{ padding: 1rem; }}
.p-6 {{ padding: 1.5rem; }}
.text-xs {{ font-size: 0.75rem; }}
.text-sm {{ font-size: 0.875rem; }}
.text-base {{ font-size: 1rem; }}
.text-lg {{ font-size: 1.125rem; }}
.text-xl {{ font-size: 1.25rem; }}
.text-2xl {{ font-size: 1.5rem; }}
.text-3xl {{ font-size: 1.875rem; }}
.font-normal {{ font-weight: 400; }}
.font-medium {{ font-weight: 500; }}
.font-semibold {{ font-weight: 600; }}
.font-bold {{ font-weight: 700; }}
.text-muted, .text-gray-500, .text-gray-400 {{ color: var(--text-muted); }}
.text-main, .text-gray-900, .text-white {{ color: var(--text-main); }}
.bg-subtle, .bg-gray-100, .bg-gray-800 {{ background-color: rgba(255, 255, 255, 0.05); }}
.rounded, .rounded-md {{ border-radius: var(--radius-sm); }}
.rounded-lg {{ border-radius: var(--radius-md); }}
.w-full {{ width: 100%; }}
.h-full {{ height: 100%; }}

/* 5. Buttons & Interactive Elements */
.btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.55rem 1.1rem;
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: var(--transition);
  outline: none;
}}

.btn-primary {{
  background-color: var(--primary-color);
  color: #ffffff;
}}
.btn-primary:hover {{
  opacity: 0.9;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}}

.btn-secondary {{
  background-color: transparent;
  border-color: var(--border-color);
  color: var(--text-main);
}}
.btn-secondary:hover {{
  background-color: rgba(255, 255, 255, 0.08);
  border-color: var(--text-muted);
}}

.btn-danger {{
  background-color: #ef4444;
  color: #ffffff;
}}
.btn-danger:hover {{ opacity: 0.9; }}

.btn-icon {{
  padding: 0.5rem;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  border: none;
  cursor: pointer;
}}
.btn-icon:hover {{
  color: var(--text-main);
  background-color: rgba(255, 255, 255, 0.08);
}}

/* 6. Badges & Status Indicators */
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}}

.badge-success {{
  background-color: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}}

.badge-warning {{
  background-color: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}}

.badge-danger {{
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}}

.badge-info {{
  background-color: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}}

/* 7. Forms & Inputs */
.form-group {{
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 1rem;
}}

.form-label {{
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
}}

.input-field, .select-field, .textarea-field {{
  width: 100%;
  padding: 0.6rem 0.85rem;
  background-color: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-main);
  font-size: 0.9rem;
  outline: none;
  transition: var(--transition);
}}

.input-field:focus, .select-field:focus, .textarea-field:focus {{
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}}

/* 8. Tables & Data Lists */
.table-container {{
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background-color: var(--card-bg);
}}

.table {{
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.875rem;
}}

.table th {{
  padding: 0.85rem 1rem;
  background-color: rgba(0, 0, 0, 0.15);
  color: var(--text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
}}

.table td {{
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-main);
}}

.table tr:last-child td {{
  border-bottom: none;
}}

.table tr:hover td {{
  background-color: rgba(255, 255, 255, 0.03);
}}

/* 9. Scrollbar Formatting */
.custom-scrollbar::-webkit-scrollbar {{
  width: 6px;
  height: 6px;
}}
.custom-scrollbar::-webkit-scrollbar-track {{
  background: transparent;
}}
.custom-scrollbar::-webkit-scrollbar-thumb {{
  background-color: rgba(255, 255, 255, 0.15);
  border-radius: 20px;
}}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {{
  background-color: rgba(255, 255, 255, 0.3);
}}

/* 10. Modal & Overlay */
.modal-overlay {{
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.15s ease;
}}

.modal {{
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 1.75rem;
  width: 100%;
  max-width: 520px;
  box-shadow: var(--shadow-lg);
  animation: slideUp 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}}

.modal-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--border-color);
}}

.modal-title {{
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-main);
}}

.modal-footer {{
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}}

@keyframes fadeIn {{
  from {{ opacity: 0; }}
  to {{ opacity: 1; }}
}}

@keyframes slideUp {{
  from {{ transform: translateY(16px); opacity: 0; }}
  to {{ transform: translateY(0); opacity: 1; }}
}}

/* 11. Toast Notifications */
.toast-container {{
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  z-index: 2000;
}}

.toast {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.1rem;
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  font-size: 0.875rem;
  color: var(--text-main);
  min-width: 280px;
  max-width: 400px;
  animation: slideUp 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}}

.toast-success {{ border-left: 4px solid #10b981; }}
.toast-warning {{ border-left: 4px solid #f59e0b; }}
.toast-danger  {{ border-left: 4px solid #ef4444; }}
.toast-info    {{ border-left: 4px solid var(--primary-color); }}

/* 12. Skeleton Loaders */
.skeleton {{
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 25%,
    rgba(255, 255, 255, 0.09) 50%,
    rgba(255, 255, 255, 0.04) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-sm);
}}

.skeleton-text {{
  height: 0.85rem;
  margin-bottom: 0.5rem;
  border-radius: 9999px;
}}

.skeleton-text.w-3-4 {{ width: 75%; }}
.skeleton-text.w-1-2 {{ width: 50%; }}
.skeleton-text.w-1-4 {{ width: 25%; }}

.skeleton-avatar {{
  width: 40px;
  height: 40px;
  border-radius: 50%;
}}

.skeleton-card {{
  height: 120px;
  border-radius: var(--radius-md);
}}

@keyframes shimmer {{
  0%   {{ background-position: 200% 0; }}
  100% {{ background-position: -200% 0; }}
}}

/* 13. Chips & Tags */
.chip {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.7rem;
  border-radius: 9999px;
  font-size: 0.78rem;
  font-weight: 500;
  background-color: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  cursor: default;
  transition: var(--transition);
}}

.chip-primary {{
  background-color: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.3);
  color: var(--primary-color);
}}

.chip-removable {{ cursor: pointer; }}
.chip-removable:hover {{
  background-color: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}}

/* 14. Progress Bars */
.progress {{
  width: 100%;
  height: 6px;
  background-color: rgba(255, 255, 255, 0.08);
  border-radius: 9999px;
  overflow: hidden;
}}

.progress-bar {{
  height: 100%;
  border-radius: 9999px;
  background-color: var(--primary-color);
  transition: width 0.4s ease;
}}

.progress-bar.success {{ background-color: #10b981; }}
.progress-bar.warning {{ background-color: #f59e0b; }}
.progress-bar.danger  {{ background-color: #ef4444; }}

/* 15. Dividers & Spacers */
.divider {{
  height: 1px;
  background-color: var(--border-color);
  margin: 1rem 0;
}}

.spacer-sm {{ height: 0.5rem; }}
.spacer-md {{ height: 1rem; }}
.spacer-lg {{ height: 2rem; }}
"""

    def parse_blueprint_style_overrides(self, blueprint_content: str, base_style: str = "Glassmorphism") -> Dict[str, Any]:
        """
        Parses a user's blueprint/spec document for explicit UI style declarations
        and returns an overridden design system that respects the user spec.
        
        Priority: explicit blueprint declarations > ui_style parameter > default Glassmorphism.
        """
        import re
        text = blueprint_content.lower()
        
        overrides: Dict[str, Any] = {}
        detected_theme = base_style
        
        theme_patterns = [
            (r'\b(glassmorphism|glass morphism)\b', 'Glassmorphism'),
            (r'\b(soft ui|soft-ui|neumorphism)\b', 'Soft UI'),
            (r'\b(clean saas dark|saas dark|saas)\b', 'Clean SaaS Dark'),
            (r'\b(developer dark|dev dark|ide dark)\b', 'Developer Dark'),
            (r'\b(light theme|clean light|light mode|white theme)\b', 'Light'),
            (r'\b(corporate|enterprise|professional)\b', 'Corporate'),
            (r'\b(neon|cyberpunk|cyber punk)\b', 'Neon'),
            (r'\b(terminal|hacker|cli|monospace theme)\b', 'Terminal'),
        ]
        for pattern, theme_name in theme_patterns:
            if re.search(pattern, text):
                detected_theme = theme_name
                break
        
        primary_hex = re.search(
            r'(?:primary|brand|main)\s*(?:color)?\s*[:\-=]?\s*#([0-9a-fA-F]{3,6})', 
            blueprint_content, re.IGNORECASE
        )
        secondary_hex = re.search(
            r'(?:secondary|accent)\s*(?:color)?\s*[:\-=]?\s*#([0-9a-fA-F]{3,6})',
            blueprint_content, re.IGNORECASE
        )
        bg_hex = re.search(
            r'(?:background|bg)\s*(?:color)?\s*[:\-=]?\s*#([0-9a-fA-F]{3,6})',
            blueprint_content, re.IGNORECASE
        )
        
        if primary_hex:
            overrides['primary'] = f'#{primary_hex.group(1)}'
        if secondary_hex:
            overrides['secondary'] = f'#{secondary_hex.group(1)}'
        if bg_hex:
            overrides['background'] = f'#{bg_hex.group(1)}'
        
        COLOR_NAMES = {
            'blue': '#3b82f6', 'indigo': '#6366f1', 'purple': '#8b5cf6',
            'pink': '#ec4899', 'red': '#ef4444', 'orange': '#f97316',
            'yellow': '#f59e0b', 'green': '#22c55e', 'teal': '#14b8a6',
            'cyan': '#06b6d4', 'sky': '#0ea5e9',
        }
        primary_name = re.search(
            r'(?:primary|brand)\s*(?:color)?\s*[:\-=]?\s*(' + '|'.join(COLOR_NAMES.keys()) + r')\b',
            text
        )
        if primary_name and 'primary' not in overrides:
            overrides['primary'] = COLOR_NAMES[primary_name.group(1)]
        
        FONT_PATTERNS = [
            (r'\broboto\b', 'Roboto, sans-serif'),
            (r'\bpoppins\b', 'Poppins, sans-serif'),
            (r'\bmontserrat\b', 'Montserrat, sans-serif'),
            (r'\binter\b', 'Inter, sans-serif'),
            (r'\blato\b', 'Lato, sans-serif'),
            (r'\bnunito\b', 'Nunito, sans-serif'),
            (r'\bsource code pro\b', 'Source Code Pro, monospace'),
            (r'\bfira code\b', 'Fira Code, monospace'),
        ]
        for pattern, font_val in FONT_PATTERNS:
            if re.search(pattern, text):
                overrides['font_body'] = font_val
                break
        
        layout_hints: Dict[str, bool] = {
            'has_sidebar': bool(re.search(r'\b(sidebar|side bar|side nav|side panel|navigation panel)\b', text)),
            'no_sidebar': bool(re.search(r'\b(no sidebar|without sidebar|full.?width|single column)\b', text)),
            'is_dashboard': bool(re.search(r'\b(dashboard|analytics|monitor|kpi|metric|chart|graph)\b', text)),
            'is_landing': bool(re.search(r'\b(landing page|hero|homepage|marketing|showcase)\b', text)),
            'is_form_heavy': bool(re.search(r'\b(form|wizard|step|onboarding|registration|login page)\b', text)),
            'has_table': bool(re.search(r'\b(table|list view|data grid|records|crud)\b', text)),
            'has_kanban': bool(re.search(r'\b(kanban|board|task card|drag.?drop|columns)\b', text)),
            'is_chat': bool(re.search(r'\b(chat|messaging|conversation|inbox|thread)\b', text)),
        }
        
        framework_hints: Dict[str, bool] = {
            'use_nextjs': bool(re.search(r'\b(next\.?js|nextjs|app router|pages router)\b', text)),
            'use_tailwind': bool(re.search(r'\b(tailwind|tw css)\b', text)),
            'use_shadcn': bool(re.search(r'\b(shadcn|shadcn/ui|radix)\b', text)),
            'use_mui': bool(re.search(r'\b(mui|material ui|material-ui)\b', text)),
        }
        
        base_ds = self.get_design_system(detected_theme)
        merged_colors = dict(base_ds['colors'])
        merged_colors.update({k: v for k, v in overrides.items() if k in merged_colors})
        merged_typography = dict(base_ds['typography'])
        if 'font_body' in overrides:
            merged_typography['font_body'] = overrides['font_body']
        
        return {
            'detected_theme': detected_theme,
            'overrides_applied': list(overrides.keys()),
            'layout_hints': layout_hints,
            'framework_hints': framework_hints,
            'colors': merged_colors,
            'typography': merged_typography,
            'checklist': base_ds['checklist'],
        }

ui_ux_pro_max = UIUXProMaxEngine()

