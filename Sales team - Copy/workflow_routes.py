"""
workflow_routes.py - Bridge to the standalone workflow package (in workflow/)
Preserves compatibility with app.py and existing imports while isolating all workflow logic.
"""

from workflow.routes import (
    router,
    run_workflow,
    save_project,
    list_projects,
    load_project,
    delete_project,
    get_workflow_logs,
    list_workflow_outputs,
    download_workflow_output
)
from workflow.models import Node, Edge, NodeData, SaveProjectRequest
from workflow.engine import execute_workflow, WORKFLOW_OUTPUTS_DIR, WORKFLOW_LOGS_DIR

__all__ = [
    "router",
    "run_workflow",
    "save_project",
    "list_projects",
    "load_project",
    "delete_project",
    "get_workflow_logs",
    "list_workflow_outputs",
    "download_workflow_output",
    "Node",
    "Edge",
    "NodeData",
    "SaveProjectRequest",
    "execute_workflow",
    "WORKFLOW_OUTPUTS_DIR",
    "WORKFLOW_LOGS_DIR"
]
