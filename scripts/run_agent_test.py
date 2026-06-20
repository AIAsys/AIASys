#!/usr/bin/env python3
"""
Agent 能力测试辅助脚本：发送 prompt 到 Agent，收集 SSE 流响应，解析工具调用。
用法：python run_agent_test.py <session_id> "<prompt>" [output_file]
"""

import json
import sys
import urllib.request
import urllib.error
import time

BASE_URL = "http://localhost:13001"

def send_prompt(session_id: str, prompt: str):
    url = f"{BASE_URL}/api/agent/execute/stream"
    data = json.dumps({"session_id": session_id, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    events = []
    tool_calls = []
    tool_results = []
    contents = []
    start_time = time.time()
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
                    elif t == "content":
                        contents.append(evt)
                except json.JSONDecodeError:
                    pass
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None

    elapsed = time.time() - start_time
    return {
        "elapsed_sec": round(elapsed, 1),
        "event_count": len(events),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "contents": contents,
        "all_events": events,
    }


def summarize(result):
    if result is None:
        return "FAILED: request error"
    lines = []
    lines.append(f"elapsed: {result['elapsed_sec']}s")
    lines.append(f"events: {result['event_count']}")
    lines.append(f"tool_calls: {len(result['tool_calls'])}")
    for tc in result['tool_calls']:
        name = tc.get("name", "?")
        args = tc.get("arguments", {})
        lines.append(f"  -> {name}({json.dumps(args, ensure_ascii=False)[:120]})")
    lines.append(f"tool_results: {len(result['tool_results'])}")
    for tr in result['tool_results']:
        status = "ok" if "error" not in str(tr).lower() else "error"
        lines.append(f"  <- {status}")
    # 收集所有文本内容
    texts = []
    for c in result['contents']:
        if c.get('content_type') == 'text':
            texts.append(c.get('content', ''))
    if texts:
        full_text = ''.join(texts)
        lines.append(f"text_output_preview: {full_text[:300]}")
    return '\n'.join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <session_id> '<prompt>' [output.json]", file=sys.stderr)
        sys.exit(1)
    session_id = sys.argv[1]
    prompt = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"Sending prompt to session {session_id}...", file=sys.stderr)
    result = send_prompt(session_id, prompt)
    summary = summarize(result)
    print(summary)

    if output_file and result:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nFull result saved to {output_file}", file=sys.stderr)
