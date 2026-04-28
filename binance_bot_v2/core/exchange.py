import os
import json
import asyncio
import ccxt.async_support as ccxt
from config.settings import SG_DOMAIN, OHLCV_LIMIT
from core.logger import log

RETRIABLE = (ccxt.NetworkError, ccxt.ExchangeError, ccxt.BadResponse,
             ccxt.RateLimitExceeded, ccxt.DDoSProtection, ccxt.RequestTimeout)

async def _retry_async(fn, *args, max_retries=3, tag="EXCHANGE", **kwargs):
    """通用异步重试：指数退避，覆盖所有瞬时网络错误"""
    for i in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except RETRIABLE as e:
            if i == max_retries - 1:
                raise
            delay = min(2 ** i, 8)
            log.bind(tag=tag).debug(f"重试 {i+1}/{max_retries}，{delay}s 后重试: {e}")
            await asyncio.sleep(delay)

class BinanceClient:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': os.getenv("TESTNET_API_KEY"),
            'secret': os.getenv("TESTNET_SECRET_KEY"),
            'enableRateLimit': True,
            'headers': {'x-is-testnet': 'true'},
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        })
        self.exchange.set_sandbox_mode(True)
        self._hijack_urls()

    def _hijack_urls(self):
        urls_str = json.dumps(self.exchange.urls)
        urls_str = urls_str.replace("testnet.binance.vision", SG_DOMAIN)
        self.exchange.urls = json.loads(urls_str)

    async def fetch_ohlcv_safe(self, symbol, timeframe, limit=None):
        if limit is None:
            limit = OHLCV_LIMIT
        return await _retry_async(
            self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit,
            tag="EXCHANGE",
        )

    async def fetch_balance_safe(self):
        return await _retry_async(self.exchange.fetch_balance, tag="ORDER")

    async def fetch_ticker_safe(self, symbol):
        return await _retry_async(self.exchange.fetch_ticker, symbol, tag="ORDER")

    async def close(self):
        await self.exchange.close()
