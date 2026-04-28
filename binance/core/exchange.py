import os
import json
import asyncio
import ccxt.async_support as ccxt
from config.settings import SG_DOMAIN

class BinanceSniperClient:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': os.getenv("TESTNET_API_KEY"),
            'secret': os.getenv("TESTNET_SECRET_KEY"),
            'enableRateLimit': True, 
            'headers': {'x-is-testnet': 'true'}, # 🛡️ 补上这个救命的 Header，告诉 Vercel 这是测试网！
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        })
        self.exchange.set_sandbox_mode(True)
        self._hijack_urls()
        
    def _hijack_urls(self):
        """核心：通过修改底层字典，将流量代理至 Vercel"""
        urls_str = json.dumps(self.exchange.urls)
        urls_str = urls_str.replace("testnet.binance.vision", SG_DOMAIN)
        self.exchange.urls = json.loads(urls_str)
        
    async def fetch_ohlcv_safe(self, symbol, timeframe, limit=100):
        """带指数退避重试的 K 线获取"""
        retries = 3
        for i in range(retries):
            try:
                return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            # 🛡️ 扩大捕获范围：涵盖网络断开、Vercel 502网关超时、交易所熔断等所有异常
            except (ccxt.NetworkError, ccxt.ExchangeError, ccxt.BadResponse) as e:
                if i == retries - 1: raise e
                await asyncio.sleep(2 ** i) # 1s, 2s, 4s 避让
    
    async def close(self):
        await self.exchange.close()