"""
Live Trading Engine
Executes real trades on Bitunix using the same strategy as paper trading.
"""

import time
import uuid
from typing import Optional
from bitunix_client import BitunixClient
from strategy import MultiTFStrategy, Signal
from risk_manager import RiskManager
import config


class LiveTrader:
    """Live trading engine for a single bot configuration on Bitunix."""

    def __init__(self, bot_config: dict, client: BitunixClient):
        self.bot_name = bot_config["name"]
        self.leverage = bot_config["leverage"]
        self.client = client
        self.strategy = MultiTFStrategy(client)
        self.risk = RiskManager(
            bot_name=self.bot_name,
            leverage=self.leverage,
            allocation=bot_config["allocation"],
        )
        self.trade_history = []
        self._leverage_set = set()  # track which symbols have leverage set

    def _ensure_leverage(self, symbol: str):
        """Set leverage on Bitunix for a symbol (only once per session)."""
        if symbol not in self._leverage_set:
            try:
                self.client.change_leverage(symbol, self.leverage)
                self._leverage_set.add(symbol)
            except Exception as e:
                print(f"[{self.bot_name}] Failed to set leverage for {symbol}: {e}")

    def _get_qty_precision(self, symbol: str) -> int:
        """Determine quantity decimal precision for a symbol."""
        # Standard precisions for major pairs
        precisions = {
            "BTCUSDT": 3,
            "ETHUSDT": 2,
            "SOLUSDT": 1,
            "XRPUSDT": 0,
        }
        return precisions.get(symbol, 2)

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
        """Scan for signals and execute real orders."""
        new_trades = []
        signals = self.strategy.scan_all_pairs()

        for signal in signals:
            can_trade, reason = self.risk.can_trade(signal.symbol)
            if not can_trade:
                continue

            pos_size = self.risk.calculate_position_size(signal)
            if pos_size is None:
                continue

            # Ensure leverage is set
            self._ensure_leverage(signal.symbol)

            # Format quantity
            precision = self._get_qty_precision(signal.symbol)
            qty_str = f"{pos_size['qty']:.{precision}f}"

            # Determine order side
            side = "BUY" if signal.direction == "LONG" else "SELL"

            # Place order with SL/TP
            try:
                sl_str = f"{signal.stop_loss:.{self._price_precision(signal.symbol)}f}"
                tp_str = f"{signal.take_profit:.{self._price_precision(signal.symbol)}f}"

                result = self.client.place_order(
                    symbol=signal.symbol,
                    side=side,
                    qty=qty_str,
                    order_type="MARKET",
                    stop_loss=sl_str,
                    take_profit=tp_str,
                )

                position_id = result.get("orderId", f"{self.bot_name}_{uuid.uuid4().hex[:8]}")
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
                    "order_result": result,
                }
                new_trades.append(trade_entry)

            except Exception as e:
                print(f"[{self.bot_name}] Order failed for {signal.symbol}: {e}")

        return new_trades

    def check_for_exits(self) -> list:
        """Check positions for exit conditions and close them."""
        prices = self.get_current_prices()
        if not prices:
            return []

        exits = self.risk.check_exits(prices)
        closed_trades = []

        for position_id, exit_price, reason in exits:
            pos = self.risk.open_positions.get(position_id)
            if not pos:
                continue

            # Place close order
            close_side = "SELL" if pos["direction"] == "LONG" else "BUY"
            precision = self._get_qty_precision(pos["symbol"])
            qty_str = f"{pos['qty']:.{precision}f}"

            try:
                self.client.close_position(
                    symbol=pos["symbol"],
                    side=pos["direction"],  # original side
                    qty=qty_str,
                )

                result = self.risk.close_position(position_id, exit_price, reason)
                if result:
                    self.trade_history.append(result)
                    closed_trades.append(result)

            except Exception as e:
                print(f"[{self.bot_name}] Close order failed: {e}")

        return closed_trades

    def tick(self) -> dict:
        """Run one cycle of the live trading bot."""
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

    @staticmethod
    def _price_precision(symbol: str) -> int:
        """Price decimal precision per symbol."""
        precisions = {
            "BTCUSDT": 2,
            "ETHUSDT": 2,
            "SOLUSDT": 4,
            "XRPUSDT": 5,
        }
        return precisions.get(symbol, 4)
