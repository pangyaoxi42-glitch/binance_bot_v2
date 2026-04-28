"""DeepSeek AI 守门人 — 仅异常检测，不生成交易信号"""
import os
import json
import asyncio
import httpx
from openai import AsyncOpenAI
from core.logger import log

_client = None
_http_client = None

def _get_client():
    global _client, _http_client
    if _client is None:
        _http_client = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(25.0, connect=10.0))
        _client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
            http_client=_http_client,
        )
    return _client

async def close_guard():
    global _client, _http_client
    if _http_client:
        await _http_client.aclose()
        _client = None
        _http_client = None


async def check_anomaly(symbol: str, primary: dict, position_pnl_pct: float) -> dict:
    """
    检测当前持仓是否处于异常市场状态。
    返回 {"anomaly": bool, "p": float, "reason": str}
    p 是"安全的概率"，p < 0.15 触发异常否决。
    """
    prompt = f"""你是一个加密货币量化风控引擎的异常检测模块。
当前持仓: {symbol}
1H 指标: 现价 {primary['close']:.2f} | RSI {primary['RSI_14']:.1f} | ROC_9 {primary['ROC_9']:.2f}
布林带: 上轨 {primary['BBU_20_2.0']:.2f} / 下轨 {primary['BBL_20_2.0']:.2f}
EMA50: {primary['EMA_50']:.2f} | 当前盈亏: {position_pnl_pct:+.2%}

你的唯一任务：判断当前市场是否存在足以危及持仓的异常情况。
异常包括但不限于：
- 动量(ROC_9)急剧恶化（由正转负且幅度 > 2）
- 价格放量跌破关键支撑（EMA50 或 布林下轨）
- 出现极端反转形态信号

注意：RSI超买、正常的趋势回调、触及布林上轨——这些是正常的上涨行情特征，不是异常。

输出严格 JSON: {{"p": 0.0-1.0的安全概率, "reason": "简短判断理由"}}
"""

    try:
        response = await _get_client().chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={'type': 'json_object'},
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = _clean_fences(raw)
        res = json.loads(raw)
        p = float(res.get("p", 0.5))
        return {"anomaly": p < 0.15, "p": p, "reason": res.get("reason", "")}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.bind(tag="STRATEGY").warning(f"AI 守门人异常: {e}")
        return {"anomaly": False, "p": 0.5, "reason": "AI 不可用，放行"}


import re

def _clean_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*\n?', '', t)
    t = re.sub(r'\n?```\s*$', '', t)
    return t.strip()