from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class NodeData(BaseModel):
    label: Optional[str] = None
    saveOption: Optional[str] = None
    model_config = {"extra": "allow"}

class Node(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]
    position: Optional[Dict[str, float]] = None

class Edge(BaseModel):
    id: str
    source: str
    target: str

class SaveProjectRequest(BaseModel):
    id: Optional[str] = None
    name: str
    nodes: list
    edges: list
