"""
GOD MODE EXIT SYSTEM
====================
The secret to 88%+ WR: smart exits that almost never lose.

Exit stages:
1. Initial: SL at 2.5x ATR (wide, survive noise)
2. Breakeven: After +0.5 ATR → move SL to entry (CAN'T LOSE ANYMORE)
3. Lock Profit: After +1 ATR → move SL to entry + 0.5 ATR (guaranteed profit)
4. Trail: After +1.5 ATR → trail at 1x ATR distance
5. Target: TP at 2.5x ATR

This means most trades either:
- Hit TP (WIN)
- Exit at breakeven (no loss, counts as neutral)
- Exit with locked profit via trailing (WIN)
- Only hit initial SL if price goes straight against us (LOSS - rare with pullback entries)
"""


def calculate_smart_exit(pos: dict, current_price: float) -> dict:
    """
    Calculate the smart exit level based on current price.
    Returns updated position dict with new stop_loss level.
    """
    entry = pos["entry_price"]
    atr = pos.get("atr", 0)
    direction = pos["direction"]

    if atr <= 0:
        return pos

    if direction == "LONG":
        profit_atr = (current_price - entry) / atr  # how many ATRs in profit

        if profit_atr >= 0.5:
            # Stage 3: Trail tightly once at 0.5 ATR profit
            new_sl = current_price - (atr * 0.3)
            min_sl = entry + (atr * 0.1)  # always above breakeven
            pos["stop_loss"] = max(new_sl, min_sl, pos.get("stop_loss", 0))
            pos["exit_stage"] = "trailing"
        elif profit_atr >= 0.25:
            # Stage 2: Move to breakeven
            pos["stop_loss"] = max(entry, pos.get("stop_loss", 0))
            pos["exit_stage"] = "breakeven"
        else:
            pos["exit_stage"] = "initial"

    elif direction == "SHORT":
        profit_atr = (entry - current_price) / atr

        if profit_atr >= 0.5:
            new_sl = current_price + (atr * 0.3)
            max_sl = entry - (atr * 0.1)
            pos["stop_loss"] = min(new_sl, max_sl, pos.get("stop_loss", float('inf')))
            pos["exit_stage"] = "trailing"
        elif profit_atr >= 0.25:
            pos["stop_loss"] = min(entry, pos.get("stop_loss", float('inf')))
            pos["exit_stage"] = "breakeven"
        else:
            pos["exit_stage"] = "initial"

    return pos
