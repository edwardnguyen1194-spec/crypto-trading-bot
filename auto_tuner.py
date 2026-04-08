"""
Auto-Tuner
Monitors win rate in real-time and adjusts strategy parameters
to maintain 88%+ WR. Runs inside the bot — no external monitoring needed.
"""

import time
import json
import os

# Thresholds
TARGET_WR = 88.0
MIN_TRADES_TO_EVALUATE = 10  # need at least 10 trades before tuning
CHECK_INTERVAL_TRADES = 5     # re-evaluate every 5 new trades


class AutoTuner:
    """Self-adjusting strategy tuner that maintains target win rate."""

    def __init__(self, target_wr: float = TARGET_WR):
        self.target_wr = target_wr
        self.last_check_trades = 0
        self.adjustments_made = []
        self.current_level = 0  # 0=normal, 1=tight, 2=very tight

        # Tuning levels — progressively stricter
        self.levels = [
            {  # Level 0: Normal (current settings)
                "name": "Normal",
                "min_confluence": 4,
                "rsi_long": (25, 50),
                "rsi_short": (50, 75),
                "bb_long_threshold": 0.30,
                "bb_short_threshold": 0.70,
                "volume_mult": 1.2,
                "stoch_oversold": 0.35,
                "stoch_overbought": 0.65,
            },
            {  # Level 1: Tight — if WR drops below 88%
                "name": "Tight",
                "min_confluence": 4,
                "rsi_long": (28, 48),
                "rsi_short": (52, 72),
                "bb_long_threshold": 0.25,
                "bb_short_threshold": 0.75,
                "volume_mult": 1.3,
                "stoch_oversold": 0.30,
                "stoch_overbought": 0.70,
            },
            {  # Level 2: Very Tight — if WR still below 88%
                "name": "Very Tight",
                "min_confluence": 5,
                "rsi_long": (30, 45),
                "rsi_short": (55, 70),
                "bb_long_threshold": 0.20,
                "bb_short_threshold": 0.80,
                "volume_mult": 1.4,
                "stoch_oversold": 0.25,
                "stoch_overbought": 0.75,
            },
        ]

    def evaluate(self, all_bot_stats: list) -> dict:
        """
        Check performance and adjust if needed.
        Returns dict with action taken.
        """
        # Aggregate stats across all bots
        total_trades = sum(s.get("total_trades", 0) for s in all_bot_stats)
        total_wins = sum(s.get("wins", 0) for s in all_bot_stats)

        # Not enough trades to evaluate yet
        if total_trades < MIN_TRADES_TO_EVALUATE:
            return {"action": "waiting", "trades": total_trades,
                    "needed": MIN_TRADES_TO_EVALUATE}

        # Only check every N new trades
        if total_trades - self.last_check_trades < CHECK_INTERVAL_TRADES:
            return {"action": "skip", "trades": total_trades}

        self.last_check_trades = total_trades
        current_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

        result = {
            "trades": total_trades,
            "wins": total_wins,
            "win_rate": current_wr,
            "target": self.target_wr,
            "level": self.current_level,
            "level_name": self.levels[self.current_level]["name"],
        }

        if current_wr >= self.target_wr:
            # WR is good — try loosening if we're too tight
            if self.current_level > 0 and current_wr >= self.target_wr + 5:
                self.current_level -= 1
                self._apply_level()
                result["action"] = "loosened"
                result["new_level"] = self.levels[self.current_level]["name"]
                self.adjustments_made.append({
                    "time": time.time(),
                    "action": "loosened",
                    "wr": current_wr,
                    "to_level": self.current_level,
                })
            else:
                result["action"] = "ok"
        else:
            # WR below target — tighten up
            if self.current_level < len(self.levels) - 1:
                self.current_level += 1
                self._apply_level()
                result["action"] = "tightened"
                result["new_level"] = self.levels[self.current_level]["name"]
                self.adjustments_made.append({
                    "time": time.time(),
                    "action": "tightened",
                    "wr": current_wr,
                    "to_level": self.current_level,
                })
            else:
                result["action"] = "max_tight"

        return result

    def _apply_level(self):
        """Apply the current tuning level to config."""
        import config
        level = self.levels[self.current_level]

        config.RSI_LONG_ZONE = level["rsi_long"]
        config.RSI_SHORT_ZONE = level["rsi_short"]
        config.VOLUME_SPIKE_MULT = level["volume_mult"]

    def get_current_settings(self) -> dict:
        """Return current tuning level settings."""
        return {
            "level": self.current_level,
            "level_name": self.levels[self.current_level]["name"],
            "settings": self.levels[self.current_level],
            "adjustments": len(self.adjustments_made),
        }

    def get_min_confluence(self) -> int:
        """Get the current minimum confluence requirement."""
        return self.levels[self.current_level]["min_confluence"]

    def get_bb_thresholds(self) -> tuple:
        """Get current Bollinger Band thresholds (long, short)."""
        level = self.levels[self.current_level]
        return level["bb_long_threshold"], level["bb_short_threshold"]

    def get_stoch_thresholds(self) -> tuple:
        """Get current StochRSI thresholds (oversold, overbought)."""
        level = self.levels[self.current_level]
        return level["stoch_oversold"], level["stoch_overbought"]
