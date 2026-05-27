from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "builtin"
    / "competition-research-skill"
    / "scripts"
)


def run_update_research_views(tmp_path: Path, *args: str) -> dict[str, object]:
    env = {**os.environ, "AIASYS_WORKSPACE_ROOT": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "update_research_views.py"),
            "--experiments",
            "experiments/index.json",
            "--output-dir",
            "research_views",
            *args,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def run_init(tmp_path: Path, *args: str) -> dict[str, object]:
    env = {**os.environ, "AIASYS_WORKSPACE_ROOT": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "init.py"),
            *args,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def run_experiment(tmp_path: Path, *args: str) -> dict[str, object]:
    env = {**os.environ, "AIASYS_WORKSPACE_ROOT": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "experiment.py"),
            "--experiments",
            "experiments/index.json",
            "--workspace",
            str(tmp_path),
            *args,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def write_experiments(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    (experiments_dir / "index.json").write_text(
        json.dumps(
            {
                "competition": "测试竞赛",
                "metric": "profit",
                "direction": "maximize",
                "best_score": 2.0,
                "best_version": "lgb_b001_gain",
                "trusted_best_score": 2.0,
                "trusted_best_version": "lgb_b001_gain",
                "highest_observed_score": 3.0,
                "highest_observed_version": "lgb_b002_unstable",
                "current_phase": "model",
                "knowledge_graph_id": "test-competition",
                "knowledge_graph_db_path": "/global/resources/graphs/test-competition.db",
                "research_dashboard_path": "research_views/current.html",
                "research_canvas_path": "research_views/current.canvas",
                "experiments": [
                    {
                        "version": "lgb_b000_base",
                        "phase": "feature",
                        "score": 1.0,
                        "decision": "keep",
                        "findings": "建立起点",
                    },
                    {
                        "version": "lgb_b001_gain",
                        "phase": "model",
                        "score": 2.0,
                        "decision": "keep",
                        "findings": "可信提升",
                    },
                    {
                        "version": "lgb_b002_unstable",
                        "phase": "model",
                        "score": 3.0,
                        "decision": "keep",
                        "role": "historical_high_observed",
                        "trust_status": "holdout_unstable",
                        "findings": "分数高但不稳",
                    },
                ],
                "anti_patterns": [
                    {
                        "pattern": "继续堆复杂后处理",
                        "source_version": "lgb_b003_complex",
                        "consequence": "持平但更复杂",
                    }
                ],
                "priority_queue": [
                    {
                        "priority": 1,
                        "direction": "复核不稳高分",
                        "candidate_version": "lgb_b004_recheck",
                        "phase": "model",
                        "rationale": "只做严格复核",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_init_creates_research_dashboard(tmp_path: Path) -> None:
    result = run_init(
        tmp_path,
        "--name",
        "test-competition",
        "--metric",
        "profit",
        "--direction",
        "maximize",
        "--output_dir",
        ".",
    )

    assert "test-competition/research_views/current.html" in result["created_files"]
    html_path = tmp_path / "test-competition" / "research_views" / "current.html"
    html_content = html_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in html_content


def test_update_research_views_does_not_rewrite_canvas(tmp_path: Path) -> None:
    write_experiments(tmp_path)
    output_dir = tmp_path / "research_views"
    output_dir.mkdir(parents=True)
    legacy_canvas = {
        "nodes": [],
        "edges": [],
        "custom": {
            "aiasys": {
                "view_type": "competition_research_semantic_graph",
                "relation_fingerprint": "old",
            }
        },
    }
    (output_dir / "current.canvas").write_text(
        json.dumps(legacy_canvas, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_update_research_views(tmp_path)

    assert result["dashboard_written"] is True
    assert "canvas_written" not in result
    canvas = json.loads((output_dir / "current.canvas").read_text(encoding="utf-8"))
    assert canvas == legacy_canvas


def test_preflight_ignores_non_version_output_dirs(tmp_path: Path) -> None:
    write_experiments(tmp_path)
    (tmp_path / "outputs" / "observations").mkdir(parents=True)
    (tmp_path / "outputs" / "observations" / "2026-05-13-auto-research.md").write_text(
        "环境观察\n",
        encoding="utf-8",
    )
    (tmp_path / "outputs" / "lgb_b004_recheck").mkdir(parents=True)
    (tmp_path / "outputs" / "lgb_b004_recheck" / "run_summary.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    result = run_experiment(tmp_path, "--mode", "preflight", "--version", "lgb_b005_next")

    assert "observations" not in result["versions_with_outputs"]
    assert "lgb_b004_recheck" in result["versions_with_outputs"]
