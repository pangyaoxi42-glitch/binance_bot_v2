from config.settings import MAX_RISK_PER_TRADE, SL_ATR_MULTIPLIER, TP_ATR_MULTIPLIER

def get_detailed_kelly_size(win_rate_p: float, total_capital: float, atr: float, price: float) -> dict:
    """
    计算详细的凯利仓位，并返回所有计算细节用于日志输出
    """
    # 1. 计算赔率 b (盈亏比)
    b = TP_ATR_MULTIPLIER / SL_ATR_MULTIPLIER 
    q = 1.0 - win_rate_p
    
    # 2. 全凯利公式: f* = p - (q / b)
    f_star = win_rate_p - (q / b)
    
    # 3. 采用半凯利策略 (Fractional Kelly)
    f_half = max(0, f_star / 2.0)
    final_risk_ratio = min(f_half, MAX_RISK_PER_TRADE)
    
    # 4. 根据止损距离反推名义下单金额
    sl_dist = atr * SL_ATR_MULTIPLIER
    sl_pct = sl_dist / price if price > 0 else 0
    position_usd = (total_capital * final_risk_ratio) / sl_pct if sl_pct > 0 else 0

    # 🛡️ 现货防爆仓补丁：硬性拦截！不管公式算出来多少，绝对不能超过手头的总本金（禁止杠杆）
    position_usd = min(position_usd, total_capital)

    return {
        "b": round(b, 2),
        "f_star": round(f_star, 4),
        "risk_pct": f"{final_risk_ratio:.2%}",
        "position_usd": round(position_usd, 2)
    }

def calculate_fractional_kelly_position(win_rate_p, total_capital, atr, price):
    res = get_detailed_kelly_size(win_rate_p, total_capital, atr, price)
    return res["position_usd"]