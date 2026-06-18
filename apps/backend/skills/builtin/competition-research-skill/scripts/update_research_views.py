#!/usr/bin/env python3
"""生成竞赛研究视图。

`current.html` 是自动研究看板，适合每轮 record 后刷新。
环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RESEARCH_DASHBOARD_PATH = "research_views/current.html"


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
    except ValueError as exc:
        raise PermissionError(f"路径超出工作区: {raw}") from exc
    return host


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return html.escape(text, quote=True)


def format_score(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def format_version(value: Any) -> str:
    return str(value or "N/A")


def generated_at_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def latest_experiment(data: dict[str, Any]) -> dict[str, Any]:
    experiments = data.get("experiments")
    if isinstance(experiments, list) and experiments:
        for item in reversed(experiments):
            if isinstance(item, dict):
                return item
    return {}


def experiment_by_version(data: dict[str, Any], version: str | None) -> dict[str, Any]:
    if not version:
        return {}
    for item in data.get("experiments", []):
        if isinstance(item, dict) and item.get("version") == version:
            return item
    return {}


def first_priority(data: dict[str, Any]) -> dict[str, Any]:
    queue = data.get("priority_queue")
    if isinstance(queue, list) and queue:
        first = queue[0]
        if isinstance(first, dict):
            return first
    return {}


def get_graph_config(data: dict[str, Any]) -> tuple[str, str]:
    graph_id = str(data.get("knowledge_graph_id") or "").strip()
    graph_path = str(data.get("knowledge_graph_db_path") or "").strip()
    graph_file = str(data.get("knowledge_graph_file") or "").strip()
    if not graph_id and graph_file:
        graph_id = Path(graph_file).stem.removesuffix(".graph")
    if not graph_path:
        graph_path = f"/global/resources/graphs/{graph_id}.db" if graph_id else "<未登记>"
    return graph_id or "<未登记>", graph_path


def trusted_best(data: dict[str, Any]) -> tuple[str, Any]:
    return (
        str(data.get("trusted_best_version") or data.get("best_version") or ""),
        data.get("trusted_best_score")
        if data.get("trusted_best_score") is not None
        else data.get("best_score"),
    )


def decision_label(decision: Any) -> str:
    mapping = {
        "keep": "保留",
        "discard": "废弃",
        "crash": "崩溃",
    }
    return mapping.get(str(decision or ""), str(decision or "N/A"))


def html_table_rows(items: list[dict[str, Any]], columns: list[tuple[str, str]], empty: str) -> str:
    if not items:
        return f'<tr><td colspan="{len(columns)}" class="muted">{esc(empty)}</td></tr>'
    rows: list[str] = []
    for item in items:
        cells = []
        for key, _label in columns:
            cells.append(f"<td>{esc(item.get(key, ''))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join(rows)


def build_research_dashboard_html(data: dict[str, Any], dashboard_path: str) -> str:
    competition = data.get("competition", "Unknown Competition")
    metric = data.get("metric", "Unknown Metric")
    direction = data.get("direction", "maximize")
    trusted_version, trusted_score = trusted_best(data)
    highest_version = str(data.get("highest_observed_version") or "")
    highest_score = data.get("highest_observed_score")
    latest = latest_experiment(data)
    latest_version = str(data.get("latest_version") or latest.get("version") or "")
    latest_score = latest.get("score")
    latest_decision = latest.get("decision")
    latest_findings = latest.get("findings") or ""
    priority = first_priority(data)
    next_candidate = str(
        data.get("next_candidate_version")
        or priority.get("candidate_version")
        or priority.get("slug")
        or ""
    )
    next_direction = priority.get("direction") or "暂无下一步候选"
    next_rationale = (
        priority.get("rationale") or "优先队列为空，下一轮先根据当前阶段、反模式和图谱线索补候选。"
    )
    auto_task_status = data.get("auto_task_status") or "unknown"
    runner_status = data.get("runner_status") or "unknown"
    graph_id, graph_path = get_graph_config(data)
    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    runtime = runner.get("expected_runtime_minutes")
    runtime_text = f"{runtime} 分钟" if runtime not in (None, "") else "未登记"
    auto_task_ids = data.get("auto_task_ids") if isinstance(data.get("auto_task_ids"), list) else []
    recent = [item for item in data.get("experiments", [])[-8:] if isinstance(item, dict)]
    recent_rows = [
        {
            "version": item.get("version", ""),
            "phase": item.get("phase", ""),
            "score": format_score(item.get("score")),
            "decision": decision_label(item.get("decision")),
            "finding": item.get("findings", ""),
        }
        for item in recent
    ]
    anti_rows = []
    for item in data.get("anti_patterns", [])[:8]:
        if isinstance(item, dict):
            anti_rows.append(
                {
                    "pattern": item.get("pattern", ""),
                    "source": item.get("source_version", ""),
                    "consequence": item.get("consequence", ""),
                }
            )
        else:
            anti_rows.append({"pattern": str(item), "source": "", "consequence": ""})
    priority_rows = []
    for item in data.get("priority_queue", [])[:8]:
        if isinstance(item, dict):
            priority_rows.append(
                {
                    "priority": item.get("priority", ""),
                    "candidate": item.get("candidate_version") or item.get("slug") or "",
                    "direction": item.get("direction", ""),
                    "rationale": item.get("rationale", ""),
                }
            )
    highest_exp = experiment_by_version(data, highest_version)
    highest_reason = (
        highest_exp.get("findings")
        or highest_exp.get("trust_status")
        or "只代表历史观测分数更高，是否接管主线仍看 holdout、泄漏风险和复现证据。"
    )
    generated = generated_at_text()
    direction_label = "最大化" if direction == "maximize" else "最小化"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(competition)} 自动研究看板</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #182230;
      --muted: #667085;
      --line: #d0d5dd;
      --blue: #175cd3;
      --green: #067647;
      --amber: #b54708;
      --red: #b42318;
      --violet: #6941c6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 22px; }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; line-height: 1.2; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 14px; letter-spacing: 0; }}
    p {{ margin: 0; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
    .muted {{ color: var(--muted); }}
    .status-strip {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
    .pill {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      white-space: nowrap;
    }}
    .pill.ok {{ border-color: #abefc6; color: var(--green); background: #ecfdf3; }}
    .pill.warn {{ border-color: #fedf89; color: var(--amber); background: #fffaeb; }}
    .grid {{ display: grid; gap: 14px; margin-top: 16px; }}
    .cards {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .two {{ grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }}
    .metric-label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
    .metric-value {{ font-size: 18px; font-weight: 650; overflow-wrap: anywhere; }}
    .metric-sub {{ color: var(--muted); font-size: 12px; margin-top: 4px; overflow-wrap: anywhere; }}
    .decision {{
      border-left: 4px solid var(--blue);
      padding-left: 12px;
    }}
    .risk {{ border-left: 4px solid var(--amber); padding-left: 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-top: 1px solid var(--line); padding: 8px 6px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 12px; }}
    td {{ font-size: 13px; overflow-wrap: anywhere; }}
    .evidence {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }}
    .evidence div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fcfcfd;
      min-width: 0;
    }}
    .evidence strong {{ display: block; margin-bottom: 4px; }}
    @media (max-width: 900px) {{
      main {{ padding: 14px; }}
      header {{ display: block; }}
      .status-strip {{ justify-content: flex-start; margin-top: 12px; }}
      .cards, .two, .evidence {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header id="status">
      <div>
        <h1>{esc(competition)}</h1>
        <p class="muted">目标：{esc(direction_label)} <code>{esc(metric)}</code> · 生成时间：{esc(generated)}</p>
      </div>
      <div class="status-strip" aria-label="状态">
        <span class="pill warn">AutoTask: {esc(auto_task_status)}</span>
        <span class="pill ok">Runner: {esc(runner_status)}</span>
        <span class="pill">阶段: {esc(data.get("current_phase", "N/A"))}</span>
      </div>
    </header>

    <section class="grid cards" aria-label="关键指标">
      <div class="panel">
        <div class="metric-label">可信最优</div>
        <div class="metric-value">{esc(format_version(trusted_version))}</div>
        <div class="metric-sub">{esc(format_score(trusted_score))}</div>
      </div>
      <div class="panel">
        <div class="metric-label">历史最高观测</div>
        <div class="metric-value">{esc(format_version(highest_version))}</div>
        <div class="metric-sub">{esc(format_score(highest_score))}</div>
      </div>
      <div class="panel">
        <div class="metric-label">最新实验</div>
        <div class="metric-value">{esc(format_version(latest_version))}</div>
        <div class="metric-sub">{esc(format_score(latest_score))} · {esc(decision_label(latest_decision))}</div>
      </div>
      <div class="panel">
        <div class="metric-label">下一候选</div>
        <div class="metric-value">{esc(format_version(next_candidate))}</div>
        <div class="metric-sub">单轮只启动一个版本</div>
      </div>
    </section>

    <section class="grid two" id="decision">
      <div class="panel decision">
        <h2>下一步判断</h2>
        <h3>{esc(format_version(next_candidate))}</h3>
        <p>{esc(next_direction)}</p>
        <p class="muted" style="margin-top:8px">{esc(next_rationale)}</p>
      </div>
      <div class="panel risk">
        <h2>为什么历史最高没有接管主线</h2>
        <p><code>{esc(format_version(highest_version))}</code> 的观测分数是 <code>{esc(format_score(highest_score))}</code>。</p>
        <p class="muted" style="margin-top:8px">{esc(highest_reason)}</p>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>优先队列</h2>
        <table>
          <thead><tr><th>优先级</th><th>候选版本</th><th>方向</th><th>理由</th></tr></thead>
          <tbody>
            {html_table_rows(priority_rows, [("priority", "优先级"), ("candidate", "候选版本"), ("direction", "方向"), ("rationale", "理由")], "暂无优先队列")}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>反模式</h2>
        <table>
          <thead><tr><th>不要重试</th><th>来源</th><th>后果</th></tr></thead>
          <tbody>
            {html_table_rows(anti_rows, [("pattern", "不要重试"), ("source", "来源"), ("consequence", "后果")], "暂无反模式")}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel grid" style="display:block">
      <h2>最近实验</h2>
      <table>
        <thead><tr><th>版本</th><th>阶段</th><th>分数</th><th>决策</th><th>发现</th></tr></thead>
        <tbody>
          {html_table_rows(recent_rows, [("version", "版本"), ("phase", "阶段"), ("score", "分数"), ("decision", "决策"), ("finding", "发现")], "暂无实验记录")}
        </tbody>
      </table>
      <p class="muted" style="margin-top:10px">最新发现：{esc(latest_findings or "暂无")}</p>
    </section>

    <section class="panel" id="evidence" style="margin-top:16px">
      <h2>证据入口</h2>
      <div class="evidence">
        <div><strong>实验索引</strong><code>experiments/index.json</code></div>
        <div><strong>Agent 约束</strong><code>AGENTS.md</code></div>
        <div><strong>论文注册表</strong><code>references/index.json</code></div>
        <div><strong>知识图谱</strong><code>{esc(graph_path)}</code></div>
      </div>
      <p class="muted" style="margin-top:12px">runner: <code>{esc(runner.get("type", "N/A"))}</code> · <code>{esc(runner.get("command", "N/A"))}</code> · 单轮预计 {esc(runtime_text)} · AutoTask IDs: {esc(", ".join(map(str, auto_task_ids)) or "N/A")}</p>
      <p class="muted" style="margin-top:6px">本看板路径：<code>{esc(dashboard_path)}</code></p>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="生成竞赛研究 HTML 看板")
    parser.add_argument("--experiments", required=True, help="experiments/index.json 路径")
    parser.add_argument("--output-dir", required=True, help="research_views 输出目录")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        experiments_path = resolve_path(args.experiments, workspace_root)
        output_dir = resolve_path(args.output_dir, workspace_root)
        data = load_json(experiments_path)

        dashboard_rel = str(data.get("research_dashboard_path") or DEFAULT_RESEARCH_DASHBOARD_PATH)
        dashboard_path = output_dir / Path(dashboard_rel).name
        dashboard_rel_for_view = str(dashboard_path.relative_to(experiments_path.parent.parent))

        html_content = build_research_dashboard_html(
            data,
            dashboard_rel_for_view,
        )
        write_text(dashboard_path, html_content)

        print(
            json.dumps(
                {
                    "status": "ok",
                    "dashboard": str(dashboard_path),
                    "dashboard_written": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
