"""资产快照 — 定时采集 + 例行指标写入"""
import time
import json
from collections import deque
from core.database import (
    insert_snapshot, get_snapshots, get_recent_closed_trades,
    count_consecutive_losses,
)
from analytics.metrics import compute_metrics
from core.logger import log

_SNAPSHOT_DAYS = 90  # 回看天数用于 Sharpe/MDD 计算
_INSTANT_BUFFER = deque(maxlen=1440)  # 内存中保留最近 1440 条 (24h @ 60s)

# 线程安全的最新快照，供 circuit_breaker 等模块读取
_latest_equity = {"total_equity": 0.0, "free_usdt": 0.0, "positions": {}}


def get_latest_in_memory_snapshot() -> dict:
    return dict(_latest_equity)


async def capture_instant_snapshot(free_usdt: float, positions: dict, total_equity: float):
    """仅更新内存快照，不写数据库。供实时风控读取。"""
    _latest_equity["total_equity"] = total_equity
    _latest_equity["free_usdt"] = free_usdt
    _latest_equity["positions"] = positions
    _INSTANT_BUFFER.append({"ts": time.time(), "equity": total_equity})


def get_instant_equities() -> list:
    """返回内存中的 (timestamp, equity) 列表，供指标计算"""
    return list(_INSTANT_BUFFER)


async def capture_periodic_snapshot(free_usdt: float, positions: dict, total_equity: float):
    """日/周/月判断 → 写入对应周期快照（仅这三种持久化到 SQLite）"""
    now = time.time()
    now_dt = time.localtime(now)
    wday = now_dt.tm_wday
    hour = now_dt.tm_hour

    checks = [
        ("daily", True),
        ("weekly", wday == 6 and hour >= 20),
        ("monthly", now_dt.tm_mday == 1 and hour >= 4),
    ]

    for period, should in checks:
        if not should:
            continue
        last = await _get_latest_period_snapshot(period)
        if last:
            last_dt = time.localtime(last['timestamp'])
            if period == "daily" and last_dt.tm_yday == now_dt.tm_yday and last_dt.tm_year == now_dt.tm_year:
                continue
            if period == "weekly" and last_dt.tm_year == now_dt.tm_year and _week_of_year(last_dt) == _week_of_year(now_dt):
                continue
            if period == "monthly" and last_dt.tm_mon == now_dt.tm_mon and last_dt.tm_year == now_dt.tm_year:
                continue

        since = now - _SNAPSHOT_DAYS * 86400
        past = await get_snapshots("daily", since)
        closed = await get_recent_closed_trades(50)
        consec = await count_consecutive_losses()
        # 优先用 DB 日级快照计算指标，不足时回退到内存 instant 数据
        if not past or len(past) < 2:
            instant_list = list(_INSTANT_BUFFER)
            if len(instant_list) >= 2:
                past = [{"timestamp": x["ts"], "total_equity": x["equity"]} for x in instant_list]
        metrics = compute_metrics(closed, past)

        snap = {
            "timestamp": now,
            "period": period,
            "total_equity": total_equity,
            "free_usdt": free_usdt,
            "positions_json": json.dumps(positions, ensure_ascii=False),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "win_rate": metrics.get("win_rate", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "consecutive_losses": consec,
        }
        await insert_snapshot(snap)
        log.bind(tag="BALANCE").info(
            f"{period} 快照 | 净值 ${total_equity:,.0f} | "
            f"Sharpe {metrics['sharpe_ratio']:.2f} | MDD {metrics['max_drawdown']:.1%} | "
            f"胜率 {metrics['win_rate']:.1%}"
        )


async def _get_latest_period_snapshot(period: str) -> dict | None:
    from core.database import get_latest_snapshot
    return await get_latest_snapshot(period)


def _week_of_year(dt) -> int:
    return int(time.strftime('%W', time.struct_time(dt)))
