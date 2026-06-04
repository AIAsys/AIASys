#!/usr/bin/env python3
"""AIASys skill 触发测试 —— 替换 run_eval.py 的 claude -p 依赖。

通过直接调用 LLM API 测试 skill description 的触发准确率。
支持两种模式：
  - mock（默认）：构造模拟 system prompt，让模型判断是否应该触发
  - api：调用 AIASys backend /agent/execute/stream 观察实际 LoadSkill 调用

环境变量：
  AIASYS_LLM_API_KEY / OPENAI_API_KEY — LLM API key
  AIASYS_LLM_BASE_URL / OPENAI_BASE_URL — 可选，自定义 base URL
  AIASYS_LLM_MODEL — 模型 ID（默认 deepseek-chat）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

from scripts.utils import parse_skill_md


def get_llm_client() -> OpenAI:
    """获取配置好的 OpenAI 兼容客户端。"""
    api_key = os.environ.get("AIASYS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未找到 LLM API key。请设置 AIASYS_LLM_API_KEY 或 OPENAI_API_KEY 环境变量。"
        )
    base_url = os.environ.get("AIASYS_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url)


def get_model() -> str:
    return os.environ.get("AIASYS_LLM_MODEL", "deepseek-chat")


def build_trigger_prompt(skill_name: str, skill_desc: str, query: str, other_skills: list[dict] | None = None) -> str:
    """构造触发判断 prompt。

    模拟 AIASys 中 skill 常驻注入 system prompt 的方式，让模型判断
    给定 query 是否应该触发目标 skill。
    """
    lines = [
        "You are an AI assistant with access to the following skills:",
        "",
    ]
    if other_skills:
        for s in other_skills:
            lines.append(f"- {s['name']}: {s['description']}")
    lines.append(f"- {skill_name}: {skill_desc}")
    lines.extend([
        "",
        "When a user sends a query, you decide whether to use a skill based on its name and description.",
        "You only consult skills for tasks you can't easily handle on your own.",
        "Simple, one-step queries usually don't need a skill.",
        "Complex, multi-step, or specialized queries reliably trigger skills when the description matches.",
        "",
        f"User query: {query}",
        "",
        "Should the skill '{skill_name}' be triggered for this query?",
        "Answer with ONLY a JSON object: {\"triggered\": true/false, \"reasoning\": \"brief explanation\"}",
    ])
    return "\n".join(lines)


def run_single_query_mock(
    query: str,
    skill_name: str,
    skill_desc: str,
    timeout: int,
    other_skills: list[dict] | None = None,
) -> bool:
    """Mock 模式：直接调用 LLM 判断是否应该触发。"""
    client = get_llm_client()
    prompt = build_trigger_prompt(skill_name, skill_desc, query, other_skills)

    try:
        response = client.chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
            timeout=timeout,
        )
        content = response.choices[0].message.content or ""
        # 尝试从响应中提取 JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[len("```json"):]
        if content.startswith("```"):
            content = content[len("```"):]
        if content.endswith("```"):
            content = content[:-len("```")]
        content = content.strip()

        result = json.loads(content)
        return bool(result.get("triggered", False))
    except Exception as e:
        print(f"Warning: query failed: {e}", file=sys.stderr)
        return False


def run_single_query_api(
    query: str,
    skill_name: str,
    skill_path: Path,
    backend_url: str,
    workspace_id: str,
    user_id: str,
    timeout: int,
) -> bool:
    """API 模式：调用 AIASys backend 观察实际 LoadSkill 调用。

    TODO: 实现 SSE 流解析，检测 LoadSkill 工具调用。
    当前未实现，fallback 到 mock 模式。
    """
    print(
        f"Warning: API mode not yet implemented for query '{query[:40]}...'. "
        "Falling back to mock mode.",
        file=sys.stderr,
    )
    _, skill_desc, _ = parse_skill_md(skill_path)
    return run_single_query_mock(query, skill_name, skill_desc, timeout)


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    skill_desc: str,
    skill_path: Path,
    num_workers: int,
    timeout: int,
    runs_per_query: int,
    trigger_threshold: float,
    mode: str,
    backend_url: str | None,
    workspace_id: str | None,
    user_id: str | None,
    other_skills: list[dict] | None,
) -> dict:
    """运行完整的 eval set 并返回结果。"""
    results = []

    def run_one(item: dict, _run_idx: int) -> bool:
        query = item["query"]
        if mode == "api":
            return run_single_query_api(
                query, skill_name, skill_path,
                backend_url or "", workspace_id or "", user_id or "",
                timeout,
            )
        return run_single_query_mock(query, skill_name, skill_desc, timeout, other_skills)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(run_one, item, run_idx)
                future_to_info[future] = item

        query_triggers: dict[str, list[bool]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
            try:
                query_triggers[query].append(future.result())
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_triggers[query].append(False)

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": skill_desc,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Skill trigger evaluation for AIASys")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=5, help="并行 workers (默认 5)")
    parser.add_argument("--timeout", type=int, default=60, help="单个 query 超时秒数 (默认 60)")
    parser.add_argument("--runs-per-query", type=int, default=3, help="每个 query 运行次数 (默认 3)")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="触发率阈值 (默认 0.5)")
    parser.add_argument("--mode", choices=["mock", "api"], default="mock",
                        help="测试模式：mock=直接调用LLM (默认), api=调用backend API")
    parser.add_argument("--backend-url", default=None, help="Backend API URL (api 模式)")
    parser.add_argument("--workspace-id", default=None, help="Workspace ID (api 模式)")
    parser.add_argument("--user-id", default=None, help="User ID (api 模式)")
    parser.add_argument("--other-skills", default=None, help="其他 skill JSON 文件路径，用于模拟竞争环境")
    parser.add_argument("--verbose", action="store_true", help="打印进度")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, _ = parse_skill_md(skill_path)
    description = args.description or original_description

    other_skills = None
    if args.other_skills:
        other_skills = json.loads(Path(args.other_skills).read_text())

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)
        print(f"Mode: {args.mode}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        skill_desc=description,
        skill_path=skill_path,
        num_workers=args.num_workers,
        timeout=args.timeout,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        mode=args.mode,
        backend_url=args.backend_url,
        workspace_id=args.workspace_id,
        user_id=args.user_id,
        other_skills=other_skills,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
