from __future__ import annotations

import re
from typing import Iterable

from app.models.session import ExecutionReplayRisk, ExecutionRiskLevel


class ReplayRiskRule:
    def __init__(
        self,
        *,
        level: ExecutionRiskLevel,
        tag: str,
        reason: str,
        patterns: Iterable[str],
    ) -> None:
        self.level = level
        self.tag = tag
        self.reason = reason
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    def matches(self, code: str) -> bool:
        return any(pattern.search(code) for pattern in self.patterns)


RISK_PRIORITY: dict[ExecutionRiskLevel, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


REPLAY_RISK_RULES: list[ReplayRiskRule] = [
    ReplayRiskRule(
        level="high",
        tag="network_write",
        reason="可能调用外部写接口或删除接口",
        patterns=[
            r"\brequests\.(post|put|patch|delete)\s*\(",
            r"\bhttpx\.(post|put|patch|delete)\s*\(",
            r"\baiohttp\.clientsession\(\).*?\.(post|put|patch|delete)\s*\(",
        ],
    ),
    ReplayRiskRule(
        level="high",
        tag="database_write",
        reason="可能写入或修改数据库",
        patterns=[
            r"\.to_sql\s*\(",
            r"\b(insert\s+into|update\s+\w+|delete\s+from|drop\s+table|alter\s+table|create\s+table)\b",
        ],
    ),
    ReplayRiskRule(
        level="high",
        tag="subprocess",
        reason="可能执行外部命令或系统脚本",
        patterns=[
            r"\bsubprocess\.(run|Popen|call|check_call|check_output)\s*\(",
            r"\bos\.system\s*\(",
            r"(^|\n)\s*![a-z0-9_\-]+",
        ],
    ),
    ReplayRiskRule(
        level="high",
        tag="package_install",
        reason="可能安装、升级或删除依赖",
        patterns=[
            r"\b(pip|uv|npm|pnpm|yarn|apt-get|conda)\s+(install|add|remove|uninstall|upgrade)\b",
        ],
    ),
    ReplayRiskRule(
        level="high",
        tag="destructive_fs",
        reason="可能删除、移动或重命名文件",
        patterns=[
            r"\b(os\.(remove|unlink|rename)|shutil\.(move|rmtree)|Path\([^)]*\)\.unlink)\s*\(",
        ],
    ),
    ReplayRiskRule(
        level="medium",
        tag="file_write",
        reason="可能写入或覆盖本地文件",
        patterns=[
            r"\bopen\s*\([^,\n]+,\s*[\"'](?:w|a|x|wb|ab|xb|w\+|a\+|x\+)[\"']",
            r"\b(write_text|write_bytes|touch)\s*\(",
            r"\.(to_csv|to_json|to_excel|to_parquet|to_pickle|savefig|dump)\s*\(",
        ],
    ),
    ReplayRiskRule(
        level="medium",
        tag="directory_create",
        reason="可能创建目录或初始化本地结构",
        patterns=[
            r"\b(os\.makedirs|Path\([^)]*\)\.mkdir)\s*\(",
        ],
    ),
]


def derive_execution_replay_risk(code: str) -> ExecutionReplayRisk:
    normalized_code = (code or "").strip()
    if not normalized_code:
        return ExecutionReplayRisk()

    matched_tags: list[str] = []
    matched_reasons: list[str] = []
    level: ExecutionRiskLevel = "low"

    for rule in REPLAY_RISK_RULES:
        if not rule.matches(normalized_code):
            continue
        matched_tags.append(rule.tag)
        matched_reasons.append(rule.reason)
        if RISK_PRIORITY[rule.level] > RISK_PRIORITY[level]:
            level = rule.level

    deduped_tags = list(dict.fromkeys(matched_tags))
    deduped_reasons = list(dict.fromkeys(matched_reasons))
    return ExecutionReplayRisk(
        level=level,
        tags=deduped_tags,
        reasons=deduped_reasons,
        has_side_effect_risk=bool(deduped_tags),
    )
