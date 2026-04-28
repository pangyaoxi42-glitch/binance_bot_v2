import os

# 交易对与周期
PRIMARY_SYMBOL = "BTC/USDT"
SECONDARY_SYMBOL = "SOL/USDT"
TIMEFRAME = "1h"

# 核心策略参数
SL_ATR_MULTIPLIER = 1.8
TP_ATR_MULTIPLIER = 3.9
MAX_RISK_PER_TRADE = 0.02  # 2% 最大单笔风险

# 僵局判定 (小时)
STALEMATE_HOURS_BTC = 12
STALEMATE_HOURS_SOL = 6
STALEMATE_ROI_THRESHOLD = 0.01  # 利润低于1%视为僵局

# Vercel 网关配置
SG_DOMAIN = "binance-sg-gateway.vercel.app"
# --- 财务统计配置 ---
INITIAL_CAPITAL = 320203.04  # 填入你启动机器人时的初始总资产（USDT折合）