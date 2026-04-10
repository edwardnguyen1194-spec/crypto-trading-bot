"""
Risk Manager
Position sizing, drawdown protection, daily limits.
Includes:
- Volatility-based leverage
- Signal strength scaling
- Consecutive loss cooldown (5 losses → 5 min pause)
- Slippage simulation
- Funding rate tracking (stub)
- ExitManager-based exit logic
"""

import time
from typing import Optional
import config
from strategy import Signal
from exit_manager import ExitManager


class RiskManager:
    """Manages risk for a single bot instance."""

    def __init__(self, bot_name: str, leverage: int, allocation: float):
        self.bot_name = bot_name
        self.leverage = leverage
        self.base_leverage = leverage
        self.allocation = allocation
        self.initial_allocation = allocation

        # Daily tracking
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_reset_time = self._next_daily_reset()
        self.paused = False

        # Consecutive loss cooldown
        self.consecutive_losses = 0
        self.cooldown_until = 0.0  # timestamp when cooldown expires

        # Funding rate tracking (per symbol)
        self.funding_paid = {}  # symbol -> total funding paid
        self.last_funding_time = {}  # symbol -> last funding application time

        # Position tracking
        self.open_positions = {}  # symbol -> position dict

    # ─── Daily Reset ─────────────────────────────────────────────────────

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

    # ─── Trading Gate ────────────────────────────────────────────────────

    def can_trade(self, symbol: str) -> tuple:
        """
        Check if we can take a new trade.
        Returns (bool, reason_string)
        """
        self.check_daily_reset()

        # Consecutive loss cooldown
        now = time.time()
        if self.cooldown_until > now:
            remaining = int(self.cooldown_until - now)
            return False, f"Consecutive loss cooldown ({remaining}s remaining)"
        # If cooldown expired, reset counter so we can trade again
        if self.cooldown_until > 0 and self.cooldown_until <= now:
            self.consecutive_losses = 0
            self.cooldown_until = 0

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
        for pid, pos in self.open_positions.items():
            if (pos.get("symbol") == symbol and
                pos.get("status") == "closed" and
                pos.get("close_reason") == "stop_loss" and
                now - pos.get("close_time", 0) < 600):
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

    # ─── Volatility-Based Leverage ───────────────────────────────────────

    def calculate_leverage(self, atr: float, price: float) -> int:
        """
        Calculate appropriate leverage based on volatility (ATR as % of price).
        Matches JS bot logic:
          vol > 5%: 3x
          vol > 3%: 5x
          vol > 2%: 8x
          vol > 1%: 10x
          else:    15x
        Capped by bot's base leverage.
        """
        if price <= 0 or atr <= 0:
            return self.base_leverage

        vol_pct = (atr / price) * 100

        if vol_pct > 5:
            dynamic = 3
        elif vol_pct > 3:
            dynamic = 5
        elif vol_pct > 2:
            dynamic = 8
        elif vol_pct > 1:
            dynamic = 10
        else:
            dynamic = 15

        # Don't exceed the bot's base leverage setting
        return min(dynamic, self.base_leverage)

    # ─── Position Sizing ─────────────────────────────────────────────────

    def calculate_position_size(self, signal: Signal) -> dict:
        """
        Calculate position size based on risk parameters.
        - Volatility-based leverage
        - Signal strength scaling: size scales with signal confidence
          (strengthMultiplier = min(1, signalStrength/80))
        """
        # Dynamic leverage based on volatility
        dynamic_leverage = self.calculate_leverage(signal.atr, signal.entry_price)

        # Signal strength scaling
        signal_strength = getattr(signal, "composite_score", 50)
        strength_multiplier = min(1.0, signal_strength / 80.0)

        # Risk amount = allocation * risk_pct * strength_multiplier
        base_risk = self.allocation * (config.RISK_PER_TRADE_PCT / 100)
        risk_amount = base_risk * strength_multiplier

        # Distance from entry to stop loss
        sl_distance = abs(signal.entry_price - signal.stop_loss)
        if sl_distance <= 0:
            return None

        # Position size (qty) = risk_amount / sl_distance
        qty = risk_amount / sl_distance

        # Notional value
        notional = qty * signal.entry_price

        # Margin required = notional / leverage
        margin_required = notional / dynamic_leverage

        # Don't use more than 25% of remaining allocation per trade
        max_margin = self.allocation * 0.25
        if margin_required > max_margin:
            margin_required = max_margin
            notional = margin_required * dynamic_leverage
            qty = notional / signal.entry_price

        return {
            "qty": qty,
            "margin_required": margin_required,
            "notional_value": notional,
            "effective_leverage": notional / margin_required if margin_required > 0 else 0,
            "dynamic_leverage": dynamic_leverage,
            "risk_amount": risk_amount,
            "strength_multiplier": strength_multiplier,
            "sl_distance": sl_distance,
        }

    # ─── Open / Close Position ───────────────────────────────────────────

    def open_position(self, signal: Signal, position_size: dict, position_id: str):
        """Record an opened position with entry slippage."""
        # Apply adverse entry slippage
        raw_entry = signal.entry_price
        if signal.direction == "LONG":
            entry_with_slippage = raw_entry * (1 + config.ENTRY_SLIPPAGE)
        else:
            entry_with_slippage = raw_entry * (1 - config.ENTRY_SLIPPAGE)

        self.open_positions[position_id] = {
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": entry_with_slippage,
            "raw_entry_price": raw_entry,
            "qty": position_size["qty"],
            "margin_used": position_size["margin_required"],
            "dynamic_leverage": position_size.get("dynamic_leverage", self.base_leverage),
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "trailing_activate": signal.trailing_activate,
            "trailing_distance": signal.trailing_distance,
            "trailing_active": False,
            "trailing_stop": None,
            "atr": signal.atr,
            "exit_stage": "initial",
            "open_time": time.time(),
            "composite_score": getattr(signal, "composite_score", 0),
            "status": "open",
        }

        self.allocation -= position_size["margin_required"]
        self.daily_trades += 1

    def close_position(self, position_id: str, exit_price: float, reason: str) -> dict:
        """
        Close a position and calculate PnL.
        Applies adverse exit slippage.
        """
        pos = self.open_positions.get(position_id)
        if not pos or pos["status"] != "open":
            return None

        # Apply adverse exit slippage
        if pos["direction"] == "LONG":
            exit_with_slippage = exit_price * (1 - config.EXIT_SLIPPAGE)
        else:
            exit_with_slippage = exit_price * (1 + config.EXIT_SLIPPAGE)

        # Calculate PnL
        if pos["direction"] == "LONG":
            pnl_per_unit = exit_with_slippage - pos["entry_price"]
        else:
            pnl_per_unit = pos["entry_price"] - exit_with_slippage

        raw_pnl = pnl_per_unit * pos["qty"]

        # Apply Bitunix VIP 1 fees (entry + exit)
        notional_entry = pos["entry_price"] * pos["qty"]
        notional_exit = exit_with_slippage * pos["qty"]
        entry_fee = notional_entry * config.TAKER_FEE
        exit_fee = notional_exit * config.TAKER_FEE
        total_fees = entry_fee + exit_fee

        # Apply any accumulated funding
        funding = self.funding_paid.get(pos["symbol"], 0.0)

        pnl = raw_pnl - total_fees - funding
        pnl_pct = (pnl / pos["margin_used"]) * 100 if pos["margin_used"] > 0 else 0

        # Update state
        pos["status"] = "closed"
        pos["exit_price"] = exit_with_slippage
        pos["raw_exit_price"] = exit_price
        pos["pnl"] = pnl
        pos["raw_pnl"] = raw_pnl
        pos["fees"] = total_fees
        pos["funding_paid"] = funding
        pos["pnl_pct"] = pnl_pct
        pos["close_time"] = time.time()
        pos["close_reason"] = reason

        self.allocation += pos["margin_used"] + pnl
        self.daily_pnl += pnl

        # Track consecutive losses for cooldown
        if pnl <= 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= config.CONSECUTIVE_LOSS_COOLDOWN:
                self.cooldown_until = time.time() + (config.COOLDOWN_MINUTES * 60)
                print(f"[{self.bot_name}] {self.consecutive_losses} consecutive losses - pausing {config.COOLDOWN_MINUTES} min")
        else:
            # Reset counter on win
            self.consecutive_losses = 0

        # Check daily loss limit
        max_loss = self.initial_allocation * (config.MAX_DAILY_LOSS_PCT / 100)
        if self.daily_pnl <= -max_loss:
            self.paused = True

        return {
            "position_id": position_id,
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_with_slippage,
            "qty": pos["qty"],
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "duration": pos["close_time"] - pos["open_time"],
            "win": pnl > 0,
        }

    # ─── Funding Rate Tracking ────────────────────────────────────────────

    def apply_funding(self, symbol: str, funding_rate: float):
        """
        Apply funding rate to open positions in this symbol.
        Stub implementation - funding is applied every 8 hours.
        funding_rate is a decimal (e.g., 0.0001 = 0.01%).
        """
        now = time.time()
        last = self.last_funding_time.get(symbol, 0)

        # Only apply every 8 hours (28800 seconds)
        if now - last < 28800:
            return

        for pid, pos in self.open_positions.items():
            if pos.get("symbol") != symbol or pos.get("status") != "open":
                continue
            notional = pos["entry_price"] * pos["qty"]
            funding_cost = notional * funding_rate
            # Longs pay positive funding; shorts receive
            if pos["direction"] == "SHORT":
                funding_cost = -funding_cost
            self.funding_paid[symbol] = self.funding_paid.get(symbol, 0.0) + funding_cost

        self.last_funding_time[symbol] = now

    # ─── Exit Checks ──────────────────────────────────────────────────────

    def check_exits(self, current_prices: dict) -> list:
        """
        Check open positions for exit conditions using ExitManager.
        Returns list of (position_id, exit_price, exit_reason) tuples.
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

            # Smart exit management: breakeven + trailing
            ExitManager.update_exit_levels(pos, price)

            # Stop Loss
            if pos["direction"] == "LONG" and price <= pos["stop_loss"]:
                exits.append((pid, price, "stop_loss"))
                continue
            if pos["direction"] == "SHORT" and price >= pos["stop_loss"]:
                exits.append((pid, price, "stop_loss"))
                continue

            # Take Profit
            if pos["direction"] == "LONG" and price >= pos["take_profit"]:
                exits.append((pid, price, "take_profit"))
                continue
            if pos["direction"] == "SHORT" and price <= pos["take_profit"]:
                exits.append((pid, price, "take_profit"))
                continue

            # Time Stop — varies by exit stage
            hours_open = (now - pos["open_time"]) / 3600
            if ExitManager.check_time_stop(pos, hours_open):
                exits.append((pid, price, "time_stop"))
                continue

        return exits

    # ─── Stats ────────────────────────────────────────────────────────────

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
            "consecutive_losses": self.consecutive_losses,
            "in_cooldown": self.cooldown_until > time.time(),
        }
