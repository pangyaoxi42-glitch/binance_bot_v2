"""核心指标计算：夏普比率、最大回撤、盈亏比、胜率"""
import math
import numpy as np

SECONDS_PER_YEAR = 365.25 * 24 * 3600

def _derive_annual_factor(snapshots: list) -> float:
    """从快照时间戳推导 sqrt(periods_per_year)，缺失时间戳时回退到 sqrt(365)"""
    try:
        timestamps = [s.get('timestamp') for s in snapshots if s.get('timestamp')]
        if len(timestamps) >= 2:
            avg_interval = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
            if avg_interval > 0:
                periods_per_year = SECONDS_PER_YEAR / avg_interval
                return math.sqrt(periods_per_year)
    except Exception:
        pass
    return math.sqrt(365)

def compute_metrics(closed_trades: list, snapshots: list = None) -> dict:
    """
    closed_trades: status='CLOSED' 的交易列表 (dict with net_pnl, net_pnl_pct)
    snapshots: 按时间排序的资产快照列表 (dict with total_equity)
    """
    result = {
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "profit_factor": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "total_net_pnl": 0.0,
    }
    if not closed_trades:
        return result

    pnl_list = [t['net_pnl'] for t in closed_trades if t['net_pnl'] is not None]
    pnl_pct_list = [t['net_pnl_pct'] for t in closed_trades if t['net_pnl_pct'] is not None]

    result["total_trades"] = len(pnl_list)
    result["total_net_pnl"] = sum(pnl_list)

    wins = sum(1 for p in pnl_list if p > 0)
    result["win_rate"] = wins / len(pnl_list) if pnl_list else 0.0

    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    result["profit_factor"] = gross_profit / gross_loss if gross_loss > 0 else 0.0

    if snapshots and len(snapshots) >= 2:
        equities = [s['total_equity'] for s in snapshots]
        returns = [(equities[i] / equities[i - 1] - 1) for i in range(1, len(equities))]
        if returns:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns, ddof=0)
            # 动态推导年化乘数，避免 instant/daily 混用时失真
            annual_factor = _derive_annual_factor(snapshots)
            result["sharpe_ratio"] = (mean_ret / std_ret * annual_factor) if std_ret > 0 else 0.0

            peak = equities[0]
            mdd = 0.0
            for eq in equities:
                peak = max(peak, eq)
                dd = (peak - eq) / peak if peak > 0 else 0
                mdd = max(mdd, dd)
            result["max_drawdown"] = mdd
    elif pnl_pct_list:
        cumulative = 1.0
        peak = 1.0
        mdd = 0.0
        for r in pnl_pct_list:
            cumulative *= (1 + r)
            peak = max(peak, cumulative)
            mdd = max(mdd, (peak - cumulative) / peak)
        result["max_drawdown"] = mdd

    return result