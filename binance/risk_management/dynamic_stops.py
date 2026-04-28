from core.logger import logger

def check_and_update_stops(pos: dict, current_price: float, atr: float) -> str:
    """
    多维风控检测
    """
    if current_price <= pos['sl_price']:
        return 'SL'
    
    if current_price >= pos['tp_price']:
        return 'TP_FINAL'
    
    # ⚙️ 统一风控基准：直接读取状态机里写死的分批止盈位
    if not pos.get('has_partial_tp', False):
        if current_price >= pos.get('partial_tp_price', float('inf')):
            return 'TP_PARTIAL'
            
    return 'HOLD'

def apply_partial_tp_state(pos: dict, current_price: float) -> dict:
    pos['has_partial_tp'] = True
    pos['sl_price'] = pos['entry_price'] 
    logger.info(f"🛡️  分批止盈完成，止损已移动至保本价: ${pos['sl_price']:.2f}")
    return pos