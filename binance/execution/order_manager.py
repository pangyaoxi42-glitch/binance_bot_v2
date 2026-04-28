from core.logger import logger
import ccxt

class OrderManager:
    def __init__(self, exchange_client):
        self.client = exchange_client
        self.exchange = exchange_client.exchange

    async def execute_entry(self, symbol: str, usd_amount: float, current_price: float):
        """
        执行进场订单：计算精度 -> 截断 -> 市价单开仓
        """
        try:
            # 1. 确保市场信息已加载，这是获取精度步长的基础
            await self.exchange.load_markets()
            
            # 2. 计算原始下单数量
            raw_amount = usd_amount / current_price
            
            # 🛡️ 漏洞修复：使用 CCXT 内置工具进行精度格式化（截断而非四舍五入）
            # 这是防止币安报 LOT_SIZE 错误的核武级修复
            amount_str = self.exchange.amount_to_precision(symbol, raw_amount)
            safe_amount = float(amount_str)
            
            # 3. 最终二次确认数量（防止精度截断后变成0）
            if safe_amount <= 0:
                logger.warning(f"⚠️ [精度阻断] {symbol} 下单量过小({raw_amount} -> {amount_str})，取消开仓")
                return None

            logger.info(f"🚀 [执行开仓] {symbol} | 预估金额: ${usd_amount} | 精确数量: {amount_str}")
            
            # 4. 执行开仓：为了不错过 AI 信号，强制改用 'market' 市价单
            # 这样不需要传 price，直接按盘口最快成交
            order = await self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='buy',
                amount=safe_amount
            )
            
            return {
                "order_id": order['id'],
                "amount": safe_amount
            }
        except Exception as e:
            logger.error(f"❌ [开仓失败] 接口报错: {e}")
            return None

    async def execute_exit(self, symbol: str, total_amount: float, current_price: float, is_partial=False):
        """
        执行出场订单：全平或分批止盈，同样带精度防御
        """
        try:
            await self.exchange.load_markets()
            
            # 1. 决定卖出比例
            target_amount = total_amount / 2.0 if is_partial else total_amount
            
            # 🛡️ 漏洞修复：出场同样进行精度截断，防止“灰尘余额”导致卖不出
            amount_str = self.exchange.amount_to_precision(symbol, target_amount)
            safe_amount = float(amount_str)
            
            if safe_amount <= 0:
                logger.warning(f"⚠️ [精度阻断] {symbol} 平仓量过小，无法执行。")
                return 0.0
            
            logger.info(f"💥 [执行平仓] {symbol} | 模式: {'分批止盈' if is_partial else '全平'} | 数量: {amount_str}")
            
            # 2. 市价单离场，保证风控指令（止损/AI一票否决）绝对优先执行
            order = await self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='sell',
                amount=safe_amount
            )
            
            return safe_amount
        except Exception as e:
            logger.error(f"❌ [平仓失败] 接口报错: {e}")
            return 0.0