#!/usr/bin/env python3
"""竞赛实验的规划、执行与记录。

三个模式：
    plan   — 读取实验状态 + 知识图谱，生成带数据支撑的 hypothesis
    run    — 复制 baseline、注入修改指引、运行实验、捕获 score
    record — 记录实验结果，自动更新 best_score / phase，清理废弃资源

用法:
    python3 experiment.py --mode plan --experiments /workspace/experiments/index.json --workspace /workspace
    python3 experiment.py --mode run --experiments /workspace/experiments/index.json --workspace /workspace --version v1 --name "scale_features" --hypothesis "对数值特征做标准化" --timeout 1800
    python3 experiment.py --mode record --experiments /workspace/experiments/index.json --workspace /workspace --version v1 --score 0.123 --decision keep --findings "标准化后提升 2%"

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from baseline_names import (
    is_valid_baseline_name,
    slugify_baseline_slug,
    suggest_next_version,
)

DEFAULT_RESEARCH_DASHBOARD_PATH = "research_views/current.html"
RUNNER_LOCK_RELATIVE_PATH = ".aiasys/workspace/runner.lock"


# ---------------------------------------------------------------------------
# 路径与安全
# ---------------------------------------------------------------------------


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = (
            Path(*p.parts[2:]) if str(p) == "/workspace" or str(p).startswith("/workspace/") else p
        )
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def path_for_display(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 知识图谱读取
# ---------------------------------------------------------------------------


def find_graph_db(
    project_dir: Path,
    experiments_data: dict,
    workspace_root: Path | None = None,
) -> Path | None:
    """根据 experiments/index.json 中的配置找到 graph.db 路径。

    解析优先级与 ingest.py 的 resolve_graph_db_path 保持一致：
    1. knowledge_graph_db_path
    2. knowledge_graph_id
    3. knowledge_graph_file
    4. 兜底扫描项目目录下的 .graph.db
    """
    ws_root = workspace_root or get_workspace_root()

    kg_path = str(experiments_data.get("knowledge_graph_db_path") or "").strip()
    if kg_path:
        if kg_path.startswith("/workspace/"):
            candidate = ws_root / kg_path[len("/workspace/") :]
        elif kg_path.startswith("/global/"):
            candidate = ws_root.parent / "global_workspace" / kg_path[len("/global/") :]
        else:
            candidate = Path(kg_path)
            if not candidate.is_absolute():
                candidate = project_dir / kg_path
        if candidate.exists():
            return candidate

    kg_id = str(experiments_data.get("knowledge_graph_id") or "").strip()
    if kg_id:
        global_candidate = (
            ws_root.parent / "global_workspace" / "resources" / "graphs" / f"{kg_id}.db"
        )
        if global_candidate.exists():
            return global_candidate

    kg_file = str(experiments_data.get("knowledge_graph_file") or "").strip()
    if kg_file:
        candidate = project_dir / kg_file
        if candidate.exists():
            return candidate

    # 兜底：按名称匹配项目目录下的 .graph.db
    for f in project_dir.iterdir():
        if f.suffix == ".db" and f.name.endswith(".graph.db"):
            return f
    return None


def get_methods_from_graph(graph_db_path: Path) -> list[dict]:
    """从知识图谱中获取所有 method 实体。"""
    if not graph_db_path or not graph_db_path.exists():
        return []
    try:
        with sqlite3.connect(str(graph_db_path)) as conn:
            rows = conn.execute(
                "SELECT entity_id, name, description, properties FROM entities WHERE entity_type = ?",
                ("method",),
            ).fetchall()
            methods = []
            for row in rows:
                props = {}
                if row[3]:
                    try:
                        props = json.loads(row[3])
                    except json.JSONDecodeError:
                        pass
                methods.append(
                    {
                        "entity_id": row[0],
                        "name": row[1],
                        "description": row[2] or "",
                        "properties": props,
                    }
                )
            return methods
    except Exception:
        return []


def get_papers_from_graph(graph_db_path: Path) -> list[dict]:
    """从知识图谱中获取所有 paper 实体。"""
    if not graph_db_path or not graph_db_path.exists():
        return []
    try:
        with sqlite3.connect(str(graph_db_path)) as conn:
            rows = conn.execute(
                "SELECT entity_id, name, description, properties FROM entities WHERE entity_type = ?",
                ("paper",),
            ).fetchall()
            papers = []
            for row in rows:
                props = {}
                if row[3]:
                    try:
                        props = json.loads(row[3])
                    except json.JSONDecodeError:
                        pass
                papers.append(
                    {
                        "entity_id": row[0],
                        "title": row[1],
                        "abstract": row[2] or "",
                        "properties": props,
                    }
                )
            return papers
    except Exception:
        return []


# ---------------------------------------------------------------------------
# plan 模式
# ---------------------------------------------------------------------------


def generate_plan(data: dict, methods: list[dict], project_dir: Path | None = None) -> dict:
    """根据当前状态生成实验建议。"""
    current_phase = data.get("current_phase", "literature")
    priority_queue = data.get("priority_queue", [])
    anti_patterns = data.get("anti_patterns", [])
    experiments = data.get("experiments", [])
    competition = data.get("competition", "unknown")
    metric = data.get("metric", "unknown metric")
    direction = data.get("direction", "minimize")
    best_score = data.get("best_score")

    # 从知识图谱的方法中提取灵感
    method_names = [m["name"] for m in methods[:5]]  # 取前 5 个
    method_hint = ""
    if method_names:
        method_hint = f"知识图谱中记录的方法: {', '.join(method_names)}。"

    if priority_queue:
        top = priority_queue[0]
        hypothesis = top.get("direction", "")
        expected_direction = top.get("direction", direction)
        phase = top.get("phase", current_phase)
        rationale = top.get("rationale", "")
        if rationale:
            hypothesis += f"（理由: {rationale}）"
    else:
        phase = current_phase
        expected_direction = direction

        phase_hypotheses = {
            "literature": (f"查阅相关文献，寻找可迁移到 {competition} 的方法。{method_hint}"),
            "feature": (f"基于当前最佳特征集，尝试新的特征工程方向以改善 {metric}。{method_hint}"),
            "model": (f"尝试新的模型架构或超参数组合，目标 {direction} {metric}。{method_hint}"),
            "ensemble": (f"构建模型集成策略，进一步 {direction} {metric}。{method_hint}"),
        }
        hypothesis = phase_hypotheses.get(
            current_phase,
            f"探索新的实验方向以改善 {metric}。{method_hint}",
        )

    # 附加 anti-patterns 提醒
    if anti_patterns:
        ap_texts = []
        for ap in anti_patterns[:5]:
            if isinstance(ap, dict):
                ap_texts.append(f"{ap.get('pattern', str(ap))}")
            else:
                ap_texts.append(str(ap))
        hypothesis += f"\n注意：以下方向已被验证无效，应避免重复 — " + "; ".join(ap_texts)

    # 阶段转换建议
    phase_transition_hint = ""
    recent_experiments = experiments[-3:] if len(experiments) >= 3 else []
    if len(recent_experiments) >= 3:
        recent_discards = sum(1 for e in recent_experiments if e.get("decision") == "discard")
        if recent_discards >= 3:
            next_phases = {
                "literature": "feature",
                "feature": "model",
                "model": "ensemble",
            }
            if current_phase in next_phases:
                phase_transition_hint = (
                    f"连续 3 轮无改善，建议切换到 {next_phases[current_phase]} 阶段。"
                )

    version_slug = slugify_baseline_slug(phase or "experiment", fallback="experiment")
    if priority_queue and isinstance(priority_queue[0], dict):
        version_slug = slugify_baseline_slug(
            str(priority_queue[0].get("slug") or priority_queue[0].get("direction") or phase),
            fallback=version_slug,
        )
    if project_dir is None:
        project_dir = Path.cwd()

    suggested = {
        "version": suggest_next_version(data, project_dir, slug=version_slug),
        "phase": phase,
        "hypothesis": hypothesis,
        "expected_direction": expected_direction,
        "metric": metric,
        "target_improvement": "显著优于当前最佳" if best_score is not None else "建立基准",
        "phase_transition_hint": phase_transition_hint,
        "methods_available": [m["name"] for m in methods[:10]],
    }
    return suggested


def cmd_plan(args):
    workspace_root = get_workspace_root()
    experiments_path = resolve_path(args.experiments, workspace_root)
    project_dir = experiments_path.parent.parent  # experiments/index.json -> 项目根

    if not experiments_path.exists():
        raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

    data = load_json(experiments_path)
    graph_db = find_graph_db(project_dir, data, workspace_root)
    methods = get_methods_from_graph(graph_db) if graph_db else []

    suggested = generate_plan(data, methods, project_dir)

    result = {
        "status": "ok",
        "current_phase": data.get("current_phase", "literature"),
        "anti_patterns_count": len(data.get("anti_patterns", [])),
        "priority_queue_length": len(data.get("priority_queue", [])),
        "suggested_experiment": suggested,
        "knowledge_graph_methods_found": len(methods),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# run 模式
# ---------------------------------------------------------------------------


def find_baseline_files(project_dir: Path, baseline_name: str | None = None) -> list[Path]:
    """查找 baselines/ 下的可执行文件，优先 .py，其次 .ipynb。
    如果指定了 baseline_name，优先匹配该文件。"""
    baselines_dir = project_dir / "baselines"
    if not baselines_dir.exists():
        return []

    if baseline_name:
        # 先尝试精确匹配
        exact = baselines_dir / baseline_name
        if exact.is_file() and exact.suffix in {".py", ".ipynb"}:
            return [exact]
        if exact.is_dir():
            preferred = [
                exact / "run.py",
                exact / "lgb_baseline.py",
                exact / "catboost_baseline.py",
                exact / "catboost_real_baseline.py",
            ]
            for candidate in preferred:
                if candidate.exists():
                    return [candidate]
            nested_py = sorted(exact.glob("*.py"))
            nested_ipynb = sorted(exact.glob("*.ipynb"))
            if nested_py or nested_ipynb:
                return nested_py + nested_ipynb
        # 尝试加后缀匹配
        for ext in (".py", ".ipynb"):
            candidate = baselines_dir / (baseline_name + ext)
            if candidate.exists():
                return [candidate]
        # 尝试递归查找
        for candidate in baselines_dir.rglob(baseline_name):
            if candidate.exists():
                return [candidate]
        for ext in (".py", ".ipynb"):
            for candidate in baselines_dir.rglob(baseline_name + ext):
                if candidate.exists():
                    return [candidate]

    py_files = sorted(baselines_dir.rglob("*.py"))
    ipynb_files = sorted(baselines_dir.rglob("*.ipynb"))
    return py_files + ipynb_files


def _normalize_cell_source(source) -> list[str]:
    """将 notebook cell 的 source 统一为字符串列表。"""
    if isinstance(source, list):
        return source
    if isinstance(source, str):
        return source.splitlines(keepends=True)
    return [str(source)]


def inject_hypothesis_comments(content: str, hypothesis: str, ext: str) -> str:
    """在文件内容中注入 hypothesis 的 TODO 注释。"""
    header = f"""
# {"=" * 60}
# EXPERIMENT HYPOTHESIS
# {"=" * 60}
# {hypothesis}
# TODO: 按上述 hypothesis 修改以下代码
# {"=" * 60}

"""
    if ext == ".py":
        return header + content
    elif ext == ".ipynb":
        # 在第一个 code cell 前插入 markdown cell
        try:
            nb = json.loads(content)
            cells = nb.get("cells", [])
            new_cell = {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# Experiment Hypothesis\n\n{hypothesis}\n\n",
                    "TODO: 按上述 hypothesis 修改以下代码",
                ],
            }
            # 找到第一个 code cell 的位置
            insert_idx = 0
            for i, cell in enumerate(cells):
                if cell.get("cell_type") == "code":
                    insert_idx = i
                    break
            cells.insert(insert_idx, new_cell)
            # 规范化所有 cell 的 source 格式
            for cell in cells:
                if "source" in cell:
                    cell["source"] = _normalize_cell_source(cell["source"])
            nb["cells"] = cells
            return json.dumps(nb, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return content
    return content


def parse_score_from_output(stdout: str, stderr: str) -> float | None:
    """从输出中解析 score。支持多种格式。"""
    combined = stdout + "\n" + stderr
    patterns = [
        r"FINAL_SCORE[:\s=]+([+-]?\d+\.?\d*)",
        r"CV_SCORE[:\s=]+([+-]?\d+\.?\d*)",
        r"SCORE[:\s=]+([+-]?\d+\.?\d*)",
        r"BEST_SCORE[:\s=]+([+-]?\d+\.?\d*)",
        r"METRIC[:\s=]+([+-]?\d+\.?\d*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def run_with_timeout(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    env: dict | None = None,
) -> tuple[int, str, str, float]:
    """运行命令，超时自动 kill。返回 (returncode, stdout, stderr, runtime_seconds)。"""
    start_time = time.time()
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    killed = threading.Event()

    def kill_after_timeout():
        killed.set()
        try:
            process.send_signal(signal.SIGTERM)
            time.sleep(5)
            if process.poll() is None:
                process.kill()
        except ProcessLookupError:
            pass

    timer = threading.Timer(timeout, kill_after_timeout)
    timer.start()

    try:
        stdout, stderr = process.communicate()
    finally:
        timer.cancel()

    runtime = time.time() - start_time
    return process.returncode, stdout, stderr, runtime


def _find_source_file(
    project_dir: Path, from_version: str | None, baseline_name: str | None
) -> tuple[Path, str]:
    """确定实验的起点文件。

    优先级：
    1. --from_version → 在 experiments/ 下找对应版本的 keep 实验文件
    2. --baseline → 在 baselines/ 下找指定文件
    3. 默认 → baselines/ 下第一个 .py/.ipynb

    返回 (source_file, source_type)，source_type 为 'experiment' 或 'baseline'
    """
    experiments_dir = project_dir / "experiments"
    baselines_dir = project_dir / "baselines"

    # 1. 优先从上一轮 keep 的实验复制
    if from_version:
        prefix = from_version + "_"
        found = False
        if experiments_dir.exists():
            candidates = sorted(experiments_dir.iterdir())
            for f in candidates:
                if f.is_file() and f.name.startswith(prefix):
                    return f, "experiment"
        # 明确指定了 from_version 但找不到，报错而不是回退
        raise FileNotFoundError(
            f"找不到版本 {from_version} 的实验文件，无法在此基础上改进。"
            f"请确认该版本已运行且产物在 {experiments_dir}/ 下。"
        )

    # 2. 查找 baseline
    baseline_files = find_baseline_files(project_dir, baseline_name)
    if baseline_files:
        return baseline_files[0], "baseline"

    raise FileNotFoundError(
        "找不到实验起点文件。"
        + (f"--from_version={from_version} 对应的实验文件不存在。" if from_version else "")
        + (f"--baseline={baseline_name} 不存在。" if baseline_name else "")
        + "baselines/ 目录为空。"
    )


def _save_experiment_logs(
    project_dir: Path, version: str, exp_name: str, stdout: str, stderr: str
) -> tuple[Path, Path]:
    """保存实验日志到 outputs/logs/，返回 (stdout_log, stderr_log) 路径。"""
    logs_dir = project_dir / "outputs" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]+", "_", exp_name).strip("_")
    prefix = f"{version}_{safe_name}"
    out_path = logs_dir / f"{prefix}.out.log"
    err_path = logs_dir / f"{prefix}.err.log"
    out_path.write_text(stdout, encoding="utf-8")
    err_path.write_text(stderr, encoding="utf-8")
    return out_path, err_path


def cmd_run(args):
    workspace_root = get_workspace_root()
    experiments_path = resolve_path(args.experiments, workspace_root)
    project_dir = experiments_path.parent.parent

    if not experiments_path.exists():
        raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

    data = load_json(experiments_path)

    # 确定实验起点文件
    source_type = None
    try:
        source_file, source_type = _find_source_file(project_dir, args.from_version, args.baseline)
    except FileNotFoundError as exc:
        hint = "baselines/ 为空。这是 bootstrap 阶段，Agent 需要先写一个可运行的 baseline。"
        if args.baseline:
            hint = f"找不到指定的 baseline: {args.baseline}。"
        if args.from_version:
            hint = f"找不到版本 {args.from_version} 的实验文件，无法在此基础上改进。"
        result = {
            "status": "error",
            "error": str(exc),
            "hint": hint,
            "bootstrap_needed": not args.from_version,
            "bootstrap_guide": (
                "1. 读取 data/raw/README.md 了解数据格式\n"
                "2. 用 WriteFile 写一个最简单的可运行 baseline（如线性回归、随机森林）到 baselines/baseline.py\n"
                "3. baseline 必须输出 FINAL_SCORE: <value>\n"
                "4. 然后重新调用 experiment.py --mode run"
            ),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    source_ext = source_file.suffix

    # 确定实验文件路径
    exp_name = args.name or "experiment"
    safe_name = re.sub(r"[^\w\-]+", "_", exp_name).strip("_")
    if not safe_name:
        safe_name = "experiment"
    version = args.version or suggest_next_version(
        data,
        project_dir,
        slug=slugify_baseline_slug(safe_name),
    )
    if not is_valid_baseline_name(version):
        raise ValueError(
            f"实验版本名不符合规范: {version}。必须使用 {{family}}_b{{NNN}}_{{slug}}，"
            "例如 lgb_b045_pairranker_on_trigrid。"
        )
    exp_file = project_dir / "experiments" / f"{version}_{safe_name}{source_ext}"

    # 复制并注入 hypothesis（仅在文件不存在时）
    exp_file.parent.mkdir(parents=True, exist_ok=True)
    file_existed = exp_file.exists() and exp_file.stat().st_size > 0

    if not file_existed:
        original_content = source_file.read_text(encoding="utf-8")
        modified_content = inject_hypothesis_comments(
            original_content, args.hypothesis or "无明确假设", source_ext
        )
        exp_file.write_text(modified_content, encoding="utf-8")

    # 运行实验
    timeout = args.timeout or 1800
    returncode = -1
    stdout = ""
    stderr = ""
    runtime = 0.0

    if source_ext == ".py":
        cmd = [sys.executable, str(exp_file)]
        returncode, stdout, stderr, runtime = run_with_timeout(
            cmd, cwd=project_dir, timeout=timeout, env=os.environ.copy()
        )
    elif source_ext == ".ipynb":
        # 尝试用 jupyter nbconvert 执行
        try:
            cmd = [
                "jupyter",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                "--inplace",
                str(exp_file),
            ]
            returncode, stdout, stderr, runtime = run_with_timeout(
                cmd, cwd=project_dir, timeout=timeout, env=os.environ.copy()
            )
        except FileNotFoundError:
            stderr = "jupyter 未安装，无法执行 .ipynb。请安装 jupyter 或将 baseline 转为 .py 文件。"
            returncode = 127
            runtime = 0.0

    # 保存日志
    out_log, err_log = _save_experiment_logs(project_dir, version, exp_name, stdout, stderr)

    # 解析 score
    score = parse_score_from_output(stdout, stderr)

    # 判断是否 crash
    status = "completed" if returncode == 0 else "failed"
    crashed = returncode != 0

    # 智能截取 preview：如果有错误信息，优先展示错误部分
    def smart_preview(text: str, max_len: int = 2000) -> str:
        if len(text) <= max_len:
            return text
        error_keywords = ["Traceback", "ERROR", "Exception", "Error:", "Failed"]
        error_pos = -1
        for kw in error_keywords:
            pos = text.rfind(kw)
            if pos != -1:
                error_pos = max(error_pos, pos)
        if error_pos != -1:
            start = max(0, error_pos - 200)
            snippet = text[start:]
            if len(snippet) > max_len:
                return "..." + snippet[-max_len:]
            return snippet
        return text[-max_len:]

    result = {
        "status": "ok",
        "version": version,
        "experiment_file": str(exp_file.relative_to(workspace_root)),
        "file_existed": file_existed,
        "source": {
            "file": str(source_file.relative_to(workspace_root)),
            "type": source_type,  # "experiment" 或 "baseline"
        },
        "hypothesis": args.hypothesis,
        "execution": {
            "returncode": returncode,
            "status": status,
            "crashed": crashed,
            "timeout_triggered": returncode == -signal.SIGTERM if returncode < 0 else False,
            "runtime_seconds": round(runtime, 2),
            "timeout_configured": timeout,
        },
        "score": score,
        "stdout_preview": smart_preview(stdout),
        "stderr_preview": smart_preview(stderr),
        "log_files": {
            "stdout": str(out_log.relative_to(workspace_root)),
            "stderr": str(err_log.relative_to(workspace_root)),
        },
        "next_step": (
            "实验成功完成，请调用 record 模式记录结果"
            if not crashed
            else "实验崩溃，请检查 stderr 或调试后重试"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# preflight 模式
# ---------------------------------------------------------------------------


def _read_runner_lock(project_dir: Path) -> dict:
    lock_path = project_dir / RUNNER_LOCK_RELATIVE_PATH
    result = {
        "path": RUNNER_LOCK_RELATIVE_PATH,
        "exists": lock_path.exists(),
        "active": False,
        "stale": False,
        "pid": None,
        "data": None,
    }
    if not lock_path.exists():
        return result

    raw = lock_path.read_text(encoding="utf-8").strip()
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw}
    pid = data.get("pid")
    try:
        pid = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid = None

    active = False
    if pid is not None:
        try:
            os.kill(pid, 0)
            active = True
        except ProcessLookupError:
            active = False
        except PermissionError:
            active = True

    result.update(
        {
            "active": active,
            "stale": not active,
            "pid": pid,
            "data": data,
        }
    )
    return result


def _all_versions(data: dict) -> set[str]:
    versions = set()
    for item in data.get("experiments", []):
        version = str(item.get("version") or "").strip()
        if version:
            versions.add(version)
    return versions


def _versions_with_run_summaries(project_dir: Path) -> set[str]:
    outputs_dir = project_dir / "outputs"
    if not outputs_dir.exists():
        return set()
    versions = set()
    for summary in outputs_dir.glob("*/run_summary.json"):
        if summary.parent.name != "logs":
            versions.add(summary.parent.name)
    return versions


def _versions_with_outputs(project_dir: Path) -> set[str]:
    outputs_dir = project_dir / "outputs"
    if not outputs_dir.exists():
        return set()
    versions = set()
    for child in outputs_dir.iterdir():
        if child.name in {
            "logs",
            "submissions",
            "observations",
            "reports",
            "runtime-prep",
            "parallel_research",
        }:
            continue
        if child.is_dir() and is_valid_baseline_name(child.name) and any(child.iterdir()):
            versions.add(child.name)
    return versions


def _versions_with_logs(project_dir: Path) -> set[str]:
    logs_dir = project_dir / "outputs" / "logs"
    if not logs_dir.exists():
        return set()
    versions = set()
    for log_file in logs_dir.glob("*.log"):
        name = log_file.name
        if name.endswith(".out.log"):
            versions.add(name[:-8])
        elif name.endswith(".err.log"):
            versions.add(name[:-8])
        else:
            versions.add(log_file.stem)
    return versions


def _existing_version_paths(project_dir: Path, version: str) -> dict:
    candidates = {
        "baseline_dir": project_dir / "baselines" / version,
        "output_dir": project_dir / "outputs" / version,
        "submission_dir": project_dir / "outputs" / "submissions" / version,
        "log_file": project_dir / "outputs" / "logs" / f"{version}.log",
        "stdout_log": project_dir / "outputs" / "logs" / f"{version}.out.log",
        "stderr_log": project_dir / "outputs" / "logs" / f"{version}.err.log",
        "run_summary": project_dir / "outputs" / version / "run_summary.json",
    }
    return {
        key: path_for_display(path, project_dir)
        for key, path in candidates.items()
        if path.exists()
    }


def cmd_preflight(args):
    """启动 runner 前的机器检查。"""
    workspace_root = get_workspace_root()
    experiments_path = resolve_path(args.experiments, workspace_root)
    project_dir = experiments_path.parent.parent

    if not experiments_path.exists():
        raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

    data = load_json(experiments_path)
    recorded_versions = _all_versions(data)
    run_summary_versions = _versions_with_run_summaries(project_dir)
    output_versions = _versions_with_outputs(project_dir)
    log_versions = _versions_with_logs(project_dir)

    unrecorded_outputs = sorted(run_summary_versions - recorded_versions)
    candidate_version = str(args.version or "").strip()
    invalid_candidate_version = bool(
        candidate_version and not is_valid_baseline_name(candidate_version)
    )
    existing_candidate_paths = (
        _existing_version_paths(project_dir, candidate_version) if candidate_version else {}
    )
    active_auto_task_sessions = _active_auto_task_sessions(project_dir)
    runner_lock = _read_runner_lock(project_dir)

    blocking_reasons = []
    if runner_lock["active"]:
        blocking_reasons.append("runner_lock_active")
    if unrecorded_outputs:
        blocking_reasons.append("unrecorded_outputs")
    if candidate_version and existing_candidate_paths:
        blocking_reasons.append("candidate_version_already_has_artifacts")
    if invalid_candidate_version:
        blocking_reasons.append("candidate_version_name_invalid")
    if active_auto_task_sessions:
        blocking_reasons.append("active_auto_task_sessions_present")

    result = {
        "status": "ok",
        "safe_to_start_new_run": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "runner_lock": runner_lock,
        "candidate_version": candidate_version or None,
        "candidate_version_name_valid": not invalid_candidate_version,
        "candidate_existing_paths": existing_candidate_paths,
        "unrecorded_outputs": unrecorded_outputs,
        "versions_with_outputs": sorted(output_versions),
        "versions_with_logs": sorted(log_versions),
        "active_auto_task_sessions": active_auto_task_sessions,
        "next_action": (
            "可以启动一个新 runner"
            if not blocking_reasons
            else "先处理 blocking_reasons，再启动新 runner"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _active_auto_task_sessions(project_dir: Path) -> list[dict]:
    conversations_path = project_dir / ".aiasys" / "workspace" / "conversations.json"
    if not conversations_path.exists():
        return []
    try:
        data = load_json(conversations_path)
    except Exception:
        return []
    active = []
    for item in data.get("conversations", []):
        if item.get("source") != "auto_task":
            continue
        session_id = str(item.get("session_id") or item.get("conversation_id") or "").strip()
        if not session_id:
            continue
        user_root = project_dir.parent
        session_root = user_root / session_id
        metadata = _load_session_metadata(session_root / "metadata.json")
        running_monitors = _running_monitors(session_root)
        if metadata.get("status") in {"completed", "failed", "cancelled"} and not running_monitors:
            continue
        active.append(
            {
                "session_id": session_id,
                "auto_task_id": item.get("auto_task_id"),
                "title": item.get("title"),
                "created_at": item.get("created_at"),
                "status": metadata.get("status"),
                "running_monitors": running_monitors,
            }
        )
    return active


def _load_session_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _running_monitors(session_root: Path) -> list[dict]:
    monitors_dir = session_root / "monitors"
    if not monitors_dir.exists():
        return []
    running = []
    for meta_path in sorted(monitors_dir.glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("status") not in {"completed", "failed", "killed", "cancelled"}:
            running.append(
                {
                    "id": meta.get("id") or meta_path.stem.removesuffix(".meta"),
                    "status": meta.get("status"),
                    "command": meta.get("command"),
                }
            )
    return running


# ---------------------------------------------------------------------------
# record 模式
# ---------------------------------------------------------------------------


def is_score_better(new_score: float, best_score: float | None, direction: str) -> bool:
    """判断新分数是否优于当前最佳。"""
    if best_score is None:
        return True
    if direction == "minimize":
        return new_score < best_score
    return new_score > best_score


def should_transition_phase(experiments: list[dict], current_phase: str) -> str | None:
    """根据最近实验结果判断是否需要切换阶段。"""
    if len(experiments) < 3:
        return None
    recent = experiments[-3:]
    discards = sum(1 for e in recent if e.get("decision") == "discard")
    if discards < 3:
        return None
    transitions = {
        "literature": "feature",
        "feature": "model",
        "model": "ensemble",
    }
    return transitions.get(current_phase)


def cleanup_experiment_artifacts(project_dir: Path, version: str, decision: str) -> list[str]:
    """根据决策清理实验产物。

    清理语义：
    - keep：保留代码、输出、日志和提交文件。
    - discard/crash：保留日志作为证据，删除实验代码、输出产物和提交文件。
    """
    cleaned = []
    if decision not in ("discard", "crash"):
        return cleaned

    # 删除 experiments/ 下匹配版本前缀的代码文件
    exp_dir = project_dir / "experiments"
    if exp_dir.exists():
        prefix = version + "_"
        for f in exp_dir.iterdir():
            if f.name.startswith(prefix):
                try:
                    if f.is_file():
                        f.unlink()
                        cleaned.append(str(f))
                except OSError:
                    pass

    # 删除 outputs/<version>/ 下的产物目录
    output_version_dir = project_dir / "outputs" / version
    if output_version_dir.exists():
        try:
            shutil.rmtree(output_version_dir)
            cleaned.append(str(output_version_dir))
        except OSError:
            pass

    # 删除 outputs/submissions/<version>/ 下的提交文件
    submission_version_dir = project_dir / "outputs" / "submissions" / version
    if submission_version_dir.exists():
        try:
            shutil.rmtree(submission_version_dir)
            cleaned.append(str(submission_version_dir))
        except OSError:
            pass

    return cleaned


def cmd_record(args):
    workspace_root = get_workspace_root()
    experiments_path = resolve_path(args.experiments, workspace_root)
    project_dir = experiments_path.parent.parent

    if not experiments_path.exists():
        raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

    data = load_json(experiments_path)

    version = args.version
    if not is_valid_baseline_name(str(version or "")):
        raise ValueError(
            f"实验版本名不符合规范: {version}。必须使用 {{family}}_b{{NNN}}_{{slug}}。"
        )
    score = args.score
    decision = args.decision
    findings = args.findings or ""
    hypothesis = args.hypothesis or ""
    description = args.description or ""
    status = args.status or ("completed" if decision != "crash" else "failed")
    method_tested = args.method_tested or ""
    pipeline_layer = args.pipeline_layer or ""
    inspired_by = args.inspired_by or []

    now = datetime.now(timezone.utc).isoformat()

    # 构造实验条目
    experiment_entry = {
        "version": version,
        "name": args.name or version,
        "phase": data.get("current_phase", "literature"),
        "status": status,
        "score": score,
        "decision": decision,
        "hypothesis": hypothesis,
        "description": description,
        "started_at": args.started_at or now,
        "completed_at": now,
        "findings": findings,
        "inspired_by": inspired_by if isinstance(inspired_by, list) else [inspired_by],
        "method_tested": method_tested,
        "pipeline_layer": pipeline_layer,
    }

    # 添加到 experiments 数组
    experiments = data.get("experiments", [])
    # 如果已有同版本条目，替换
    existing_idx = None
    for i, e in enumerate(experiments):
        if e.get("version") == version:
            existing_idx = i
            break
    if existing_idx is not None:
        experiments[existing_idx] = experiment_entry
    else:
        experiments.append(experiment_entry)
    data["experiments"] = experiments

    # 更新 best_score 和 trusted_best
    # 默认规则：keep 且优于当前 best 时，同时更新 best 和 trusted_best。
    # 如果后续发现 holdout 不稳定、数据泄漏风险或复现证据不足，
    # Agent 应手动将 trusted_best 回退到更早的稳定版本，并把高分版本写入 highest_observed。
    direction = data.get("direction", "minimize")
    best_score = data.get("best_score")
    trusted_best_score = data.get("trusted_best_score")
    if decision == "keep" and score is not None:
        if is_score_better(score, best_score, direction):
            data["best_score"] = score
            data["best_version"] = version
        # 默认同步更新 trusted_best；如需保留旧 trusted_best，应在 record 前手动设置 trust_status
        if is_score_better(score, trusted_best_score, direction):
            data["trusted_best_score"] = score
            data["trusted_best_version"] = version

    # 更新 anti_patterns
    if decision == "discard" and findings:
        anti_patterns = data.get("anti_patterns", [])
        # 去重：相同的 pattern 不重复添加
        existing_patterns = {
            ap.get("pattern", str(ap)) if isinstance(ap, dict) else str(ap) for ap in anti_patterns
        }
        new_pattern_text = hypothesis or findings
        if new_pattern_text and new_pattern_text not in existing_patterns:
            anti_patterns.append(
                {
                    "pattern": new_pattern_text,
                    "consequence": findings,
                    "source_version": version,
                    "category": pipeline_layer or "strategy",
                }
            )
        data["anti_patterns"] = anti_patterns

    # 阶段转换判断
    new_phase = should_transition_phase(experiments, data.get("current_phase", "literature"))
    old_phase = data.get("current_phase")
    if new_phase:
        data["current_phase"] = new_phase

    # 更新时间戳
    data["last_updated"] = now

    # 保存
    save_json(experiments_path, data)

    # 资源清理
    cleaned_files = cleanup_experiment_artifacts(project_dir, version, decision)

    result = {
        "status": "ok",
        "version": version,
        "decision": decision,
        "score": score,
        "best_score": data.get("best_score"),
        "best_version": data.get("best_version"),
        "current_phase": data.get("current_phase"),
        "phase_changed": new_phase is not None and new_phase != old_phase,
        "old_phase": old_phase if new_phase else None,
        "new_phase": new_phase,
        "anti_patterns_count": len(data.get("anti_patterns", [])),
        "experiments_count": len(experiments),
        "cleaned_files": [str(Path(f).relative_to(workspace_root)) for f in cleaned_files],
        "next_action": (
            "实验已保留，可继续下一轮"
            if decision == "keep"
            else (
                "实验已废弃，产物已清理，建议调整方向"
                if decision == "discard"
                else "实验崩溃，建议调试后重试"
            )
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# status 模式
# ---------------------------------------------------------------------------


def cmd_status(args):
    """快速查看项目当前状态。"""
    workspace_root = get_workspace_root()
    experiments_path = resolve_path(args.experiments, workspace_root)
    project_dir = experiments_path.parent.parent

    if not experiments_path.exists():
        raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

    data = load_json(experiments_path)
    experiments = data.get("experiments", [])

    # 最近实验摘要
    recent_summary = []
    for e in experiments[-5:]:
        recent_summary.append(
            {
                "version": e.get("version"),
                "decision": e.get("decision"),
                "score": e.get("score"),
                "phase": e.get("phase"),
                "name": e.get("name", ""),
            }
        )

    # 统计
    total = len(experiments)
    keep_count = sum(1 for e in experiments if e.get("decision") == "keep")
    discard_count = sum(1 for e in experiments if e.get("decision") == "discard")
    crash_count = sum(1 for e in experiments if e.get("decision") == "crash")

    # 知识图谱统计
    graph_db = find_graph_db(project_dir, data, workspace_root)
    graph_stats = {"entities": 0, "relations": 0, "methods": 0}
    if graph_db and graph_db.exists():
        try:
            with sqlite3.connect(str(graph_db)) as conn:
                row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
                graph_stats["entities"] = row[0] if row else 0
                row = conn.execute("SELECT COUNT(*) FROM relations").fetchone()
                graph_stats["relations"] = row[0] if row else 0
                row = conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE entity_type = ?", ("method",)
                ).fetchone()
                graph_stats["methods"] = row[0] if row else 0
        except Exception:
            pass

    # references 统计
    refs_path = project_dir / "references" / "index.json"
    paper_count = 0
    if refs_path.exists():
        refs_data = load_json(refs_path)
        paper_count = len(refs_data.get("papers", []))

    # 检查 bootstrap 状态
    baselines_dir = project_dir / "baselines"
    baseline_files = find_baseline_files(project_dir) if baselines_dir.exists() else []
    has_baseline = len(baseline_files) > 0

    data_raw_dir = project_dir / "data" / "raw"
    has_data = False
    if data_raw_dir.exists():
        for f in data_raw_dir.iterdir():
            if f.name.lower() not in ("readme.md", "readme.txt", ".gitkeep"):
                has_data = True
                break

    bootstrap_status = "ready"
    bootstrap_actions = []
    if not has_data:
        bootstrap_status = "needs_data"
        bootstrap_actions.append("请提供竞赛数据文件并放入 data/raw/")
    if not has_baseline:
        if bootstrap_status == "ready":
            bootstrap_status = "needs_baseline"
        bootstrap_actions.append("请提供 baseline 代码放入 baselines/，或由 Agent 自行创建")
    if not experiments:
        bootstrap_actions.append("运行首个 baseline 建立 v0 基准")

    result = {
        "status": "ok",
        "competition": data.get("competition", "unknown"),
        "metric": data.get("metric", "unknown"),
        "direction": data.get("direction", "minimize"),
        "current_phase": data.get("current_phase", "literature"),
        "best_score": data.get("best_score"),
        "best_version": data.get("best_version"),
        "last_updated": data.get("last_updated"),
        "research_dashboard_path": data.get(
            "research_dashboard_path", DEFAULT_RESEARCH_DASHBOARD_PATH
        ),
        "research_dashboard_exists": (
            project_dir / str(data.get("research_dashboard_path", DEFAULT_RESEARCH_DASHBOARD_PATH))
        ).exists(),
        "bootstrap": {
            "status": bootstrap_status,
            "has_data": has_data,
            "has_baseline": has_baseline,
            "baseline_files": [str(f.relative_to(workspace_root)) for f in baseline_files],
            "needed_actions": bootstrap_actions,
        },
        "experiments_summary": {
            "total": total,
            "keep": keep_count,
            "discard": discard_count,
            "crash": crash_count,
            "recent": recent_summary,
        },
        "knowledge_graph": graph_stats,
        "papers_ingested": paper_count,
        "anti_patterns_count": len(data.get("anti_patterns", [])),
        "priority_queue_length": len(data.get("priority_queue", [])),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="竞赛实验的规划、执行与记录")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["preflight", "plan", "run", "record", "status"],
        help="运行模式: preflight=启动前检查, plan=生成建议, run=执行实验, record=记录结果, status=查看状态",
    )
    parser.add_argument(
        "--experiments",
        required=True,
        help="experiments/index.json 路径",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="工作区根目录路径（用于解析相对路径）",
    )

    # run / record 共用参数
    parser.add_argument("--version", help="实验版本号，如 v1")
    parser.add_argument("--name", help="实验名称")
    parser.add_argument("--hypothesis", help="实验假设/方向")

    # run 专属参数
    parser.add_argument(
        "--from_version",
        help="从上一轮 keep 的实验文件复制作为起点（如 v3），不指定则从 baselines/ 复制",
    )
    parser.add_argument(
        "--baseline",
        help="指定 baseline 文件名（如 baseline.py），不指定则自动检测第一个",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="实验运行超时时间（秒），默认 1800（30 分钟）",
    )

    # record 专属参数
    parser.add_argument("--score", type=float, help="实验得分")
    parser.add_argument(
        "--decision",
        choices=["keep", "discard", "crash"],
        help="实验决策: keep=保留, discard=废弃, crash=崩溃",
    )
    parser.add_argument("--findings", help="实验发现和结论")
    parser.add_argument("--description", help="实验修改的具体描述")
    parser.add_argument("--status", choices=["completed", "failed"], help="实验执行状态")
    parser.add_argument("--method_tested", help="测试的方法名称")
    parser.add_argument(
        "--pipeline_layer",
        choices=["features", "loss", "model", "post-processing", "strategy"],
        help="实验修改的层级",
    )
    parser.add_argument(
        "--inspired_by",
        nargs="+",
        help="启发本实验的论文 ID 列表",
    )
    parser.add_argument("--started_at", help="实验开始时间（ISO8601）")

    args = parser.parse_args()

    try:
        if args.mode == "preflight":
            cmd_preflight(args)
        elif args.mode == "plan":
            cmd_plan(args)
        elif args.mode == "run":
            cmd_run(args)
        elif args.mode == "record":
            cmd_record(args)
        elif args.mode == "status":
            cmd_status(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
