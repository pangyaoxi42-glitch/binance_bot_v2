"""订单执行器 — 精度截断 + 成交回执 + 手续费记录"""
from config.settings import MIN_NOTIONAL_USD
from core.logger import log

class OrderManager:
    def __init__(self, exchange_client):
        self.client = exchange_client
        self.exchange = exchange_client.exchange

    async def execute_entry(self, symbol: str, usd_amount: float, current_price: float) -> dict | None:
        if current_price <= 0:
            log.bind(tag="ORDER").error(f"{symbol} 价格异常: {current_price}")
            return None

        try:
            await self.exchange.load_markets()
            raw_amount = usd_amount / current_price
            amount_str = self.exchange.amount_to_precision(symbol, raw_amount)
            safe_amount = float(amount_str)
            if safe_amount <= 0:
                log.bind(tag="ORDER").warning(f"{symbol} 精度截断后数量为0: {raw_amount} → {amount_str}")
                return None

            log.bind(tag="ORDER").info(
                f"开仓 {symbol} | 金额 ${usd_amount:.0f} | 数量 {amount_str}"
            )
            order = await self.exchange.create_order(
                symbol=symbol, type='market', side='buy', amount=amount_str
            )

            fill_price = float(order.get('average') or order.get('price') or current_price)
            filled = float(order.get('filled') or safe_amount)
            cost = float(order.get('cost', filled * fill_price))
            fee = order.get('fee')
            fee_cost = float(fee['cost']) if fee and fee.get('cost') else cost * 0.001
            fee_asset = fee['currency'] if fee and fee.get('currency') else 'USDT'
            fee_usdt = await self._fee_to_usdt(fee_cost, fee_asset, fill_price)

            return {
                "order_id": order['id'],
                "amount": filled,
                "fill_price": fill_price,
                "fee": fee_usdt,
                "fee_asset": fee_asset,
            }
        except Exception as e:
            log.bind(tag="ORDER").error(f"开仓失败: {e}")
            return None

    async def execute_exit(self, symbol: str, total_amount: float, current_price: float,
                           is_partial: bool = False) -> dict | None:
        try:
            await self.exchange.load_markets()
            target_amount = total_amount / 2.0 if is_partial else total_amount
            # 分批止盈最小名义价值检查: 低于阈值则强制全平
            if is_partial and target_amount * current_price < MIN_NOTIONAL_USD:
                log.bind(tag="ORDER").warning(
                    f"分批止盈价值 ${target_amount * current_price:.2f} < ${MIN_NOTIONAL_USD}，转为全平"
                )
                is_partial = False
                target_amount = total_amount

            amount_str = self.exchange.amount_to_precision(symbol, target_amount)
            safe_amount = float(amount_str)
            if safe_amount <= 0:
                log.bind(tag="ORDER").warning(f"{symbol} 平仓量过小: {amount_str}")
                return None

            mode = "分批止盈50%" if is_partial else "全平"
            log.bind(tag="ORDER").info(f"平仓 {symbol} | {mode} | 数量 {amount_str}")
            order = await self.exchange.create_order(
                symbol=symbol, type='market', side='sell', amount=amount_str
            )

            fill_price = float(order.get('average') or order.get('price') or current_price)
            filled = float(order.get('filled') or safe_amount)
            cost = float(order.get('cost', filled * fill_price))
            fee = order.get('fee')
            fee_cost = float(fee['cost']) if fee and fee.get('cost') else cost * 0.001
            fee_asset = fee['currency'] if fee and fee.get('currency') else 'USDT'
            fee_usdt = await self._fee_to_usdt(fee_cost, fee_asset, fill_price)

            return {
                "amount": filled,
                "fill_price": fill_price,
                "fee": fee_usdt,
                "fee_asset": fee_asset,
            }
        except Exception as e:
            log.bind(tag="ORDER").error(f"平仓失败: {e}")
            return None

    async def _fee_to_usdt(self, fee_amount: float, fee_asset: str, ref_price: float) -> float:
        """将非 USDT 手续费按当前市价折算为 USDT"""
        if fee_asset == 'USDT' or fee_amount <= 0:
            return fee_amount
        try:
            symbol = f"{fee_asset}/USDT"
            ticker = await self.exchange.fetch_ticker(symbol)
            return fee_amount * float(ticker['last'])
        except Exception:
            return fee_amount * ref_price