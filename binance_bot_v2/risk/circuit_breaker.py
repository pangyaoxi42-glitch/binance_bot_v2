"""熔断机制 — 日亏损上限 + 连续亏损保护"""
import time
from config.settings import (
    DAILY_LOSS_CAP, MAX_CONSECUTIVE_LOSSES, CIRCUIT_BREAKER_COOLDOWN,
    INITIAL_CAPITAL,
)
from core.database import count_consecutive_losses
from core.logger import log

class CircuitBreaker:
    def __init__(self):
        self.daily_start_equity = None
        self.daily_date = None
        self.tripped_until = 0

    def update_day(self, current_equity: float):
        today = time.strftime('%Y-%m-%d')
        if self.daily_date != today:
            self.daily_date = today
            self.daily_start_equity = current_equity

    async def check(self, current_equity: float) -> tuple[bool, str]:
        """
        返回 (is_tripped, reason)
        """
        now = time.time()
        if now < self.tripped_until:
            remain = int(self.tripped_until - now)
            return True, f"熔断冷却中，剩余 {remain}s"

        today = time.strftime('%Y-%m-%d')
        if self.daily_date == today and self.daily_start_equity:
            daily_loss = (current_equity / self.daily_start_equity) - 1
            if daily_loss < -DAILY_LOSS_CAP:
                self.tripped_until = now + CIRCUIT_BREAKER_COOLDOWN
                msg = f"日亏损 {daily_loss:.2%} 超过 {DAILY_LOSS_CAP:.0%} 上限，熔断 {CIRCUIT_BREAKER_COOLDOWN // 3600}h"
                log.bind(tag="RISK").error(msg)
                return True, msg

        consec = await count_consecutive_losses()
        if consec >= MAX_CONSECUTIVE_LOSSES:
            self.tripped_until = now + CIRCUIT_BREAKER_COOLDOWN
            msg = f"连续亏损 {consec} 笔 ≥ {MAX_CONSECUTIVE_LOSSES}，熔断 {CIRCUIT_BREAKER_COOLDOWN // 3600}h"
            log.bind(tag="RISK").error(msg)
            return True, msg

        return False, ""