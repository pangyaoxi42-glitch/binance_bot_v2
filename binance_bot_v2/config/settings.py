# 交易对 & 周期
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME_PRIMARY = "1h"
TIMEFRAME_CONFIRM = "15m"

# ATR 止损止盈乘数
SL_ATR_MULTIPLIER = 1.8
TP_ATR_MULTIPLIER = 3.9
PARTIAL_TP_MULTIPLIER = 1.5
PARTIAL_TP_RATIO = 0.5
TRAILING_ATR_MULTIPLIER = 2.0

# 凯利仓位
MAX_RISK_PER_TRADE = 0.02       # 单笔最大风险 2%
MAX_POSITION_RATIO = 0.50       # 单币种 ≤ 可用 USDT 的 50%
KELLY_COLD_START_MIN_TRADES = 20  # 不足 20 笔平仓单 → 冷启动
KELLY_COLD_START_RISK = 0.01    # 冷启动用 1% 风险
KELLY_WINDOW = 50               # 最近 N 笔平仓统计胜率
FEE_ROUNDTRIP = 0.002           # 双边市价手续费 0.1% * 2

# 僵局 & 机会成本
STALEMATE_HOURS = {"BTC/USDT": 12, "ETH/USDT": 8, "SOL/USDT": 6}
STALEMATE_ROI_THRESHOLD = 0.01
MIN_ROC_ADVANTAGE = 1.0
SWITCH_COOLDOWN_HOURS = 2

# 下跌保护
BEAR_ROC_THRESHOLD = -2.0
BEAR_COOLDOWN_SECONDS = 7200

# AI 守门人
AI_GUARD_INTERVAL = 600         # 每 10 分钟检查一次
AI_GUARD_VETO_THRESHOLD = 0.15  # 异常概率 < 15% → 平仓
AI_GUARD_TIMEOUT = 20.0

# 熔断
DAILY_LOSS_CAP = 0.05           # 日亏损 > 5% 总资产 → 熔断
MAX_CONSECUTIVE_LOSSES = 5      # 连续亏损 5 笔 → 暂停
CIRCUIT_BREAKER_COOLDOWN = 14400  # 熔断冷却 4 小时

# 入场信号阈值
ENTRY_ROC_MIN = 0.5             # 1h ROC_9 必须 > 0.5
ENTRY_RSI_MAX = 70
CONFIRM_ROC_MIN = 0.0           # 15min ROC_9 必须 > 0

# 风控
MIN_NOTIONAL_USD = 10.0         # 币安最小名义价值

# 数据采集
OHLCV_LIMIT = 120
MAIN_LOOP_SLEEP = 60
HOLDING_SLEEP = 30

# 初始资本 (用于回撤计算)
INITIAL_CAPITAL = 320203.04

# Vercel 代理
SG_DOMAIN = "binance-sg-gateway.vercel.app"
