from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "builtin"
    / "aiasys-canvas-skill"
)
SCRIPTS = SKILL_ROOT / "scripts"


def run_script(tmp_path: Path, script: str, *args: str) -> dict[str, object]:
    env = {**os.environ, "AIASYS_WORKSPACE_ROOT": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=SCRIPTS,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_canvas_skill_modify_preserves_extensions_and_subpath(tmp_path: Path) -> None:
    canvas_path = tmp_path / "board.canvas"
    canvas_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "external-node",
                        "type": "text",
                        "x": 0,
                        "y": 0,
                        "width": 260,
                        "height": 120,
                        "text": "外部节点",
                        "foreignNodeField": {"keep": True},
                    }
                ],
                "edges": [],
                "foreignDocumentField": {"keep": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_script(
        tmp_path,
        "modify.py",
        "--file",
        "/workspace/board.canvas",
        "--action",
        "add_node",
        "--node_type",
        "file",
        "--file_path",
        "notes/report.md",
        "--subpath",
        "#结论",
        "--x",
        "320",
        "--y",
        "0",
    )

    node = result["node"]
    assert isinstance(node, dict)
    assert node["file"] == "notes/report.md"
    assert node["subpath"] == "#结论"

    saved = json.loads(canvas_path.read_text(encoding="utf-8"))
    assert saved["foreignDocumentField"] == {"keep": True}
    assert saved["nodes"][0]["foreignNodeField"] == {"keep": True}
    assert saved["nodes"][1]["subpath"] == "#结论"

    stats = run_script(
        tmp_path,
        "validate.py",
        "--file",
        "/workspace/board.canvas",
    )
    assert stats["status"] == "success"
    assert stats["nodes"] == 2


def test_canvas_skill_intent_appends_semantic_node_and_edge(tmp_path: Path) -> None:
    canvas_path = tmp_path / "intent.canvas"
    first = run_script(
        tmp_path,
        "modify.py",
        "--file",
        "/workspace/intent.canvas",
        "--action",
        "add_node",
        "--text",
        "中心主题",
        "--x",
        "0",
        "--y",
        "0",
    )
    source_id = first["node"]["id"]

    result = run_script(
        tmp_path,
        "modify.py",
        "--file",
        "/workspace/intent.canvas",
        "--action",
        "add_node",
        "--text",
        "关联说明",
        "--x",
        "360",
        "--y",
        "0",
    )
    target_id = result["node"]["id"]

    edge = run_script(
        tmp_path,
        "modify.py",
        "--file",
        "/workspace/intent.canvas",
        "--action",
        "add_edge",
        "--from_node",
        str(source_id),
        "--to_node",
        str(target_id),
        "--label",
        "关联",
    )

    node = result["node"]
    edge_data = edge["edge"]
    assert isinstance(node, dict)
    assert isinstance(edge_data, dict)
    assert edge_data["label"] == "关联"

    saved = json.loads(canvas_path.read_text(encoding="utf-8"))
    assert len(saved["nodes"]) == 2
    assert len(saved["edges"]) == 1
