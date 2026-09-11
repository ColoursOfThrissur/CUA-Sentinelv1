"""
Hierarchical Task Planner Module for CUA-Sentinel.

Decomposes complex requests into a structured JSON Intermediate Representation (IR) tree
to prevent context drift and VRAM memory bloat on 7B-14B local models.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class HierarchicalTaskPlanner:
    def __init__(self, state_manager=None):
        self.state_manager = state_manager

    def decompose_task(self, goal: str, category: str = "coding") -> Dict[str, Any]:
        """
        Decomposes a high-level goal into a structured JSON IR plan.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        
        # Generate initial IR structure
        ir_plan = {
            "plan_id": plan_id,
            "goal": goal,
            "category": category,
            "status": "in_progress",
            "nodes": []
        }
        
        # Create standard sub-task nodes based on category
        if category in ("coding", "architecture"):
            ir_plan["nodes"] = [
                {
                    "node_id": f"{plan_id}_n1",
                    "step_number": 1,
                    "title": "Define Architecture & Schemas",
                    "description": "Establish core data structures and function contracts.",
                    "expected_symbols": ["config", "schema", "init"],
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n2",
                    "step_number": 2,
                    "title": "Implement Core Logic",
                    "description": "Write implementation modules following the defined schema.",
                    "expected_symbols": ["handler", "process"],
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n3",
                    "step_number": 3,
                    "title": "Verification & Integration",
                    "description": "Verify code AST syntax and run verification gates.",
                    "expected_symbols": ["verify", "test"],
                    "status": "pending",
                    "output_artifact": None
                }
            ]
        else:
            ir_plan["nodes"] = [
                {
                    "node_id": f"{plan_id}_n1",
                    "step_number": 1,
                    "title": "Information Gathering",
                    "description": "Gather relevant facts and document sources.",
                    "expected_symbols": ["facts", "sources"],
                    "status": "pending",
                    "output_artifact": None
                },
                {
                    "node_id": f"{plan_id}_n2",
                    "step_number": 2,
                    "title": "Synthesis & Action Plan",
                    "description": "Synthesize observations into actionable JSON items.",
                    "expected_symbols": ["summary", "action_items"],
                    "status": "pending",
                    "output_artifact": None
                }
            ]

        logger.info(f"Created Hierarchical IR Plan {plan_id} with {len(ir_plan['nodes'])} nodes.")
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
