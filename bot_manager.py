"""
Bot Manager
Runs 4 bots in parallel (20x, 30x, 40x, 50x) with shared market data.
Includes state persistence: saves/loads bot state to/from JSON files.
"""

import asyncio
import time
import json
import os
from typing import Optional
from bitunix_client import BitunixClient
from paper_trader import PaperTrader
from live_trader import LiveTrader
from auto_tuner import AutoTuner
import config


class BotManager:
    """Manages multiple trading bots running concurrently."""

    STATE_FILE_PREFIX = "state_"

    def __init__(self, mode: str = "paper", specific_leverage: int = None):
        """
        mode: 'paper' or 'live'
        specific_leverage: if set, only run that one bot
        """
        self.mode = mode
        self.client = BitunixClient()
        self.bots = []
        self.running = False
        self.cycle_count = 0
        self.start_time = None
        self.tuner = AutoTuner(target_wr=85.0)

        # Initialize bots
        bot_configs = config.BOTS
        if specific_leverage:
            bot_configs = [b for b in config.BOTS if b["leverage"] == specific_leverage]

        for bot_cfg in bot_configs:
            if mode == "paper":
                bot = PaperTrader(bot_cfg, self.client)
            else:
                bot = LiveTrader(bot_cfg, self.client)
            self.bots.append(bot)

        # Try to load persisted state on startup
        self.load_state()

    # ─── State Persistence ──────────────────────────────────────────────

    def _state_path(self, bot_name: str) -> str:
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"{self.STATE_FILE_PREFIX}{bot_name}.json",
        )

    def save_state(self):
        """Save all bot states to JSON files (survives restarts)."""
        for bot in self.bots:
            try:
                state = {
                    "bot_name": bot.bot_name,
                    "leverage": bot.leverage,
                    "allocation": bot.risk.allocation,
                    "initial_allocation": bot.risk.initial_allocation,
                    "daily_trades": bot.risk.daily_trades,
                    "daily_pnl": bot.risk.daily_pnl,
                    "daily_reset_time": bot.risk.daily_reset_time,
                    "paused": bot.risk.paused,
                    "consecutive_losses": bot.risk.consecutive_losses,
                    "cooldown_until": bot.risk.cooldown_until,
                    "open_positions": bot.risk.open_positions,
                    "trade_history": getattr(bot, "trade_history", []),
                    "saved_at": time.time(),
                }
                path = self._state_path(bot.bot_name)
                with open(path, "w") as f:
                    json.dump(state, f, indent=2, default=str)
            except Exception as e:
                print(f"[BotManager] Failed to save state for {bot.bot_name}: {e}")

    def load_state(self):
        """Load bot states from JSON files if they exist."""
        for bot in self.bots:
            path = self._state_path(bot.bot_name)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r") as f:
                    state = json.load(f)

                bot.risk.allocation = state.get("allocation", bot.risk.allocation)
                bot.risk.initial_allocation = state.get("initial_allocation", bot.risk.initial_allocation)
                bot.risk.daily_trades = state.get("daily_trades", 0)
                bot.risk.daily_pnl = state.get("daily_pnl", 0.0)
                bot.risk.daily_reset_time = state.get("daily_reset_time", bot.risk.daily_reset_time)
                bot.risk.paused = state.get("paused", False)
                bot.risk.consecutive_losses = state.get("consecutive_losses", 0)
                bot.risk.cooldown_until = state.get("cooldown_until", 0)
                # Only load open positions; closed positions stay in trade_history
                all_positions = state.get("open_positions", {})
                bot.risk.open_positions = {
                    pid: p for pid, p in all_positions.items()
                }
                if hasattr(bot, "trade_history"):
                    bot.trade_history = state.get("trade_history", [])
                print(f"[BotManager] Loaded state for {bot.bot_name} (alloc=${bot.risk.allocation:.2f})")
            except Exception as e:
                print(f"[BotManager] Failed to load state for {bot.bot_name}: {e}")

    # ─── Core Loop ──────────────────────────────────────────────────────

    def tick_all(self) -> list:
        """Run one tick for all bots sequentially."""
        results = []
        for bot in self.bots:
            try:
                result = bot.tick()
                results.append(result)
            except Exception as e:
                results.append({
                    "bot": bot.bot_name,
                    "leverage": bot.leverage,
                    "error": str(e),
                    "stats": bot.risk.get_stats() if hasattr(bot, 'risk') else {},
                })
        return results

    def get_all_stats(self) -> list:
        """Get stats from all bots."""
        stats = []
        for bot in self.bots:
            if hasattr(bot, 'get_report'):
                stats.append(bot.get_report())
            else:
                stats.append(bot.risk.get_stats())
        return stats

    def save_all(self):
        """Save trade data for all bots."""
        for bot in self.bots:
            if hasattr(bot, 'save_trades'):
                bot.save_trades()

        # Save state files (for restart resilience)
        self.save_state()

        # Save combined report
        report = {
            "mode": self.mode,
            "bots": self.get_all_stats(),
            "total_cycles": self.cycle_count,
            "uptime_hours": (time.time() - self.start_time) / 3600 if self.start_time else 0,
            "auto_tuner": self.tuner.get_current_settings(),
            "saved_at": time.time(),
        }
        path = os.path.join(os.path.dirname(__file__), "combined_report.json")
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)

    async def run(self, callback=None, interval: int = 30):
        """
        Main async loop. Ticks all bots every `interval` seconds.
        callback: optional function called after each tick with results
        """
        self.running = True
        self.start_time = time.time()

        print(f"\n{'='*60}")
        print(f"  Starting {self.mode.upper()} Trading - {len(self.bots)} bots")
        print(f"  Strategy: SmartStrategy (5-strategy composite)")
        print(f"  Pairs: {', '.join(config.TRADING_PAIRS)}")
        print(f"  Bots: {', '.join(b.bot_name for b in self.bots)}")
        print(f"  Scan interval: {interval}s")
        print(f"{'='*60}\n")

        try:
            while self.running:
                self.cycle_count += 1
                results = self.tick_all()

                # Auto-tuner: check WR and adjust strategy if needed
                all_stats = [r.get("stats", r) for r in results]
                tune_result = self.tuner.evaluate(all_stats)
                if tune_result.get("action") in ("tightened", "loosened"):
                    # Store tuner state in results for dashboard
                    for r in results:
                        r["tuner"] = tune_result

                if callback:
                    callback(results, self.cycle_count)

                # Auto-save every 10 cycles (more frequent for monitoring)
                if self.cycle_count % 10 == 0:
                    self.save_all()

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.running = False
            self.save_all()
            print("All data saved.")

    def stop(self):
        """Stop the bot manager."""
        self.running = False
