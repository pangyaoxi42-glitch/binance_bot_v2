"""ATR 动态追踪止损 + 固定止损 + 分批/终极止盈"""
from config.settings import (
    SL_ATR_MULTIPLIER, TP_ATR_MULTIPLIER, PARTIAL_TP_MULTIPLIER,
    TRAILING_ATR_MULTIPLIER,
)
from core.logger import log

class TrailingStopEngine:
    def __init__(self, entry_price: float, atr: float, has_partial_tp: bool = False,
                 highest_price: float = None):
        self.entry_price = entry_price
        self.hard_sl = entry_price - atr * SL_ATR_MULTIPLIER
        self.tp_final = entry_price + atr * TP_ATR_MULTIPLIER
        self.tp_partial = entry_price + atr * PARTIAL_TP_MULTIPLIER
        self.has_partial_tp = has_partial_tp
        # 水合: 恢复历史最高价，避免重启后追踪止损线掉回初始位
        self.highest_price = highest_price if highest_price is not None else entry_price
        self.trailing_sl = max(self.hard_sl,
            self.highest_price - atr * TRAILING_ATR_MULTIPLIER) if highest_price is not None else self.hard_sl

    def update(self, current_price: float) -> str:
        """
        每 tick 更新追踪止损并返回决策信号。
        返回: 'SL' | 'TP_FINAL' | 'TP_PARTIAL' | 'HOLD'
        """
        self.highest_price = max(self.highest_price, current_price)
        # 追踪线：最高价 - ATR * 2.0，只上移不下移
        atr = (self.entry_price - self.hard_sl) / SL_ATR_MULTIPLIER
        candidate_trail = self.highest_price - atr * TRAILING_ATR_MULTIPLIER
        # 只上移不下移
        self.trailing_sl = max(self.trailing_sl, candidate_trail)

        # 优先级 1: 硬止损（永不移动）
        if current_price <= self.hard_sl:
            log.bind(tag="RISK").info(f"硬止损触发 | 现价 {current_price:.2f} ≤ {self.hard_sl:.2f}")
            return 'SL'

        # 优先级 2: 追踪止损
        if current_price <= self.trailing_sl:
            log.bind(tag="RISK").info(f"追踪止损触发 | 现价 {current_price:.2f} ≤ {self.trailing_sl:.2f}")
            return 'SL'

        # 优先级 3: 分批止盈
        if not self.has_partial_tp and current_price >= self.tp_partial:
            log.bind(tag="RISK").info(f"分批止盈触发 | 现价 {current_price:.2f} ≥ {self.tp_partial:.2f}")
            return 'TP_PARTIAL'

        # 优先级 4: 终极止盈
        if current_price >= self.tp_final:
            log.bind(tag="RISK").info(f"终极止盈触发 | 现价 {current_price:.2f} ≥ {self.tp_final:.2f}")
            return 'TP_FINAL'

        return 'HOLD'

    def mark_partial_tp(self):
        self.has_partial_tp = True
        self.trailing_sl = self.entry_price * 0.998
        log.bind(tag="RISK").info(f"分批止盈已执行，保本追踪线: {self.trailing_sl:.2f}")