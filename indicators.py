"""
Technical Indicators Module
Uses the 'ta' library for reliable indicator calculations
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


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators needed for the strategy."""
    if df.empty or len(df) < config.EMA_SLOW:
        return df

    # === Trend Indicators ===
    df["ema_fast"] = ta.trend.ema_indicator(df["close"], window=config.EMA_FAST)
    df["ema_slow"] = ta.trend.ema_indicator(df["close"], window=config.EMA_SLOW)
    df["trend_bullish"] = df["ema_fast"] > df["ema_slow"]

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

    return df


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
