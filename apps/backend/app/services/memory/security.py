"""Memory 内容安全扫描。

在 MemoryStore.write_text() 前检测威胁内容，防止 prompt injection、
credential exfiltration、invisible Unicode 等攻击。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# ---------- Invisible Unicode ----------
_INVISIBLE_UNICODE_PATTERN = re.compile(
    "[\u200b\u200c\u200d\u2060\ufeff" "\u202a\u202b\u202c\u202d\u202e]"
)

# ---------- Prompt Injection ----------
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s+you\s+are\s+(?:a|an|the)", re.IGNORECASE),
    re.compile(r"do\s+not\s+tell\s+(the\s+)?user", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"ignore\s+the\s+above", re.IGNORECASE),
    re.compile(r"new\s+instructions?:", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s+you\s+are", re.IGNORECASE),
]

# ---------- Credential Exfiltration ----------
_CREDENTIAL_EXFIL_PATTERNS = [
    re.compile(
        r"(curl|wget|fetch)\s+.*\$\{?\w*?(KEY|TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)\}?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(curl|wget|fetch)\s+.*\$\w*?(KEY|TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)",
        re.IGNORECASE,
    ),
    re.compile(
        r"cat\s+.*(\.(env|credentials|netrc|pgpass|aws|npmrc))|"
        r"cat\s+.*(id_rsa|id_ed25519|\.ssh/authorized_keys)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(echo|print|printf)\s+.*\$\{?\w*?(KEY|TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)\}?",
        re.IGNORECASE,
    ),
]

# ---------- Persistence Attacks ----------
_PERSISTENCE_PATTERNS = [
    re.compile(r"authorized_keys", re.IGNORECASE),
    re.compile(r"\.ssh/", re.IGNORECASE),
    re.compile(r"\$HOME/\.[a-zA-Z0-9_]+/\.env", re.IGNORECASE),
    re.compile(r"crontab\s+-", re.IGNORECASE),
    re.compile(r"systemctl\s+.*enable", re.IGNORECASE),
]


ThreatType = Literal[
    "invisible_unicode",
    "prompt_injection",
    "credential_exfiltration",
    "persistence_attack",
]


@dataclass(frozen=True)
class SecurityScanResult:
    """安全扫描结果。"""

    clean: bool
    threats: list[dict[str, str]]

    @property
    def blocked(self) -> bool:
        return not self.clean


def scan_memory_content(content: str) -> SecurityScanResult:
    """扫描 memory 内容，返回所有检测到的威胁。

    正常内容返回 clean=True；检测到任何威胁返回 clean=False 并附带详情。
    """
    threats: list[dict[str, str]] = []

    # 1. Invisible Unicode
    for match in _INVISIBLE_UNICODE_PATTERN.finditer(content):
        char = match.group()
        codepoint = f"U+{ord(char):04X}"
        threats.append(
            {
                "type": "invisible_unicode",
                "codepoint": codepoint,
                "position": str(match.start()),
                "snippet": _snippet(content, match.start()),
            }
        )

    # 2. Prompt Injection
    for pattern in _PROMPT_INJECTION_PATTERNS:
        for match in pattern.finditer(content):
            threats.append(
                {
                    "type": "prompt_injection",
                    "pattern": pattern.pattern[:60],
                    "matched": match.group()[:120],
                    "position": str(match.start()),
                }
            )

    # 3. Credential Exfiltration
    for pattern in _CREDENTIAL_EXFIL_PATTERNS:
        for match in pattern.finditer(content):
            threats.append(
                {
                    "type": "credential_exfiltration",
                    "pattern": pattern.pattern[:60],
                    "matched": match.group()[:120],
                    "position": str(match.start()),
                }
            )

    # 4. Persistence Attacks
    for pattern in _PERSISTENCE_PATTERNS:
        for match in pattern.finditer(content):
            threats.append(
                {
                    "type": "persistence_attack",
                    "pattern": pattern.pattern[:60],
                    "matched": match.group()[:120],
                    "position": str(match.start()),
                }
            )

    return SecurityScanResult(clean=len(threats) == 0, threats=threats)


def _snippet(content: str, position: int, radius: int = 20) -> str:
    """提取 position 附近的上下文片段。"""
    start = max(0, position - radius)
    end = min(len(content), position + radius)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet
