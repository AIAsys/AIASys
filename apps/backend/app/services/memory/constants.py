"""Memory 子系统常量。"""

MEMORY_DIR_NAME = ".aiasys_memory"

USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE = "user_default_global_workspace"
LEGACY_USER_DEFAULT_SCOPE = "user_default"
WORKSPACE_MEMORY_SCOPE = "workspace"


def normalize_memory_scope_key(scope_key: str | None) -> str:
    """规范化 memory scope key。"""

    normalized = str(scope_key or "").strip()
    if not normalized or normalized == LEGACY_USER_DEFAULT_SCOPE:
        return USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE
    return normalized


def is_user_default_global_workspace_scope(scope_key: str | None) -> bool:
    return normalize_memory_scope_key(scope_key) == USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE


# 容量限制（字符数，model-independent）
# 注意：以下值为系统 fallback，优先使用用户 config.toml [memory] 段配置
MAX_MEMORY_SIZE = 10000  # MEMORY.md 上限
MAX_SUMMARY_SIZE = 3000  # memory_summary.md 上限
MAX_SINGLE_ENTRY = 500  # 单条 memory 上限
MAX_WORKSPACE_MEMORY_SIZE = 5000  # workspace_memory.md 上限

# 容量告警阈值（相对于上限的百分比）
CAPACITY_WARNING_PCT = 0.80
CAPACITY_CRITICAL_PCT = 0.90
CAPACITY_HARD_LIMIT_PCT = 1.00

# Codex 风格 memory layout：
# - 用户默认全局工作区层：workspaces/<user_id>/global_workspace/.aiasys/.memory/
#   - MEMORY.md：主记忆注册表，内容是纯 Markdown 文稿
#   - memory_summary.md：轻量注入入口
#   - raw_memories.md：原始提炼结果镜像
#   - rollout_summaries/：按会话/执行归档的摘要目录
# - 工作区层：workspaces/<user_id>/<workspace_id>/.aiasys/memory/workspace_memory.md
MEMORY_FILE_NAME = "MEMORY.md"
MEMORY_SUMMARY_FILE_NAME = "memory_summary.md"
RAW_MEMORIES_FILE_NAME = "raw_memories.md"
ROLLOUT_SUMMARIES_DIR_NAME = "rollout_summaries"
CHAT_HISTORY_DB_FILE_NAME = "chat_history.db"
USER_MEMORY_STATE_DIR_RELATIVE_PATH = ".memory"
MEMORY_SNAPSHOT_MIRROR_DIR_NAME = "snapshots"

WORKSPACE_MEMORY_KEY = "workspace.memory_markdown"
