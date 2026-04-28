import math
import pandas as pd
import numpy as np

_LOOKBACK = 60  # 覆盖最长窗口 EMA_50 + 安全边际

def _wilder_smooth(series, length):
    return series.ewm(alpha=1.0 / length, adjust=False).mean()

def calculate_signals(ohlcv_data, limit: int = None):
    if limit is None:
        limit = _LOOKBACK
    # 仅取最近 N 根 K 线参与计算
    trimmed = ohlcv_data[-limit:] if len(ohlcv_data) > limit else ohlcv_data
    df = pd.DataFrame(trimmed, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    close = df['close']
    high = df['high']
    low = df['low']

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = _wilder_smooth(gain, 14)
    avg_loss = _wilder_smooth(loss, 14)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100.0 - (100.0 / (1.0 + rs))

    df['EMA_50'] = close.ewm(span=50, adjust=False).mean()
    df['ROC_9'] = ((close - close.shift(9)) / close.shift(9).replace(0, np.nan)) * 100

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df['ATRr_14'] = _wilder_smooth(tr, 14)

    bb_mid = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std(ddof=0)
    df['BBL_20_2.0'] = bb_mid - 2.0 * bb_std
    df['BBU_20_2.0'] = bb_mid + 2.0 * bb_std

    df['VOL_MA_20'] = df['volume'].rolling(20).mean()

    last = df.iloc[-1]

    result = {
        'close': float(last['close']),
        'RSI_14': float(last['RSI_14']),
        'EMA_50': float(last['EMA_50']),
        'ROC_9': float(last['ROC_9']),
        'ATRr_14': float(last['ATRr_14']),
        'BBL_20_2.0': float(last['BBL_20_2.0']),
        'BBU_20_2.0': float(last['BBU_20_2.0']),
        'VOL_MA_20': float(last['VOL_MA_20']),
    }

    nan_fields = [k for k, v in result.items() if isinstance(v, float) and math.isnan(v)]
    if nan_fields:
        raise ValueError(f"指标计算失败，以下字段为 NaN（K线不足）: {nan_fields}")

    return result