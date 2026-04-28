"""动态 Kelly 仓位管理 + 冷启动保护"""
from config.settings import (
    MAX_RISK_PER_TRADE, MAX_POSITION_RATIO, SL_ATR_MULTIPLIER,
    PARTIAL_TP_MULTIPLIER, PARTIAL_TP_RATIO, TP_ATR_MULTIPLIER,
    KELLY_COLD_START_MIN_TRADES, KELLY_COLD_START_RISK, KELLY_WINDOW,
    FEE_ROUNDTRIP,
)
from core.database import count_closed_trades, get_recent_closed_trades
from core.logger import log

def _calc_weighted_b() -> float:
    weighted_tp = PARTIAL_TP_RATIO * PARTIAL_TP_MULTIPLIER + (1 - PARTIAL_TP_RATIO) * TP_ATR_MULTIPLIER
    return (weighted_tp - FEE_ROUNDTRIP) / (SL_ATR_MULTIPLIER + FEE_ROUNDTRIP)


async def get_dynamic_kelly(total_capital: float, atr: float, price: float) -> dict:
    """
    从数据库统计真实胜率 → Kelly 公式 → 仓位金额。
    冷启动：平仓单 < 20 笔 → 固定 1% 风险。
    """
    closed_count = await count_closed_trades()

    if closed_count < KELLY_COLD_START_MIN_TRADES:
        risk_ratio = KELLY_COLD_START_RISK
        win_rate_p = 0.50
        source = "冷启动"
    else:
        recent = await get_recent_closed_trades(KELLY_WINDOW)
        wins = sum(1 for t in recent if (t['net_pnl'] or 0) > 0)
        win_rate_p = wins / len(recent) if recent else 0.50
        b = _calc_weighted_b()
        q = 1.0 - win_rate_p
        f_star = win_rate_p - (q / b) if b > 0 else 0
        f_half = max(0, f_star / 2.0)
        risk_ratio = min(f_half, MAX_RISK_PER_TRADE)
        source = f"动态Kelly(n={len(recent)}, w={wins}/{len(recent)})"

    sl_pct = (atr * SL_ATR_MULTIPLIER) / price if price > 0 else 0
    position_usd = (total_capital * risk_ratio) / sl_pct if sl_pct > 0 else 0
    position_usd = min(position_usd, total_capital * MAX_POSITION_RATIO)

    return {
        "win_rate": round(win_rate_p, 4),
        "risk_ratio": f"{risk_ratio:.2%}",
        "position_usd": round(position_usd, 2),
        "closed_trades": closed_count,
        "source": source,
    }