import pandas as pd
import pandas_ta as ta

def calculate_signals(ohlcv_data):
    """
    计算技术指标并返回统一命名的字典
    """
    # 1. 转换为 DataFrame 并确保数据类型
    df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    # 2. 计算各项指标
    df['RSI_14'] = ta.rsi(df['close'], length=14)
    df['EMA_50'] = ta.ema(df['close'], length=50)
    df['ROC_9'] = ta.roc(df['close'], length=9)
    df['ATRr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # 计算布林带
    bbands = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bbands], axis=1)
    
    # 3. 取最后一行并进行“模糊匹配”重命名
    last_row = df.iloc[-1].to_dict()
    
    # 初始化基础输出
    result = {
        'close': float(last_row.get('close', 0)),
        'RSI_14': float(last_row.get('RSI_14', 0)),
        'EMA_50': float(last_row.get('EMA_50', 0)),
        'ROC_9': float(last_row.get('ROC_9', 0)),
        'ATRr_14': float(last_row.get('ATRr_14', 0)),
    }
    
    # 核心修复：自动寻找布林带列，防止 KeyError
    for key in last_row.keys():
        # 寻找下轨 (BBL)
        if key.startswith('BBL_'):
            result['BBL_20_2.0'] = float(last_row[key])
        # 寻找上轨 (BBU)
        if key.startswith('BBU_'):
            result['BBU_20_2.0'] = float(last_row[key])
            
    return result