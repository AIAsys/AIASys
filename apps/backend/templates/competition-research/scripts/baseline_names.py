#!/usr/bin/env python3
"""校验和生成竞赛 baseline 版本名。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

BASELINE_NAME_PATTERN = re.compile(
    r"^(?P<family>[a-z][a-z0-9]*)_b(?P<number>\d{3})_(?P<slug>[a-z0-9]+(?:_[a-z0-9]+)*)$"
)
RESERVED_OUTPUT_DIRS = {
    "logs",
    "observations",
    "outputs",
    "reports",
    "runtime-prep",
    "submissions",
    "figures",
}


def get_workspace_root(raw: str | None = None) -> Path:
    if raw:
        return Path(raw).resolve()
    env_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_baseline_name(name: str) -> dict | None:
    match = BASELINE_NAME_PATTERN.match(name or "")
    if not match:
        return None
    return {
        "family": match.group("family"),
        "number": int(match.group("number")),
        "slug": match.group("slug"),
    }


def is_valid_baseline_name(name: str) -> bool:
    return parse_baseline_name(name) is not None


def slugify_baseline_slug(value: str, fallback: str = "experiment") -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    parts = [part for part in text.split("_") if part]
    text = "_".join(parts[:6]) if parts else fallback
    return text[:48].strip("_") or fallback


def infer_family(data: dict) -> str:
    for key in ("trusted_best_version", "best_version", "highest_observed_version"):
        parsed = parse_baseline_name(str(data.get(key) or ""))
        if parsed:
            return parsed["family"]
    return "model"


def iter_version_tokens(raw: str) -> list[str]:
    tokens = []
    for part in str(raw or "").split(","):
        value = part.strip()
        if value:
            tokens.append(value)
    return tokens


def collect_candidate_names(workspace: Path, data: dict) -> set[str]:
    names: set[str] = set()
    baselines_dir = workspace / "baselines"
    if baselines_dir.exists():
        names.update(child.name for child in baselines_dir.iterdir() if child.is_dir())

    outputs_dir = workspace / "outputs"
    if outputs_dir.exists():
        for child in outputs_dir.iterdir():
            if child.is_dir() and child.name not in RESERVED_OUTPUT_DIRS:
                names.add(child.name)

    logs_dir = workspace / "outputs" / "logs"
    if logs_dir.exists():
        for path in logs_dir.glob("*.log"):
            stem = path.stem
            if stem.endswith(".out") or stem.endswith(".err"):
                stem = stem.rsplit(".", 1)[0]
            names.add(stem)

    for item in data.get("experiments", []):
        version = str(item.get("version") or "").strip()
        if version:
            names.add(version)
    for key in ("best_version", "trusted_best_version", "highest_observed_version"):
        version = str(data.get(key) or "").strip()
        if version:
            names.add(version)
    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    default_version = str(runner.get("default_version") or "").strip()
    if default_version:
        names.add(default_version)
    return names


def suggest_next_version(
    data: dict,
    workspace: Path,
    family: str | None = None,
    slug: str | None = None,
) -> str:
    family = slugify_baseline_slug(family or infer_family(data), fallback="model")
    slug = slugify_baseline_slug(slug or "experiment")
    max_number = -1
    for name in collect_candidate_names(workspace, data):
        parsed = parse_baseline_name(name)
        if parsed and parsed["family"] == family:
            max_number = max(max_number, parsed["number"])
    return f"{family}_b{max_number + 1:03d}_{slug}"


def validate_workspace(workspace: Path, experiments_path: Path) -> dict:
    data = load_json(experiments_path)
    errors: list[dict] = []
    warnings: list[dict] = []

    def check_name(name: str, source: str, severity: str = "error") -> None:
        if not name:
            return
        target = errors if severity == "error" else warnings
        if not is_valid_baseline_name(name):
            target.append(
                {
                    "source": source,
                    "name": name,
                    "message": "baseline 名必须使用 {family}_b{NNN}_{slug}",
                }
            )

    seen_numbers: dict[tuple[str, int], str] = {}
    baselines_dir = workspace / "baselines"
    baseline_dirs: set[str] = set()
    if baselines_dir.exists():
        for child in sorted(baselines_dir.iterdir()):
            if not child.is_dir():
                continue
            baseline_dirs.add(child.name)
            check_name(child.name, f"baselines/{child.name}")
            parsed = parse_baseline_name(child.name)
            if not parsed:
                continue
            key = (parsed["family"], parsed["number"])
            if key in seen_numbers:
                errors.append(
                    {
                        "source": f"baselines/{child.name}",
                        "name": child.name,
                        "message": f"同一 family 内编号重复，已存在 {seen_numbers[key]}",
                    }
                )
            else:
                seen_numbers[key] = child.name

    experiment_versions: set[str] = set()
    for index, item in enumerate(data.get("experiments", [])):
        version = str(item.get("version") or "").strip()
        check_name(version, f"experiments[{index}].version")
        if version in experiment_versions:
            errors.append(
                {
                    "source": f"experiments[{index}].version",
                    "name": version,
                    "message": "experiments 中出现重复 version",
                }
            )
        experiment_versions.add(version)
        if version and baseline_dirs and version not in baseline_dirs:
            warnings.append(
                {
                    "source": f"experiments[{index}].version",
                    "name": version,
                    "message": "experiments 有记录，但 baselines/ 中没有同名代码快照",
                }
            )

    for key in ("best_version", "trusted_best_version", "highest_observed_version"):
        check_name(str(data.get(key) or "").strip(), key)

    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    check_name(str(runner.get("default_version") or "").strip(), "runner.default_version")

    for index, item in enumerate(data.get("anti_patterns", [])):
        if not isinstance(item, dict):
            continue
        for token in iter_version_tokens(item.get("source_version")):
            check_name(token, f"anti_patterns[{index}].source_version")

    outputs_dir = workspace / "outputs"
    if outputs_dir.exists():
        for child in sorted(outputs_dir.iterdir()):
            if not child.is_dir() or child.name in RESERVED_OUTPUT_DIRS:
                continue
            check_name(child.name, f"outputs/{child.name}")

    submissions_dir = workspace / "outputs" / "submissions"
    if submissions_dir.exists():
        for child in sorted(submissions_dir.iterdir()):
            if child.is_dir():
                check_name(child.name, f"outputs/submissions/{child.name}")

    logs_dir = workspace / "outputs" / "logs"
    if logs_dir.exists():
        for path in sorted(logs_dir.glob("*.log")):
            stem = path.stem
            if stem.endswith(".out") or stem.endswith(".err"):
                stem = stem.rsplit(".", 1)[0]
            check_name(stem, f"outputs/logs/{path.name}")

    return {
        "status": "success" if not errors else "error",
        "workspace": str(workspace),
        "pattern": "{family}_b{NNN}_{slug}",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "baseline_dirs": len(baseline_dirs),
            "experiment_versions": len(experiment_versions),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="竞赛 baseline 命名工具")
    parser.add_argument("--mode", choices=["check", "validate", "next"], required=True)
    parser.add_argument(
        "--workspace", help="竞赛工作区根目录，默认当前目录或 AIASYS_WORKSPACE_ROOT"
    )
    parser.add_argument("--experiments", default="experiments/index.json")
    parser.add_argument("--name", help="需要检查的单个 baseline 版本名")
    parser.add_argument("--family", help="模型或方法家族，如 lgb、blend、catboost")
    parser.add_argument("--slug", help="本轮核心变化，如 quantile_trigrid")
    args = parser.parse_args()

    workspace = get_workspace_root(args.workspace)
    experiments_path = Path(args.experiments)
    if not experiments_path.is_absolute():
        experiments_path = workspace / experiments_path
    data = load_json(experiments_path)

    if args.mode == "check":
        if not args.name:
            raise ValueError("--mode check 需要传入 --name")
        parsed = parse_baseline_name(args.name)
        result = {
            "status": "success" if parsed else "error",
            "name": args.name,
            "pattern": "{family}_b{NNN}_{slug}",
            "parsed": parsed,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not parsed:
            sys.exit(1)
        return

    if args.mode == "validate":
        result = validate_workspace(workspace, experiments_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "success":
            sys.exit(1)
        return

    result = {
        "status": "success",
        "next_version": suggest_next_version(
            data,
            workspace,
            family=args.family,
            slug=args.slug,
        ),
        "pattern": "{family}_b{NNN}_{slug}",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
