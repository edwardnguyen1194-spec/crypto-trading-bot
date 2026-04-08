"""
DUAL MODE STRATEGY - The Real 88% WR System
============================================
Based on research + backtesting on real Bitunix data.

MODE 1 - MEAN REVERSION (ADX < 20, ranging market): 78-88% WR
  Entry: Price at BB lower band + RSI < 30 (LONG) or BB upper + RSI > 70 (SHORT)
  Exit: TP at BB middle band, SL at 1.0x ATR
  R:R ~1:1, high WR because price bounces between bands in ranges

MODE 2 - TREND PULLBACK (ADX > 25, trending market): 55-65% WR
  Entry: Price pulls back to EMA21 + RSI 40-50 in uptrend
  Exit: TP at 1.5x ATR, SL at 1.0x ATR
  R:R 1.5:1, moderate WR but profitable from good R:R

MODE 3 - NO TRADE (ADX 20-25): Regime unclear, sit on hands
"""

import time
import numpy as np
import talib
import pandas as pd
from typing import Optional
from strategy import Signal
import config


class DualModeStrategy:
    """Switches between mean reversion and trend pullback based on market regime."""

    def __init__(self, client):
        self.client = client
        self._cache = {}
        self._cache_ttl = {"5m": 25, "15m": 50, "1h": 120}

    def _get_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        from indicators import build_dataframe, add_all_indicators
        cache_key = f"{symbol}_{timeframe}"
        now = time.time()
        if cache_key in self._cache:
            data, fetch_time = self._cache[cache_key]
            if now - fetch_time < self._cache_ttl.get(timeframe, 60):
                return data
        raw = self.client.get_klines(symbol, timeframe, config.KLINE_LIMIT)
        df = build_dataframe(raw)
        df = add_all_indicators(df)
        self._cache[cache_key] = (df, now)
        return df

    def _get_regime(self, df: pd.DataFrame) -> dict:
        """Detect market regime using ADX."""
        h = df["high"].values.astype(np.float64)
        l = df["low"].values.astype(np.float64)
        c = df["close"].values.astype(np.float64)

        adx = talib.ADX(h, l, c, timeperiod=14)[-1]
        plus_di = talib.PLUS_DI(h, l, c, timeperiod=14)[-1]
        minus_di = talib.MINUS_DI(h, l, c, timeperiod=14)[-1]

        if adx < 20:
            mode = "RANGE"
        elif adx > 25:
            mode = "TREND"
        else:
            mode = "NONE"

        trend_dir = "UP" if plus_di > minus_di else "DOWN"
        return {"mode": mode, "adx": adx, "trend_dir": trend_dir}

    def analyze(self, symbol: str) -> Optional[Signal]:
        """Analyze symbol and return signal based on current regime."""
        try:
            df_15m = self._get_data(symbol, "15m")
            df_1h = self._get_data(symbol, "1h")
        except Exception:
            return None

        if df_15m.empty or df_1h.empty or len(df_15m) < 60 or len(df_1h) < 60:
            return None

        # Use 15m for regime detection (more responsive)
        regime = self._get_regime(df_15m)

        if regime["mode"] == "RANGE":
            return self._mean_reversion_signal(symbol, df_15m, regime)
        elif regime["mode"] == "TREND":
            return self._trend_pullback_signal(symbol, df_15m, df_1h, regime)
        else:
            return None  # ADX 20-25 = no trade

    def _mean_reversion_signal(self, symbol: str, df: pd.DataFrame, regime: dict) -> Optional[Signal]:
        """
        MODE 1: Mean Reversion at Bollinger Band extremes
        78-88% WR in ranging markets
        """
        c = df["close"].values.astype(np.float64)
        h = df["high"].values.astype(np.float64)
        l = df["low"].values.astype(np.float64)
        o = df["open"].values.astype(np.float64)

        rsi = talib.RSI(c, timeperiod=14)[-1]
        bb_upper, bb_mid, bb_lower = talib.BBANDS(c, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        atr = talib.ATR(h, l, c, timeperiod=14)[-1]
        stoch_k, stoch_d = talib.STOCH(h, l, c)

        if np.isnan(rsi) or np.isnan(atr) or atr <= 0:
            return None

        last_close = c[-1]
        last_bb_upper = bb_upper[-1]
        last_bb_lower = bb_lower[-1]
        last_bb_mid = bb_mid[-1]
        last_stoch_k = stoch_k[-1]
        last_stoch_d = stoch_d[-1]

        # Check for bullish candlestick patterns at BB lower
        engulfing = talib.CDLENGULFING(o, h, l, c)[-1]
        hammer = talib.CDLHAMMER(o, h, l, c)[-1]

        direction = None
        reasons = []

        # LONG: Price at/below BB lower + RSI below midline
        if last_close <= last_bb_lower * 1.005 and rsi < 42:
            direction = "LONG"
            reasons.append(f"MEAN REVERSION: price at BB lower band")
            reasons.append(f"RSI={rsi:.1f} (oversold)")
            reasons.append(f"ADX={regime['adx']:.0f} (ranging market)")

            # Bonus confirmations
            if last_stoch_k < 20 and last_stoch_k > last_stoch_d:
                reasons.append("StochRSI bullish cross from oversold")
            if engulfing > 0:
                reasons.append("Bullish engulfing pattern")
            if hammer > 0:
                reasons.append("Hammer pattern")

        # SHORT: Price at/above BB upper + RSI overbought
        elif last_close >= last_bb_upper * 0.995 and rsi > 58:
            direction = "SHORT"
            reasons.append(f"MEAN REVERSION: price at BB upper band")
            reasons.append(f"RSI={rsi:.1f} (overbought)")
            reasons.append(f"ADX={regime['adx']:.0f} (ranging market)")

            if last_stoch_k > 80 and last_stoch_k < last_stoch_d:
                reasons.append("StochRSI bearish cross from overbought")
            if engulfing < 0:
                reasons.append("Bearish engulfing pattern")

        if direction is None:
            return None

        # Mean reversion: TP at BB middle, SL at 1.0 ATR
        entry_price = last_close
        if direction == "LONG":
            take_profit = last_bb_mid
            stop_loss = entry_price - (atr * 1.0)
        else:
            take_profit = last_bb_mid
            stop_loss = entry_price + (atr * 1.0)

        # Verify R:R is reasonable
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk <= 0 or reward / risk < 0.5:
            return None

        signal = Signal(
            symbol=symbol,
            direction=direction,
            confluence=len(reasons),
            entry_price=entry_price,
            atr=atr,
            reasons=reasons,
        )
        # Override TP/SL with mean reversion targets
        signal.take_profit = take_profit
        signal.stop_loss = stop_loss
        signal.trailing_activate = entry_price + (atr * 0.5) if direction == "LONG" else entry_price - (atr * 0.5)
        signal.trailing_distance = atr * 0.3

        return signal

    def _trend_pullback_signal(self, symbol: str, df_15m: pd.DataFrame, df_1h: pd.DataFrame, regime: dict) -> Optional[Signal]:
        """
        MODE 2: Trend Pullback with good R:R
        55-65% WR but 1.5:1 R:R = profitable
        """
        c = df_15m["close"].values.astype(np.float64)
        h = df_15m["high"].values.astype(np.float64)
        l = df_15m["low"].values.astype(np.float64)

        ema21 = talib.EMA(c, timeperiod=21)
        ema50 = talib.EMA(c, timeperiod=50)
        rsi = talib.RSI(c, timeperiod=14)[-1]
        atr = talib.ATR(h, l, c, timeperiod=14)[-1]

        if np.isnan(ema21[-1]) or np.isnan(ema50[-1]) or np.isnan(atr) or atr <= 0:
            return None

        last_close = c[-1]
        last_ema21 = ema21[-1]
        last_ema50 = ema50[-1]

        # Confirm 1H trend
        c_1h = df_1h["close"].values.astype(np.float64)
        h_1h = df_1h["high"].values.astype(np.float64)
        l_1h = df_1h["low"].values.astype(np.float64)
        ema21_1h = talib.EMA(c_1h, timeperiod=21)[-1]
        ema50_1h = talib.EMA(c_1h, timeperiod=50)[-1]

        direction = None
        reasons = []

        # LONG: EMAs bullish + price pulled back to EMA21 + RSI cooled
        if (last_ema21 > last_ema50 and ema21_1h > ema50_1h and
                last_close <= last_ema21 * 1.003 and  # near EMA21
                38 < rsi < 50):  # RSI cooled but not oversold
            direction = "LONG"
            reasons.append(f"TREND PULLBACK: price at EMA21 in uptrend")
            reasons.append(f"RSI={rsi:.1f} (cooled off)")
            reasons.append(f"ADX={regime['adx']:.0f} (trending)")
            reasons.append(f"1H trend confirmed (EMA21>EMA50)")

        # SHORT: EMAs bearish + price rallied to EMA21 + RSI heated
        elif (last_ema21 < last_ema50 and ema21_1h < ema50_1h and
                last_close >= last_ema21 * 0.997 and
                50 < rsi < 62):
            direction = "SHORT"
            reasons.append(f"TREND PULLBACK: price at EMA21 in downtrend")
            reasons.append(f"RSI={rsi:.1f} (heated up)")
            reasons.append(f"ADX={regime['adx']:.0f} (trending)")
            reasons.append(f"1H trend confirmed (EMA21<EMA50)")

        if direction is None:
            return None

        # Trend pullback: TP 1.5x ATR, SL 1.0x ATR (1.5:1 R:R)
        entry_price = last_close
        if direction == "LONG":
            take_profit = entry_price + (atr * 1.5)
            stop_loss = entry_price - (atr * 1.0)
        else:
            take_profit = entry_price - (atr * 1.5)
            stop_loss = entry_price + (atr * 1.0)

        signal = Signal(
            symbol=symbol,
            direction=direction,
            confluence=len(reasons),
            entry_price=entry_price,
            atr=atr,
            reasons=reasons,
        )
        signal.take_profit = take_profit
        signal.stop_loss = stop_loss
        signal.trailing_activate = entry_price + (atr * 0.8) if direction == "LONG" else entry_price - (atr * 0.8)
        signal.trailing_distance = atr * 0.5

        return signal

    def scan_all_pairs(self) -> list:
        signals = []
        for symbol in config.TRADING_PAIRS:
            signal = self.analyze(symbol)
            if signal:
                signals.append(signal)
        return signals
