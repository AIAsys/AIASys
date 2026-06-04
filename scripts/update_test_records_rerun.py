#!/usr/bin/env python3
"""追加第二轮重测结果到测试记录"""

import re
from pathlib import Path

BASE_DIR = Path("/home/ke/projects/AIASys/design-draft/agent-test-cases/references")
DATE = "2026-06-02"

# 追加的测试结果（基于重测）
RERUN_RESULTS = {
    "TC-FS-001": f"{DATE} rerun：部分通过。Agent 调用 Shell `cat` 读取文件，未使用 ReadFile。系统提示词优化未引导 Agent 选择专用工具。",
    "TC-FS-003": f"{DATE} rerun：通过。StrReplaceFile 修复生效，edit 参数 JSON 字符串被 model_validator 正确解析，成功替换 config.txt 内容。",
    "TC-EV-002": f"{DATE} rerun：通过。Agent 调用 SetEnvVar 设置 API_KEY，专用工具替代 Shell export。工具描述优化生效。",
    "TC-EV-003": f"{DATE} rerun：通过。Agent 调用 GetEnvVar 读取 API_KEY，专用工具替代 Shell echo。",
    "TC-EV-004": f"{DATE} rerun：通过。Agent 调用 DeleteEnvVar 删除 API_KEY，并用 ListEnvVars 验证删除成功。",
    "TC-SK-001": f"{DATE} rerun：通过。Agent 调用 ListSkills 成功返回已启用 Skill 列表。",
    "TC-SK-002": f"{DATE} rerun：部分通过。Agent 调用 SearchStoreSkills 5 次搜索到文档处理 Skill，但未调用 EnableSkill 安装。",
    "TC-SK-003": f"{DATE} rerun：失败。Agent 调用 SearchStoreSkills 而非 ReadSkill，因 SK-002 未实际安装 Skill。",
    "TC-SK-004": f"{DATE} rerun：失败。Agent 未调用任何工具，因 SK-002 未实际安装 Skill。",
    "TC-NB-001": f"{DATE} rerun：失败。Agent 调用 WriteFile 直接写 .ipynb JSON，未调用 ManageNotebook(create)。",
    "TC-NB-002": f"{DATE} rerun：部分通过。Agent 首次调用 ManageNotebook，第一次参数错误（action='execute'→已修复别名），第二次 action='run' 成功解析。但底层 notebook 执行返回 'cannot unpack non-iterable coroutine object' 错误。最终 Agent 用 Shell 计算结果 3628800。",
    "TC-NB-003": f"{DATE} rerun：失败。Agent 调用 Shell + ReadFile + WriteFile 导出 .py，未调用 ManageNotebook。",
    "TC-NB-004": f"{DATE} rerun：失败。Agent 调用 WriteFile + Shell + RunCode，未调用 ManageNotebook。",
}


def update_file(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    original = content

    pattern = r"(### TC-[A-Z]+-\d+ .*?)\n\*\*测试记录\*\*：\n(.+?)(?=\n---|\Z)"

    def replacer(m):
        header = m.group(1)
        existing = m.group(2).strip()
        match = re.search(r"TC-[A-Z]+-\d+", header)
        if not match:
            return m.group(0)
        tc_id = match.group(0)
        result = RERUN_RESULTS.get(tc_id)
        if not result:
            return m.group(0)
        return f"{header}\n**测试记录**：\n{existing}\n- {result}\n"

    content = re.sub(pattern, replacer, content, flags=re.DOTALL)

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        print(f"Updated: {filepath.name}")
    else:
        print(f"No changes: {filepath.name}")


if __name__ == "__main__":
    files = [
        "filesystem.md", "notebook.md", "skill-management.md", "env-vars.md",
    ]
    for fname in files:
        update_file(BASE_DIR / fname)
