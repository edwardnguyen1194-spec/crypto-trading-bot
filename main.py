#!/usr/bin/env python3
"""
Crypto Trading Bot - Main Entry Point
Supports paper trading (testing) and live trading on Bitunix.

Usage:
  python3 main.py                    # Start paper trading (default)
  python3 main.py --mode paper       # Start paper trading
  python3 main.py --mode live        # Start live trading (USE WITH CAUTION)
  python3 main.py --mode live --leverage 20  # Live with specific bot only
  python3 main.py --report           # Show performance report
  python3 main.py --test             # Quick connectivity test
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Add project dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitunix_client import BitunixClient
from bot_manager import BotManager
from dashboard import print_dashboard
import config


def test_connection():
    """Test API connectivity and data availability."""
    print("\n=== Connection Test ===\n")

    client = BitunixClient()

    # Test public endpoint (no API key needed)
    print("[1] Testing public market data...")
    try:
        tickers = client.get_tickers()
        if isinstance(tickers, list) and len(tickers) > 0:
            print(f"    OK - Got {len(tickers)} tickers")
            for sym in config.TRADING_PAIRS:
                for t in tickers:
                    if t.get("symbol") == sym:
                        price = t.get("last", t.get("lastPrice", "N/A"))
                        print(f"    {sym}: ${price}")
                        break
        else:
            print(f"    WARNING - Unexpected response: {type(tickers)}")
    except Exception as e:
        print(f"    FAILED - {e}")
        print("    Attempting fallback with individual ticker requests...")

    # Test kline data
    print("\n[2] Testing kline data (BTCUSDT 5m)...")
    try:
        klines = client.get_klines("BTCUSDT", "5m", limit=10)
        if klines:
            print(f"    OK - Got {len(klines)} candles")
        else:
            print("    WARNING - Empty kline response")
    except Exception as e:
        print(f"    FAILED - {e}")

    # Test authenticated endpoints (if API keys set)
    if config.API_KEY and config.API_SECRET:
        print("\n[3] Testing authenticated access...")
        try:
            account = client.get_account()
            print(f"    OK - Account accessible")
            if isinstance(account, dict):
                balance = account.get("available", account.get("balance", "N/A"))
                print(f"    Balance: {balance}")
        except Exception as e:
            print(f"    FAILED - {e}")
            print("    Check your API key and secret in .env file")
    else:
        print("\n[3] Skipping auth test (no API keys in .env)")
        print("    Create a .env file with BITUNIX_API_KEY and BITUNIX_API_SECRET")

    # Test indicators
    print("\n[4] Testing indicator calculations...")
    try:
        from indicators import build_dataframe, add_all_indicators
        klines = client.get_klines("BTCUSDT", "15m", limit=250)
        df = build_dataframe(klines)
        if not df.empty:
            df = add_all_indicators(df)
            last = df.iloc[-1]
            print(f"    OK - DataFrame shape: {df.shape}")
            print(f"    Latest close: ${last['close']:.2f}")
            if 'rsi' in df.columns:
                print(f"    RSI(14): {last['rsi']:.1f}")
            if 'ema_fast' in df.columns:
                print(f"    EMA50: ${last['ema_fast']:.2f}")
            if 'atr' in df.columns:
                print(f"    ATR(14): ${last['atr']:.2f}")
            if 'trend_bullish' in df.columns:
                trend = "BULLISH" if last['trend_bullish'] else "BEARISH"
                print(f"    1H Trend: {trend}")
        else:
            print("    WARNING - Empty DataFrame")
    except Exception as e:
        print(f"    FAILED - {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Test Complete ===\n")


def show_report():
    """Display the combined performance report."""
    report_path = os.path.join(os.path.dirname(__file__), "combined_report.json")

    if not os.path.exists(report_path):
        print("No report found. Run paper trading first.")
        return

    with open(report_path) as f:
        report = json.load(f)

    print(f"\n{'='*60}")
    print(f"  PERFORMANCE REPORT")
    print(f"  Mode: {report.get('mode', 'unknown').upper()}")
    print(f"  Uptime: {report.get('uptime_hours', 0):.1f} hours")
    print(f"  Total cycles: {report.get('total_cycles', 0)}")
    print(f"{'='*60}\n")

    bots = report.get("bots", [])
    if not bots:
        print("No bot data found.")
        return

    # Bot comparison
    print(f"{'Bot':<12} {'Lev':>5} {'Trades':>7} {'Wins':>5} {'WR%':>7} "
          f"{'P&L':>10} {'P&L%':>8} {'MaxDD':>8}")
    print("-" * 70)

    best_wr = 0
    best_bot = None

    for b in bots:
        wr = b.get("win_rate", 0)
        pnl = b.get("pnl_total", 0)
        pnl_pct = b.get("pnl_pct", 0)
        max_dd = b.get("max_drawdown", 0)

        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        pnl_pct_str = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"

        print(f"{b.get('bot_name', '?'):<12} {b.get('leverage', '?'):>4}x "
              f"{b.get('total_trades', 0):>7} {b.get('wins', 0):>5} {wr:>6.1f}% "
              f"{pnl_str:>10} {pnl_pct_str:>8} ${max_dd:>7.2f}")

        if wr > best_wr and b.get("total_trades", 0) >= 5:
            best_wr = wr
            best_bot = b

    print("-" * 70)

    if best_bot:
        print(f"\n  BEST PERFORMER: {best_bot['bot_name']} "
              f"({best_bot['leverage']}x) - {best_wr:.1f}% WR")

        if best_wr >= 88:
            print(f"  >>> TARGET MET! Win rate >= 88% <<<")
            print(f"  Ready for live trading with: python3 main.py --mode live "
                  f"--leverage {best_bot['leverage']}")
        else:
            print(f"  Target: 88% WR | Current best: {best_wr:.1f}%")
            print(f"  Keep paper trading to collect more data.")

    # Per-symbol breakdown
    print(f"\n{'='*40}")
    print(f"  BY SYMBOL")
    print(f"{'='*40}")

    for b in bots:
        by_sym = b.get("trades_by_symbol", {})
        if by_sym:
            print(f"\n  {b['bot_name']} ({b['leverage']}x):")
            for sym, data in by_sym.items():
                wr = data.get("win_rate", 0)
                print(f"    {sym}: {data['total']} trades, {wr:.1f}% WR, "
                      f"P&L: ${data['pnl']:.2f}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Crypto Trading Bot for Bitunix")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper",
                        help="Trading mode (default: paper)")
    parser.add_argument("--leverage", type=int, default=None,
                        help="Run only a specific leverage bot")
    parser.add_argument("--report", action="store_true",
                        help="Show performance report")
    parser.add_argument("--test", action="store_true",
                        help="Test API connectivity")
    parser.add_argument("--interval", type=int, default=30,
                        help="Scan interval in seconds (default: 30)")

    args = parser.parse_args()

    if args.test:
        test_connection()
        return

    if args.report:
        show_report()
        return

    # Safety check for live mode
    if args.mode == "live":
        if not config.API_KEY or not config.API_SECRET:
            print("ERROR: API keys not configured. Set BITUNIX_API_KEY and "
                  "BITUNIX_API_SECRET in .env file")
            sys.exit(1)

        print("\n" + "!" * 60)
        print("  WARNING: LIVE TRADING MODE")
        print("  This will execute REAL trades with REAL money!")
        print("!" * 60)
        confirm = input("\nType 'YES' to confirm: ")
        if confirm != "YES":
            print("Aborted.")
            sys.exit(0)

    # Initialize bot manager
    manager = BotManager(
        mode=args.mode,
        specific_leverage=args.leverage,
    )

    start_time = time.time()

    def on_tick(results, cycle):
        """Callback after each trading cycle."""
        print_dashboard(results, cycle, start_time, args.mode)

    # Run the bot
    print(f"\nStarting in {args.mode.upper()} mode...")
    print(f"Press Ctrl+C to stop\n")

    try:
        asyncio.run(manager.run(callback=on_tick, interval=args.interval))
    except KeyboardInterrupt:
        print("\nStopping...")
        manager.stop()
        manager.save_all()
        print("Saved. Run --report to see results.")


if __name__ == "__main__":
    main()
