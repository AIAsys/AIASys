#!/usr/bin/env python3
"""AIASys skill description 优化 —— 替换 improve_description.py 的 claude -p 依赖。

基于 trigger_test.py 的 eval 结果，调用 LLM API 生成改进后的 description。

环境变量：
  AIASYS_LLM_API_KEY / OPENAI_API_KEY
  AIASYS_LLM_BASE_URL / OPENAI_BASE_URL
  AIASYS_LLM_MODEL
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

from scripts.utils import parse_skill_md


def get_llm_client() -> OpenAI:
    api_key = os.environ.get("AIASYS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未找到 LLM API key。请设置 AIASYS_LLM_API_KEY 或 OPENAI_API_KEY 环境变量。"
        )
    base_url = os.environ.get("AIASYS_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url)


def get_model() -> str:
    return os.environ.get("AIASYS_LLM_MODEL", "deepseek-chat")


def call_llm(prompt: str, timeout: int = 300, mock: bool = False) -> str:
    """调用 LLM 获取文本响应。"""
    if mock:
        # Mock: 返回一个轻微修改的 description
        return "<new_description>An improved test skill description that better matches user queries.</new_description>"
    client = get_llm_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1024,
        timeout=timeout,
    )
    return response.choices[0].message.content or ""


def improve_description(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    log_dir: Path | None = None,
    iteration: int | None = None,
    mock: bool = False,
) -> str:
    """基于 eval 结果调用 LLM 改进 description。"""
    failed_triggers = [r for r in eval_results["results"] if r["should_trigger"] and not r["pass"]]
    false_triggers = [
        r for r in eval_results["results"] if not r["should_trigger"] and not r["pass"]
    ]

    train_score = f"{eval_results['summary']['passed']}/{eval_results['summary']['total']}"

    prompt = f"""You are optimizing a skill description for an AIASys skill called "{skill_name}".

A "skill" is like a prompt with progressive disclosure — there's a title and description that the AI sees when deciding whether to use the skill, and then if it does use the skill, it reads the SKILL.md file which has detailed instructions and optional scripts/resources.

The description appears in the AI's "available_skills" list. When a user sends a query, the AI decides whether to invoke the skill based solely on the title and description. Your goal is to write a description that triggers for relevant queries, and doesn't trigger for irrelevant ones.

Here's the current description:
<current_description>
"{current_description}"
</current_description>

Current score: {train_score}
"""
    if failed_triggers:
        prompt += "\nFAILED TO TRIGGER (should have triggered but didn't):\n"
        for r in failed_triggers:
            prompt += f'  - "{r["query"]}" (triggered {r["triggers"]}/{r["runs"]} times)\n'

    if false_triggers:
        prompt += "\nFALSE TRIGGERS (triggered but shouldn't have):\n"
        for r in false_triggers:
            prompt += f'  - "{r["query"]}" (triggered {r["triggers"]}/{r["runs"]} times)\n'

    if history:
        prompt += (
            "\nPREVIOUS ATTEMPTS (do NOT repeat these — try something structurally different):\n\n"
        )
        for h in history:
            score_str = f"{h.get('passed', 0)}/{h.get('total', 0)}"
            prompt += f"<attempt score={score_str}>\n"
            prompt += f'Description: "{h["description"]}"\n'
            if h.get("note"):
                prompt += f"Note: {h['note']}\n"
            prompt += "</attempt>\n\n"

    prompt += f"""
Skill content (for context on what the skill does):
<skill_content>
{skill_content}
</skill_content>

Based on the failures, write a new and improved description. Generalize from the failures to broader categories of user intent — do NOT produce an ever-expanding list of specific queries.

Constraints:
- Description should not be more than about 100-200 words
- Hard limit of 1024 characters — descriptions over that will be truncated
- Phrase in the imperative: "Use this skill for..." rather than "This skill does..."
- Focus on user intent, not implementation details
- Make it distinctive and immediately recognizable

Please respond with ONLY the new description text in <new_description> tags, nothing else."""

    text = call_llm(prompt, mock=mock)

    match = re.search(r"<new_description>(.*?)</new_description>", text, re.DOTALL)
    description = match.group(1).strip().strip('"') if match else text.strip().strip('"')

    transcript = {
        "iteration": iteration,
        "prompt": prompt,
        "response": text,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > 1024,
    }

    # Safety net: if over limit, ask for shorter rewrite
    if len(description) > 1024:
        shorten_prompt = (
            f"{prompt}\n\n"
            f"---\n\n"
            f"A previous attempt produced this description, which at "
            f"{len(description)} characters is over the 1024-character hard limit:\n\n"
            f'"{description}"\n\n'
            f"Rewrite it to be under 1024 characters while keeping the most "
            f"important trigger words and intent coverage. Respond with only "
            f"the new description in <new_description> tags."
        )
        shorten_text = call_llm(shorten_prompt, mock=mock)
        match = re.search(r"<new_description>(.*?)</new_description>", shorten_text, re.DOTALL)
        shortened = match.group(1).strip().strip('"') if match else shorten_text.strip().strip('"')
        transcript["rewrite_description"] = shortened
        transcript["rewrite_char_count"] = len(shortened)
        description = shortened

    transcript["final_description"] = description

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"improve_iter_{iteration or 'unknown'}.json"
        log_file.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

    return description


def main():
    parser = argparse.ArgumentParser(
        description="Improve a skill description based on eval results"
    )
    parser.add_argument(
        "--eval-results", required=True, help="Path to eval results JSON (from trigger_test.py)"
    )
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--history", default=None, help="Path to history JSON (previous attempts)")
    parser.add_argument("--verbose", action="store_true", help="Print thinking to stderr")
    parser.add_argument("--mock", action="store_true", help="使用 mock LLM (无需 API key)")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text())
    history = []
    if args.history:
        history = json.loads(Path(args.history).read_text())

    name, _, content = parse_skill_md(skill_path)
    current_description = eval_results["description"]

    if args.verbose:
        print(f"Current: {current_description}", file=sys.stderr)
        print(
            f"Score: {eval_results['summary']['passed']}/{eval_results['summary']['total']}",
            file=sys.stderr,
        )

    new_description = improve_description(
        skill_name=name,
        skill_content=content,
        current_description=current_description,
        eval_results=eval_results,
        history=history,
        mock=args.mock,
    )

    if args.verbose:
        print(f"Improved: {new_description}", file=sys.stderr)

    output = {
        "description": new_description,
        "history": history
        + [
            {
                "description": current_description,
                "passed": eval_results["summary"]["passed"],
                "failed": eval_results["summary"]["failed"],
                "total": eval_results["summary"]["total"],
                "results": eval_results["results"],
            }
        ],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
