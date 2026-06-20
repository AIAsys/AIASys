#!/usr/bin/env python3
"""重测未通过的用例"""

import json
import sys
import urllib.request
import time
import os
from pathlib import Path

BASE_URL = "http://localhost:13001"
SESSION_ID = "564c9f2f-48e2-42ec-bd46-02618fa44566"
OUTPUT_DIR = "/tmp/agent_test_rerun"

os.makedirs(OUTPUT_DIR, exist_ok=True)

TEST_CASES = [
    # FS 域
    {"id": "FS-001", "prompt": "当前工作区里有没有一个叫 README.md 的文件？如果有的话，把前 10 行内容给我看看。"},
    {"id": "FS-003", "prompt": "当前工作区有个文件 config.txt，里面有一行 api_url = \"http://localhost:8000\"，帮我把这个地址改成 https://api.example.com"},
    # EV 域
    {"id": "EV-002", "prompt": "我需要在这个工作区里设一个 API_KEY，值是 test_12345。"},
    {"id": "EV-003", "prompt": "我工作区里那个 API_KEY 的值是什么？帮我查一下。"},
    {"id": "EV-004", "prompt": "那个 API_KEY 不用了，帮我删掉，然后确认一下已经没了。"},
    # SK 域
    {"id": "SK-001", "prompt": "我当前工作区都启用了哪些 skill？帮我列出来看看。"},
    {"id": "SK-002", "prompt": "我想加一个能帮我处理文档的 skill，去 skill 仓库里找一个合适的帮我装上。"},
    {"id": "SK-003", "prompt": "我想看看刚才装上的那个 skill 具体能做什么，把它的说明文档读给我看看。"},
    {"id": "SK-004", "prompt": "有个 skill 我不太需要了，帮我把它禁用掉，别让它再占资源。"},
    # NB 域
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
                # FastAPI/Starlette always sends UTF-8 encoded responses
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
    print("RERUN SUMMARY", file=sys.stderr)
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
