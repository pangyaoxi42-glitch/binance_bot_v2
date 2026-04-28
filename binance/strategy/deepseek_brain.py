import os
import json
import asyncio
import httpx
from openai import AsyncOpenAI
from core.logger import logger

# 核心修复：彻底无视 3x-ui 或系统的代理环境变量，防止参数碰撞
http_client = httpx.AsyncClient(trust_env=False)

client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    http_client=http_client
)

async def get_ai_prediction(symbol: str, indicator_data: dict) -> dict:
    """
    [旧版单核督战] 仅用于当前已有持仓时的风险评估
    """
    prompt = f"""
    [量化风控模式] 交易对: {symbol} (1H 周期)
    实时数据: 现价 {indicator_data['close']} | RSI {indicator_data['RSI_14']:.1f} | ROC_9 {indicator_data['ROC_9']:.2f}
    布林带: 上轨 {indicator_data['BBU_20_2.0']:.2f} / 下轨 {indicator_data['BBL_20_2.0']:.2f}

    任务: 评估当前多单(Long)继续持有的胜率。
    核心纪律: 在强势上涨行情中，RSI超买(>70)和触及布林带上轨属于正常的“轧空”现象。除非出现动能(ROC_9)明显衰竭拐头向下，或者极其明确的暴跌做空信号，否则绝对不要轻易给出极低的胜率！
    输出要求: 仅返回 JSON 格式 {{"p": 0.0到1.0, "reason": "简短理由"}}
    """
    try:
        response = await client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
            response_format={'type': 'json_object'}, temperature=0.1
        )
        raw_content = response.choices[0].message.content.strip()
        
        # 🛡️ 拆分为多行，防止 nano 粘贴时把反引号截断
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
            
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
            
        res = json.loads(raw_content.strip())
        return {"p": float(res.get("p", 0.5)), "reason": res.get("reason", "保持观望")}
    except Exception as e:
        logger.error(f"❌ AI 单核督战调用异常: {e}")
        # 🛡️ 致命修复：网络断开时，默认给出 0.5 的中性胜率，防止恐慌性砸盘平仓！
        return {"p": 0.5, "reason": "接口异常，安全降级保持观望"}

async def get_ai_comparative_prediction(symbol_a: str, data_a: dict, symbol_b: str, data_b: dict) -> dict:
    """
    [全新双核大脑] 用于空仓时，强制 AI 对比两个资产并选出最强者
    """
    prompt = f"""
    [量化基金总监模式] 
    你手里有一笔空闲资金。当前有两个现货交易对，请综合对比它们的动能(ROC)、支撑位和爆发潜力，选出最优的开多(Long)目标。
    注意：你必须重点关注“相对动能(ROC_9)”的强弱对比，优先选择趋势更强、盈亏比合理的资产。如果两者都很差，请坚决空仓。

    资产 A ({symbol_a}) 1H数据:
    - 现价: {data_a['close']} | ATR: {data_a['ATRr_14']:.2f} | RSI: {data_a['RSI_14']:.1f}
    - 动能 (ROC_9): {data_a['ROC_9']:.2f}
    - 布林带位置: {(data_a['close'] - data_a['BBL_20_2.0']) / (data_a['BBU_20_2.0'] - data_a['BBL_20_2.0']):.2%}

    资产 B ({symbol_b}) 1H数据:
    - 现价: {data_b['close']} | ATR: {data_b['ATRr_14']:.2f} | RSI: {data_b['RSI_14']:.1f}
    - 动能 (ROC_9): {data_b['ROC_9']:.2f}
    - 布林带位置: {(data_b['close'] - data_b['BBL_20_2.0']) / (data_b['BBU_20_2.0'] - data_b['BBL_20_2.0']):.2%}

    输出要求: 必须仅返回标准 JSON 格式：
    {{
        "target": "{symbol_a}" 或 "{symbol_b}" 或 "NONE",
        "p": 0.0到1.0的浮点数 (选中目标的胜率，选NONE则为0),
        "reason": "30字以内，重点说明为什么选A不选B（或都不选）的对比逻辑"
    }}
    """
    try:
        response = await client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
            response_format={'type': 'json_object'}, temperature=0.1
        )
        raw_content = response.choices[0].message.content.strip()
        
        # 🛡️ 拆分为多行，防止 nano 粘贴时把反引号截断
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
            
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
            
        res = json.loads(raw_content.strip())
        return {
            "target": res.get("target", "NONE"),
            "p": float(res.get("p", 0.0)), 
            "reason": res.get("reason", "双币均无明显优势，保持空仓观望")
        }
    except Exception as e:
        logger.error(f"❌ AI 综合统筹引擎调用异常: {e}")
        # 🛡️ 致命修复：必须保留 "target" 键，否则主程序会报 KeyError 崩溃！
        # 空仓选美时遇到断网，直接返回 NONE 强行观望即可。
        return {
            "target": "NONE", 
            "p": 0.0, 
            "reason": "AI 接口异常，强制空仓"
        }