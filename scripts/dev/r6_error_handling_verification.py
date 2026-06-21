"""Verify R6 error-handling fixes and detect new issues in modified backend files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

BASE_DIR = Path("/home/ke/projects/AIASys")
R6_REPORT = BASE_DIR / "design-draft/bug-discovery/bugs/error-handling-r6-2026-06-21.md"

TARGET_ROUTES = [
    "apps/backend/app/api/routes/agent.py",
    "apps/backend/app/api/routes/file_database.py",
    "apps/backend/app/api/routes/files_core.py",
    "apps/backend/app/api/routes/llm_config.py",
    "apps/backend/app/api/routes/mcp.py",
    "apps/backend/app/api/routes/sessions_approvals.py",
    "apps/backend/app/api/routes/sessions_branches.py",
    "apps/backend/app/api/routes/sessions_execution.py",
    "apps/backend/app/api/routes/sessions_exports.py",
    "apps/backend/app/api/routes/sessions_messages.py",
    "apps/backend/app/api/routes/sessions_tools.py",
    "apps/backend/app/api/routes/skills.py",
    "apps/backend/app/api/routes/ui_settings.py",
    "apps/backend/app/api/routes/workspace_templates.py",
    "apps/backend/app/api/routes/workspaces.py",
    "apps/backend/app/api/routes/workspaces_core.py",
    "apps/backend/app/graphrag/api/routes.py",
]

TARGET_SERVICES = [
    "apps/backend/app/services/agent/runtime_backends/aiasys/tools/task_tool.py",
    "apps/backend/app/services/export/session_import_service.py",
    "apps/backend/app/services/export/workspace_import_service.py",
    "apps/backend/app/services/memory/session_db.py",
    "apps/backend/app/services/memory/state_runtime.py",
    "apps/backend/app/services/runtime_storage_settings.py",
    "apps/backend/app/services/session/core.py",
    "apps/backend/app/services/session/status.py",
    "apps/backend/app/services/mcp_external_market_service.py",
    "apps/backend/app/services/claw/adapters/feishu.py",
    "apps/backend/app/services/claw/adapters/helpers.py",
    "apps/backend/app/services/claw/adapters/utils.py",
]

# Patterns of interest
RE_EXCEPT_RAISE_HTTP = re.compile(r"except\s+\w[\w\s,()]+:\s*\n\s*raise\s+HTTPException", re.MULTILINE)
RE_RAISE_FROM_NONE = re.compile(r"raise\s+.*\s+from\s+None")
RE_EXCEPT_PASS = re.compile(r"except\s+.*:\s*\n\s*pass")
RE_CREATE_TASK_NO_CALLBACK = re.compile(r"asyncio\.create_task\([^)]+\)")


def load_report_locations(report: Path) -> set[str]:
    """Extract file:line locations from R6 report markdown table."""
    text = report.read_text(encoding="utf-8")
    locations: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 3:
            loc = parts[2]
            if loc.startswith("`") and "`" in loc[1:]:
                locations.add(loc.strip("`"))
    return locations


def iter_files(paths: Iterable[str]) -> Iterable[Path]:
    for rel in paths:
        p = BASE_DIR / rel
        if p.is_file():
            yield p


def scan_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = {
        "except_raise_http": [],
        "raise_from_none": [],
        "except_pass": [],
        "create_task_no_callback": [],
    }
    for m in RE_EXCEPT_RAISE_HTTP.finditer(text):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        snippet = text[m.start():m.start() + 200].splitlines()[0]
        findings["except_raise_http"].append((line_no, snippet.strip()))
    for m in RE_RAISE_FROM_NONE.finditer(text):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        snippet = text[m.start():m.start() + 200].splitlines()[0]
        findings["raise_from_none"].append((line_no, snippet.strip()))
    for m in RE_EXCEPT_PASS.finditer(text):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        snippet = text[m.start():m.start() + 200].splitlines()[0]
        findings["except_pass"].append((line_no, snippet.strip()))
    for m in RE_CREATE_TASK_NO_CALLBACK.finditer(text):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        snippet = text[m.start():m.start() + 200].splitlines()[0]
        findings["create_task_no_callback"].append((line_no, snippet.strip()))
    return findings


KNOWN_ACCEPTABLE_EXCEPT_PASS_PREFIXES = (
    "cleanup",
    "cancel",
    "close",
    "release",
    "shutdown",
)


def is_acceptable_except_pass(path: Path, line_no: int, snippet: str) -> bool:
    name = path.name
    lower = snippet.lower()
    if name.endswith("task_tool.py") and "cancel" in lower:
        return True
    if name == "feishu.py" and "finally" in lower:
        return True
    if name == "utils.py" and "cleanup" in lower:
        return True
    if "logger" not in lower and "shutdown" in lower:
        return True
    return False


KNOWN_ACCEPTABLE_CREATE_TASK = {
    "apps/backend/app/services/claw/adapters/feishu.py",
    "apps/backend/app/services/claw/adapters/helpers.py",
}


def main() -> None:
    r6_locations = load_report_locations(R6_REPORT)
    print("# R6 Error-handling Verification Report")
    print(f"R6 locations in report: {sorted(r6_locations)}\n")

    print("## Modified files scan")
    all_targets = list(iter_files(TARGET_ROUTES)) + list(iter_files(TARGET_SERVICES))
    new_findings = []
    for path in sorted(all_targets, key=lambda p: p.as_posix()):
        rel = path.relative_to(BASE_DIR).as_posix()
        findings = scan_file(path)
        # except ...: raise HTTPException without from
        for line_no, snippet in findings["except_raise_http"]:
            loc = f"{rel}:{line_no}"
            if loc not in r6_locations:
                # check if it already has 'from' in the same block via heuristic
                if "from" not in snippet:
                    new_findings.append(("missing_from_http", rel, line_no, snippet))
        # raise ... from None
        for line_no, snippet in findings["raise_from_none"]:
            loc = f"{rel}:{line_no}"
            if loc not in r6_locations:
                new_findings.append(("raise_from_none", rel, line_no, snippet))
        # except ...: pass
        for line_no, snippet in findings["except_pass"]:
            if is_acceptable_except_pass(path, line_no, snippet):
                continue
            new_findings.append(("except_pass", rel, line_no, snippet))
        # create_task no callback
        for line_no, snippet in findings["create_task_no_callback"]:
            if rel in KNOWN_ACCEPTABLE_CREATE_TASK:
                continue
            new_findings.append(("create_task_no_callback", rel, line_no, snippet))

    if not new_findings:
        print("No new error-handling findings detected in modified files.")
    else:
        print(f"Detected {len(new_findings)} new error-handling pattern(s):")
        for kind, rel, line_no, snippet in new_findings:
            print(f"- `{kind}` in `{rel}:{line_no}` -> `{snippet}`")

    print("\n## R6 fix verification (sample)")
    sample_checks = [
        ("apps/backend/app/api/routes/llm_config.py", [244, 340, 364, 391, 458, 496]),
        ("apps/backend/app/api/routes/sessions_branches.py", [907, 987, 1043, 1072, 1104, 1211, 1314]),
        ("apps/backend/app/api/routes/sessions_exports.py", [93, 123]),
        ("apps/backend/app/api/routes/sessions_messages.py", [90, 180, 260]),
        ("apps/backend/app/api/routes/ui_settings.py", [120, 180]),
        ("apps/backend/app/api/routes/workspaces_core.py", [80]),
    ]
    for rel, lines in sample_checks:
        p = BASE_DIR / rel
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        print(f"- {rel}:")
        for ln in lines:
            file_lines = text.splitlines()
            if ln - 1 < len(file_lines):
                line = file_lines[ln - 1]
                if "from e" in line or "from exc" in line:
                    print(f"  - line {ln}: OK (exception chained)")
                elif "raise HTTPException" in line:
                    print(f"  - line {ln}: MISSING 'from exc'")
                else:
                    print(f"  - line {ln}: (no raise)")


if __name__ == "__main__":
    main()
