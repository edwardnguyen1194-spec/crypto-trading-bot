"""
Risk Manager
Position sizing, drawdown protection, daily limits
"""

import time
from typing import Optional
import config
from strategy import Signal


class RiskManager:
    """Manages risk for a single bot instance."""

    def __init__(self, bot_name: str, leverage: int, allocation: float):
        self.bot_name = bot_name
        self.leverage = leverage
        self.allocation = allocation
        self.initial_allocation = allocation

        # Daily tracking
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_reset_time = self._next_daily_reset()
        self.paused = False

        # Position tracking
        self.open_positions = {}  # symbol -> position dict

    def _next_daily_reset(self) -> float:
        """Get timestamp for next UTC midnight."""
        now = time.time()
        return now - (now % 86400) + 86400

    def check_daily_reset(self):
        """Reset daily counters if new day."""
        if time.time() >= self.daily_reset_time:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.paused = False
            self.daily_reset_time = self._next_daily_reset()

    def can_trade(self, symbol: str) -> tuple:
        """
        Check if we can take a new trade.
        Returns (bool, reason_string)
        """
        self.check_daily_reset()

        if self.paused:
            return False, "Bot paused (daily loss limit hit)"

        if self.daily_trades >= config.MAX_DAILY_TRADES:
            return False, f"Daily trade limit ({config.MAX_DAILY_TRADES}) reached"

        # Check max concurrent positions for this symbol
        positions_for_symbol = sum(
            1 for pid, p in self.open_positions.items()
            if p.get("symbol") == symbol and p.get("status") == "open"
        )
        if positions_for_symbol >= config.MAX_CONCURRENT_POSITIONS:
            return False, f"Max concurrent positions ({config.MAX_CONCURRENT_POSITIONS}) for {symbol}"

        # Cooldown after stop loss — wait 10 minutes before re-entering same symbol
        import time as _time
        for pid, pos in self.open_positions.items():
            if (pos.get("symbol") == symbol and
                pos.get("status") == "closed" and
                pos.get("close_reason") == "stop_loss" and
                _time.time() - pos.get("close_time", 0) < 600):
                return False, f"Cooldown after stop loss on {symbol} (10 min)"

        # Check daily loss limit
        max_loss = self.initial_allocation * (config.MAX_DAILY_LOSS_PCT / 100)
        if self.daily_pnl <= -max_loss:
            self.paused = True
            return False, f"Daily loss limit (-${max_loss:.2f}) reached"

        # Check if we have enough allocation
        if self.allocation <= 0:
            return False, "No allocation remaining"

        return True, "OK"

    def calculate_position_size(self, signal: Signal) -> dict:
        """
        Calculate position size based on risk parameters.
        Returns dict with qty, margin_used, effective_position_size
        """
        # Risk amount = allocation * risk_pct
        risk_amount = self.allocation * (config.RISK_PER_TRADE_PCT / 100)

        # Distance from entry to stop loss
        sl_distance = abs(signal.entry_price - signal.stop_loss)
        if sl_distance <= 0:
            return None

        # Position size in base currency (before leverage)
        # risk_amount = qty * sl_distance
        # With leverage: effective_qty = qty * leverage
        # But risk is still on the margin, so:
        # qty (in contracts/coins) = risk_amount / sl_distance
        qty = risk_amount / sl_distance

        # Notional value
        notional = qty * signal.entry_price

        # Margin required = notional / leverage
        margin_required = notional / self.leverage

        # Don't use more than 25% of remaining allocation per trade
        max_margin = self.allocation * 0.25
        if margin_required > max_margin:
            margin_required = max_margin
            notional = margin_required * self.leverage
            qty = notional / signal.entry_price

        return {
            "qty": qty,
            "margin_required": margin_required,
            "notional_value": notional,
            "effective_leverage": notional / margin_required if margin_required > 0 else 0,
            "risk_amount": risk_amount,
            "sl_distance": sl_distance,
        }

    def open_position(self, signal: Signal, position_size: dict, position_id: str):
        """Record an opened position."""
        self.open_positions[position_id] = {
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "qty": position_size["qty"],
            "margin_used": position_size["margin_required"],
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "trailing_activate": signal.trailing_activate,
            "trailing_distance": signal.trailing_distance,
            "trailing_active": False,
            "trailing_stop": None,
            "open_time": time.time(),
            "status": "open",
        }

        self.allocation -= position_size["margin_required"]
        self.daily_trades += 1

    def close_position(self, position_id: str, exit_price: float, reason: str) -> dict:
        """
        Close a position and calculate PnL.
        Returns trade result dict.
        """
        pos = self.open_positions.get(position_id)
        if not pos or pos["status"] != "open":
            return None

        # Calculate PnL
        if pos["direction"] == "LONG":
            pnl_per_unit = exit_price - pos["entry_price"]
        else:
            pnl_per_unit = pos["entry_price"] - exit_price

        raw_pnl = pnl_per_unit * pos["qty"]

        # Apply Bitunix VIP 1 fees (entry + exit)
        notional_entry = pos["entry_price"] * pos["qty"]
        notional_exit = exit_price * pos["qty"]
        entry_fee = notional_entry * config.TAKER_FEE   # market order on entry
        exit_fee = notional_exit * config.TAKER_FEE     # market order on exit
        total_fees = entry_fee + exit_fee

        pnl = raw_pnl - total_fees
        pnl_pct = (pnl / pos["margin_used"]) * 100 if pos["margin_used"] > 0 else 0

        # Update state
        pos["status"] = "closed"
        pos["exit_price"] = exit_price
        pos["pnl"] = pnl
        pos["raw_pnl"] = raw_pnl
        pos["fees"] = total_fees
        pos["pnl_pct"] = pnl_pct
        pos["close_time"] = time.time()
        pos["close_reason"] = reason

        self.allocation += pos["margin_used"] + pnl
        self.daily_pnl += pnl

        # Check daily loss limit
        max_loss = self.initial_allocation * (config.MAX_DAILY_LOSS_PCT / 100)
        if self.daily_pnl <= -max_loss:
            self.paused = True

        return {
            "position_id": position_id,
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "qty": pos["qty"],
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "duration": pos["close_time"] - pos["open_time"],
            "win": pnl > 0,
        }

    def check_exits(self, current_prices: dict) -> list:
        """
        Check all open positions for exit conditions.
        current_prices: {symbol: current_price}
        Returns list of (position_id, exit_reason) tuples.
        """
        exits = []
        now = time.time()

        for pid, pos in list(self.open_positions.items()):
            if pos["status"] != "open":
                continue

            symbol = pos["symbol"]
            price = current_prices.get(symbol)
            if price is None:
                continue

            # === Stop Loss ===
            if pos["direction"] == "LONG" and price <= pos["stop_loss"]:
                exits.append((pid, price, "stop_loss"))
                continue
            if pos["direction"] == "SHORT" and price >= pos["stop_loss"]:
                exits.append((pid, price, "stop_loss"))
                continue

            # === Take Profit ===
            if pos["direction"] == "LONG" and price >= pos["take_profit"]:
                exits.append((pid, price, "take_profit"))
                continue
            if pos["direction"] == "SHORT" and price <= pos["take_profit"]:
                exits.append((pid, price, "take_profit"))
                continue

            # === Trailing Stop ===
            if pos["direction"] == "LONG":
                if price >= pos["trailing_activate"]:
                    pos["trailing_active"] = True
                if pos["trailing_active"]:
                    new_trail = price - pos["trailing_distance"]
                    if pos["trailing_stop"] is None or new_trail > pos["trailing_stop"]:
                        pos["trailing_stop"] = new_trail
                    if price <= pos["trailing_stop"]:
                        exits.append((pid, price, "trailing_stop"))
                        continue
            else:  # SHORT
                if price <= pos["trailing_activate"]:
                    pos["trailing_active"] = True
                if pos["trailing_active"]:
                    new_trail = price + pos["trailing_distance"]
                    if pos["trailing_stop"] is None or new_trail < pos["trailing_stop"]:
                        pos["trailing_stop"] = new_trail
                    if price >= pos["trailing_stop"]:
                        exits.append((pid, price, "trailing_stop"))
                        continue

            # === Time Stop ===
            hours_open = (now - pos["open_time"]) / 3600
            if hours_open >= config.TIME_STOP_HOURS:
                exits.append((pid, price, "time_stop"))
                continue

        return exits

    def get_stats(self) -> dict:
        """Get current risk manager stats."""
        closed = [p for p in self.open_positions.values() if p["status"] == "closed"]
        open_pos = [p for p in self.open_positions.values() if p["status"] == "open"]
        wins = [p for p in closed if p.get("pnl", 0) > 0]

        total_pnl = sum(p.get("pnl", 0) for p in closed)
        win_rate = (len(wins) / len(closed) * 100) if closed else 0

        return {
            "bot_name": self.bot_name,
            "leverage": self.leverage,
            "allocation": self.allocation,
            "initial_allocation": self.initial_allocation,
            "pnl_total": total_pnl,
            "pnl_pct": (total_pnl / self.initial_allocation * 100) if self.initial_allocation > 0 else 0,
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(closed) - len(wins),
            "win_rate": win_rate,
            "open_positions": len(open_pos),
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "paused": self.paused,
        }
