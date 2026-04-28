"""Binance Bot V2 — 机构级测试网自动交易系统"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import time

from config.settings import (
    SYMBOLS, TIMEFRAME_PRIMARY, TIMEFRAME_CONFIRM,
    MAIN_LOOP_SLEEP, HOLDING_SLEEP,
    SWITCH_COOLDOWN_HOURS, BEAR_COOLDOWN_SECONDS,
    AI_GUARD_INTERVAL, AI_GUARD_VETO_THRESHOLD, AI_GUARD_TIMEOUT,
    MIN_ROC_ADVANTAGE, STALEMATE_HOURS, STALEMATE_ROI_THRESHOLD,
)
from core.logger import log
from core.exchange import BinanceClient
from core.database import (
    get_db, close_db, get_open_trades, insert_trade, update_trade_exit,
    update_trade_partial, update_trade_highest_price,
)
from strategy.indicators import calculate_signals
from strategy.signals import evaluate_entry, select_best_symbol, check_bear_market
from strategy.deepseek_guard import check_anomaly, close_guard
from execution.order_manager import OrderManager
from execution.position_sizer import get_dynamic_kelly
from risk.trailing_stops import TrailingStopEngine
from risk.circuit_breaker import CircuitBreaker
from analytics.snapshots import capture_instant_snapshot, capture_periodic_snapshot


async def hydrate_state() -> list[dict]:
    """状态水合：恢复所有未平仓订单到内存"""
    open_trades = await get_open_trades()
    if open_trades:
        log.bind(tag="STRATEGY").info(f"状态水合: 恢复 {len(open_trades)} 笔未平仓订单")
        for t in open_trades:
            log.bind(tag="STRATEGY").info(
                f"  {t['symbol']} | 入场 ${t['entry_price']:.2f} | "
                f"数量 {t['entry_amount']:.6f} | 状态 {t['status']}"
            )
    return open_trades


async def run_sniper():
    await get_db()
    client = BinanceClient()
    order_exec = OrderManager(client)
    breaker = CircuitBreaker()
    last_guard_time = 0
    last_switch_time = 0
    total_equity = 0.0

    # 水合
    open_positions = await hydrate_state()
    position = open_positions[0] if open_positions else None
    trailing_engine = None
    _last_known_prices = {}  # 防止单次 OHLCV 失败导致 phantom 熔断

    log.bind(tag="STRATEGY").info("V2 深空狙击手已点火 — 多周期确定性信号 + AI守门人")

    try:
        while True:
            now = time.time()

            # ═══ 熔断检查 ═══
            tripped, reason = await breaker.check(total_equity)
            if tripped:
                log.bind(tag="RISK").warning(f"熔断激活: {reason}")
                await asyncio.sleep(300)
                continue

            # ═══ 数据采集 (1h + 15min + balance 并发) ═══
            try:
                tasks = [client.fetch_ohlcv_safe(s, TIMEFRAME_PRIMARY) for s in SYMBOLS] + \
                        [client.fetch_ohlcv_safe(s, TIMEFRAME_CONFIRM) for s in SYMBOLS] + \
                        [client.fetch_balance_safe()]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                balance = results[6]
                if isinstance(balance, Exception):
                    log.bind(tag="STRATEGY").error(f"余额获取失败: {balance}")
                    await asyncio.sleep(30)
                    continue

                # 按 symbol 细粒度处理：仅跳过失败的 symbol
                primary_ohlcv = {}
                confirm_ohlcv = {}
                failed = []
                for i, sym in enumerate(SYMBOLS):
                    p = results[i]
                    c = results[i + 3]
                    if isinstance(p, Exception):
                        failed.append(f"{sym}/1h")
                        log.bind(tag="STRATEGY").warning(f"{sym} 1h K线获取失败: {p}")
                    else:
                        primary_ohlcv[sym] = p
                    if isinstance(c, Exception):
                        failed.append(f"{sym}/15m")
                        log.bind(tag="STRATEGY").warning(f"{sym} 15m K线获取失败: {c}")
                    else:
                        confirm_ohlcv[sym] = c

                if not primary_ohlcv:
                    log.bind(tag="STRATEGY").error("全部 symbol OHLCV 获取失败")
                    await asyncio.sleep(30)
                    continue

            except Exception as e:
                log.bind(tag="STRATEGY").error(f"数据采集异常: {e}")
                await asyncio.sleep(30)
                continue

            # ═══ 指标计算 ═══
            primary_signals = {}
            confirm_signals = {}
            for sym in primary_ohlcv:
                try:
                    primary_signals[sym] = calculate_signals(primary_ohlcv[sym])
                except ValueError as e:
                    log.bind(tag="STRATEGY").warning(f"{sym} 1h 指标异常: {e}")
            for sym in confirm_ohlcv:
                try:
                    confirm_signals[sym] = calculate_signals(confirm_ohlcv[sym])
                except ValueError as e:
                    log.bind(tag="STRATEGY").warning(f"{sym} 15m 指标异常: {e}")

            # 更新价格缓存，防止单次失败导致幽灵熔断
            for sym in primary_signals:
                _last_known_prices[sym] = primary_signals[sym]['close']

            # ═══ 资产概览 ═══
            free_usdt = balance['free'].get('USDT', 0)
            positions_holdings = {}
            total_equity = free_usdt

            for sym in SYMBOLS:
                base = sym.split('/')[0]
                amt = balance['total'].get(base, 0)
                px = primary_signals[sym]['close'] if sym in primary_signals else _last_known_prices.get(sym, 0)
                val = amt * px
                total_equity += val
                if amt > 0:
                    positions_holdings[sym] = {"amount": amt, "value_usd": val}

            breaker.update_day(total_equity)

            # ═══ 快照 ═══
            await capture_instant_snapshot(free_usdt, positions_holdings, total_equity)
            await capture_periodic_snapshot(free_usdt, positions_holdings, total_equity)

            # ═══ 持仓监控 ═══
            if position:
                sym = position['symbol']
                if sym not in primary_signals:
                    await asyncio.sleep(HOLDING_SLEEP)
                    continue

                px_1h = primary_signals[sym]
                ticker = await client.fetch_ticker_safe(sym)
                live_price = ticker['last']
                pnl_pct = (live_price / position['entry_price']) - 1

                # 重建追踪引擎（水合后第一次，恢复已锁定的最高价）
                if trailing_engine is None:
                    restored_highest = position.get('highest_price')
                    trailing_engine = TrailingStopEngine(
                        position['entry_price'], px_1h['ATRr_14'],
                        has_partial_tp=(position.get('status') == 'PARTIAL'),
                        highest_price=restored_highest,
                    )
                    if restored_highest:
                        log.bind(tag="STRATEGY").info(
                            f"水合追踪止损 | 历史最高价 ${restored_highest:.2f} | "
                            f"追踪SL ${trailing_engine.trailing_sl:.2f}"
                        )

                # 风控判断
                old_highest = trailing_engine.highest_price
                decision = trailing_engine.update(live_price)
                # 仅在创新高时持久化，避免每 30s 冗余写库
                if trailing_engine.highest_price > old_highest:
                    await update_trade_highest_price(position['id'], trailing_engine.highest_price)

                if decision == 'SL':
                    result = await order_exec.execute_exit(sym, position['entry_amount'], live_price)
                    if result:
                        net_pnl = _calc_net_pnl(position, result, 'SHORT')
                        await update_trade_exit(position['id'], {
                            'exit_time': now, 'exit_price': result['fill_price'],
                            'exit_amount': result['amount'], 'exit_fee': result['fee'],
                            'exit_fee_asset': result['fee_asset'], 'exit_reason': 'SL',
                            'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                        })
                        log.bind(tag="BALANCE").info(
                            f"止损出场 {sym} | PnL ${net_pnl['usdt']:+.2f} ({net_pnl['pct']:+.2%})"
                        )
                    position = None
                    trailing_engine = None
                    continue

                elif decision == 'TP_FINAL':
                    result = await order_exec.execute_exit(sym, position['entry_amount'], live_price)
                    if result:
                        net_pnl = _calc_net_pnl(position, result, 'SHORT')
                        await update_trade_exit(position['id'], {
                            'exit_time': now, 'exit_price': result['fill_price'],
                            'exit_amount': result['amount'], 'exit_fee': result['fee'],
                            'exit_fee_asset': result['fee_asset'], 'exit_reason': 'TP_FINAL',
                            'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                        })
                        log.bind(tag="BALANCE").info(
                            f"终极止盈 {sym} | PnL ${net_pnl['usdt']:+.2f} ({net_pnl['pct']:+.2%})"
                        )
                    position = None
                    trailing_engine = None
                    continue

                elif decision == 'TP_PARTIAL':
                    result = await order_exec.execute_exit(sym, position['entry_amount'], live_price, is_partial=True)
                    if result:
                        net_pnl = _calc_net_pnl(position, result, 'PARTIAL')
                        await update_trade_partial(position['id'], {
                            'exit_time': now, 'exit_price': result['fill_price'],
                            'exit_amount': result['amount'], 'exit_fee': result['fee'],
                            'exit_fee_asset': result['fee_asset'], 'exit_reason': 'TP_PARTIAL',
                            'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                            'notes': '50%止盈,止损已移至保本线',
                        })
                        position['entry_amount'] -= result['amount']
                        position['status'] = 'PARTIAL'
                        trailing_engine.mark_partial_tp()
                        log.bind(tag="BALANCE").info(
                            f"分批止盈 {sym} | PnL ${net_pnl['usdt']:+.2f} | 剩余 {position['entry_amount']:.6f}"
                        )
                    continue

                # AI 守门人
                if now - last_guard_time >= AI_GUARD_INTERVAL:
                    last_guard_time = now
                    guard_task = asyncio.create_task(
                        check_anomaly(sym, px_1h, pnl_pct)
                    )
                    try:
                        guard = await asyncio.wait_for(guard_task, timeout=AI_GUARD_TIMEOUT)
                    except asyncio.TimeoutError:
                        guard_task.cancel()
                        try:
                            await guard_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        guard = {"anomaly": False, "p": 0.5, "reason": "超时"}
                    if guard['anomaly']:
                        log.bind(tag="RISK").warning(f"AI守门人否决: {guard['reason']} | p={guard['p']:.2f}")
                        result = await order_exec.execute_exit(sym, position['entry_amount'], live_price)
                        if result:
                            net_pnl = _calc_net_pnl(position, result, 'SHORT')
                            await update_trade_exit(position['id'], {
                                'exit_time': now, 'exit_price': result['fill_price'],
                                'exit_amount': result['amount'], 'exit_fee': result['fee'],
                                'exit_fee_asset': result['fee_asset'], 'exit_reason': 'AI_VETO',
                                'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                            })
                        position = None
                        trailing_engine = None
                        continue

                # 下跌保护
                is_bear, bear_reason = check_bear_market(px_1h)
                if is_bear:
                    log.bind(tag="RISK").warning(f"下跌趋势检测: {bear_reason} — 强制平仓")
                    result = await order_exec.execute_exit(sym, position['entry_amount'], live_price)
                    if result:
                        net_pnl = _calc_net_pnl(position, result, 'SHORT')
                        await update_trade_exit(position['id'], {
                            'exit_time': now, 'exit_price': result['fill_price'],
                            'exit_amount': result['amount'], 'exit_fee': result['fee'],
                            'exit_fee_asset': result['fee_asset'], 'exit_reason': 'BEAR_MARKET',
                            'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                        })
                    position = None
                    trailing_engine = None
                    cooldown = BEAR_COOLDOWN_SECONDS
                    log.bind(tag="RISK").info(f"下跌保护冷却 {cooldown}s")
                    await asyncio.sleep(min(cooldown, HOLDING_SLEEP))
                    continue

                # 僵局检测
                if trailing_engine and not trailing_engine.has_partial_tp:
                    hold_hours = (now - position.get('entry_time', now)) / 3600
                    stalemate_limit = STALEMATE_HOURS.get(sym, 12)
                    roi = (live_price / position['entry_price']) - 1
                    if hold_hours >= stalemate_limit and roi < STALEMATE_ROI_THRESHOLD:
                        other_syms = [s for s in SYMBOLS if s != sym]
                        current_roc = px_1h['ROC_9']
                        best_other_roc = max(primary_signals[s]['ROC_9'] for s in other_syms if s in primary_signals)
                        if best_other_roc > current_roc + MIN_ROC_ADVANTAGE and now - last_switch_time > SWITCH_COOLDOWN_HOURS * 3600:
                            log.bind(tag="STRATEGY").info(f"僵局迁移 {sym} → 对手ROC={best_other_roc:.2f} > {current_roc:.2f}")
                            result = await order_exec.execute_exit(sym, position['entry_amount'], live_price)
                            if result:
                                net_pnl = _calc_net_pnl(position, result, 'SHORT')
                                await update_trade_exit(position['id'], {
                                    'exit_time': now, 'exit_price': result['fill_price'],
                                    'exit_amount': result['amount'], 'exit_fee': result['fee'],
                                    'exit_fee_asset': result['fee_asset'], 'exit_reason': 'STALEMATE',
                                    'net_pnl': net_pnl['usdt'], 'net_pnl_pct': net_pnl['pct'],
                                })
                                last_switch_time = now
                            position = None
                            trailing_engine = None
                            continue

                log.bind(tag="STRATEGY").info(
                    f"持仓 {sym} | 入场 ${position['entry_price']:.2f} | "
                    f"现价 ${live_price:.2f} | PnL {pnl_pct:+.2%} | "
                    f"追踪SL ${trailing_engine.trailing_sl:.2f}"
                )
                await asyncio.sleep(HOLDING_SLEEP)

            else:
                # ═══ 空仓选币 ═══
                # 下跌保护：检查是否应该空仓
                bear_detected = False
                for sym in SYMBOLS:
                    if sym in primary_signals:
                        is_bear, bear_reason = check_bear_market(primary_signals[sym])
                        if is_bear:
                            log.bind(tag="STRATEGY").info(f"下跌趋势 {sym}: {bear_reason}")
                            bear_detected = True

                if bear_detected:
                    log.bind(tag="STRATEGY").info("市场下跌趋势，保持空仓观望")
                    await asyncio.sleep(MAIN_LOOP_SLEEP)
                    continue

                # 入场信号评估
                entry_candidates = {}
                for sym in SYMBOLS:
                    if sym not in primary_signals or sym not in confirm_signals:
                        continue
                    passed, reason = evaluate_entry(primary_signals[sym], confirm_signals[sym])
                    entry_candidates[sym] = {
                        'primary': primary_signals[sym],
                        'confirm': confirm_signals[sym],
                        'pass': passed,
                        'reason': reason,
                    }

                best = select_best_symbol(entry_candidates)
                if best:
                    ps = primary_signals[best]
                    log.bind(tag="STRATEGY").info(f"选中 {best} | {entry_candidates[best]['reason']}")

                    # 动态 Kelly
                    kelly = await get_dynamic_kelly(free_usdt * 0.99, ps['ATRr_14'], ps['close'])
                    log.bind(tag="STRATEGY").info(
                        f"Kelly仓位 | 胜率 {kelly['win_rate']:.1%} | "
                        f"风险 {kelly['risk_ratio']} | ${kelly['position_usd']:,.0f} | {kelly['source']}"
                    )

                    if kelly['position_usd'] >= 10:
                        result = await order_exec.execute_entry(best, kelly['position_usd'], ps['close'])
                        if result:
                            trade = {
                                'symbol': best,
                                'entry_time': now,
                                'entry_price': result['fill_price'],
                                'entry_amount': result['amount'],
                                'entry_fee': result['fee'],
                                'entry_fee_asset': result['fee_asset'],
                                'entry_order_id': result.get('order_id'),
                                'notes': kelly['source'],
                            }
                            trade_id = await insert_trade(trade)
                            position = {
                                'id': trade_id,
                                'symbol': best,
                                'entry_price': result['fill_price'],
                                'entry_amount': result['amount'],
                                'entry_time': now,
                                'status': 'OPEN',
                            }
                            trailing_engine = TrailingStopEngine(
                                result['fill_price'], ps['ATRr_14']
                            )
                            log.bind(tag="BALANCE").info(
                                f"开仓成功 {best} | 成交 ${result['fill_price']:.2f} | "
                                f"数量 {result['amount']:.6f} | 手续费 ${result['fee']:.4f}"
                            )
                    else:
                        log.bind(tag="STRATEGY").info(f"Kelly 金额 ${kelly['position_usd']:.0f} < $10，跳过")
                else:
                    # 无满足条件的标的
                    log.bind(tag="STRATEGY").info(
                        "无入场信号 | " + " | ".join(
                            f"{s}={entry_candidates[s]['primary']['ROC_9']:.2f}" for s in SYMBOLS if s in entry_candidates
                        )
                    )

                await asyncio.sleep(MAIN_LOOP_SLEEP)

    except Exception as e:
        log.opt(exception=True).bind(tag="STRATEGY").error(f"主循环崩溃: {e}")
    finally:
        await client.close()
        await close_guard()
        await close_db()
        log.bind(tag="STRATEGY").warning("系统已安全停机")


def _calc_net_pnl(position: dict, exit_result: dict, direction: str) -> dict:
    """
    计算净盈亏。
    exit_result 含 fill_price, fill_amount(or amount), fee
    """
    entry_usd = position['entry_price'] * exit_result['amount']
    exit_usd = exit_result['fill_price'] * exit_result['amount']
    gross = exit_usd - entry_usd
    fee_total = position.get('entry_fee', 0) + exit_result.get('fee', 0)
    net = gross - fee_total
    pct = net / entry_usd if entry_usd > 0 else 0
    return {"usdt": round(net, 4), "pct": round(pct, 6)}


def main():
    while True:
        try:
            asyncio.run(run_sniper())
        except KeyboardInterrupt:
            log.bind(tag="STRATEGY").warning("收到中断信号，退出")
            break
        except Exception as e:
            log.opt(exception=True).bind(tag="STRATEGY").error(f"守护进程崩溃: {e}")
            log.bind(tag="STRATEGY").info("30秒后自动重启...")
            time.sleep(30)


if __name__ == "__main__":
    main()