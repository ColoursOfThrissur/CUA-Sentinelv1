"""
Hierarchical Task Planner Module for CUA-Sentinel.

Decomposes complex requests into a structured JSON Intermediate Representation (IR) tree
to prevent context drift and VRAM memory bloat on 7B-14B local models.
"""

import uuid
import logging
import os
from typing import Dict, Any, List, Optional
from core.solution_context import solution_context_engine

logger = logging.getLogger(__name__)

class HierarchicalTaskPlanner:
    def __init__(self, state_manager=None):
        self.state_manager = state_manager

    def _extract_keywords(self, goal: str) -> dict:
        g = goal.lower()
        return {
            'has_auth': any(k in g for k in ['auth', 'login', 'jwt', 'token', 'oauth', 'session', 'user', 'password']),
            'has_api': any(k in g for k in ['api', 'endpoint', 'route', 'rest', 'fastapi', 'flask', 'request', 'response']),
            'has_ui': any(k in g for k in ['ui', 'frontend', 'react', 'component', 'dashboard', 'page', 'view', 'button', 'form']),
            'has_db': any(k in g for k in ['database', 'db', 'sqlite', 'postgres', 'sql', 'model', 'schema', 'migration', 'table']),
            'has_test': any(k in g for k in ['test', 'unittest', 'pytest', 'coverage', 'mock', 'assert']),
            'has_security': any(k in g for k in ['security', 'encrypt', 'hash', 'sanitize', 'xss', 'csrf', 'injection']),
            'has_refactor': any(k in g for k in ['refactor', 'cleanup', 'optimize', 'improve', 'fix', 'rewrite', 'bug', 'error']),
            'has_websocket': any(k in g for k in ['websocket', 'ws', 'realtime', 'socket', 'stream', 'event']),
            'has_css': any(k in g for k in ['css', 'style', 'styling', 'theme', 'dark', 'color', 'font', 'layout', 'responsive', 'animation', 'glassmorphism', 'glass']),
            'has_component': any(k in g for k in ['component', 'widget', 'modal', 'card', 'navbar', 'sidebar', 'table', 'chart', 'panel', 'statcard']),
        }

    def decompose_task(self, goal: str, category: str = "coding", project_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Decomposes a high-level goal into a structured JSON IR plan.
        Leverages Solution Architecture Map if project_path is provided.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"

        # Scan project context if path exists
        sol_map = {}
        file_count = 0
        if project_path and os.path.exists(project_path):
            try:
                sol_map = solution_context_engine.build_solution_map(project_path)
                file_count = sol_map.get("total_files", 0)
            except Exception as err:
                logger.warning(f"Planner solution scan skipped: {err}")

        # Generate initial IR structure
        ir_plan = {
            "plan_id": plan_id,
            "goal": goal,
            "category": category,
            "status": "in_progress",
            "project_files_scanned": file_count,
            "nodes": []
        }

        # Create standard sub-task nodes based on category & domain analysis
        if category in ("coding", "architecture"):
            kw = self._extract_keywords(goal)
            
            domains = []
            if kw['has_auth']: domains.append('Auth & Security')
            if kw['has_api']: domains.append('FastAPI Endpoints')
            if kw['has_ui']: domains.append('React UI Components')
            if kw['has_component']: domains.append('Modular UI Components')
            if kw['has_css']: domains.append('Design System & CSS Styling')
            if kw['has_db']: domains.append('Database Schema')
            if kw['has_websocket']: domains.append('WebSocket Realtime Stream')
            if kw['has_refactor']: domains.append('AST Refactor & Bug Fixes')
            domain_str = ' & '.join(domains) if domains else 'System Architecture'

            # Node 1: Architecture & Contract Definition
            arch_symbols = ['config', 'schema', 'types']
            if kw['has_auth']: arch_symbols.extend(['User', 'Token', 'auth_middleware'])
            if kw['has_db']: arch_symbols.extend(['Model', 'Migration', 'db_session'])
            if kw['has_api']: arch_symbols.extend(['Router', 'endpoint_handler', 'RequestSchema'])
            if kw['has_ui']: arch_symbols.extend(['Props', 'ComponentState', 'apiClient'])
            if kw['has_css']: arch_symbols.extend(['theme_tokens', 'css_classes', 'index.css'])
            if kw['has_component']: arch_symbols.extend(['ComponentProps', 'ModularWidget'])

            node1_title = f"Design & Contract Setup: {domain_str}"
            node1_desc = (
                f"Establish core interfaces, data structures, and import contracts for goal: '{goal[:100]}'. "
                f"Scanned {file_count} solution files to prevent breaking existing components."
            )

            # Node 2: Implementation & Code Synthesis
            impl_title = f"Synthesize Core Modules for {domain_str}"
            impl_desc = (
                f"Implement and update source modules for goal: '{goal[:140]}'. "
                f"Ensure strict TypeScript typing and Python AST syntax."
            )
            impl_symbols = ['handler', 'process', 'render', 'execute']
            if kw['has_auth']: impl_symbols.extend(['authenticate_user', 'create_access_token'])
            if kw['has_ui']: impl_symbols.extend(['renderView', 'useWorkspaceStore', 'fetchData'])
            if kw['has_component']: impl_symbols.extend(['createModularWidget', 'mountComponent'])
            if kw['has_css']: impl_symbols.extend(['applyStyles', 'colorVariables', 'responsiveLayout'])
            if kw['has_websocket']: impl_symbols.extend(['broadcast_event', 'on_connect'])

            # Node 3: Verification & Integration Gate
            verify_title = "AST Syntax, Type & Verification Gate"
            verify_desc = (
                "Run static analysis (TypeScript npx tsc --noEmit / Python ast.parse), "
                "verify zero stub comments (TODO/FIXME/pass), and validate server integration."
            )

            nodes = [
                {
                    "node_id": f"{plan_id}_n1",
                    "step_number": 1,
                    "title": node1_title,
                    "description": node1_desc,
                    "expected_symbols": arch_symbols,
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n2",
                    "step_number": 2,
                    "title": impl_title,
                    "description": impl_desc,
                    "expected_symbols": impl_symbols,
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n3",
                    "step_number": 3,
                    "title": verify_title,
                    "description": verify_desc,
                    "expected_symbols": ['verify_ast', 'tsc_build', 'zero_stub_check'],
                    "status": "pending",
                    "output_artifact": None
                }
            ]
            ir_plan["nodes"] = nodes
        else:
            ir_plan["nodes"] = [
                {
                    "node_id": f"{plan_id}_n1",
                    "step_number": 1,
                    "title": "Information & Requirement Gathering",
                    "description": "Gather relevant facts, solution context, and document sources.",
                    "expected_symbols": ["facts", "sources"],
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n2",
                    "step_number": 2,
                    "title": "Synthesis & Execution Roadmap",
                    "description": "Synthesize observations into actionable JSON items and file updates.",
                    "expected_symbols": ["summary", "action_items"],
                    "status": "pending",
                    "output_artifact": None
                }
            ]

        logger.info(f"Created Hierarchical IR Plan {plan_id} ({file_count} files scanned) with {len(ir_plan['nodes'])} nodes.")
        return ir_plan

    def update_node_status(self, plan: Dict[str, Any], node_id: str, status: str, output: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Updates node completion status and stores output artifact in JSON IR.
        """
        all_completed = True
        for node in plan.get("nodes", []):
            if node["node_id"] == node_id:
                node["status"] = status
                if output:
                    node["output_artifact"] = output
            if node["status"] != "completed":
                all_completed = False
                
        if all_completed:
            plan["status"] = "completed"
            
        return plan

hierarchical_planner = HierarchicalTaskPlanner()
