"""
Exit Manager - Smart Trade Exit Logic
======================================
Ported from proven JavaScript bot (94.8% WR).

Exit stages:
1. Initial: Wide SL at 2.5x ATR (survive noise)
2. Breakeven: After 0.5x ATR profit → SL to entry (CANNOT LOSE)
3. Trailing: After breakeven → trail at 0.4x ATR distance
4. Target: TP at 1.5x ATR (tight wins)

Time stops:
- In profit: NO time stop (let winners run)
- At breakeven: 12 hours
- At loss: 8 hours
"""

import config


class ExitManager:
    """Smart exit management with breakeven + trailing."""

    @staticmethod
    def update_exit_levels(pos: dict, current_price: float) -> dict:
        """
        Update stop loss based on current price.
        Moves SL to breakeven after 0.5 ATR profit, then trails at 0.4 ATR.
        SL NEVER moves backwards (locks in profit).
        """
        entry = pos.get("entry_price", 0)
        atr = pos.get("atr", 0)
        direction = pos.get("direction", "LONG")

        if atr <= 0 or entry <= 0:
            return pos

        if direction == "LONG":
            profit_atr = (current_price - entry) / atr

            if profit_atr >= config.BREAKEVEN_ATR:
                # Breakeven + trailing stage
                trail_distance = atr * config.TRAILING_DISTANCE_ATR
                new_sl = current_price - trail_distance
                # Always at least breakeven
                new_sl = max(new_sl, entry)
                # Never move backwards
                existing_sl = pos.get("stop_loss", entry - atr * config.SL_ATR_MULT)
                pos["stop_loss"] = max(new_sl, existing_sl)
                pos["exit_stage"] = "trailing" if profit_atr > config.BREAKEVEN_ATR * 1.5 else "breakeven"
                pos["trailing_active"] = True
            else:
                pos["exit_stage"] = "initial"

        elif direction == "SHORT":
            profit_atr = (entry - current_price) / atr

            if profit_atr >= config.BREAKEVEN_ATR:
                trail_distance = atr * config.TRAILING_DISTANCE_ATR
                new_sl = current_price + trail_distance
                new_sl = min(new_sl, entry)
                existing_sl = pos.get("stop_loss", entry + atr * config.SL_ATR_MULT)
                pos["stop_loss"] = min(new_sl, existing_sl)
                pos["exit_stage"] = "trailing" if profit_atr > config.BREAKEVEN_ATR * 1.5 else "breakeven"
                pos["trailing_active"] = True
            else:
                pos["exit_stage"] = "initial"

        return pos

    @staticmethod
    def check_time_stop(pos: dict, hours_open: float) -> bool:
        """
        Check if the position should be closed due to time stop.
        - In profit: no time stop (let winners run)
        - At breakeven: 12h
        - At loss: 8h
        """
        stage = pos.get("exit_stage", "initial")

        if stage == "trailing":
            # In profit — no time stop, let it run
            return False
        if stage == "breakeven":
            return hours_open >= config.TIME_STOP_HOURS  # 12h
        # Initial stage (at loss or neutral)
        return hours_open >= 8  # tighter 8h time stop when losing
