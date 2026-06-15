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


@router.get("/heatmap")
async def get_token_heatmap(
    user: UserInfo = Depends(require_auth()),
    workspace_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    granularity: str = Query("day"),
):
    """返回指定时间范围内的 token 消耗日聚合数据。

    - 扫描用户所有 session 的 usage.jsonl，按天聚合 token 消耗量。
    - 支持按 workspace_id 过滤，按 from/to 限定日期范围。
    """
    if granularity not in ("day", "week", "month"):
        raise HTTPException(status_code=400, detail="granularity 只支持 day/week/month")

    user_workspaces_dir = WORKSPACE_DIR / user.user_id

    # 确定要扫描的 workspace 目录列表
    if workspace_id:
        workspace_dirs = [user_workspaces_dir / workspace_id]
        if not workspace_dirs[0].exists():
            raise HTTPException(status_code=404, detail="工作区不存在")
    else:
        if not user_workspaces_dir.exists():
            return {
                "granularity": granularity,
                "from": from_date,
                "to": to_date,
                "total_input": 0,
                "total_output": 0,
                "total_tokens": 0,
                "daily": [],
            }
        workspace_dirs = sorted(
            p for p in user_workspaces_dir.iterdir()
            if p.is_dir() and p.name != "global_workspace"
        )

    # 聚合：按天汇总 token
    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0}
    )

    for ws_dir in workspace_dirs:
        try:
            session_dirs = [p for p in ws_dir.iterdir() if p.is_dir()]
        except OSError:
            continue
        for session_dir in session_dirs:
            usage_file = session_dir / ".aiasys" / "session" / "usage.jsonl"
            if not usage_file.exists():
                continue
            try:
                # 按行流式读取，避免一次性加载大文件
                with usage_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
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
        daily_list.append({
            "date": date,
            "input": d["input"],
            "output": d["output"],
            "cache_read": d["cache_read"],
            "cache_write": d["cache_write"],
            "reasoning": d["reasoning"],
            "total": total_tokens,
        })

    total_tokens_all = total_input + total_output
    # cache 不计入 total_tokens 避免重复（cache token 已包含在 input 中）
    # 但实际上 cache_read 和 cache_write 和 input 是不同语义
    # 这里 total 用 input+output+cache_read+cache_write+reasoning 求和

    return {
        "granularity": granularity,
        "from": from_date or (sorted_dates[0] if sorted_dates else None),
        "to": to_date or (sorted_dates[-1] if sorted_dates else None),
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": sum(d["total"] for d in daily_list),
        "daily": daily_list,
    }