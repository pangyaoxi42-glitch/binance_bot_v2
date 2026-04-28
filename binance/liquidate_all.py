import asyncio
import os
from dotenv import load_dotenv  # 👈 新增：导入环境变量工具
load_dotenv()                   # 👈 新增：强制让脚本去读取 .env 文件

from core.exchange import BinanceSniperClient
from core.logger import logger

async def liquidate_everything():
# ... 下面的代码完全不用动 ...
    client = BinanceSniperClient()
    exchange = client.exchange
    
    logger.info("清理行动开始：正在扫描账户所有资产...")
    
    try:
        # 1. 获取所有余额
        balance = await exchange.fetch_balance()
        total_usdt_value = 0.0
        
        # 获取账户中所有有余额的币种（排除 USDT 和极小额资产）
        assets = balance['total']
        to_sell = []
        
        usdt_balance = balance['free'].get('USDT', 0) + balance['used'].get('USDT', 0)
        total_usdt_value += usdt_balance
        
        for symbol, amount in assets.items():
            if symbol == 'USDT' or amount <= 0:
                continue
            
            # 过滤掉极小额资产（防止因数量过小导致接口报错）
            if (symbol == 'BTC' and amount < 0.0001) or (symbol == 'SOL' and amount < 0.01):
                continue
                
            to_sell.append((symbol, amount))

        if not to_sell:
            logger.info(f"✅ 账户中除 USDT 外无其他显著资产。当前总价值约: ${total_usdt_value:.2f}")
            return

        logger.info(f"发现 {len(to_sell)} 种待处理资产，准备执行清仓...")

        # 2. 逐一变现
        for asset, amount in to_sell:
            market_symbol = f"{asset}/USDT"
            try:
                # 获取实时价格计算价值
                ticker = await exchange.fetch_ticker(market_symbol)
                price = ticker['last']
                value = amount * price
                total_usdt_value += value
                
                logger.info(f"⏳ 正在卖出 {amount} {asset} (价值约 ${value:.2f})...")
                
                # 精度截断
                await exchange.load_markets()
                amount_str = exchange.amount_to_precision(market_symbol, amount)
                
                # 执行市价卖单
                await exchange.create_order(
                    symbol=market_symbol,
                    type='market',
                    side='sell',
                    amount=float(amount_str)
                )
                logger.info(f"✅ {asset} 已成功换成 USDT")
            except Exception as e:
                logger.error(f"❌ 卖出 {asset} 失败: {e}")

        # 3. 最终汇报
        # 刷新一下最终余额
        final_balance = await exchange.fetch_balance()
        final_usdt = final_balance['total'].get('USDT', 0)
        
        print("\n" + "="*50)
        print(f"💰 变现行动结束！")
        print(f"📊 最终账户总值: ${final_usdt:.2f} USDT")
        print("="*50 + "\n")

    except Exception as e:
        logger.error(f"❌ 清仓脚本崩溃: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(liquidate_everything())