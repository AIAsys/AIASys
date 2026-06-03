#!/usr/bin/env python3
"""批量更新测试用例文件的测试记录"""

import re
from pathlib import Path

BASE_DIR = Path("/home/ke/projects/AIASys/design-draft/agent-test-cases/references")
DATE = "2026-06-02"

# 每个用例的测试结果
RESULTS = {
    # filesystem.md
    "TC-FS-001": "部分通过。Agent 调用 ReadFile，路径正确。文件不存在时 tool_result 返回错误信息，但 Agent 未生成文本回复告知用户。",
    "TC-FS-002": "通过。Agent 先尝试 `/workspace/hello.txt` 路径两次（失败），后改用相对路径 `hello.txt` 成功。两次 WriteFile 分别写入和覆盖，最终文件内容验证为 'Hello World'。",
    "TC-FS-003": "失败。StrReplaceFile 工具 edit 参数 Pydantic 验证失败，Agent 6 次调用全部报错。最终靠 Shell `sed` 命令绕过完成替换。",
    "TC-FS-004": "通过。Agent 正确调用 ReadFile 并传入 `/global/MEMORY.md` 前缀，成功读取全局工作区文件内容。",
    # shell.md
    "TC-SH-001": "通过。Agent 调用 Shell 执行 `ls -la`，成功返回当前工作区根目录文件列表。",
    "TC-SH-002": "通过。Agent 调用 Shell 执行 `uname -a && python --version`，成功返回 Linux 信息和 Python 3.14.3。",
    "TC-SH-003": "部分通过。Agent 调用 Shell 执行 `grep -rl TODO --include='*.py' . > todo_list.txt`，命令执行但无匹配（工作区无含 TODO 的 .py 文件），生成空文件。",
    # notebook.md
    "TC-NB-001": "失败。Agent 未调用任何工具，可能系统缺少 CreateNotebook 工具。",
    "TC-NB-002": "失败。Agent 调用 ReadFile + Shell，工作区中不存在 analysis.ipynb，无 Notebook 执行工具可用。",
    "TC-NB-003": "失败。Agent 调用 ReadFile 报错（analysis.ipynb 不存在），无 ExportNotebook/nbconvert 工具可用。",
    "TC-NB-004": "失败。Agent 未调用任何工具，可能系统缺少 Notebook 创建和执行工具。",
    # env-vars.md
    "TC-EV-001": "部分通过。Agent 调用 Shell `env` 命令返回环境变量列表，未使用 ListEnvironmentVariables 专用工具。",
    "TC-EV-002": "失败。Agent 未调用任何工具，未使用 SetEnvironmentVariable。",
    "TC-EV-003": "部分通过。Agent 调用 Shell `echo $API_KEY` 读取变量，未使用 GetEnvironmentVariable 专用工具。",
    "TC-EV-004": "部分通过。Agent 调用 Shell `unset API_KEY` 删除变量，未使用 DeleteEnvironmentVariable 专用工具。",
    # skill-management.md
    "TC-SK-001": "通过。Agent 调用 ListSkills 成功返回当前工作区已启用 Skill 列表。",
    "TC-SK-002": "部分通过。Agent 调用 SearchStoreSkills 成功搜索到文档处理相关 Skill，但未调用 EnableSkill/InstallSkill 完成安装。",
    "TC-SK-003": "失败。因 TC-SK-002 未实际安装 Skill，Agent 无目标可读取说明文档。",
    "TC-SK-004": "失败。因 TC-SK-002 未实际安装 Skill，Agent 无目标可禁用。",
    # expert.md
    "TC-EX-001": "部分通过。Agent 调用 tool_search + ListSubagents，未调用 ListSystemExperts 专用工具。",
    "TC-EX-002": "失败。Agent 未调用任何工具，可能缺少 InstallExpert 工具。",
    "TC-EX-003": "失败。Agent 未调用任何工具，可能缺少 ConfigureExpert 工具。",
    "TC-EX-004": "失败。Agent 未调用任何工具，可能缺少 Task/Agent 调度专家的工具。",
    # mcp.md
    "TC-MC-001": "部分通过。Agent 调用 tool_search，未调用 ListMCPServers 专用工具。",
    "TC-MC-002": "部分通过。Agent 调用 tool_search，未调用 SearchMCPMarket 专用工具。",
    "TC-MC-003": "失败。Agent 未调用任何工具，可能缺少 InstallMCPServer/EnableMCPTools 工具。",
    # workspace-management.md
    "TC-WS-001": "部分通过。Agent 调用 SearchStoreSkills，未调用 CreateWorkspace/ListWorkspaceTemplates 专用工具。",
    "TC-WS-002": "部分通过。Agent 调用 Shell + ReadFile 尝试处理，未调用 ExportWorkspaceTemplate 专用工具。",
    "TC-WS-003": "失败。Agent 未调用任何工具，可能缺少 ImportWorkspaceTemplate 工具。",
    "TC-WS-004": "失败。Agent 未调用任何工具，可能缺少 SwitchWorkspace 工具。",
}


def update_file(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    original = content

    # 匹配每个用例的测试记录部分
    # 格式: **测试记录**：
    # - 未测
    pattern = r"(### TC-[A-Z]+-\d+ .*?)\n\*\*测试记录\*\*：\n- 未测"

    def replacer(m):
        header = m.group(1)
        # 提取用例编号
        match = re.search(r"TC-[A-Z]+-\d+", header)
        if not match:
            return m.group(0)
        tc_id = match.group(0)
        result = RESULTS.get(tc_id, "未测")
        return f"{header}\n**测试记录**：\n- {DATE}：{result}"

    content = re.sub(pattern, replacer, content, flags=re.DOTALL)

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        print(f"Updated: {filepath.name}")
    else:
        print(f"No changes: {filepath.name}")


if __name__ == "__main__":
    files = [
        "filesystem.md", "shell.md", "notebook.md",
        "skill-management.md", "expert.md", "mcp.md",
        "workspace-management.md", "env-vars.md",
    ]
    for fname in files:
        update_file(BASE_DIR / fname)
