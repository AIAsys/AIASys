#!/usr/bin/env python3
"""AIASys Skill 开发工作台主控脚本。

统一管理 skill 的版本、测试、对比和优化。

用法:
    python3 scripts/skill_dev.py init --name my-skill --workspace /workspace
    python3 scripts/skill_dev.py version save --label v1
    python3 scripts/skill_dev.py version list
    python3 scripts/skill_dev.py version checkout v1
    python3 scripts/skill_dev.py test trigger --evals evals/trigger-eval.json
    python3 scripts/skill_dev.py test task --evals evals/task-eval.json
    python3 scripts/skill_dev.py compare v1 v2 --evals evals/task-eval.json
    python3 scripts/skill_dev.py improve --evals evals/trigger-eval.json --max-iterations 5
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.utils import parse_skill_md


def get_dev_root(workspace: Path, skill_name: str) -> Path:
    """获取 skill 开发工作区根目录。"""
    return workspace / "skill-dev" / skill_name


def init_skill_dev(skill_name: str, workspace: Path) -> Path:
    """初始化 skill 开发环境。"""
    dev_root = get_dev_root(workspace, skill_name)
    dirs = [
        dev_root / "versions",
        dev_root / "evals",
        dev_root / "iterations",
        dev_root / "benchmarks",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    state = {
        "skill_name": skill_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "current_version": None,
        "best_version": None,
        "iterations": 0,
    }
    (dev_root / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 创建示例 eval 文件
    trigger_eval_example = [
        {"query": f"使用 {skill_name} 做某事", "should_trigger": True},
        {"query": "写一个 hello world 程序", "should_trigger": False},
    ]
    (dev_root / "evals" / "trigger-eval.json").write_text(
        json.dumps(trigger_eval_example, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    task_eval_example = {
        "skill_name": skill_name,
        "evals": [
            {
                "id": 1,
                "prompt": "User's example prompt",
                "expected_output": "Description of expected result",
                "files": [],
                "assertions": [],
            }
        ],
    }
    (dev_root / "evals" / "task-eval.json").write_text(
        json.dumps(task_eval_example, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return dev_root


def load_state(dev_root: Path) -> dict:
    state_path = dev_root / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(dev_root: Path, state: dict) -> None:
    (dev_root / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def version_save(dev_root: Path, skill_path: Path, label: str | None = None) -> str:
    """保存当前 skill 版本。"""
    versions_dir = dev_root / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # 自动分配版本号
    existing = sorted([d.name for d in versions_dir.iterdir() if d.is_dir()])
    if label:
        version_dir = versions_dir / label
        if version_dir.exists():
            raise FileExistsError(f"版本 {label} 已存在")
    else:
        next_num = len(existing)
        label = f"v{next_num}"
        version_dir = versions_dir / label

    # 复制 skill 目录内容
    if version_dir.exists():
        shutil.rmtree(version_dir)
    shutil.copytree(
        skill_path,
        version_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules"),
    )

    state = load_state(dev_root)
    state["current_version"] = label
    save_state(dev_root, state)

    return label


def version_list(dev_root: Path) -> list[str]:
    versions_dir = dev_root / "versions"
    if not versions_dir.exists():
        return []
    return sorted([d.name for d in versions_dir.iterdir() if d.is_dir()])


def version_checkout(dev_root: Path, skill_path: Path, label: str) -> None:
    """检出指定版本到 skill 路径。"""
    version_dir = dev_root / "versions" / label
    if not version_dir.exists():
        raise FileNotFoundError(f"版本 {label} 不存在")

    if skill_path.exists():
        shutil.rmtree(skill_path)
    shutil.copytree(version_dir, skill_path)

    state = load_state(dev_root)
    state["current_version"] = label
    save_state(dev_root, state)


def run_trigger_test(skill_path: Path, eval_path: Path, args: list[str]) -> dict:
    """调用 trigger_test.py 运行触发测试。"""
    script_dir = Path(__file__).parent
    cmd = [
        sys.executable,
        "-m",
        "scripts.trigger_test",
        "--eval-set",
        str(eval_path),
        "--skill-path",
        str(skill_path),
    ] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=script_dir.parent)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"trigger_test.py 失败: {result.returncode}")
    return json.loads(result.stdout)


def run_improve(
    skill_path: Path, eval_results_path: Path, history_path: Path | None, mock: bool = False
) -> dict:
    """调用 improve_desc.py 改进 description。"""
    script_dir = Path(__file__).parent
    cmd = [
        sys.executable,
        "-m",
        "scripts.improve_desc",
        "--eval-results",
        str(eval_results_path),
        "--skill-path",
        str(skill_path),
    ]
    if history_path:
        cmd += ["--history", str(history_path)]
    if mock:
        cmd.append("--mock")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=script_dir.parent)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"improve_desc.py 失败: {result.returncode}")
    return json.loads(result.stdout)


def cmd_init(args: argparse.Namespace) -> None:
    dev_root = init_skill_dev(args.name, Path(args.workspace))
    print(f"Initialized skill dev workspace: {dev_root}")
    print(f"  - versions/   : 保存各版本 SKILL.md")
    print(f"  - evals/      : 测试用例 (已生成示例)")
    print(f"  - iterations/ : 测试运行输出")
    print(f"  - benchmarks/ : 聚合报告")
    print(f"\nNext steps:")
    print(f"  1. Write your SKILL.md in the skill directory")
    print(f"  2. Edit {dev_root}/evals/trigger-eval.json with realistic test queries")
    print(
        f"  3. Run: python3 scripts/skill_dev.py test trigger --skill-path <path> --workspace {args.workspace}"
    )


def cmd_version(args: argparse.Namespace) -> None:
    dev_root = get_dev_root(Path(args.workspace), args.name)
    if not dev_root.exists():
        print(f"Error: Skill dev workspace not found. Run init first.", file=sys.stderr)
        sys.exit(1)

    if args.version_action == "save":
        skill_path = Path(args.skill_path) if args.skill_path else dev_root / "versions" / "draft"
        label = version_save(dev_root, skill_path, args.label)
        print(f"Saved version: {label}")
    elif args.version_action == "list":
        versions = version_list(dev_root)
        state = load_state(dev_root)
        current = state.get("current_version")
        best = state.get("best_version")
        for v in versions:
            markers = []
            if v == current:
                markers.append("current")
            if v == best:
                markers.append("best")
            marker = f" ({', '.join(markers)})" if markers else ""
            print(f"  {v}{marker}")
    elif args.version_action == "checkout":
        if not args.label:
            print("Error: --label required for checkout", file=sys.stderr)
            sys.exit(1)
        skill_path = Path(args.skill_path) if args.skill_path else dev_root / "versions" / "draft"
        version_checkout(dev_root, skill_path, args.label)
        print(f"Checked out version: {args.label}")


def cmd_test(args: argparse.Namespace) -> None:
    dev_root = get_dev_root(Path(args.workspace), args.name)
    skill_path = Path(args.skill_path)

    if args.test_action == "trigger":
        eval_path = Path(args.evals) if args.evals else dev_root / "evals" / "trigger-eval.json"
        extra = []
        if args.verbose:
            extra.append("--verbose")
        if args.mock:
            extra += ["--mode", "mock"]
        if args.runs_per_query:
            extra += ["--runs-per-query", str(args.runs_per_query)]
        result = run_trigger_test(skill_path, eval_path, extra)

        # 保存结果
        iterations_dir = dev_root / "iterations"
        iterations_dir.mkdir(parents=True, exist_ok=True)
        result_file = (
            iterations_dir
            / f"trigger-test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
        )
        result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults saved to: {result_file}")
        print(f"Passed: {result['summary']['passed']}/{result['summary']['total']}")
    elif args.test_action == "task":
        print("Task testing not yet implemented. Use AIASys backend API manually.")


def cmd_improve(args: argparse.Namespace) -> None:
    dev_root = get_dev_root(Path(args.workspace), args.name)
    skill_path = Path(args.skill_path)
    eval_path = Path(args.evals) if args.evals else dev_root / "evals" / "trigger-eval.json"

    # 保存当前版本作为 baseline（如果尚未保存）
    if "baseline" not in version_list(dev_root):
        version_save(dev_root, skill_path, "baseline")

    history = []
    history_file = dev_root / "improve_history.json"
    if history_file.exists():
        history = json.loads(history_file.read_text(encoding="utf-8"))

    for iteration in range(1, args.max_iterations + 1):
        print(f"\n{'=' * 60}")
        print(f"Iteration {iteration}/{args.max_iterations}")
        print(f"{'=' * 60}")

        # 1. 运行触发测试
        print("Running trigger test...")
        result = run_trigger_test(skill_path, eval_path, ["--verbose"])
        passed = result["summary"]["passed"]
        total = result["summary"]["total"]
        print(f"Score: {passed}/{total}")

        if passed == total:
            print("All queries passed!")
            break

        # 保存 eval 结果到临时文件
        eval_results_file = dev_root / f"eval_results_iter_{iteration}.json"
        eval_results_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        # 2. 改进 description
        print("Improving description...")
        improve_result = run_improve(
            skill_path, eval_results_file, history_file if history else None, args.mock
        )
        new_description = improve_result["description"]
        print(f"New description: {new_description}")

        # 3. 更新 SKILL.md
        skill_md = skill_path / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        # 替换 frontmatter 中的 description
        import re

        new_content = re.sub(
            r"(description:\s*)(.*?)(?=\n\w+:|\n---|\Z)",
            lambda m: f"description: {new_description}",
            content,
            count=1,
            flags=re.DOTALL,
        )
        skill_md.write_text(new_content, encoding="utf-8")

        # 4. 保存改进历史
        history = improve_result.get("history", [])
        history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False))

        # 5. 保存版本
        version_save(dev_root, skill_path, f"v{iteration}")

    # 找出最佳版本
    best = max(history, key=lambda h: h.get("passed", 0)) if history else None
    if best:
        state = load_state(dev_root)
        state["best_version"] = f"v{history.index(best) + 1}"
        save_state(dev_root, state)
        print(f"\nBest version: {state['best_version']} (score: {best['passed']}/{best['total']})")


def main():
    parser = argparse.ArgumentParser(description="AIASys Skill Development Workbench")
    parser.add_argument("--workspace", default="/workspace", help="工作区根目录 (默认 /workspace)")
    subparsers = parser.add_subparsers(dest="command")

    # init
    p_init = subparsers.add_parser("init", help="初始化 skill 开发工作区")
    p_init.add_argument("--name", required=True, help="Skill 名称")

    # version
    p_version = subparsers.add_parser("version", help="版本管理")
    p_version.add_argument("version_action", choices=["save", "list", "checkout"])
    p_version.add_argument("--name", required=True, help="Skill 名称")
    p_version.add_argument("--skill-path", default=None, help="Skill 目录路径")
    p_version.add_argument("--label", default=None, help="版本标签 (save/checkout)")

    # test
    p_test = subparsers.add_parser("test", help="运行测试")
    p_test.add_argument("test_action", choices=["trigger", "task"])
    p_test.add_argument("--name", required=True, help="Skill 名称")
    p_test.add_argument("--skill-path", required=True, help="Skill 目录路径")
    p_test.add_argument("--evals", default=None, help="Eval JSON 路径")
    p_test.add_argument("--runs-per-query", type=int, default=None)
    p_test.add_argument("--verbose", action="store_true")
    p_test.add_argument("--mock", action="store_true", help="使用 mock LLM (无需 API key)")

    # improve
    p_improve = subparsers.add_parser("improve", help="自动优化 description")
    p_improve.add_argument("--name", required=True, help="Skill 名称")
    p_improve.add_argument("--skill-path", required=True, help="Skill 目录路径")
    p_improve.add_argument("--evals", default=None, help="Trigger eval JSON 路径")
    p_improve.add_argument("--max-iterations", type=int, default=5)
    p_improve.add_argument("--mock", action="store_true", help="使用 mock LLM (无需 API key)")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "version":
        cmd_version(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "improve":
        cmd_improve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
