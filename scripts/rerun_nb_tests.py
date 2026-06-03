#!/usr/bin/env python3
"""重测 NB 域用例"""

import json
import sys
import urllib.request
import time
import os
from pathlib import Path

BASE_URL = "http://localhost:13001"
SESSION_ID = "1866195f-8e42-45f0-8b38-ef79e5c5ae0a"
OUTPUT_DIR = "/tmp/agent_test_nb_rerun"

os.makedirs(OUTPUT_DIR, exist_ok=True)

TEST_CASES = [
    {"id": "NB-001", "prompt": "帮我创建一个 Jupyter notebook，名字叫 analysis.ipynb，里面加一个代码单元格，写一段计算 1 到 10 乘积的代码。"},
    {"id": "NB-002", "prompt": "当前工作区里有个 analysis.ipynb，帮我执行里面的第一个代码单元格，然后把输出结果给我。"},
    {"id": "NB-003", "prompt": "把当前工作区的 analysis.ipynb 导出成一个 Python 脚本 analysis.py，然后让我看看这个脚本的内容。"},
    {"id": "NB-004", "prompt": "在当前工作区创建一个 notebook package_test.ipynb，添加一个代码单元格安装 numpy，再添加一个代码单元格用 numpy 生成一个 3x3 的随机矩阵并打印出来。然后执行这两个单元格。"},
]


def send_prompt(prompt: str):
    url = f"{BASE_URL}/api/agent/execute/stream"
    data = json.dumps({"session_id": SESSION_ID, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
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


def run_test(tc: dict):
    print(f"[RUN] {tc['id']}: {tc['prompt'][:50]}...", file=sys.stderr)
    start = time.time()
    result = send_prompt(tc["prompt"])
    elapsed = time.time() - start
    result["elapsed_sec"] = round(elapsed, 1)
    result["test_id"] = tc["id"]

    out_file = Path(OUTPUT_DIR) / f"test_{tc['id'].lower()}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if "error" in result:
        summary = f"ERROR: {result['error']}"
    else:
        tc_names = [tc.get("tool_name", "?") for tc in result["tool_calls"]]
        tr_errors = sum(1 for tr in result["tool_results"] if tr.get("is_error"))
        summary = f"tools={tc_names} errors={tr_errors}/{len(result['tool_results'])}"
    print(f"[DONE] {tc['id']}: {summary} ({elapsed:.1f}s)", file=sys.stderr)
    time.sleep(2)
    return result


if __name__ == "__main__":
    results = []
    for tc in TEST_CASES:
        results.append(run_test(tc))

    print("\n" + "=" * 60, file=sys.stderr)
    print("NB RERUN SUMMARY", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
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
        print(f"{tid}: {status} | {detail} | {r.get('elapsed_sec', '?')}s", file=sys.stderr)
