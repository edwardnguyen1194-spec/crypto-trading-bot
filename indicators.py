"""
Technical Indicators Module
Uses the 'ta' library for reliable indicator calculations.
Includes SuperTrend, Ichimoku Cloud, ADX, OBV, and full analysis dict.
"""

import pandas as pd
import numpy as np
import ta
import config


def build_dataframe(klines: list) -> pd.DataFrame:
    """
    Convert raw kline data to a pandas DataFrame.
    Bitunix kline format: list of [timestamp, open, high, low, close, volume]
    """
    if not klines:
        return pd.DataFrame()

    # Handle both dict and list formats
    if isinstance(klines[0], dict):
        df = pd.DataFrame(klines)
        # Bitunix format: open, high, low, close, quoteVol, baseVol, time
        rename_map = {}
        if "time" in df.columns and "timestamp" not in df.columns:
            rename_map["time"] = "timestamp"
        if "t" in df.columns and "timestamp" not in df.columns:
            rename_map["t"] = "timestamp"
        if "o" in df.columns:
            rename_map.update({"o": "open", "h": "high", "l": "low", "c": "close"})
        # Map volume from Bitunix fields
        if "baseVol" in df.columns and "volume" not in df.columns:
            rename_map["baseVol"] = "volume"
        elif "quoteVol" in df.columns and "volume" not in df.columns:
            rename_map["quoteVol"] = "volume"
        elif "v" in df.columns and "volume" not in df.columns:
            rename_map["v"] = "volume"
        if rename_map:
            df = df.rename(columns=rename_map)
    else:
        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.dropna(subset=["close"])

    return df


def calculate_supertrend(df: pd.DataFrame, period: int = None, multiplier: float = None) -> pd.DataFrame:
    """
    Calculate SuperTrend indicator.
    SuperTrend = ATR-based trend-following indicator.
    Returns df with 'supertrend', 'supertrend_direction' columns.
    """
    period = period or config.SUPERTREND_PERIOD
    multiplier = multiplier or config.SUPERTREND_MULTIPLIER

    if len(df) < period + 1:
        df["supertrend"] = np.nan
        df["supertrend_direction"] = 0
        return df

    atr = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=period)

    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1 = bullish, -1 = bearish

    for i in range(period, len(df)):
        if i == period:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
            continue

        # Adjust bands based on previous values
        if lower_band.iloc[i] > lower_band.iloc[i - 1] or df["close"].iloc[i - 1] < lower_band.iloc[i - 1]:
            pass  # keep current lower_band
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        if upper_band.iloc[i] < upper_band.iloc[i - 1] or df["close"].iloc[i - 1] > upper_band.iloc[i - 1]:
            pass  # keep current upper_band
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Determine direction
        if supertrend.iloc[i - 1] == upper_band.iloc[i - 1]:
            if df["close"].iloc[i] > upper_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:
            if df["close"].iloc[i] < lower_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    df["supertrend"] = supertrend
    df["supertrend_direction"] = direction
    return df


def calculate_ichimoku(df: pd.DataFrame, conv_period: int = None,
                       base_period: int = None, span_b_period: int = None) -> pd.DataFrame:
    """
    Calculate Ichimoku Cloud components.
    Returns df with tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b columns.
    """
    conv_period = conv_period or config.ICHIMOKU_CONV
    base_period = base_period or config.ICHIMOKU_BASE
    span_b_period = span_b_period or config.ICHIMOKU_SPAN_B

    if len(df) < span_b_period:
        df["tenkan_sen"] = np.nan
        df["kijun_sen"] = np.nan
        df["senkou_span_a"] = np.nan
        df["senkou_span_b"] = np.nan
        return df

    # Tenkan-sen (Conversion Line) = (highest high + lowest low) / 2 over conv_period
    high_conv = df["high"].rolling(window=conv_period).max()
    low_conv = df["low"].rolling(window=conv_period).min()
    df["tenkan_sen"] = (high_conv + low_conv) / 2

    # Kijun-sen (Base Line) = (highest high + lowest low) / 2 over base_period
    high_base = df["high"].rolling(window=base_period).max()
    low_base = df["low"].rolling(window=base_period).min()
    df["kijun_sen"] = (high_base + low_base) / 2

    # Senkou Span A = (Tenkan + Kijun) / 2, shifted forward base_period
    df["senkou_span_a"] = ((df["tenkan_sen"] + df["kijun_sen"]) / 2).shift(base_period)

    # Senkou Span B = (highest high + lowest low) / 2 over span_b_period, shifted forward base_period
    high_span_b = df["high"].rolling(window=span_b_period).max()
    low_span_b = df["low"].rolling(window=span_b_period).min()
    df["senkou_span_b"] = ((high_span_b + low_span_b) / 2).shift(base_period)

    return df


def calculate_adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Calculate ADX, +DI, -DI using ta library (NOT talib).
    """
    if len(df) < window + 1:
        df["adx"] = np.nan
        df["plus_di"] = np.nan
        df["minus_di"] = np.nan
        return df

    adx_indicator = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=window)
    df["adx"] = adx_indicator.adx()
    df["plus_di"] = adx_indicator.adx_pos()
    df["minus_di"] = adx_indicator.adx_neg()
    return df


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate On Balance Volume (OBV).
    """
    if len(df) < 2:
        df["obv"] = 0
        return df

    df["obv"] = ta.volume.on_balance_volume(df["close"], df["volume"])
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators needed for the strategy."""
    if df.empty or len(df) < config.EMA_SLOW:
        return df

    # === Trend Indicators ===
    df["ema_fast"] = ta.trend.ema_indicator(df["close"], window=config.EMA_FAST)
    df["ema_slow"] = ta.trend.ema_indicator(df["close"], window=config.EMA_SLOW)
    df["trend_bullish"] = df["ema_fast"] > df["ema_slow"]

    # EMA 9, 21, 50 for SmartStrategy
    df["ema9"] = ta.trend.ema_indicator(df["close"], window=9)
    df["ema21"] = ta.trend.ema_indicator(df["close"], window=21)
    df["ema50"] = ta.trend.ema_indicator(df["close"], window=50)

    # === RSI ===
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIOD)

    # === MACD ===
    macd = ta.trend.MACD(
        df["close"],
        window_slow=config.MACD_SLOW,
        window_fast=config.MACD_FAST,
        window_sign=config.MACD_SIGNAL
    )
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    df["macd_hist_prev"] = df["macd_hist"].shift(1)

    # === Bollinger Bands ===
    bb = ta.volatility.BollingerBands(
        df["close"],
        window=config.BB_PERIOD,
        window_dev=config.BB_STD
    )
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_pct"] = bb.bollinger_pband()  # 0 = at lower, 1 = at upper
    # BB width for squeeze detection
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # === ATR (Average True Range) ===
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=config.ATR_PERIOD
    )

    # === Volume ===
    df["vol_ma"] = df["volume"].rolling(window=20).mean()
    df["vol_spike"] = df["volume"] > (df["vol_ma"] * config.VOLUME_SPIKE_MULT)

    # === Stochastic RSI ===
    stoch = ta.momentum.StochRSIIndicator(
        df["close"], window=config.STOCH_RSI_PERIOD
    )
    df["stoch_k"] = stoch.stochrsi_k()
    df["stoch_d"] = stoch.stochrsi_d()

    # === Additional Confluence ===
    # VWAP approximation (reset per session — use cumulative for crypto)
    df["vwap"] = (df["volume"] * (df["high"] + df["low"] + df["close"]) / 3).cumsum() / df["volume"].cumsum()

    # Price position relative to VWAP
    df["above_vwap"] = df["close"] > df["vwap"]

    # === SuperTrend ===
    df = calculate_supertrend(df)

    # === Ichimoku Cloud ===
    df = calculate_ichimoku(df)

    # === ADX / +DI / -DI ===
    df = calculate_adx(df)

    # === OBV ===
    df = calculate_obv(df)

    return df


def analyze_full(candles_df: pd.DataFrame) -> dict:
    """
    Full technical analysis on a DataFrame, returning a dict like the JS bot's
    TechnicalAnalysis.analyze(). Expects df already has add_all_indicators() applied.
    Returns dict with: price, rsi, macd, bb, atr, stochastic, adx, obv, vwap,
                       supertrend, ema, ichimoku, volume, avgVolume, candles
    """
    if candles_df.empty or len(candles_df) < 10:
        return {}

    last = candles_df.iloc[-1]
    prev = candles_df.iloc[-2] if len(candles_df) >= 2 else last

    def safe(val, default=0):
        """Safely convert to float, returning default if NaN."""
        try:
            v = float(val)
            if np.isnan(v):
                return default
            return v
        except (TypeError, ValueError):
            return default

    analysis = {
        "price": safe(last.get("close")),
        "open": safe(last.get("open")),
        "high": safe(last.get("high")),
        "low": safe(last.get("low")),
        "close": safe(last.get("close")),
        "rsi": safe(last.get("rsi"), 50),
        "macd": {
            "macd": safe(last.get("macd")),
            "signal": safe(last.get("macd_signal")),
            "histogram": safe(last.get("macd_hist")),
            "prev_histogram": safe(last.get("macd_hist_prev")),
        },
        "bb": {
            "upper": safe(last.get("bb_upper")),
            "lower": safe(last.get("bb_lower")),
            "mid": safe(last.get("bb_mid")),
            "pct": safe(last.get("bb_pct"), 0.5),
            "width": safe(last.get("bb_width"), 0.02),
        },
        "atr": safe(last.get("atr")),
        "stochastic": {
            "k": safe(last.get("stoch_k"), 50),
            "d": safe(last.get("stoch_d"), 50),
        },
        "adx": {
            "value": safe(last.get("adx"), 20),
            "plus_di": safe(last.get("plus_di"), 0),
            "minus_di": safe(last.get("minus_di"), 0),
        },
        "obv": safe(last.get("obv")),
        "vwap": safe(last.get("vwap")),
        "supertrend": {
            "value": safe(last.get("supertrend")),
            "direction": int(safe(last.get("supertrend_direction"), 1)),
        },
        "ema": {
            "ema9": safe(last.get("ema9")),
            "ema21": safe(last.get("ema21")),
            "ema50": safe(last.get("ema50")),
        },
        "ichimoku": {
            "tenkan": safe(last.get("tenkan_sen")),
            "kijun": safe(last.get("kijun_sen")),
            "spanA": safe(last.get("senkou_span_a")),
            "spanB": safe(last.get("senkou_span_b")),
        },
        "volume": safe(last.get("volume")),
        "avgVolume": safe(last.get("vol_ma")),
        # Include last few candles for pattern detection
        "candles": {
            "last_green": safe(last.get("close")) > safe(last.get("open")),
            "prev_green": safe(prev.get("close")) > safe(prev.get("open")),
            "last_body": abs(safe(last.get("close")) - safe(last.get("open"))),
            "last_range": safe(last.get("high")) - safe(last.get("low")),
        },
    }

    return analysis


def get_signal_strength(df: pd.DataFrame) -> dict:
    """
    Analyze the latest candle and return signal strength.
    Returns dict with 'direction' ('LONG', 'SHORT', 'NONE') and 'confluence' score (0-6).
    """
    if df.empty or len(df) < config.EMA_SLOW + 5:
        return {"direction": "NONE", "confluence": 0, "reasons": []}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    long_score = 0
    short_score = 0
    long_reasons = []
    short_reasons = []

    # 1. Trend alignment (EMA cross)
    if last["trend_bullish"]:
        long_score += 1
        long_reasons.append("EMA50>EMA200 (uptrend)")
    else:
        short_score += 1
        short_reasons.append("EMA50<EMA200 (downtrend)")

    # 2. RSI in entry zone
    rsi = last["rsi"]
    if config.RSI_LONG_ZONE[0] <= rsi <= config.RSI_LONG_ZONE[1]:
        long_score += 1
        long_reasons.append(f"RSI={rsi:.1f} in long zone")
    elif config.RSI_SHORT_ZONE[0] <= rsi <= config.RSI_SHORT_ZONE[1]:
        short_score += 1
        short_reasons.append(f"RSI={rsi:.1f} in short zone")

    # 3. MACD histogram momentum
    if last["macd_hist"] > 0 and last["macd_hist"] > prev["macd_hist"]:
        long_score += 1
        long_reasons.append("MACD histogram positive & rising")
    elif last["macd_hist"] > 0 and prev["macd_hist"] <= 0:
        long_score += 1
        long_reasons.append("MACD histogram turned positive")
    elif last["macd_hist"] < 0 and last["macd_hist"] < prev["macd_hist"]:
        short_score += 1
        short_reasons.append("MACD histogram negative & falling")
    elif last["macd_hist"] < 0 and prev["macd_hist"] >= 0:
        short_score += 1
        short_reasons.append("MACD histogram turned negative")

    # 4. Bollinger Band position
    if last["bb_pct"] <= 0.30:  # lower half of BB
        long_score += 1
        long_reasons.append(f"Price in lower BB zone ({last['bb_pct']:.2f})")
    elif last["bb_pct"] >= 0.70:  # upper half of BB
        short_score += 1
        short_reasons.append(f"Price in upper BB zone ({last['bb_pct']:.2f})")

    # 5. Volume spike
    if last["vol_spike"]:
        long_score += 1
        short_score += 1
        long_reasons.append("Volume spike confirmed")
        short_reasons.append("Volume spike confirmed")

    # 6. Stochastic RSI confirmation
    if last["stoch_k"] < 0.35 and last["stoch_k"] > last["stoch_d"]:
        long_score += 1
        long_reasons.append("StochRSI oversold + bullish cross")
    elif last["stoch_k"] > 0.65 and last["stoch_k"] < last["stoch_d"]:
        short_score += 1
        short_reasons.append("StochRSI overbought + bearish cross")

    # 7. VWAP alignment
    if last["above_vwap"] and last["trend_bullish"]:
        long_score += 1
        long_reasons.append("Price above VWAP in uptrend")
    elif not last["above_vwap"] and not last["trend_bullish"]:
        short_score += 1
        short_reasons.append("Price below VWAP in downtrend")

    # 8. Momentum — price making higher highs (last 3 candles)
    if len(df) >= 4:
        recent = df.iloc[-3:]
        if recent["close"].is_monotonic_increasing:
            long_score += 1
            long_reasons.append("3-candle momentum up")
        elif recent["close"].is_monotonic_decreasing:
            short_score += 1
            short_reasons.append("3-candle momentum down")

    # Determine direction — need minimum 4/8 confluence
    min_confluence = 4

    if long_score >= min_confluence and long_score > short_score:
        return {
            "direction": "LONG",
            "confluence": long_score,
            "reasons": long_reasons,
            "atr": last["atr"],
            "close": last["close"],
        }
    elif short_score >= min_confluence and short_score > long_score:
        return {
            "direction": "SHORT",
            "confluence": short_score,
            "reasons": short_reasons,
            "atr": last["atr"],
            "close": last["close"],
        }

    return {"direction": "NONE", "confluence": max(long_score, short_score), "reasons": []}
