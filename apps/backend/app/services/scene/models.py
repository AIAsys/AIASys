from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SubAgentRoleDef(BaseModel):
    display_name: str
    description: str


class SceneDefinition(BaseModel):
    scene_id: str
    display_name: str
    description: str
    category: str
    icon: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    config_path: str
    prompt_path: str
    subagent_config_path: Optional[str] = None
    agent_type: str
    subagent_roles: Dict[str, SubAgentRoleDef] = Field(default_factory=dict)
    requires_runtime: bool = True
    permissions_summary: List[str] = Field(default_factory=list)


class SceneSummary(BaseModel):
    scene_id: str
    display_name: str
    description: str
    category: str
    icon: Optional[str] = None
    tags: List[str]


class SceneListItem(BaseModel):
    enabled: bool = True
    path: str


class SceneRegistryIndex(BaseModel):
    scenes: Dict[str, SceneListItem]
