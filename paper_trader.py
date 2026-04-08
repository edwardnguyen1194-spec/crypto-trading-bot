"""
Paper Trading Engine
Simulates trades using real market data from Bitunix without risking real money.
Tracks all trades, calculates win rate, P&L, and generates reports.
"""

import json
import time
import uuid
import os
from typing import Optional
from bitunix_client import BitunixClient
from dual_mode_strategy import DualModeStrategy
from god_mode_exits import calculate_smart_exit
from strategy import Signal
from risk_manager import RiskManager
import config


class PaperTrader:
    """Paper trading engine for a single bot configuration."""

    def __init__(self, bot_config: dict, client: BitunixClient):
        self.bot_name = bot_config["name"]
        self.leverage = bot_config["leverage"]
        self.client = client
        self.strategy = DualModeStrategy(client)  # DUAL MODE: mean reversion + trend pullback
        self.risk = RiskManager(
            bot_name=self.bot_name,
            leverage=self.leverage,
            allocation=bot_config["allocation"],
        )
        self.trade_history = []
        self.log_file = f"trades_{self.bot_name}.json"

    def get_current_prices(self) -> dict:
        """Fetch current prices for all trading pairs."""
        prices = {}
        try:
            tickers = self.client.get_tickers(config.TRADING_PAIRS)
            if isinstance(tickers, list):
                for t in tickers:
                    sym = t.get("symbol", "")
                    if sym in config.TRADING_PAIRS:
                        prices[sym] = float(t.get("lastPrice", t.get("last", 0)))
        except Exception:
            pass
        return prices

    def check_for_entries(self) -> list:
        """Scan for new trade signals and enter positions."""
        new_trades = []
        signals = self.strategy.scan_all_pairs()

        for signal in signals:
            can_trade, reason = self.risk.can_trade(signal.symbol)
            if not can_trade:
                continue

            pos_size = self.risk.calculate_position_size(signal)
            if pos_size is None:
                continue

            position_id = f"{self.bot_name}_{signal.symbol}_{uuid.uuid4().hex[:8]}"

            self.risk.open_position(signal, pos_size, position_id)

            trade_entry = {
                "id": position_id,
                "bot": self.bot_name,
                "leverage": self.leverage,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "qty": pos_size["qty"],
                "margin": pos_size["margin_required"],
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "confluence": signal.confluence,
                "reasons": signal.reasons,
                "open_time": time.time(),
                "status": "open",
            }
            new_trades.append(trade_entry)

        return new_trades

    def check_for_exits(self) -> list:
        """Check open positions for exit conditions."""
        prices = self.get_current_prices()
        if not prices:
            return []

        exits = self.risk.check_exits(prices)
        closed_trades = []

        for position_id, exit_price, reason in exits:
            result = self.risk.close_position(position_id, exit_price, reason)
            if result:
                self.trade_history.append(result)
                closed_trades.append(result)

        return closed_trades

    def tick(self) -> dict:
        """
        Run one cycle of the paper trading bot.
        Returns dict with entries, exits, and current stats.
        """
        new_entries = self.check_for_entries()
        closed_trades = self.check_for_exits()
        stats = self.risk.get_stats()

        return {
            "bot": self.bot_name,
            "leverage": self.leverage,
            "new_entries": new_entries,
            "closed_trades": closed_trades,
            "stats": stats,
        }

    def save_trades(self):
        """Save trade history to file."""
        data = {
            "bot_name": self.bot_name,
            "leverage": self.leverage,
            "trades": self.trade_history,
            "stats": self.risk.get_stats(),
            "saved_at": time.time(),
        }
        path = os.path.join(os.path.dirname(__file__), self.log_file)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def get_report(self) -> dict:
        """Generate a comprehensive performance report."""
        stats = self.risk.get_stats()
        closed = self.trade_history

        if not closed:
            return {**stats, "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
                    "max_drawdown": 0, "sharpe": 0, "trades_by_symbol": {},
                    "trades_by_reason": {}}

        wins = [t for t in closed if t["win"]]
        losses = [t for t in closed if not t["win"]]

        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Max drawdown
        running_pnl = 0
        peak = 0
        max_dd = 0
        for t in closed:
            running_pnl += t["pnl"]
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd

        # Trades by symbol
        by_symbol = {}
        for t in closed:
            sym = t["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = {"total": 0, "wins": 0, "pnl": 0}
            by_symbol[sym]["total"] += 1
            if t["win"]:
                by_symbol[sym]["wins"] += 1
            by_symbol[sym]["pnl"] += t["pnl"]

        # Win rate by symbol
        for sym in by_symbol:
            s = by_symbol[sym]
            s["win_rate"] = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0

        # Trades by close reason
        by_reason = {}
        for t in closed:
            r = t.get("reason", "unknown")
            if r not in by_reason:
                by_reason[r] = {"total": 0, "wins": 0}
            by_reason[r]["total"] += 1
            if t["win"]:
                by_reason[r]["wins"] += 1

        return {
            **stats,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_dd,
            "trades_by_symbol": by_symbol,
            "trades_by_reason": by_reason,
        }
