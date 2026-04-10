"""
Smart Strategy - 5-Strategy Weighted Composite Engine
======================================================
Ported from the proven JavaScript bot that achieves 94.8% win rate.

Five weighted strategies analyze each candle and contribute a composite
score. Trades are only taken when the composite score and confluence
exceed minimum thresholds. ADX is used for regime detection in the scan
loop and modifies requirements based on market conditions.

Weights:
- trend_momentum:   25%
- breakout:         20%
- multi_timeframe:  25%
- mean_reversion:   15%
- scalp:            15%
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from indicators import build_dataframe, add_all_indicators, analyze_full
from strategy import Signal
import config


class SmartStrategy:
    """5-strategy weighted composite scoring engine ported from proven JS bot (94.8% WR)."""

    def __init__(self, client):
        self.client = client
        self.strategies = [
            {"name": "trend_momentum", "weight": config.STRATEGY_WEIGHTS["trend_momentum"], "fn": self.trend_momentum},
            {"name": "mean_reversion", "weight": config.STRATEGY_WEIGHTS["mean_reversion"], "fn": self.mean_reversion},
            {"name": "breakout", "weight": config.STRATEGY_WEIGHTS["breakout"], "fn": self.breakout},
            {"name": "scalp", "weight": config.STRATEGY_WEIGHTS["scalp"], "fn": self.scalp},
            {"name": "multi_timeframe", "weight": config.STRATEGY_WEIGHTS["multi_timeframe"], "fn": self.multi_timeframe_confluence},
        ]
        # Cache (symbol_timeframe -> (df, fetch_time))
        self._cache = {}
        self._cache_ttl = {"5m": 20, "15m": 50, "1h": 120, "4h": 300}

    # ─── Data Fetching ──────────────────────────────────────────────────────

    def _get_data(self, symbol: str, timeframe: str):
        """Fetch and cache kline data with indicators applied."""
        cache_key = f"{symbol}_{timeframe}"
        now = time.time()

        if cache_key in self._cache:
            data, fetch_time = self._cache[cache_key]
            if now - fetch_time < self._cache_ttl.get(timeframe, 120):
                return data

        try:
            raw = self.client.get_klines(symbol, timeframe, config.KLINE_LIMIT)
            df = build_dataframe(raw)
            df = add_all_indicators(df)
        except Exception:
            return None

        self._cache[cache_key] = (df, now)
        return df

    # ─── Strategy #1: Trend Momentum (25% weight) ──────────────────────────

    def trend_momentum(self, analysis: dict) -> dict:
        """
        Trend Momentum: EMA alignment + ADX strength + MACD + SuperTrend + Volume.
        Looks for strong trending markets with momentum confirmation.
        """
        score_long = 0
        score_short = 0
        reasons = []

        if not analysis:
            return {"long": 0, "short": 0, "reasons": []}

        ema = analysis.get("ema", {})
        ema9 = ema.get("ema9", 0)
        ema21 = ema.get("ema21", 0)
        ema50 = ema.get("ema50", 0)
        price = analysis.get("price", 0)

        # EMA alignment (25 points)
        if ema9 and ema21 and ema50:
            if ema9 > ema21 > ema50 and price > ema9:
                score_long += 25
                reasons.append("EMA stacked bullish (9>21>50)")
            elif ema9 < ema21 < ema50 and price < ema9:
                score_short += 25
                reasons.append("EMA stacked bearish (9<21<50)")

        # ADX strength (20 points)
        adx = analysis.get("adx", {})
        adx_val = adx.get("value", 0)
        plus_di = adx.get("plus_di", 0)
        minus_di = adx.get("minus_di", 0)

        if adx_val > 25:
            if plus_di > minus_di:
                score_long += 20
                reasons.append(f"ADX={adx_val:.0f} strong uptrend (+DI>-DI)")
            elif minus_di > plus_di:
                score_short += 20
                reasons.append(f"ADX={adx_val:.0f} strong downtrend (-DI>+DI)")
        elif adx_val > 20:
            if plus_di > minus_di:
                score_long += 10
            elif minus_di > plus_di:
                score_short += 10

        # MACD momentum (20 points)
        macd = analysis.get("macd", {})
        macd_line = macd.get("macd", 0)
        macd_signal = macd.get("signal", 0)
        macd_hist = macd.get("histogram", 0)
        prev_hist = macd.get("prev_histogram", 0)

        if macd_line > macd_signal and macd_hist > 0 and macd_hist > prev_hist:
            score_long += 20
            reasons.append("MACD bullish & rising")
        elif macd_line < macd_signal and macd_hist < 0 and macd_hist < prev_hist:
            score_short += 20
            reasons.append("MACD bearish & falling")

        # SuperTrend (20 points)
        st = analysis.get("supertrend", {})
        st_dir = st.get("direction", 0)
        st_val = st.get("value", 0)

        if st_dir == 1 and price > st_val:
            score_long += 20
            reasons.append("SuperTrend bullish")
        elif st_dir == -1 and price < st_val:
            score_short += 20
            reasons.append("SuperTrend bearish")

        # Volume confirmation (15 points)
        volume = analysis.get("volume", 0)
        avg_volume = analysis.get("avgVolume", 1)
        if avg_volume > 0 and volume > avg_volume * 1.2:
            # Direction matches prevailing signal
            if score_long > score_short:
                score_long += 15
                reasons.append("Volume spike confirms long")
            elif score_short > score_long:
                score_short += 15
                reasons.append("Volume spike confirms short")

        return {"long": score_long, "short": score_short, "reasons": reasons}

    # ─── Strategy #2: Mean Reversion (15% weight) ──────────────────────────

    def mean_reversion(self, analysis: dict) -> dict:
        """
        Mean Reversion: RSI extremes + BB touch + Stochastic + VWAP deviation.
        Looks for oversold/overbought bounces in ranging markets.
        """
        score_long = 0
        score_short = 0
        reasons = []

        if not analysis:
            return {"long": 0, "short": 0, "reasons": []}

        # RSI extremes (30 points)
        rsi = analysis.get("rsi", 50)
        if rsi < 30:
            score_long += 30
            reasons.append(f"RSI={rsi:.1f} oversold")
        elif rsi < 35:
            score_long += 20
            reasons.append(f"RSI={rsi:.1f} approaching oversold")
        elif rsi > 70:
            score_short += 30
            reasons.append(f"RSI={rsi:.1f} overbought")
        elif rsi > 65:
            score_short += 20
            reasons.append(f"RSI={rsi:.1f} approaching overbought")

        # Bollinger Band touch (25 points)
        bb = analysis.get("bb", {})
        bb_lower = bb.get("lower", 0)
        bb_upper = bb.get("upper", 0)
        price = analysis.get("price", 0)

        if bb_lower > 0 and price <= bb_lower * 1.002:
            score_long += 25
            reasons.append("Price at BB lower band")
        elif bb_upper > 0 and price >= bb_upper * 0.998:
            score_short += 25
            reasons.append("Price at BB upper band")

        # Stochastic (25 points)
        stoch = analysis.get("stochastic", {})
        stoch_k = stoch.get("k", 50)
        stoch_d = stoch.get("d", 50)

        if stoch_k < 20 and stoch_k > stoch_d:
            score_long += 25
            reasons.append("Stoch oversold bullish cross")
        elif stoch_k > 80 and stoch_k < stoch_d:
            score_short += 25
            reasons.append("Stoch overbought bearish cross")

        # VWAP deviation (20 points)
        vwap = analysis.get("vwap", 0)
        if vwap > 0 and price > 0:
            dev_pct = (price - vwap) / vwap * 100
            if dev_pct < -1.5:  # 1.5% below VWAP
                score_long += 20
                reasons.append(f"Price {dev_pct:.1f}% below VWAP")
            elif dev_pct > 1.5:
                score_short += 20
                reasons.append(f"Price {dev_pct:.1f}% above VWAP")

        return {"long": score_long, "short": score_short, "reasons": reasons}

    # ─── Strategy #3: Breakout (20% weight) ─────────────────────────────────

    def breakout(self, analysis: dict) -> dict:
        """
        Breakout: BB squeeze + BB break + Volume spike + ADX confirmation.
        Looks for range breakouts after volatility contractions.
        """
        score_long = 0
        score_short = 0
        reasons = []

        if not analysis:
            return {"long": 0, "short": 0, "reasons": []}

        bb = analysis.get("bb", {})
        bb_width = bb.get("width", 0.05)
        bb_upper = bb.get("upper", 0)
        bb_lower = bb.get("lower", 0)
        bb_mid = bb.get("mid", 0)
        price = analysis.get("price", 0)

        # BB squeeze (width < 3%) — setup for breakout
        squeeze = bb_width < 0.03

        # BB breakout (35 points)
        if bb_upper > 0 and price > bb_upper:
            score_long += 35
            reasons.append("Price broke above BB upper")
            if squeeze:
                score_long += 10
                reasons.append("BB squeeze breakout (explosive)")
        elif bb_lower > 0 and price < bb_lower:
            score_short += 35
            reasons.append("Price broke below BB lower")
            if squeeze:
                score_short += 10
                reasons.append("BB squeeze breakdown (explosive)")

        # Volume spike on breakout (30 points)
        volume = analysis.get("volume", 0)
        avg_volume = analysis.get("avgVolume", 1)
        if avg_volume > 0 and volume > avg_volume * 1.5:
            if score_long > score_short:
                score_long += 30
                reasons.append(f"Volume {volume/avg_volume:.1f}x confirms breakout")
            elif score_short > score_long:
                score_short += 30
                reasons.append(f"Volume {volume/avg_volume:.1f}x confirms breakdown")

        # ADX confirmation (25 points)
        adx = analysis.get("adx", {})
        adx_val = adx.get("value", 0)
        if adx_val > 20:
            if score_long > score_short:
                score_long += 25
                reasons.append(f"ADX={adx_val:.0f} confirms trend")
            elif score_short > score_long:
                score_short += 25

        return {"long": score_long, "short": score_short, "reasons": reasons}

    # ─── Strategy #4: Scalp (15% weight) ────────────────────────────────────

    def scalp(self, analysis: dict) -> dict:
        """
        Scalp: RSI momentum zones + Stochastic crossover + EMA9 proximity + MACD.
        Fast-moving high-frequency signals.
        """
        score_long = 0
        score_short = 0
        reasons = []

        if not analysis:
            return {"long": 0, "short": 0, "reasons": []}

        # RSI momentum zones (25 points) — not extremes, but bullish/bearish momentum
        rsi = analysis.get("rsi", 50)
        if 50 < rsi < 65:
            score_long += 25
            reasons.append(f"RSI={rsi:.0f} bullish momentum zone")
        elif 35 < rsi < 50:
            score_short += 25
            reasons.append(f"RSI={rsi:.0f} bearish momentum zone")

        # Stochastic crossover (25 points)
        stoch = analysis.get("stochastic", {})
        stoch_k = stoch.get("k", 50)
        stoch_d = stoch.get("d", 50)

        if stoch_k > stoch_d and 20 < stoch_k < 80:
            score_long += 25
            reasons.append("Stoch bullish crossover")
        elif stoch_k < stoch_d and 20 < stoch_k < 80:
            score_short += 25
            reasons.append("Stoch bearish crossover")

        # EMA9 proximity (30 points) — price bouncing off EMA9
        ema = analysis.get("ema", {})
        ema9 = ema.get("ema9", 0)
        ema21 = ema.get("ema21", 0)
        price = analysis.get("price", 0)

        if ema9 > 0 and ema21 > 0 and price > 0:
            ema9_dist = abs(price - ema9) / price * 100
            if ema9_dist < 0.3 and ema9 > ema21:  # within 0.3% of EMA9, uptrend
                score_long += 30
                reasons.append("Price bouncing off EMA9 (uptrend)")
            elif ema9_dist < 0.3 and ema9 < ema21:
                score_short += 30
                reasons.append("Price rejecting EMA9 (downtrend)")

        # MACD histogram (20 points)
        macd = analysis.get("macd", {})
        macd_hist = macd.get("histogram", 0)
        prev_hist = macd.get("prev_histogram", 0)

        if macd_hist > 0 and macd_hist > prev_hist:
            score_long += 20
            reasons.append("MACD hist rising")
        elif macd_hist < 0 and macd_hist < prev_hist:
            score_short += 20
            reasons.append("MACD hist falling")

        return {"long": score_long, "short": score_short, "reasons": reasons}

    # ─── Strategy #5: Multi-Timeframe Confluence (25% weight) ──────────────

    def multi_timeframe_confluence(self, analysis: dict, mtf_analyses: dict = None) -> dict:
        """
        MTF Confluence: Current TF trend + higher TF confirmations + Ichimoku.
        The most heavily weighted strategy because MTF alignment is the strongest signal.
        """
        score_long = 0
        score_short = 0
        reasons = []

        if not analysis:
            return {"long": 0, "short": 0, "reasons": []}

        # Current timeframe trend (20 points)
        ema = analysis.get("ema", {})
        ema21 = ema.get("ema21", 0)
        ema50 = ema.get("ema50", 0)
        price = analysis.get("price", 0)

        if ema21 > ema50 and price > ema21:
            score_long += 20
            reasons.append("Current TF: bullish EMA structure")
        elif ema21 < ema50 and price < ema21:
            score_short += 20
            reasons.append("Current TF: bearish EMA structure")

        # Higher timeframe confirmations (30 points — 15 each)
        if mtf_analyses:
            for tf_name in ("1h", "4h"):
                htf = mtf_analyses.get(tf_name)
                if not htf:
                    continue
                htf_ema = htf.get("ema", {})
                htf_ema21 = htf_ema.get("ema21", 0)
                htf_ema50 = htf_ema.get("ema50", 0)
                htf_price = htf.get("price", 0)

                if htf_ema21 > htf_ema50 and htf_price > htf_ema21:
                    score_long += 15
                    reasons.append(f"{tf_name} confirms bullish")
                elif htf_ema21 < htf_ema50 and htf_price < htf_ema21:
                    score_short += 15
                    reasons.append(f"{tf_name} confirms bearish")

        # Ichimoku Cloud (30 points)
        ichi = analysis.get("ichimoku", {})
        tenkan = ichi.get("tenkan", 0)
        kijun = ichi.get("kijun", 0)
        span_a = ichi.get("spanA", 0)
        span_b = ichi.get("spanB", 0)

        if span_a and span_b and price > 0:
            cloud_top = max(span_a, span_b)
            cloud_bottom = min(span_a, span_b)

            if price > cloud_top:
                score_long += 20
                reasons.append("Price above Ichimoku cloud")
            elif price < cloud_bottom:
                score_short += 20
                reasons.append("Price below Ichimoku cloud")

        # Tenkan/Kijun crossover (20 points)
        if tenkan and kijun:
            if tenkan > kijun:
                score_long += 10
                reasons.append("Tenkan > Kijun (bullish)")
            elif tenkan < kijun:
                score_short += 10
                reasons.append("Kijun > Tenkan (bearish)")

        return {"long": score_long, "short": score_short, "reasons": reasons}

    # ─── Evaluation ─────────────────────────────────────────────────────────

    def evaluate(self, analysis: dict, mtf_analyses: dict = None) -> dict:
        """
        Run all 5 strategies, calculate weighted composite score & confluence.
        Returns dict with: action, direction, score, confluence, reasons.
        """
        if not analysis:
            return {
                "action": "HOLD",
                "direction": None,
                "score": 0,
                "confluence": 0,
                "reasons": [],
                "strategies": {},
            }

        weighted_long = 0.0
        weighted_short = 0.0
        confluence_long = 0
        confluence_short = 0
        all_reasons = []
        strategies_detail = {}

        for strat in self.strategies:
            name = strat["name"]
            weight = strat["weight"]
            fn = strat["fn"]

            if name == "multi_timeframe":
                result = fn(analysis, mtf_analyses)
            else:
                result = fn(analysis)

            long_score = result.get("long", 0)
            short_score = result.get("short", 0)

            weighted_long += long_score * weight
            weighted_short += short_score * weight

            # Confluence: strategy counts if it produced a decent signal
            if long_score >= 30:
                confluence_long += 1
            if short_score >= 30:
                confluence_short += 1

            if result.get("reasons"):
                all_reasons.extend([f"[{name}] {r}" for r in result["reasons"]])

            strategies_detail[name] = {
                "long": long_score,
                "short": short_score,
                "weight": weight,
            }

        # Determine direction from net score
        net_score = weighted_long - weighted_short

        if net_score > 0:
            direction = "LONG"
            score = weighted_long
            confluence = confluence_long
        elif net_score < 0:
            direction = "SHORT"
            score = weighted_short
            confluence = confluence_short
        else:
            direction = None
            score = 0
            confluence = 0

        # Minimum thresholds
        if (score < config.MIN_COMPOSITE_SCORE or
                confluence < config.MIN_CONFLUENCE or
                direction is None):
            return {
                "action": "HOLD",
                "direction": direction,
                "score": score,
                "net_score": net_score,
                "confluence": confluence,
                "reasons": all_reasons,
                "strategies": strategies_detail,
            }

        return {
            "action": "TRADE",
            "direction": direction,
            "score": score,
            "net_score": net_score,
            "confluence": confluence,
            "reasons": all_reasons,
            "strategies": strategies_detail,
        }

    # ─── Regime Detection Helpers ──────────────────────────────────────────

    @staticmethod
    def is_dead_hours() -> bool:
        """Check if current time is in dead hours (10pm-8am ET)."""
        # ET is UTC-5 (or UTC-4 in DST). Use UTC-4 as compromise.
        et_now = datetime.now(timezone.utc) - timedelta(hours=4)
        hour = et_now.hour
        start = config.DEAD_HOURS_START
        end = config.DEAD_HOURS_END
        # 22-24 or 0-8
        if start > end:
            return hour >= start or hour < end
        return start <= hour < end

    @staticmethod
    def check_pullback_confirmation(analysis: dict, direction: str) -> bool:
        """In trending mode, last candle must confirm direction."""
        candles = analysis.get("candles", {})
        last_green = candles.get("last_green", False)
        if direction == "LONG":
            return last_green
        if direction == "SHORT":
            return not last_green
        return False

    # ─── Main Analysis Pipeline ────────────────────────────────────────────

    def analyze(self, symbol: str) -> Optional[Signal]:
        """
        Full pipeline:
        1. Fetch candles for 5m, 15m, 1h, 4h
        2. Run analyze_full() on each
        3. Run evaluate() with MTF
        4. ADX regime detection
        5. Session filter (dead hours)
        6. Build Signal with asymmetric TP/SL
        """
        # 1. Fetch data for multiple timeframes
        df_5m = self._get_data(symbol, "5m")
        df_15m = self._get_data(symbol, "15m")
        df_1h = self._get_data(symbol, "1h")
        df_4h = self._get_data(symbol, "4h")

        if df_15m is None or df_15m.empty or len(df_15m) < 60:
            return None

        # 2. Run analyze_full on each
        analysis_15m = analyze_full(df_15m)
        analysis_1h = analyze_full(df_1h) if df_1h is not None and not df_1h.empty else None
        analysis_4h = analyze_full(df_4h) if df_4h is not None and not df_4h.empty else None
        analysis_5m = analyze_full(df_5m) if df_5m is not None and not df_5m.empty else None

        if not analysis_15m:
            return None

        mtf_analyses = {}
        if analysis_1h:
            mtf_analyses["1h"] = analysis_1h
        if analysis_4h:
            mtf_analyses["4h"] = analysis_4h
        if analysis_5m:
            mtf_analyses["5m"] = analysis_5m

        # 3. Evaluate using 15m as base timeframe
        result = self.evaluate(analysis_15m, mtf_analyses)

        if result["action"] != "TRADE":
            return None

        direction = result["direction"]
        score = result["score"]
        confluence = result["confluence"]

        # 4. ADX regime detection (from JS agent._scan)
        adx_data = analysis_15m.get("adx", {})
        adx_val = adx_data.get("value", 20)
        abs_score = abs(score)

        # Momentum mode: ADX > 25 — require pullback confirmation
        if adx_val > 25:
            if not self.check_pullback_confirmation(analysis_15m, direction):
                return None  # last candle must confirm direction in trending mode

        # Mean reversion mode: ADX < 20
        elif adx_val < 20:
            bb = analysis_15m.get("bb", {})
            rsi = analysis_15m.get("rsi", 50)
            price = analysis_15m.get("price", 0)
            bb_lower = bb.get("lower", 0)
            bb_upper = bb.get("upper", 0)

            if direction == "LONG":
                # Only trade long if BB lower + RSI < 35
                if not (bb_lower > 0 and price <= bb_lower * 1.005 and rsi < 35):
                    return None
            else:  # SHORT
                if not (bb_upper > 0 and price >= bb_upper * 0.995 and rsi > 65):
                    return None

        # Transition zone: ADX 20-25 — only strongest signals
        else:
            if abs_score <= 50 or confluence < 4:
                return None

        # 5. Session filter — skip dead hours
        if self.is_dead_hours():
            return None

        # 6. Build Signal with asymmetric TP/SL
        entry_price = analysis_15m.get("price", 0)
        atr = analysis_15m.get("atr", 0)

        if entry_price <= 0 or atr <= 0:
            return None

        signal = Signal(
            symbol=symbol,
            direction=direction,
            confluence=confluence,
            entry_price=entry_price,
            atr=atr,
            reasons=result.get("reasons", [])[:8],  # cap reasons list
        )

        # Attach composite score for position sizing scaling
        signal.composite_score = abs_score
        signal.adx_value = adx_val

        # Verify R:R meets minimum (asymmetric - e.g., 1.5/2.5 = 0.6)
        if signal.risk_reward_ratio() < config.REWARD_RISK_RATIO:
            return None

        return signal

    def scan_all_pairs(self) -> list:
        """Scan all configured trading pairs and return valid signals."""
        signals = []
        for symbol in config.TRADING_PAIRS:
            try:
                signal = self.analyze(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                print(f"[SmartStrategy] Error analyzing {symbol}: {e}")
        return signals
