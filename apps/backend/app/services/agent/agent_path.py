"""子 Agent 执行路径与嵌套深度控制。"""

from __future__ import annotations

from dataclasses import dataclass


def _normalize_segment(value: str) -> str:
    normalized = str(value or "").strip().strip("/")
    if not normalized:
        raise ValueError("AgentPath segment 不能为空")
    if "/" in normalized:
        raise ValueError("AgentPath segment 不能包含 /")
    return normalized


@dataclass(frozen=True)
class AgentPath:
    """表示主控到当前子 Agent 的路径。

    `/root` 表示主控，`/root/worker_x` 表示一层子 Agent。
    depth 不计 root，因此主控 depth=0。
    """

    segments: tuple[str, ...] = ("root",)

    @classmethod
    def parse(cls, value: str | None) -> "AgentPath":
        raw = str(value or "").strip()
        if not raw:
            return cls()
        segments = tuple(_normalize_segment(item) for item in raw.split("/") if item)
        if not segments:
            return cls()
        if segments[0] != "root":
            segments = ("root", *segments)
        return cls(segments=segments)

    @property
    def depth(self) -> int:
        return max(len(self.segments) - 1, 0)

    @property
    def current_agent_id(self) -> str | None:
        if self.depth <= 0:
            return None
        return self.segments[-1]

    def child(self, agent_id: str) -> "AgentPath":
        return AgentPath((*self.segments, _normalize_segment(agent_id)))

    def ensure_child_allowed(self, *, max_depth: int, child_agent_id: str) -> "AgentPath":
        next_path = self.child(child_agent_id)
        if next_path.depth > max_depth:
            raise ValueError(
                f"子 Agent 嵌套深度已超过上限: 当前={self.depth}, 目标={next_path.depth}, 上限={max_depth}"
            )
        return next_path

    def __str__(self) -> str:
        return "/" + "/".join(self.segments)


def normalize_agent_max_depth(value: object, *, default: int = 1) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 0)
