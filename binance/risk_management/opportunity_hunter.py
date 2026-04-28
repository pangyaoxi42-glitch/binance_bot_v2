import time
from config.settings import PRIMARY_SYMBOL, SECONDARY_SYMBOL, STALEMATE_HOURS_BTC, STALEMATE_HOURS_SOL, STALEMATE_ROI_THRESHOLD

async def check_opportunity_cost(current_symbol, entry_time, entry_price, current_price, current_roc, alt_symbol_roc):
    """
    侦测僵局并决定是否迁移资金
    返回 True 表示需要立刻平仓迁移，False 表示继续持有
    """
    hold_hours = (time.time() - entry_time) / 3600
    roi = (current_price - entry_price) / entry_price
    
    is_stalemate = False
    # 彻底解耦，引用配置表的变量
    if current_symbol == PRIMARY_SYMBOL and hold_hours >= STALEMATE_HOURS_BTC and roi < STALEMATE_ROI_THRESHOLD:
        is_stalemate = True
    elif current_symbol == SECONDARY_SYMBOL and hold_hours >= STALEMATE_HOURS_SOL and roi < STALEMATE_ROI_THRESHOLD:
        is_stalemate = True
        
    if is_stalemate:
        if alt_symbol_roc > current_roc and alt_symbol_roc > 0:
            return True 
    return False