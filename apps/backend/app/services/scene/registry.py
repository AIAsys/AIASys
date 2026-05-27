import logging
import tomllib
from pathlib import Path
from typing import Dict, List, Optional

from .models import SceneDefinition, SceneRegistryIndex, SceneSummary

logger = logging.getLogger(__name__)

_AGENTS_DIR = Path(__file__).resolve().parents[3] / "app" / "agents"


class SceneRegistry:
    """Data-driven scene discovery and lookup."""

    def __init__(self, agents_dir: Path | None = None):
        self._agents_dir = agents_dir or _AGENTS_DIR
        self._scenes: Dict[str, SceneDefinition] = {}
        self._load_all()

    def _load_all(self) -> None:
        registry_path = self._agents_dir / "scenes" / "_registry.toml"
        if not registry_path.exists():
            logger.warning("Scene registry not found: %s", registry_path)
            return

        with open(registry_path, "rb") as f:
            raw = tomllib.load(f)

        index = SceneRegistryIndex(**raw)

        for scene_id, item in index.scenes.items():
            if not item.enabled:
                continue
            scene_path = self._agents_dir / "scenes" / item.path
            if not scene_path.exists():
                logger.warning("Scene file not found: %s", scene_path)
                continue
            with open(scene_path, "rb") as f:
                scene_raw = tomllib.load(f)
            scene = SceneDefinition(**scene_raw)
            if scene.scene_id != scene_id:
                logger.warning(
                    "Scene ID mismatch: registry=%s, file=%s",
                    scene_id,
                    scene.scene_id,
                )
            self._scenes[scene_id] = scene
            logger.info("Loaded scene: %s (%s)", scene_id, scene.display_name)

    def get(self, scene_id: str) -> SceneDefinition:
        if scene_id not in self._scenes:
            raise KeyError(f"Scene not found: {scene_id}")
        return self._scenes[scene_id]

    def get_by_agent_type(self, agent_type: str) -> SceneDefinition:
        for scene in self._scenes.values():
            if scene.agent_type == agent_type:
                return scene
        raise KeyError(f"No scene found for agent_type: {agent_type}")

    def list_scenes(self) -> List[SceneSummary]:
        return [
            SceneSummary(
                scene_id=s.scene_id,
                display_name=s.display_name,
                description=s.description,
                category=s.category,
                icon=s.icon,
                tags=s.tags,
            )
            for s in self._scenes.values()
        ]

    def list_categories(self) -> List[str]:
        seen = []
        for s in self._scenes.values():
            if s.category not in seen:
                seen.append(s.category)
        return seen

    def resolve_config_path(self, scene: SceneDefinition) -> Path:
        return self._agents_dir / scene.config_path

    def resolve_prompt_path(self, scene: SceneDefinition) -> Path:
        return self._agents_dir / scene.prompt_path

    def resolve_subagent_config_path(self, scene: SceneDefinition) -> Optional[Path]:
        if not scene.subagent_config_path:
            return None
        return self._agents_dir / scene.subagent_config_path


_scene_registry: Optional[SceneRegistry] = None


def get_scene_registry() -> SceneRegistry:
    global _scene_registry
    if _scene_registry is None:
        _scene_registry = SceneRegistry()
    return _scene_registry
