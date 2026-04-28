import asyncio
import time
from core.logger import logger
from core.exchange import BinanceSniperClient
from core.state_machine import load_state, save_state
from strategy.indicators import calculate_signals

# 🛡️ 路径已根据项目结构修正
from risk_management.dynamic_stops import check_and_update_stops, apply_partial_tp_state
from risk_management.opportunity_hunter import check_opportunity_cost

from strategy.deepseek_brain import get_ai_prediction, get_ai_comparative_prediction
from execution.order_manager import OrderManager
from execution.kelly_sizing import get_detailed_kelly_size
from config.settings import PRIMARY_SYMBOL, SECONDARY_SYMBOL, TIMEFRAME, INITIAL_CAPITAL

# --- 🛡️ 扩展超时保护包装器 ---
# 用于持仓时的单币种风险评估
async def get_safe_ai_prediction(symbol, status):
    try:
        return await asyncio.wait_for(get_ai_prediction(symbol, status), timeout=15.0)
    except Exception as e:
        logger.error(f"⚠️ [持仓评估异常] {symbol} AI 暂时失联: {e}")
        # 🛡️ Fail-Safe: 网络异常时返回 0.5 中性胜率，防止恐慌平仓
        return {'p': 0.5, 'reason': '网络波动，AI 暂时失联，维持当前持仓防守'}

# 用于空仓时的双币种对比选美
async def get_safe_ai_comparative_prediction(symbol_a, data_a, symbol_b, data_b):
    try:
        return await asyncio.wait_for(get_ai_comparative_prediction(symbol_a, data_a, symbol_b, data_b), timeout=20.0)
    except Exception as e:
        logger.error(f"⚠️ [统筹异常] AI 双核评估失败: {e}")
        # 🛡️ Fail-Safe: 猎物评估异常时强制 NONE 观望，防止 KeyError 崩溃
        return {'target': 'NONE', 'p': 0.0, 'reason': '双核接口异常，强制空仓防守'}

async def sniper_loop():
    client = BinanceSniperClient()
    order_exec = OrderManager(client)
    state = await load_state()
    
    logger.info("=" * 60)
    logger.info("🚀 深空狙击手 (Deep Sniper) - 财务统筹全功能版已点火")
    logger.info("=" * 60 + "\n")
    
    try:
        while True:
            logger.info("=" * 60)
            logger.info(f"🛰️  [巡逻开始] 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # --- [阶段 A] 环境检查 ---
            cooldown_time = state.get("cooldown_until", 0)
            if time.time() < cooldown_time:
                remaining = int(cooldown_time - time.time())
                logger.info(f"❄️  [状态] 处于交易冷静期，还剩 {remaining} 秒，跳过本轮扫描。")
                logger.info("=" * 60 + "\n")
                await asyncio.sleep(60)
                continue

            # --- [阶段 B] 行情采集与资产总览 ---
            try:
                # 1. 获取最新 K 线和指标
                btc_ohlcv = await client.fetch_ohlcv_safe(PRIMARY_SYMBOL, TIMEFRAME)
                sol_ohlcv = await client.fetch_ohlcv_safe(SECONDARY_SYMBOL, TIMEFRAME)
                
                btc = calculate_signals(btc_ohlcv)
                sol = calculate_signals(sol_ohlcv)
                
                # 2. 💼 资产总览仪表盘
                balance = await client.exchange.fetch_balance()
                free_usdt = balance['free'].get('USDT', 0)
                btc_amt = balance['total'].get('BTC', 0)
                sol_amt = balance['total'].get('SOL', 0)
                
                btc_value = btc_amt * btc['close']
                sol_value = sol_amt * sol['close']
                total_equity = free_usdt + btc_value + sol_value
                
                # 🛡️ 计算总资产相对于初始本金的盈亏率
                total_pnl_pct = (total_equity / INITIAL_CAPITAL) - 1 if INITIAL_CAPITAL > 0 else 0
                
                logger.info("-" * 55)
                logger.info(f"💼 [资产总览] 总权益: ${total_equity:.2f} ({total_pnl_pct:+.2%}) | 可用U: ${free_usdt:.2f}")
                
                pos = state.get("position")
                
                if btc_amt > 0.0001:
                    pnl_str = ""
                    if pos and pos['symbol'] == PRIMARY_SYMBOL:
                        pnl = (btc['close'] / pos['entry_price']) - 1
                        pnl_str = f" | 浮动盈亏: {pnl:+.2%}"
                    logger.info(f"   🪙 持仓: {btc_amt:.5f} BTC | 现值: ${btc_value:.2f}{pnl_str}")
                    
                if sol_amt > 0.01:
                    pnl_str = ""
                    if pos and pos['symbol'] == SECONDARY_SYMBOL:
                        pnl = (sol['close'] / pos['entry_price']) - 1
                        pnl_str = f" | 浮动盈亏: {pnl:+.2%}"
                    logger.info(f"   🪙 持仓: {sol_amt:.3f} SOL | 现值: ${sol_value:.2f}{pnl_str}")
                logger.info("-" * 55)
                
                # 3. 打印行情
                pb_btc = (btc['close'] - btc['BBL_20_2.0']) / (btc['BBU_20_2.0'] - btc['BBL_20_2.0'])
                logger.info(f"📊 [实时行情] BTC: ${btc['close']:.2f} | RSI: {btc['RSI_14']:.1f} | BB位置: {pb_btc:.2%}")
                logger.info(f"📊 [实时行情] SOL: ${sol['close']:.2f} | RSI: {sol['RSI_14']:.1f} | ROC: {sol['ROC_9']:.2f}")
            except Exception as e:
                logger.error(f"❌ [数据异常] 无法获取行情或资产失败: {e}")
                await asyncio.sleep(30)
                continue
                
            # --- [阶段 C] 核心决策分支 ---
            if pos:
                # --- 情况 A: 当前已有持仓 -> 执行深度监控 ---
                curr_symbol = pos['symbol']
                curr_status = btc if curr_symbol == PRIMARY_SYMBOL else sol
                alt_status = sol if curr_symbol == PRIMARY_SYMBOL else btc
                
                # 📈 计算当前单笔持仓的实时盈亏率
                current_trade_pnl_pct = (curr_status['close'] / pos['entry_price']) - 1

                logger.info(f"🔍 [持仓明细] {curr_symbol} | 入场: ${pos['entry_price']:.2f} | 盈亏: {current_trade_pnl_pct:+.2%}")
                
                # 🧠 AI 督战
                logger.info("🧠 [AI 督战] 正在让 DeepSeek 重新评估持仓风险...")
                ai_review = await get_safe_ai_prediction(curr_symbol, curr_status)
                if ai_review['p'] < 0.20:
                    logger.warning(f"🚨 [AI 紧急指令] 理由: {ai_review['reason']} | 最终盈亏: {current_trade_pnl_pct:+.2%}")
                    logger.warning("💥 触发 AI 一票否决，执行核弹级强制平仓！")
                    await order_exec.execute_exit(curr_symbol, pos['amount'], curr_status['close'])
                    state["position"] = None
                    state["cooldown_until"] = time.time() + 1800
                    await save_state(state)
                    continue

                # 🛡️ 动态止盈止损检测
                decision = check_and_update_stops(pos, curr_status['close'], curr_status['ATRr_14'])
                
                if decision == 'SL':
                    logger.warning(f"🚨 [风控] 触发硬性止损！全平 {curr_symbol} | 最终盈亏: {current_trade_pnl_pct:+.2%}")
                    await order_exec.execute_exit(curr_symbol, pos['amount'], curr_status['close'])
                    state["position"] = None
                    state["cooldown_until"] = time.time() + 3600
                    await save_state(state)
                    continue

                elif decision == 'TP_FINAL':
                    logger.info(f"💰 [获利] 触及终极止盈位！全平 {curr_symbol} | 最终盈亏: {current_trade_pnl_pct:+.2%}")
                    await order_exec.execute_exit(curr_symbol, pos['amount'], curr_status['close'])
                    state["position"] = None
                    state["cooldown_until"] = time.time() + 1800
                    await save_state(state)
                    continue

                elif decision == 'TP_PARTIAL':
                    logger.info(f"🌓 [分步] 触及一级止盈位(+1.5x ATR)，减仓 50% | 当前获利: {current_trade_pnl_pct:+.2%}")
                    sold_qty = await order_exec.execute_exit(curr_symbol, pos['amount'], curr_status['close'], is_partial=True)
                    if sold_qty > 0:
                        pos['amount'] -= sold_qty
                        state["position"] = apply_partial_tp_state(pos, curr_status['close'])
                        await save_state(state)
                    continue

                # 🔄 机会成本猎手 (僵局迁移)
                if not pos.get("has_partial_tp", False):
                    need_switch = await check_opportunity_cost(
                        pos['symbol'], pos['entry_time'], pos['entry_price'], 
                        curr_status['close'], curr_status['ROC_9'], alt_status['ROC_9']
                    )
                    if need_switch:
                        logger.info(f"🔄 [迁移] 检测到更有潜力的品种，平仓迁移 | 当前盈亏: {current_trade_pnl_pct:+.2%}")
                        await order_exec.execute_exit(curr_symbol, pos['amount'], curr_status['close'])
                        state["position"] = None
                        state["cooldown_until"] = time.time() + 300 
                        await save_state(state)
                        continue

            else:
                # --- [情况 B: 空仓寻找机会 (AI 双核统筹模式)] ---
                logger.info("🧠 [统筹大脑] 正在对比 BTC 与 SOL 的动能，寻找最强狙击目标...")
                ai_decision = await get_safe_ai_comparative_prediction(PRIMARY_SYMBOL, btc, SECONDARY_SYMBOL, sol)
                
                target_symbol = ai_decision['target']
                p = ai_decision['p']
                
                if target_symbol in [PRIMARY_SYMBOL, SECONDARY_SYMBOL] and p > 0.45:
                    target_status = btc if target_symbol == PRIMARY_SYMBOL else sol
                    balance = await client.exchange.fetch_balance()
                    free_u = balance['free'].get('USDT', 0) * 0.99 # 预留手续费容错
                    
                    k = get_detailed_kelly_size(p, free_u, target_status['ATRr_14'], target_status['close'])
                    
                    logger.info(f"🎯 [锁定目标] AI 选择狙击 {target_symbol} | 胜率预测: {p:.2%}")
                    logger.info(f"💡 [逻辑] {ai_decision['reason']}")
                    logger.info(f"🧮 [凯利计算] 建议金额: ${k['position_usd']}")
                    
                    if k['position_usd'] >= 10:
                        logger.info(f"🚀 [行动] 执行市价买入...")
                        order_data = await order_exec.execute_entry(target_symbol, k['position_usd'], target_status['close'])
                        
                        if order_data:
                            state["position"] = {
                                "symbol": target_symbol,
                                "amount": order_data['amount'],
                                "entry_price": target_status['close'],
                                "entry_time": time.time(),
                                "sl_price": target_status['close'] - (target_status['ATRr_14'] * 1.8),
                                "tp_price": target_status['close'] + (target_status['ATRr_14'] * 3.9),
                                "partial_tp_price": target_status['close'] + (target_status['ATRr_14'] * 1.5), 
                                "has_partial_tp": False
                            }
                            await save_state(state)
                            logger.info(f"✅ {target_symbol} 开仓成功并已存档。")
                    else:
                        logger.info(f"⏳ [放弃] 凯利建议金额不足 $10。")
                else:
                    logger.info(f"💤 [跳过] AI 决议: {ai_decision['reason']}")
            
            # --- [阶段 D] 休眠策略 ---
            if state.get("position"):
                logger.info("🛡️ [高频盯盘模式] 60秒后重新测算...")
                logger.info("=" * 60 + "\n")
                await asyncio.sleep(60)
            else:
                logger.info("🏁 [潜伏模式] 5分钟后开始新一轮扫描...")
                logger.info("=" * 60 + "\n")
                await asyncio.sleep(300)
            
    except Exception as e:
        logger.error(f"⚠️ [系统崩溃] 顶层捕获到严重异常: {e}")
    finally:
        await client.close()
        logger.warning("🔔 [停机] 系统已释放网络连接并安全关闭。")

if __name__ == "__main__":
    asyncio.run(sniper_loop())