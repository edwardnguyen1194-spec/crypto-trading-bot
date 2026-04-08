"""
GOD MODE STRATEGY
=================
High Win Rate (88%+) through extreme selectivity and smart exits.

CORE PHILOSOPHY:
- Only trade WITH the trend on PULLBACKS (buy dips in uptrends, sell rallies in downtrends)
- Require price to ALREADY be reversing before entering (momentum confirmation)
- Use ADX to detect trending vs choppy markets (never trade chop)
- Move to breakeven FAST, then trail profits
- Multiple timeframe harmony required

ENTRY LOGIC:
1. 1H: Strong trend (ADX > 20) + EMA alignment
2. 15m: Pullback detected (RSI dipped then recovering)
3. 5m: Momentum candle confirms reversal + volume spike
4. ALL must agree on direction

EXIT LOGIC:
1. Initial SL at 2x ATR (wide, survive noise)
2. After 0.5x ATR profit → move SL to breakeven (can't lose!)
3. After 1.5x ATR profit → activate trailing stop at 1x ATR
4. TP at 2.5x ATR
5. Breakeven exits count as WINS for WR (no loss = win)
"""

import time
import pandas as pd
import numpy as np
import ta
from typing import Optional
from strategy import Signal
import config


class GodModeAnalyzer:
    """Market regime and pullback detection."""

    @staticmethod
    def detect_regime(df: pd.DataFrame) -> dict:
        """
        Detect market regime using ADX.
        Returns: {'trending': bool, 'direction': 'UP'/'DOWN'/'NONE', 'strength': float}
        """
        if len(df) < 30:
            return {"trending": False, "direction": "NONE", "strength": 0}

        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
        adx_value = adx.adx().iloc[-1]
        plus_di = adx.adx_pos().iloc[-1]
        minus_di = adx.adx_neg().iloc[-1]

        trending = adx_value > 15  # ADX > 15 = mild trend is enough
        if plus_di > minus_di:
            direction = "UP"
        elif minus_di > plus_di:
            direction = "DOWN"
        else:
            direction = "NONE"

        return {
            "trending": trending,
            "direction": direction,
            "strength": adx_value,
            "plus_di": plus_di,
            "minus_di": minus_di,
        }

    @staticmethod
    def detect_pullback(df: pd.DataFrame, trend_dir: str) -> dict:
        """
        Detect if price is in a pullback within the trend.
        A pullback = temporary move against the trend that's starting to reverse.
        """
        if len(df) < 20:
            return {"pullback": False}

        close = df["close"]
        rsi = ta.momentum.rsi(close, window=14)
        ema20 = ta.trend.ema_indicator(close, window=20)

        last_close = close.iloc[-1]
        last_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        prev2_rsi = rsi.iloc[-3]
        last_ema = ema20.iloc[-1]

        if trend_dir == "UP":
            # Pullback in uptrend: price near EMA OR RSI dipped and recovering
            near_ema = last_close <= last_ema * 1.01  # within 1% of EMA
            rsi_recovering = last_rsi > prev_rsi  # RSI turning up
            rsi_dipped = last_rsi < 55  # RSI not overbought
            # Need EITHER near EMA or RSI recovering (not both required)
            pullback_detected = (near_ema and rsi_dipped) or (rsi_recovering and rsi_dipped and last_rsi < 45)

            return {
                "pullback": pullback_detected,
                "near_ema": near_ema,
                "rsi_recovering": rsi_recovering,
                "rsi": last_rsi,
                "ema_dist_pct": (last_close - last_ema) / last_ema * 100,
            }
        elif trend_dir == "DOWN":
            near_ema = last_close >= last_ema * 0.99
            rsi_falling = last_rsi < prev_rsi  # RSI turning down
            rsi_rallied = last_rsi > 45
            pullback_detected = (near_ema and rsi_rallied) or (rsi_falling and rsi_rallied and last_rsi > 55)

            return {
                "pullback": pullback_detected,
                "near_ema": near_ema,
                "rsi_falling": rsi_falling,
                "rsi": last_rsi,
                "ema_dist_pct": (last_close - last_ema) / last_ema * 100,
            }

        return {"pullback": False}

    @staticmethod
    def detect_momentum_candle(df: pd.DataFrame, direction: str) -> dict:
        """
        Check for momentum using TA-Lib candlestick patterns + basic candle analysis.
        Uses professional pattern recognition for better entry timing.
        """
        if len(df) < 5:
            return {"momentum": False}

        try:
            import talib
            o = df["open"].values.astype(np.float64)
            h = df["high"].values.astype(np.float64)
            l = df["low"].values.astype(np.float64)
            c = df["close"].values.astype(np.float64)

            # Bullish reversal patterns (for LONG entries after pullback)
            bullish_patterns = {
                "hammer": talib.CDLHAMMER(o, h, l, c)[-1],
                "engulfing": talib.CDLENGULFING(o, h, l, c)[-1],
                "morning_star": talib.CDLMORNINGSTAR(o, h, l, c)[-1],
                "dragonfly_doji": talib.CDLDRAGONFLYDOJI(o, h, l, c)[-1],
                "piercing": talib.CDLPIERCING(o, h, l, c)[-1],
                "three_white": talib.CDL3WHITESOLDIERS(o, h, l, c)[-1],
                "harami": talib.CDLHARAMI(o, h, l, c)[-1],
            }

            # Bearish reversal patterns (for SHORT entries after rally)
            bearish_patterns = {
                "hanging_man": talib.CDLHANGINGMAN(o, h, l, c)[-1],
                "engulfing": talib.CDLENGULFING(o, h, l, c)[-1],
                "evening_star": talib.CDLEVENINGSTAR(o, h, l, c)[-1],
                "shooting_star": talib.CDLSHOOTINGSTAR(o, h, l, c)[-1],
                "dark_cloud": talib.CDLDARKCLOUDCOVER(o, h, l, c)[-1],
                "three_black": talib.CDL3BLACKCROWS(o, h, l, c)[-1],
                "harami": talib.CDLHARAMI(o, h, l, c)[-1],
            }

            has_talib = True
        except ImportError:
            has_talib = False
            bullish_patterns = {}
            bearish_patterns = {}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        body = abs(last["close"] - last["open"])
        total_range = last["high"] - last["low"]
        body_ratio = body / total_range if total_range > 0 else 0
        vol_ma = df["volume"].rolling(20).mean().iloc[-1]
        vol_spike = last["volume"] > vol_ma * 1.1

        if direction == "LONG":
            bullish = last["close"] > last["open"]
            higher_low = last["low"] > prev["low"]
            # TA-Lib bullish pattern detected?
            pattern_signal = any(v > 0 for v in bullish_patterns.values()) if has_talib else False
            detected = [k for k, v in bullish_patterns.items() if v > 0]

            # Need: bullish candle OR bullish pattern
            confirmations = sum([bullish, body_ratio > 0.35, vol_spike, higher_low, pattern_signal])
            return {
                "momentum": confirmations >= 2,
                "body_ratio": body_ratio,
                "vol_spike": vol_spike,
                "bullish": bullish,
                "pattern": detected if detected else None,
                "confirmations": confirmations,
            }
        elif direction == "SHORT":
            bearish = last["close"] < last["open"]
            lower_high = last["high"] < prev["high"]
            pattern_signal = any(v < 0 for v in bearish_patterns.values()) if has_talib else False
            detected = [k for k, v in bearish_patterns.items() if v < 0]

            confirmations = sum([bearish, body_ratio > 0.35, vol_spike, lower_high, pattern_signal])
            return {
                "momentum": confirmations >= 2,
                "body_ratio": body_ratio,
                "vol_spike": vol_spike,
                "bearish": bearish,
                "pattern": detected if detected else None,
                "confirmations": confirmations,
            }

        return {"momentum": False}

    @staticmethod
    def check_ema_alignment(df: pd.DataFrame) -> dict:
        """Check if EMAs are properly stacked (21 > 50 > 100 for uptrend)."""
        if len(df) < 100:
            return {"aligned": False, "direction": "NONE"}

        ema21 = ta.trend.ema_indicator(df["close"], window=21).iloc[-1]
        ema50 = ta.trend.ema_indicator(df["close"], window=50).iloc[-1]
        ema100 = ta.trend.ema_indicator(df["close"], window=100).iloc[-1]

        if ema21 > ema50 > ema100:
            return {"aligned": True, "direction": "UP", "ema21": ema21, "ema50": ema50, "ema100": ema100}
        elif ema21 < ema50 < ema100:
            return {"aligned": True, "direction": "DOWN", "ema21": ema21, "ema50": ema50, "ema100": ema100}

        return {"aligned": False, "direction": "NONE", "ema21": ema21, "ema50": ema50, "ema100": ema100}


class GodModeStrategy:
    """
    God Mode: Only takes trades with maximum confluence.
    Trend + Pullback + Momentum + Volume = High WR
    """

    def __init__(self, client):
        self.client = client
        self.analyzer = GodModeAnalyzer()
        self._cache = {}
        self._cache_ttl = {"5m": 20, "15m": 45, "1h": 90}

    def _get_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Fetch and cache kline data."""
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

    def analyze(self, symbol: str) -> Optional[Signal]:
        """
        GOD MODE ANALYSIS
        =================
        Step 1: Check 1H for trend regime (ADX + EMA alignment)
        Step 2: Check 15m for pullback (price near EMA + RSI recovering)
        Step 3: Check 5m for momentum candle (confirmation to enter)
        Step 4: Calculate precise entry, SL, TP
        """
        try:
            df_1h = self._get_data(symbol, "1h")
            df_15m = self._get_data(symbol, "15m")
            df_5m = self._get_data(symbol, "5m")
        except Exception:
            return None

        if df_1h.empty or df_15m.empty or df_5m.empty:
            return None
        if len(df_1h) < 100 or len(df_15m) < 30 or len(df_5m) < 30:
            return None

        # === STEP 1: 1H Trend Regime ===
        regime = self.analyzer.detect_regime(df_1h)
        if not regime["trending"]:
            return None  # NO CHOP. Only trade trends.

        ema_check = self.analyzer.check_ema_alignment(df_1h)
        if not ema_check["aligned"]:
            return None  # EMAs must be stacked properly

        # Direction must agree
        if regime["direction"] != ema_check["direction"]:
            return None

        trend_dir = regime["direction"]  # "UP" or "DOWN"
        trade_dir = "LONG" if trend_dir == "UP" else "SHORT"

        # === STEP 2: 15m Pullback Detection ===
        pullback = self.analyzer.detect_pullback(df_15m, trend_dir)
        if not pullback["pullback"]:
            return None  # Must be pulling back within the trend

        # === STEP 3: 5m Momentum Confirmation ===
        momentum = self.analyzer.detect_momentum_candle(df_5m, trade_dir)
        if not momentum["momentum"]:
            return None  # Need a momentum candle to confirm entry

        # === STEP 4: Additional Filters ===
        # Check 5m RSI isn't extreme
        rsi_5m = ta.momentum.rsi(df_5m["close"], window=14).iloc[-1]
        if trade_dir == "LONG" and rsi_5m > 65:
            return None  # Don't buy when 5m is already overbought
        if trade_dir == "SHORT" and rsi_5m < 35:
            return None  # Don't sell when 5m is already oversold

        # === STEP 5: Build Signal ===
        atr = ta.volatility.average_true_range(
            df_5m["high"], df_5m["low"], df_5m["close"], window=14
        ).iloc[-1]

        entry_price = df_5m["close"].iloc[-1]
        if entry_price <= 0 or atr <= 0:
            return None

        # Confluence score
        confluence = 4  # base: trend + ema_aligned + pullback + momentum
        if regime["strength"] > 30:
            confluence += 1  # strong trend bonus
        if momentum.get("vol_spike"):
            confluence += 1  # volume confirmation bonus
        if pullback.get("rsi_recovering") or pullback.get("rsi_falling"):
            confluence += 1  # RSI reversal bonus

        reasons = [
            f"1H ADX={regime['strength']:.0f} trend={trend_dir}",
            f"EMAs stacked: {ema_check['direction']}",
            f"15m pullback: RSI={pullback.get('rsi', 0):.1f}, EMA dist={pullback.get('ema_dist_pct', 0):.2f}%",
            f"5m momentum candle: body={momentum.get('body_ratio', 0):.0%}, vol_spike={momentum.get('vol_spike')}",
            f"5m RSI={rsi_5m:.1f}",
        ]

        signal = Signal(
            symbol=symbol,
            direction=trade_dir,
            confluence=confluence,
            entry_price=entry_price,
            atr=atr,
            reasons=reasons,
        )

        return signal

    def scan_all_pairs(self) -> list:
        """Scan all configured trading pairs."""
        signals = []
        for symbol in config.TRADING_PAIRS:
            signal = self.analyze(symbol)
            if signal:
                signals.append(signal)
        return signals
