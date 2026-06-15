"""Token 用量聚合查询 API。

提供跨 session 的 token 消耗统计，用于 TokenDashboard 贡献图。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/token-usage", tags=["token-usage"])


def _is_session_dir(path: Path) -> bool:
    """判断目录是否为 session 目录：存在 metadata.json 且包含 session_id。"""
    meta_path = path / "metadata.json"
    if not meta_path.exists():
        return False
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(data.get("session_id"))
    except Exception:
        return False


def _read_usage_file(
    usage_file: Path,
    from_date: str | None,
    to_date: str | None,
    model_filter: str | None,
) -> tuple[dict[str, dict[str, int]], set[str]]:
    """读取单个 usage.jsonl 并返回按日期聚合的 token 数据以及出现的模型集合。"""
    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0}
    )
    models: set[str] = set()
    if not usage_file.exists():
        return daily, models

    try:
        with usage_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                model = record.get("model") or "unknown"
                models.add(model)

                if model_filter is not None and model != model_filter:
                    continue

                ts_str = record.get("ts", "")
                if not ts_str:
                    continue
                date = ts_str[:10]

                if from_date and date < from_date:
                    continue
                if to_date and date > to_date:
                    continue

                daily[date]["input"] += int(record.get("input", 0) or 0)
                daily[date]["output"] += int(record.get("output", 0) or 0)
                daily[date]["cache_read"] += int(record.get("cache_read", 0) or 0)
                daily[date]["cache_write"] += int(record.get("cache_write", 0) or 0)
                daily[date]["reasoning"] += int(record.get("reasoning", 0) or 0)
    except Exception:
        logger.debug("读取 usage.jsonl 失败: %s", usage_file, exc_info=True)

    return daily, models


@router.get("/heatmap")
async def get_token_heatmap(
    user: UserInfo = Depends(require_auth()),
    workspace_id: str | None = Query(None),
    model: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    granularity: str = Query("day"),
):
    """返回指定时间范围内的 token 消耗日聚合数据。

    - 扫描用户所有 session 的 usage.jsonl，按天聚合 token 消耗量。
    - 支持按 workspace_id、model 过滤，按 from/to 限定日期范围。
    """
    if granularity not in ("day", "week", "month"):
        raise HTTPException(status_code=400, detail="granularity 只支持 day/week/month")

    user_dir = WORKSPACE_DIR / user.user_id
    if not user_dir.exists():
        return {
            "granularity": granularity,
            "from": from_date,
            "to": to_date,
            "total_input": 0,
            "total_output": 0,
            "total_tokens": 0,
            "models": [],
            "daily": [],
        }

    # 聚合：按天汇总 token
    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0}
    )
    all_models: set[str] = set()

    try:
        candidates = [p for p in user_dir.iterdir() if p.is_dir() and p.name != "global_workspace"]
    except OSError:
        candidates = []

    def _collect_session(session_dir: Path) -> None:
        file_daily, file_models = _read_usage_file(
            session_dir / ".aiasys" / "session" / "usage.jsonl",
            from_date,
            to_date,
            model,
        )
        all_models.update(file_models)
        for date, values in file_daily.items():
            for key, value in values.items():
                daily[date][key] += value

    for candidate in candidates:
        # 直接位于 user_dir 下的 session 目录
        if _is_session_dir(candidate):
            if workspace_id is not None:
                try:
                    meta = json.loads((candidate / "metadata.json").read_text(encoding="utf-8"))
                    if meta.get("workspace_id") != workspace_id:
                        continue
                except Exception:
                    continue
            _collect_session(candidate)
            continue

        # 也可能是工作区目录，再扫描其下的 session 子目录
        try:
            sub_dirs = [p for p in candidate.iterdir() if p.is_dir()]
        except OSError:
            continue
        for session_dir in sub_dirs:
            if not _is_session_dir(session_dir):
                continue
            if workspace_id is not None:
                try:
                    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
                    if meta.get("workspace_id") != workspace_id:
                        continue
                except Exception:
                    continue
            _collect_session(session_dir)

    # 按日期排序
    sorted_dates = sorted(daily.keys())

    total_input = 0
    total_output = 0
    daily_list = []
    for date in sorted_dates:
        d = daily[date]
        total_tokens = (
            d["input"] + d["output"] + d["cache_read"] + d["cache_write"] + d["reasoning"]
        )
        total_input += d["input"]
        total_output += d["output"]
        daily_list.append(
            {
                "date": date,
                "input": d["input"],
                "output": d["output"],
                "cache_read": d["cache_read"],
                "cache_write": d["cache_write"],
                "reasoning": d["reasoning"],
                "total": total_tokens,
            }
        )

    return {
        "granularity": granularity,
        "from": from_date or (sorted_dates[0] if sorted_dates else None),
        "to": to_date or (sorted_dates[-1] if sorted_dates else None),
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": sum(d["total"] for d in daily_list),
        "models": sorted(all_models),
        "daily": daily_list,
    }
