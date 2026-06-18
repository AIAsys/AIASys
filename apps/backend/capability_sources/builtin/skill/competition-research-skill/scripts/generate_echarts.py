#!/usr/bin/env python3
"""
Generate ECharts JSON configs from experiments/index.json.

Design principles:
- One chart per analytical question. Don't cram multiple stories into one chart.
- Use color consistently: keep=green, discard=gray, crash=red, mainline=blue.
- Mark milestones (trusted best, highest observed) explicitly.
- Put JSON configs in research_views/echarts/; load overview.html in a browser.

Outputs:
  research_views/echarts/01_timeline.echarts.json      — 实验得分演进（按模型家族着色）
  research_views/echarts/02_mainline.echarts.json      — 主线提升阶梯（只保留 keep 且得分递增）
  research_views/echarts/03_family_compare.echarts.json — 模型家族得分对比
  research_views/echarts/04_phase_compare.echarts.json — 阶段/模型族得分箱线图
  research_views/echarts/05_phase_success.echarts.json — 阶段成功率对比
  research_views/echarts/06_anti_patterns.echarts.json — 反模式分类分布
  research_views/echarts/07_anti_sankey.echarts.json   — 反模式来源流向
  research_views/echarts/08_decisions.echarts.json     — 实验决策分布
  research_views/echarts/09_family_success.echarts.json — 模型家族成功率
  research_views/echarts/10_hypothesis_outcome.echarts.json — 关键假设验证结果
  research_views/echarts/overview.html                 — 统一看板（浏览器打开）
"""

import json
import os
from pathlib import Path


def load_experiments():
    workspace = Path(os.environ.get("AIASYS_WORKSPACE_ROOT", os.getcwd()))
    with open(workspace / "experiments" / "index.json") as f:
        data = json.load(f)
    return data, workspace


def _family(version: str) -> str:
    """Extract model family from version name, e.g. lgb_b042 -> lgb"""
    return version.split("_")[0] if "_" in version else "unknown"


def _short_version(version: str) -> str:
    """Shorten version for axis labels."""
    return (
        version.replace("lgb_b", "L")
        .replace("blend_b", "B")
        .replace("xgb_b", "X")
        .replace("catboost_b", "C")
        .replace("transformer_b", "T")
        .replace("lstm_b", "M")
    )


def _fmt_score(v) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f}"


def _phase_color(phase: str) -> str:
    return {
        "model": "#5470c6",
        "feature": "#91cc75",
        "ensemble": "#fac858",
        "literature": "#ee6666",
    }.get(phase, "#999")


def _decision_color(decision: str) -> str:
    return {"keep": "#22c55e", "discard": "#9ca3af", "crash": "#ef4444"}.get(decision, "#d1d5db")


def _y_axis_opts(data, padding_ratio=0.05):
    """根据所有实验分数动态计算 Y 轴 min，避免硬编码。"""
    exps = data.get("experiments", [])
    scores = [e.get("score") for e in exps if e.get("score") is not None]
    if not scores:
        return {}
    s_min = min(scores)
    s_max = max(scores)
    if s_min == s_max:
        margin = abs(s_min) * 0.1 if s_min != 0 else 1.0
        return {"min": round(s_min - margin, 2), "max": round(s_max + margin, 2)}
    span = s_max - s_min
    margin = span * padding_ratio
    margin = max(margin, abs(s_max) * 0.01 if s_max != 0 else 0.01)
    return {"min": round(s_min - margin, 2), "max": round(s_max + margin, 2)}


# ---------------------------------------------------------------------------
# Chart 1: 实验得分时间线
# ---------------------------------------------------------------------------
def gen_timeline(data):
    exps = data.get("experiments", [])
    family_colors = {
        "lgb": "#5470c6",
        "blend": "#fac858",
        "transformer": "#ee6666",
        "catboost": "#91cc75",
        "xgb": "#73c0de",
        "lstm": "#ea7ccc",
    }

    versions = []
    scores = []
    point_colors = []
    family_list = []

    for e in exps:
        v = e.get("version", "")
        s = e.get("score")
        fam = _family(v)
        versions.append(_short_version(v))
        scores.append(round(s, 2) if s is not None else None)
        point_colors.append(family_colors.get(fam, "#999"))
        family_list.append(fam)

    best_v = data.get("trusted_best_version", "")
    highest_v = data.get("highest_observed_version", "")
    best_idx = next((i for i, e in enumerate(exps) if e.get("version") == best_v), -1)
    highest_idx = next((i for i, e in enumerate(exps) if e.get("version") == highest_v), -1)

    mark_points = []
    if best_idx >= 0 and scores[best_idx] is not None:
        mark_points.append(
            {
                "name": "Trusted Best",
                "coord": [best_idx, scores[best_idx]],
                "value": scores[best_idx],
                "itemStyle": {"color": "#22c55e"},
            }
        )
    if highest_idx >= 0 and scores[highest_idx] is not None:
        mark_points.append(
            {
                "name": "Highest Observed",
                "coord": [highest_idx, scores[highest_idx]],
                "value": scores[highest_idx],
                "itemStyle": {"color": "#f59e0b"},
            }
        )

    return {
        "title": {
            "text": "实验得分演进",
            "subtext": f"{len(exps)} 次实验 | 可信最优 {data.get('trusted_best_score', 'N/A')} | 历史最高 {data.get('highest_observed_score', 'N/A')}",
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "legend": {
            "data": list(family_colors.keys()),
            "bottom": 0,
            "itemWidth": 12,
            "itemHeight": 8,
            "textStyle": {"fontSize": 10},
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "22%", "top": "12%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": versions,
            "axisLabel": {"rotate": 55, "fontSize": 8, "interval": "auto"},
            "axisTick": {"alignWithLabel": True},
        },
        "yAxis": {"type": "value", "name": "Score", **_y_axis_opts(data)},
        "series": [
            {
                "name": "Score",
                "type": "line",
                "data": [
                    {"value": s, "itemStyle": {"color": point_colors[i]}} if s is not None else None
                    for i, s in enumerate(scores)
                ],
                "smooth": True,
                "connectNulls": False,
                "lineStyle": {"color": "#5470c6", "width": 2},
                "areaStyle": {"color": "#5470c6", "opacity": 0.05},
                "markPoint": {"data": mark_points, "symbolSize": 48},
                "markLine": {
                    "silent": True,
                    "data": [
                        {
                            "yAxis": data.get("trusted_best_score"),
                            "lineStyle": {"type": "dashed", "color": "#22c55e"},
                            "label": {"formatter": "Best"},
                        }
                    ],
                }
                if data.get("trusted_best_score")
                else {},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Chart 2: 主线提升阶梯（只保留 keep 且得分递增）
# ---------------------------------------------------------------------------
def gen_mainline(data):
    exps = data.get("experiments", [])
    direction = data.get("direction", "maximize")
    running_best = None
    mainline = []

    for e in exps:
        if e.get("decision") != "keep":
            continue
        s = e.get("score")
        if s is None:
            continue
        if running_best is None:
            mainline.append(e)
            running_best = s
        elif (direction == "maximize" and s > running_best) or (
            direction == "minimize" and s < running_best
        ):
            mainline.append(e)
            running_best = s

    # Ensure trusted best is included
    trusted_v = data.get("trusted_best_version", "")
    if trusted_v and not any(e.get("version") == trusted_v for e in mainline):
        for e in exps:
            if e.get("version") == trusted_v and e.get("score") is not None:
                mainline.append(e)
                break

    versions = [_short_version(e.get("version", "")) for e in mainline]
    scores = [round(e.get("score", 0), 2) for e in mainline]
    phases = [e.get("phase", "unknown") for e in mainline]

    return {
        "title": {"text": "主线提升阶梯", "subtext": f"{len(mainline)} 个里程碑"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 80, "right": 120, "bottom": 100, "top": 60, "containLabel": False},
        "xAxis": {
            "type": "category",
            "data": versions,
            "axisLabel": {"rotate": 30, "fontSize": 10},
        },
        "yAxis": {
            "type": "value",
            "name": "Score",
            "axisLabel": {"fontSize": 10},
            **_y_axis_opts(data),
        },
        "series": [
            {
                "name": "Mainline",
                "type": "line",
                "data": [
                    {
                        "value": s,
                        "label": {
                            "show": True,
                            "position": "top",
                            "formatter": "{c}",
                            "distance": 8,
                            "color": "#333",
                            "fontSize": 11,
                        },
                    }
                    for s in scores
                ],
                "step": "end",
                "lineStyle": {"color": "#175cd3", "width": 3},
                "itemStyle": {"color": "#175cd3", "borderWidth": 2, "borderColor": "#fff"},
                "areaStyle": {"color": "#175cd3", "opacity": 0.1},
                "markPoint": {
                    "symbol": "none",
                    "data": [
                        {
                            "coord": [len(scores) - 1, scores[-1]],
                            "value": scores[-1],
                            "label": {
                                "show": True,
                                "position": "top",
                                "formatter": "{c}",
                                "color": "#333",
                                "fontSize": 11,
                                "distance": 8,
                            },
                        }
                    ]
                    if scores
                    else [],
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Chart 3: 模型家族得分对比
# ---------------------------------------------------------------------------
def gen_family_compare(data):
    exps = data.get("experiments", [])
    family_scores = {}
    for e in exps:
        fam = _family(e.get("version", ""))
        s = e.get("score")
        if s is not None:
            family_scores.setdefault(fam, []).append(s)

    families = sorted(family_scores.keys(), key=lambda f: len(family_scores[f]), reverse=True)

    def box_stats(values):
        v = sorted(values)
        n = len(v)
        if n == 0:
            return [0, 0, 0, 0, 0]
        q1 = v[n // 4] if n >= 4 else v[0]
        median = v[n // 2] if n % 2 == 1 else (v[n // 2 - 1] + v[n // 2]) / 2
        q3 = v[3 * n // 4] if n >= 4 else v[-1]
        return [round(v[0], 2), round(q1, 2), round(median, 2), round(q3, 2), round(v[-1], 2)]

    box_data = [box_stats(family_scores[f]) for f in families]
    scatter_data = []
    for i, f in enumerate(families):
        for s in family_scores[f]:
            scatter_data.append([i, round(s, 2)])

    return {
        "title": {"text": "模型家族得分分布", "subtext": "箱线图 + 散点图"},
        "tooltip": {"trigger": "item"},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": families, "name": "Family"},
        "yAxis": {"type": "value", "name": "Score", **_y_axis_opts(data)},
        "series": [
            {"name": "Boxplot", "type": "boxplot", "data": box_data},
            {
                "name": "Points",
                "type": "scatter",
                "data": scatter_data,
                "itemStyle": {"opacity": 0.5},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Chart 4: 阶段得分箱线图
# ---------------------------------------------------------------------------
def gen_phase_compare(data):
    exps = data.get("experiments", [])
    phase_scores = {}
    for e in exps:
        ph = e.get("phase", "unknown")
        s = e.get("score")
        if s is not None:
            phase_scores.setdefault(ph, []).append(s)

    phases = sorted(phase_scores.keys())

    def box_stats(values):
        v = sorted(values)
        n = len(v)
        if n == 0:
            return [0, 0, 0, 0, 0]
        q1 = v[n // 4] if n >= 4 else v[0]
        median = v[n // 2] if n % 2 == 1 else (v[n // 2 - 1] + v[n // 2]) / 2
        q3 = v[3 * n // 4] if n >= 4 else v[-1]
        return [round(v[0], 2), round(q1, 2), round(median, 2), round(q3, 2), round(v[-1], 2)]

    box_data = [box_stats(phase_scores[p]) for p in phases]
    scatter_data = []
    for i, p in enumerate(phases):
        for s in phase_scores[p]:
            scatter_data.append([i, round(s, 2)])

    return {
        "title": {"text": "阶段得分分布", "subtext": "箱线图 + 散点"},
        "tooltip": {"trigger": "item"},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
        "xAxis": {"type": "category", "data": phases, "name": "Phase"},
        "yAxis": {"type": "value", "name": "Score", **_y_axis_opts(data)},
        "series": [
            {"name": "Boxplot", "type": "boxplot", "data": box_data},
            {
                "name": "Points",
                "type": "scatter",
                "data": scatter_data,
                "itemStyle": {"opacity": 0.5},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Chart 5: 阶段成功率对比
# ---------------------------------------------------------------------------
def gen_phase_success(data):
    exps = data.get("experiments", [])
    phase_decisions = {}
    for e in exps:
        ph = e.get("phase", "unknown")
        d = e.get("decision", "unknown")
        if ph not in phase_decisions:
            phase_decisions[ph] = {}
        phase_decisions[ph][d] = phase_decisions[ph].get(d, 0) + 1

    phases = sorted(phase_decisions.keys())
    keep_counts = [phase_decisions[p].get("keep", 0) for p in phases]
    discard_counts = [phase_decisions[p].get("discard", 0) for p in phases]
    crash_counts = [phase_decisions[p].get("crash", 0) for p in phases]
    total_counts = [sum(phase_decisions[p].values()) for p in phases]
    keep_rates = [
        round(keep_counts[i] / total_counts[i] * 100, 1) if total_counts[i] else 0
        for i in range(len(phases))
    ]

    return {
        "title": {"text": "阶段成功率", "subtext": "keep / discard / crash 堆叠 + keep 率折线"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": ["keep", "discard", "crash", "keep rate %"], "top": 0},
        "grid": {"left": "3%", "right": "10%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": phases},
        "yAxis": [
            {"type": "value", "name": "Count"},
            {
                "type": "value",
                "name": "Keep Rate %",
                "max": 100,
                "axisLabel": {"formatter": "{value}%"},
            },
        ],
        "series": [
            {
                "name": "keep",
                "type": "bar",
                "stack": "total",
                "data": keep_counts,
                "itemStyle": {"color": "#22c55e"},
            },
            {
                "name": "discard",
                "type": "bar",
                "stack": "total",
                "data": discard_counts,
                "itemStyle": {"color": "#9ca3af"},
            },
            {
                "name": "crash",
                "type": "bar",
                "stack": "total",
                "data": crash_counts,
                "itemStyle": {"color": "#ef4444"},
            },
            {
                "name": "keep rate %",
                "type": "line",
                "yAxisIndex": 1,
                "data": keep_rates,
                "itemStyle": {"color": "#175cd3"},
                "label": {"show": True, "formatter": "{c}%", "color": "#333", "fontWeight": "bold"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Chart 6: 反模式分类分布
# ---------------------------------------------------------------------------
def gen_anti_patterns(data):
    patterns = data.get("anti_patterns", [])
    cat_counts = {}
    for p in patterns:
        cat = p.get("category", "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Normalize category names to avoid duplicates like post_processing vs post-processing
    normalized = {}
    for cat, count in cat_counts.items():
        key = cat.replace("-", "_")
        normalized[key] = normalized.get(key, 0) + count
    cats = sorted(normalized.keys())
    counts = [normalized[c] for c in cats]

    return {
        "title": {"text": "反模式分布", "subtext": f"共 {len(patterns)} 条反模式"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": cats, "axisLabel": {"rotate": 35, "fontSize": 10}},
        "yAxis": {"type": "value", "name": "Count"},
        "series": [
            {
                "name": "Count",
                "type": "bar",
                "data": counts,
                "itemStyle": {"color": "#ee6666", "borderRadius": [4, 4, 0, 0]},
                "label": {"show": True, "position": "top"},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Chart 7: 反模式来源桑基图
# ---------------------------------------------------------------------------
def gen_anti_sankey(data):
    patterns = data.get("anti_patterns", [])
    nodes = []
    links = []
    node_set = set()
    link_counts = {}

    for p in patterns:
        source = p.get("source_version", "unknown")
        target = p.get("pattern", "unknown")[:30]
        cat = p.get("category", "unknown").replace("-", "_")

        # source -> category -> pattern 的流向太复杂，简化为 source -> category
        key = (source, cat)
        link_counts[key] = link_counts.get(key, 0) + 1

        if source not in node_set:
            node_set.add(source)
            nodes.append({"name": source})
        if cat not in node_set:
            node_set.add(cat)
            nodes.append({"name": cat})

    for (src, tgt), count in link_counts.items():
        links.append({"source": src, "target": tgt, "value": count})

    return {
        "title": {"text": "反模式来源流向", "subtext": "来源版本 → 反模式分类"},
        "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
        "series": [
            {
                "type": "sankey",
                "data": nodes,
                "links": links,
                "left": "3%",
                "right": "22%",
                "top": "12%",
                "bottom": "5%",
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {"color": "gradient", "curveness": 0.5},
                "label": {"fontSize": 10, "color": "#333", "position": "right"},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Chart 8: 决策分布饼图
# ---------------------------------------------------------------------------
def gen_decisions(data):
    exps = data.get("experiments", [])
    decisions = {}
    for e in exps:
        d = e.get("decision", "unknown")
        decisions[d] = decisions.get(d, 0) + 1

    pie_data = [
        {"name": k, "value": v, "itemStyle": {"color": _decision_color(k)}}
        for k, v in decisions.items()
    ]

    return {
        "title": {"text": "实验决策分布"},
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "name": "Decision",
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": pie_data,
                "label": {"formatter": "{b}: {c} ({d}%)"},
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0,0,0,0.5)",
                    }
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Chart 9: 模型家族成功率
# ---------------------------------------------------------------------------
def gen_family_success(data):
    exps = data.get("experiments", [])
    family_decisions = {}
    for e in exps:
        fam = _family(e.get("version", ""))
        d = e.get("decision", "unknown")
        if fam not in family_decisions:
            family_decisions[fam] = {}
        family_decisions[fam][d] = family_decisions[fam].get(d, 0) + 1

    families = sorted(
        family_decisions.keys(), key=lambda f: sum(family_decisions[f].values()), reverse=True
    )
    keep_counts = [family_decisions[f].get("keep", 0) for f in families]
    discard_counts = [family_decisions[f].get("discard", 0) for f in families]
    crash_counts = [family_decisions[f].get("crash", 0) for f in families]
    total_counts = [sum(family_decisions[f].values()) for f in families]
    keep_rates = [
        round(keep_counts[i] / total_counts[i] * 100, 1) if total_counts[i] else 0
        for i in range(len(families))
    ]

    return {
        "title": {"text": "模型家族成功率", "subtext": "keep / discard / crash 堆叠 + keep 率折线"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": ["keep", "discard", "crash", "keep rate %"], "top": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": families},
        "yAxis": [
            {"type": "value", "name": "Count"},
            {
                "type": "value",
                "name": "Keep Rate %",
                "max": 100,
                "axisLabel": {"formatter": "{value}%"},
            },
        ],
        "series": [
            {
                "name": "keep",
                "type": "bar",
                "stack": "total",
                "data": keep_counts,
                "itemStyle": {"color": "#22c55e"},
            },
            {
                "name": "discard",
                "type": "bar",
                "stack": "total",
                "data": discard_counts,
                "itemStyle": {"color": "#9ca3af"},
            },
            {
                "name": "crash",
                "type": "bar",
                "stack": "total",
                "data": crash_counts,
                "itemStyle": {"color": "#ef4444"},
            },
            {
                "name": "keep rate %",
                "type": "line",
                "yAxisIndex": 1,
                "data": keep_rates,
                "itemStyle": {"color": "#175cd3"},
                "label": {"show": True, "formatter": "{c}%"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Chart 10: 关键假设验证结果
# ---------------------------------------------------------------------------
def gen_hypothesis_outcome(data):
    exps = data.get("experiments", [])
    # Extract key terms from hypotheses and group by decision
    keep_hypotheses = []
    discard_hypotheses = []
    for e in exps:
        h = e.get("hypothesis", "")
        d = e.get("decision", "")
        if not h:
            continue
        if d == "keep":
            keep_hypotheses.append(h)
        elif d == "discard":
            discard_hypotheses.append(h)

    # Simple keyword extraction: split by common delimiters and filter short words
    def extract_keywords(texts):
        import re

        freq = {}
        for t in texts:
            # Split by common Chinese/English delimiters
            words = re.split(r'[，、。；：！？\s\(\)\[\]\{\}"\'\/\+\-\*\=\|]', t)
            for w in words:
                w = w.strip()
                if len(w) >= 2 and len(w) <= 12 and not w.isdigit():
                    freq[w] = freq.get(w, 0) + 1
        return freq

    keep_kw = extract_keywords(keep_hypotheses)
    discard_kw = extract_keywords(discard_hypotheses)

    # Take top keywords from each group
    top_keep = sorted(keep_kw.items(), key=lambda x: x[1], reverse=True)[:10]
    top_discard = sorted(discard_kw.items(), key=lambda x: x[1], reverse=True)[:10]

    all_words = sorted(set([w for w, _ in top_keep] + [w for w, _ in top_discard]))
    keep_vals = [keep_kw.get(w, 0) for w in all_words]
    discard_vals = [discard_kw.get(w, 0) for w in all_words]

    return {
        "title": {"text": "假设关键词频率", "subtext": "keep 实验 vs discard 实验的假设用词分布"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": ["keep", "discard"], "top": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "top": "12%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": all_words,
            "axisLabel": {"rotate": 35, "fontSize": 10},
        },
        "yAxis": {"type": "value", "name": "Frequency"},
        "series": [
            {
                "name": "keep",
                "type": "bar",
                "data": keep_vals,
                "itemStyle": {"color": "#22c55e", "borderRadius": [4, 4, 0, 0]},
            },
            {
                "name": "discard",
                "type": "bar",
                "data": discard_vals,
                "itemStyle": {"color": "#9ca3af", "borderRadius": [4, 4, 0, 0]},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Overview HTML
# ---------------------------------------------------------------------------
def gen_overview_html(chart_files):
    charts_js = ",\n    ".join(f'"{f}"' for f in chart_files)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Research Overview</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #f8fafc; }}
h1 {{ margin: 0 0 20px; font-size: 20px; color: #182230; }}
.grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
.chart {{ width: 100%; height: 380px; background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 12px; box-sizing: border-box; }}
.chart-full {{ grid-column: 1 / -1; height: 420px; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>Experiment Research Overview</h1>
<div class="grid">
<div id="c1" class="chart chart-full"></div>
<div id="c2" class="chart"></div>
<div id="c3" class="chart"></div>
<div id="c4" class="chart"></div>
<div id="c5" class="chart"></div>
<div id="c6" class="chart"></div>
<div id="c7" class="chart chart-full"></div>
<div id="c8" class="chart"></div>
<div id="c9" class="chart"></div>
<div id="c10" class="chart"></div>
</div>
<script>
const files = [{charts_js}];
const ids = ["c1","c2","c3","c4","c5","c6","c7","c8","c9","c10"];
Promise.all(files.map(f => fetch(f).then(r => r.json()))).then(configs => {{
  configs.forEach((cfg, i) => {{
    const chart = echarts.init(document.getElementById(ids[i]));
    chart.setOption(cfg);
    window.addEventListener('resize', () => chart.resize());
  }});
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    data, workspace = load_experiments()
    out_dir = workspace / "research_views" / "echarts"
    out_dir.mkdir(parents=True, exist_ok=True)

    charts = {
        "01_timeline.echarts.json": gen_timeline(data),
        "02_mainline.echarts.json": gen_mainline(data),
        "03_family_compare.echarts.json": gen_family_compare(data),
        "04_phase_compare.echarts.json": gen_phase_compare(data),
        "05_phase_success.echarts.json": gen_phase_success(data),
        "06_anti_patterns.echarts.json": gen_anti_patterns(data),
        "07_anti_sankey.echarts.json": gen_anti_sankey(data),
        "08_decisions.echarts.json": gen_decisions(data),
        "09_family_success.echarts.json": gen_family_success(data),
        "10_hypothesis_outcome.echarts.json": gen_hypothesis_outcome(data),
    }

    for fname, config in charts.items():
        path = out_dir / fname
        with open(path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Generated: {path}")

    overview_path = out_dir / "overview.html"
    with open(overview_path, "w") as f:
        f.write(gen_overview_html(list(charts.keys())))
    print(f"Generated: {overview_path}")


if __name__ == "__main__":
    main()
