#!/usr/bin/env python3
"""
多轮对话上下文连续性测试

验证 Agent 在同一 session 中能否记住前一轮的工具调用结果。
专门针对 history.json 完整同步修复（tool_calls + tool 消息不丢失）。

测试流程：
  轮 1: 让 Agent 用 WriteFile 创建文件 test_multi_turn.txt，内容为 "secret_code=42"
  轮 2: 让 Agent 读回 test_multi_turn.txt 的内容（不告诉它内容，只说文件名）
  轮 3: 问 Agent "刚才读到的文件内容里 secret_code 的值是多少"——
        如果上下文完整，Agent 能直接回答 42（不需要再读文件）；
        如果上下文断裂（tool 结果丢失），Agent 会说"不知道"或重新读文件。

用法:
  python3 scripts/multi_turn_context_test.py <session_id>

前置条件:
  - 后端运行在 localhost:13001
  - session_id 对应的会话已创建
"""

import json
import sys
import time
import urllib.request

BASE_URL = "http://localhost:13001"

# ── 测试用例定义 ──────────────────────────────────────────────

TURNS = [
    {
        "id": "MT-001",
        "prompt": (
            "请用 WriteFile 在当前工作区创建文件 test_multi_turn.txt，"
            "内容为：secret_code=42"
        ),
        "expect_tools": ["WriteFile"],
        "description": "轮1: 创建文件，建立上下文",
    },
    {
        "id": "MT-002",
        "prompt": "帮我读一下 test_multi_turn.txt 的内容。",
        "expect_tools": ["ReadFile"],
        "description": "轮2: 读取文件，工具结果进入上下文",
    },
    {
        "id": "MT-003",
        "prompt": (
            "刚才读到的文件内容里，secret_code 的值是多少？"
            "直接告诉我，不要再去读文件。"
        ),
        "expect_tools": [],  # 期望不调工具，直接从上下文回答
        "description": "轮3: 验证上下文连续性——模型应记得 tool 返回的 42",
        "check_context": True,
    },
]


def send_prompt(session_id: str, prompt: str) -> dict:
    """发送 prompt 到 Agent，收集事件流。"""
    url = f"{BASE_URL}/api/agent/execute/stream"
    data = json.dumps({"session_id": session_id, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    tool_calls = []
    tool_results = []
    events = []
    assistant_text = []

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
                    elif t == "content" and evt.get("content_type") == "text":
                        assistant_text.append(evt.get("text", ""))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        return {"error": str(e)}

    return {
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "event_count": len(events),
        "assistant_text": "".join(assistant_text),
    }


def evaluate_turn(turn: dict, result: dict) -> dict:
    """评估单轮结果，返回 pass/fail 和失败原因。"""
    if "error" in result:
        return {"status": "ERROR", "failures": [result["error"]]}

    failures = []
    tool_names = [tc.get("tool_name", "") for tc in result["tool_calls"]]
    assistant_text = result.get("assistant_text", "")

    # 检查期望工具
    expected = turn.get("expect_tools", [])
    if expected:
        for t in expected:
            if t not in tool_names:
                failures.append(f"期望调用 {t}，实际调用: {tool_names or '(无)'}")
    elif turn.get("check_context"):
        # 上下文连续性检查：期望不调工具
        if tool_names:
            failures.append(
                f"期望不调用工具（应从上下文回答），但调了: {tool_names}"
            )
        # 检查回答中是否包含 "42"
        if "42" not in assistant_text:
            failures.append(
                f"回答中未包含 42，可能上下文断裂。回答摘要: {assistant_text[:200]}"
            )

    status = "PASS" if not failures else "FAIL"
    return {"status": status, "failures": failures, "tool_names": tool_names}


def run_test(session_id: str):
    """执行完整多轮对话测试。"""
    print("=" * 70)
    print("多轮对话上下文连续性测试")
    print("=" * 70)
    print(f"Session: {session_id}")
    print()

    results = []
    all_pass = True

    for i, turn in enumerate(TURNS, 1):
        print(f"[轮 {i}/{len(TURNS)}] {turn['id']}: {turn['description']}")
        print(f"  Prompt: {turn['prompt'][:80]}...")

        start = time.time()
        result = send_prompt(session_id, turn["prompt"])
        elapsed = time.time() - start

        result["elapsed_sec"] = round(elapsed, 1)
        result["test_id"] = turn["id"]

        evaluation = evaluate_turn(turn, result)
        result["status"] = evaluation["status"]
        result["failures"] = evaluation["failures"]
        result["tool_names"] = evaluation.get("tool_names", [])

        if evaluation["status"] != "PASS":
            all_pass = False

        # 打印结果
        status_icon = "✅" if evaluation["status"] == "PASS" else "❌"
        print(f"  {status_icon} {evaluation['status']} ({elapsed:.1f}s)")
        print(f"  Tools: {result['tool_names'] or '(无)'}")
        if result.get("assistant_text"):
            print(f"  Reply: {result['assistant_text'][:150]}...")
        if evaluation["failures"]:
            for f in evaluation["failures"]:
                print(f"  ⚠️  {f}")
        print()

        results.append(result)
        time.sleep(1)  # 轮间间隔

    # 汇总
    print("=" * 70)
    print("测试汇总")
    print("=" * 70)
    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {icon} {r['test_id']}: {r['status']} | tools={r['tool_names']} | {r['elapsed_sec']}s")
        if r.get("failures"):
            for f in r["failures"]:
                print(f"       → {f}")

    print()
    if all_pass:
        print("🎉 全部通过！多轮对话上下文连续性正常。")
    else:
        print("💥 有失败项！上下文可能不连续。")

    # 保存详细结果
    output_file = "/tmp/multi_turn_context_test_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存: {output_file}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <session_id>")
        print(f"示例: {sys.argv[0]} 564c9f2f-48e2-42ec-bd46-02618fa44566")
        sys.exit(1)

    session_id = sys.argv[1]
    sys.exit(run_test(session_id))
