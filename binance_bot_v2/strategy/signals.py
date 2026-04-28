"""确定性多周期信号引擎 — AI 不参与入场决策"""
from config.settings import (
    ENTRY_ROC_MIN, ENTRY_RSI_MAX, CONFIRM_ROC_MIN,
    BEAR_ROC_THRESHOLD, BEAR_COOLDOWN_SECONDS,
)
from core.logger import log

def evaluate_entry(primary: dict, confirm: dict) -> tuple[bool, str]:
    """
    双周期入场信号。
    primary:   1h 指标
    confirm:   15min 指标
    返回 (should_enter, reason)
    """
    checks = []

    # T1: 1h 方向
    t1_roc = primary['ROC_9'] > ENTRY_ROC_MIN
    checks.append((t1_roc, f"1h ROC_9={primary['ROC_9']:.2f} > {ENTRY_ROC_MIN}"))

    t1_rsi = primary['RSI_14'] < ENTRY_RSI_MAX
    checks.append((t1_rsi, f"1h RSI={primary['RSI_14']:.1f} < {ENTRY_RSI_MAX}"))

    t1_ema = primary['close'] > primary['EMA_50']
    checks.append((t1_ema, f"1h close={primary['close']:.2f} > EMA50={primary['EMA_50']:.2f}"))

    # T2: 15min 确认
    t2_roc = confirm['ROC_9'] > CONFIRM_ROC_MIN
    checks.append((t2_roc, f"15m ROC_9={confirm['ROC_9']:.2f} > {CONFIRM_ROC_MIN}"))

    t2_ema = confirm['close'] > confirm['EMA_50']
    checks.append((t2_ema, f"15m close={confirm['close']:.2f} > EMA50={confirm['EMA_50']:.2f}"))

    all_pass = all(c[0] for c in checks)
    failed = [c[1] for c in checks if not c[0]]
    reason = " + ".join([c[1].split(" ")[0][:2] + "✓" if c[0] else c[1] for c in checks])

    if all_pass:
        return True, f"全信号通过 | 1h ROC={primary['ROC_9']:.2f} RSI={primary['RSI_14']:.1f}"
    return False, f"未通过: {', '.join(failed)}" if failed else "信号不足"


def select_best_symbol(signals_map: dict) -> str | None:
    """
    从多个满足入场条件的标的中选出 ROC_9(1h) 最高者。
    signals_map: {symbol: {'primary': dict, 'confirm': dict, 'pass': bool}}
    返回 symbol 或 None
    """
    best = None
    best_roc = ENTRY_ROC_MIN
    for sym, data in signals_map.items():
        if data['pass']:
            roc = data['primary']['ROC_9']
            if roc > best_roc:
                best_roc = roc
                best = sym
    return best


def check_bear_market(primary: dict) -> tuple[bool, str]:
    """下跌趋势检测：不做空但须空仓防守"""
    roc = primary['ROC_9']
    close = primary['close']
    ema = primary['EMA_50']

    if roc < BEAR_ROC_THRESHOLD and close < ema:
        return True, f"下跌趋势 | ROC_9={roc:.2f} < {BEAR_ROC_THRESHOLD} & close < EMA50"
    return False, ""