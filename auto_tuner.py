"""
Auto-Tuner
Monitors win rate in real-time and adjusts strategy parameters
to maintain target 85%+ WR. Runs inside the bot — no external monitoring needed.

Tunes for the Smart Strategy (5-strategy composite scoring):
- MIN_COMPOSITE_SCORE: Minimum weighted score to trade
- MIN_CONFLUENCE: Minimum strategies agreeing
- TP_ATR_MULT: Take profit ATR multiplier
- SL_ATR_MULT: Stop loss ATR multiplier
- BREAKEVEN_ATR: Breakeven move threshold
"""

import time

# Thresholds
TARGET_WR = 85.0
MIN_TRADES_TO_EVALUATE = 10  # need at least 10 trades before tuning
CHECK_INTERVAL_TRADES = 5     # re-evaluate every 5 new trades


class AutoTuner:
    """Self-adjusting strategy tuner that maintains target win rate."""

    def __init__(self, target_wr: float = TARGET_WR):
        self.target_wr = target_wr
        self.last_check_trades = 0
        self.adjustments_made = []
        self.current_level = 0  # 0=normal, 1=tight, 2=very tight

        # Tuning levels — progressively stricter for higher WR
        self.levels = [
            {  # Level 0: Normal
                "name": "Normal",
                "min_composite_score": 35,
                "min_confluence": 3,
                "tp_atr_mult": 1.5,
                "sl_atr_mult": 2.5,
                "breakeven_atr": 0.5,
            },
            {  # Level 1: Tight
                "name": "Tight",
                "min_composite_score": 45,
                "min_confluence": 4,
                "tp_atr_mult": 1.2,
                "sl_atr_mult": 3.0,
                "breakeven_atr": 0.6,
            },
            {  # Level 2: Very Tight
                "name": "Very Tight",
                "min_composite_score": 55,
                "min_confluence": 4,
                "tp_atr_mult": 1.0,
                "sl_atr_mult": 3.5,
                "breakeven_atr": 0.7,
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

        config.MIN_COMPOSITE_SCORE = level["min_composite_score"]
        config.MIN_CONFLUENCE = level["min_confluence"]
        config.TP_ATR_MULT = level["tp_atr_mult"]
        config.SL_ATR_MULT = level["sl_atr_mult"]
        config.BREAKEVEN_ATR = level["breakeven_atr"]

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

    def get_min_composite_score(self) -> float:
        """Get the current minimum composite score requirement."""
        return self.levels[self.current_level]["min_composite_score"]
