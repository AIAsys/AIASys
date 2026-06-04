import json
from pathlib import Path


def test_config_example_defaults_to_local_sandbox_only() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    sandbox = config["sandbox"]
    assert sandbox["default_mode"] == "local"
    assert sandbox["enabled_modes"] == ["local"]
