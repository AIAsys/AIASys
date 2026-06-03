#!/usr/bin/env python3
"""
批量执行 Agent 能力测试用例
用法: python batch_agent_tests.py <session_id> <output_dir>
"""

import json
import sys
import urllib.request
import time
import os
from pathlib import Path

BASE_URL = "http://localhost:13001"

TEST_CASES = [
    # Notebook 域
    {"id": "NB-002", "prompt": "当前工作区里有个 analysis.ipynb，帮我执行里面的第一个代码单元格，然后把输出结果给我。"},
    {"id": "NB-003", "prompt": "把当前工作区的 analysis.ipynb 导出成一个 Python 脚本 analysis.py，然后让我看看这个脚本的内容。"},
    {"id": "NB-004", "prompt": "在当前工作区创建一个 notebook package_test.ipynb，添加一个代码单元格安装 numpy，再添加一个代码单元格用 numpy 生成一个 3x3 的随机矩阵并打印出来。然后执行这两个单元格。"},
    # 环境变量域
    {"id": "EV-001", "prompt": "我当前工作区都设置了哪些环境变量？帮我看看。"},
    {"id": "EV-002", "prompt": "我需要在这个工作区里设一个 API_KEY，值是 test_12345。"},
    {"id": "EV-003", "prompt": "我工作区里那个 API_KEY 的值是什么？帮我查一下。"},
    {"id": "EV-004", "prompt": "那个 API_KEY 不用了，帮我删掉，然后确认一下已经没了。"},
    # Skill 管理域
    {"id": "SK-001", "prompt": "我当前工作区都启用了哪些 skill？帮我列出来看看。"},
    {"id": "SK-002", "prompt": "我想加一个能帮我处理文档的 skill，去 skill 仓库里找一个合适的帮我装上。"},
    {"id": "SK-003", "prompt": "我想看看刚才装上的那个 skill 具体能做什么，把它的说明文档读给我看看。"},
    {"id": "SK-004", "prompt": "有个 skill 我不太需要了，帮我把它禁用掉，别让它再占资源。"},
    # 专家域
    {"id": "EX-001", "prompt": "系统里有哪些专家角色可以用？帮我看看列表。"},
    {"id": "EX-002", "prompt": "我想装一个数据分析专家，系统里应该有内置的，帮我装到当前工作区。"},
    {"id": "EX-003", "prompt": "有个专家我不想让它在当前会话里出现，帮我关掉它，但别卸载。"},
    {"id": "EX-004", "prompt": "我这个数据清理的任务挺复杂，让数据分析专家来帮我处理一下。"},
    # MCP 域
    {"id": "MC-001", "prompt": "MCP 市场里有哪些 server 可以用？帮我列一下。"},
    {"id": "MC-002", "prompt": "我想找一个能查天气的 MCP server，去外部市场搜搜看有没有合适的。"},
    {"id": "MC-003", "prompt": "刚才找到的天气 server 看着不错，帮我装到工作区里，把它的工具也打开。"},
    # 工作区管理域
    {"id": "WS-001", "prompt": "我想新开一个数据分析项目，用数据分析模板帮我建个工作区。"},
    {"id": "WS-002", "prompt": "我这个工作区的配置和文件结构整理得不错，想把它存成模板以后复用，帮我导出一下。"},
    {"id": "WS-003", "prompt": "我朋友给了我一个项目模板文件，帮我把它导入到系统里。"},
    {"id": "WS-004", "prompt": "帮我切换到另一个工作区，然后看看那个工作区里有什么文件，确认一下和现在的不是同一个。"},
]


def send_prompt(session_id: str, prompt: str):
    url = f"{BASE_URL}/api/agent/execute/stream"
    data = json.dumps({"session_id": session_id, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    tool_calls = []
    tool_results = []
    events = []
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    evt = json.loads(payload)
                    events.append(evt)
                    t = evt.get("type")
                    if t == "tool_call":
                        tool_calls.append(evt)
                    elif t == "tool_result":
                        tool_results.append(evt)
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        return {"error": str(e)}
    return {"tool_calls": tool_calls, "tool_results": tool_results, "event_count": len(events)}


def run_test(session_id: str, tc: dict, output_dir: str):
    print(f"[RUN] {tc['id']}: {tc['prompt'][:60]}...", file=sys.stderr)
    start = time.time()
    result = send_prompt(session_id, tc["prompt"])
    elapsed = time.time() - start
    result["elapsed_sec"] = round(elapsed, 1)
    result["test_id"] = tc["id"]
    result["prompt"] = tc["prompt"]

    # Save raw result
    out_file = Path(output_dir) / f"test_{tc['id'].lower()}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Summary
    if "error" in result:
        summary = f"ERROR: {result['error']}"
    else:
        tc_names = [tc.get("tool_name", "?") for tc in result["tool_calls"]]
        tr_errors = sum(1 for tr in result["tool_results"] if tr.get("is_error"))
        summary = f"tools={tc_names} errors={tr_errors}/{len(result['tool_results'])} events={result['event_count']}"
    print(f"[DONE] {tc['id']}: {summary} ({elapsed:.1f}s)", file=sys.stderr)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <session_id> <output_dir>", file=sys.stderr)
        sys.exit(1)
    session_id = sys.argv[1]
    output_dir = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for tc in TEST_CASES:
        result = run_test(session_id, tc, output_dir)
        results.append(result)
        # Small delay between tests
        time.sleep(2)

    # Summary report
    print("\n" + "=" * 60)
    print("BATCH TEST SUMMARY")
    print("=" * 60)
    for r in results:
        tid = r["test_id"]
        if "error" in r:
            status = "BLOCKED"
            detail = r["error"]
        else:
            tc_names = [tc.get("tool_name", "?") for tc in r["tool_calls"]]
            tr_errors = sum(1 for tr in r["tool_results"] if tr.get("is_error"))
            status = "FAIL" if tr_errors > 0 and len(r["tool_results"]) > 0 else "PASS" if len(r["tool_calls"]) > 0 else "NO_TOOLS"
            detail = f"tools={','.join(tc_names) or 'none'} errors={tr_errors}"
        print(f"{tid}: {status} | {detail} | {r.get('elapsed_sec', '?')}s")
