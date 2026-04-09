#!/usr/bin/env python3
"""
Grid Trading Bot - Main Runner
Profits from price oscillation, not direction prediction.
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitunix_client import BitunixClient
from grid_bot import GridBotManager
from dashboard import print_dashboard
import config


async def run_grid():
    client = BitunixClient()
    manager = GridBotManager(client)
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"  GRID TRADING BOT")
    print(f"  Strategy: Buy dips, sell rallies on grid levels")
    print(f"  Pairs: {', '.join(config.TRADING_PAIRS)}")
    print(f"  Bots: {', '.join(b['name'] for b in config.BOTS)}")
    print(f"  Grid levels: 15 per symbol")
    print(f"  Scan interval: 15s (faster for grid)")
    print(f"{'='*60}\n")

    cycle = 0
    try:
        while True:
            cycle += 1
            results = manager.tick_all()

            # Build dashboard-compatible results
            all_stats = manager.get_all_stats()
            dash_results = []
            for name, stats in all_stats.items():
                closed_trades = []
                for r in results:
                    for s in r.get("sells", []):
                        if r.get("bot_key", "").startswith(name):
                            closed_trades.append(s)
                dash_results.append({
                    "bot": name,
                    "leverage": stats["leverage"],
                    "new_entries": [],
                    "closed_trades": closed_trades,
                    "stats": stats,
                })

            print_dashboard(dash_results, cycle, start_time, "paper")

            # Save every 20 cycles
            if cycle % 20 == 0:
                manager.save_report()

            await asyncio.sleep(15)  # Grid needs faster scanning

    except KeyboardInterrupt:
        print("\nShutting down grid bot...")
    finally:
        manager.save_report()
        print("Report saved.")


if __name__ == "__main__":
    asyncio.run(run_grid())
