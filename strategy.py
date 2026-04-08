"""
Multi-Timeframe Confluence Strategy
Combines signals from 1H (trend), 15m (signal), 5m (entry) timeframes
Only takes trades when 5+ out of 6 confluence factors align
"""

import time
from typing import Optional
from indicators import build_dataframe, add_all_indicators, get_signal_strength
import config


class Signal:
    """Represents a trading signal."""
    def __init__(self, symbol: str, direction: str, confluence: int,
                 entry_price: float, atr: float, reasons: list,
                 timestamp: float = None):
        self.symbol = symbol
        self.direction = direction  # LONG or SHORT
        self.confluence = confluence
        self.entry_price = entry_price
        self.atr = atr
        self.reasons = reasons
        self.timestamp = timestamp or time.time()

        # Calculate SL/TP based on ATR
        if direction == "LONG":
            self.stop_loss = entry_price - (atr * config.SL_ATR_MULT)
            self.take_profit = entry_price + (atr * config.TP_ATR_MULT)
            self.trailing_activate = entry_price + (atr * config.TRAILING_ACTIVATE_ATR)
        else:
            self.stop_loss = entry_price + (atr * config.SL_ATR_MULT)
            self.take_profit = entry_price - (atr * config.TP_ATR_MULT)
            self.trailing_activate = entry_price - (atr * config.TRAILING_ACTIVATE_ATR)

        self.trailing_distance = atr * config.TRAILING_DISTANCE_ATR

    def risk_reward_ratio(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "confluence": self.confluence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_activate": self.trailing_activate,
            "trailing_distance": self.trailing_distance,
            "atr": self.atr,
            "risk_reward": self.risk_reward_ratio(),
            "reasons": self.reasons,
            "timestamp": self.timestamp,
        }

    def __repr__(self):
        return (f"Signal({self.symbol} {self.direction} conf={self.confluence} "
                f"entry={self.entry_price:.4f} SL={self.stop_loss:.4f} "
                f"TP={self.take_profit:.4f} R:R={self.risk_reward_ratio():.1f})")


class MultiTFStrategy:
    """
    Multi-timeframe confluence strategy.
    Fetches data from 3 timeframes and only generates signals
    when enough confluence factors align.
    """

    def __init__(self, client):
        """
        client: BitunixClient or any object with get_klines(symbol, interval, limit)
        """
        self.client = client
        self._cache = {}  # symbol -> {tf -> (data, fetch_time)}
        self._cache_ttl = {
            "5m": 60,     # refresh 5m data every minute
            "15m": 120,   # refresh 15m data every 2 min
            "1h": 300,    # refresh 1h data every 5 min
        }

    def _get_data(self, symbol: str, timeframe: str) -> dict:
        """Fetch and cache kline data with indicators."""
        cache_key = f"{symbol}_{timeframe}"
        now = time.time()

        if cache_key in self._cache:
            data, fetch_time = self._cache[cache_key]
            if now - fetch_time < self._cache_ttl.get(timeframe, 120):
                return data

        raw = self.client.get_klines(symbol, timeframe, config.KLINE_LIMIT)
        df = build_dataframe(raw)
        df = add_all_indicators(df)

        self._cache[cache_key] = (df, now)
        return df

    def analyze(self, symbol: str) -> Optional[Signal]:
        """
        Run full multi-timeframe analysis for a symbol.
        Returns Signal if entry criteria met, None otherwise.
        """
        # Fetch all timeframes
        try:
            df_trend = self._get_data(symbol, config.TIMEFRAMES["trend"])   # 1H
            df_signal = self._get_data(symbol, config.TIMEFRAMES["signal"]) # 15m
            df_entry = self._get_data(symbol, config.TIMEFRAMES["entry"])   # 5m
        except Exception as e:
            return None

        # Check trend direction on 1H
        if df_trend.empty or len(df_trend) < config.EMA_SLOW + 5:
            return None

        trend_bullish = df_trend.iloc[-1].get("trend_bullish", None)
        if trend_bullish is None:
            return None

        # Get signal from 15m timeframe (RSI + MACD)
        signal_15m = get_signal_strength(df_signal)

        # Get entry signal from 5m timeframe (BB + volume + stochRSI)
        signal_5m = get_signal_strength(df_entry)

        # === Multi-TF Confluence Check ===
        # We need agreement across timeframes
        if signal_5m["direction"] == "NONE":
            return None

        # Direction must agree with trend
        direction = signal_5m["direction"]
        if direction == "LONG" and not trend_bullish:
            return None
        if direction == "SHORT" and trend_bullish:
            return None

        # Signal timeframe should agree or be neutral
        if signal_15m["direction"] != "NONE" and signal_15m["direction"] != direction:
            return None

        # Combined confluence from entry TF
        total_confluence = signal_5m["confluence"]

        # Boost from 15m alignment
        if signal_15m["direction"] == direction:
            total_confluence += 1

        # Need minimum 4 confluence points
        if total_confluence < 4:
            return None

        entry_price = signal_5m.get("close", 0)
        atr = signal_5m.get("atr", 0)

        if entry_price <= 0 or atr <= 0:
            return None

        # Build combined reasons
        reasons = signal_5m.get("reasons", [])
        if signal_15m["direction"] == direction:
            reasons.append("15m timeframe confirms direction")
        reasons.append(f"1H trend: {'bullish' if trend_bullish else 'bearish'}")

        signal = Signal(
            symbol=symbol,
            direction=direction,
            confluence=total_confluence,
            entry_price=entry_price,
            atr=atr,
            reasons=reasons,
        )

        # Final check: R:R must meet minimum
        if signal.risk_reward_ratio() < config.REWARD_RISK_RATIO:
            return None

        return signal

    def scan_all_pairs(self) -> list:
        """Scan all configured trading pairs and return valid signals."""
        signals = []
        for symbol in config.TRADING_PAIRS:
            signal = self.analyze(symbol)
            if signal:
                signals.append(signal)
        return signals
