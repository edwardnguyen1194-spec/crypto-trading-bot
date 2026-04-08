"""
Backtest: TP/SL ATR Multiplier Grid Search
Fetches 5m candles for BTC, ETH, SOL, XRP and tests all TP x SL combos.
"""

import json
import sys
import numpy as np
import pandas as pd
from bitunix_client import BitunixClient
from indicators import build_dataframe, add_all_indicators

# ── Configuration ──────────────────────────────────────────────────────────
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INTERVAL = "5m"
LIMIT = 200
START_INDEX = 100  # skip first 100 candles for indicator warm-up
MAX_WALK = 60      # walk forward up to 60 candles (~5 hours on 5m)

TP_MULTS = [0.3, 0.5, 0.8, 1.0, 1.5, 2.0]
SL_MULTS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


def fetch_data(client, symbol):
    """Fetch klines and build indicator dataframe."""
    print(f"  Fetching {symbol} {INTERVAL} x {LIMIT} candles...")
    klines = client.get_klines(symbol, INTERVAL, LIMIT)
    df = build_dataframe(klines)
    df = add_all_indicators(df)
    print(f"  {symbol}: {len(df)} candles, ATR range {df['atr'].min():.6f} - {df['atr'].max():.6f}")
    return df


def simulate_trade(df, entry_idx, tp_mult, sl_mult):
    """
    Simulate a LONG trade entered at entry_idx.
    Returns: 'win', 'loss', or 'timeout'
    Also returns pnl as a fraction of entry price.
    """
    entry_price = df.iloc[entry_idx]["close"]
    atr = df.iloc[entry_idx]["atr"]

    if pd.isna(atr) or atr <= 0:
        return None, 0.0

    tp_price = entry_price + tp_mult * atr
    sl_price = entry_price - sl_mult * atr

    # Walk forward through subsequent candles
    end_idx = min(entry_idx + MAX_WALK + 1, len(df))
    for j in range(entry_idx + 1, end_idx):
        candle = df.iloc[j]
        high = candle["high"]
        low = candle["low"]

        # Check SL first (conservative: if both hit in same candle, count as loss)
        if low <= sl_price:
            pnl = (sl_price - entry_price) / entry_price
            return "loss", pnl
        if high >= tp_price:
            pnl = (tp_price - entry_price) / entry_price
            return "win", pnl

    # Timeout: exit at last candle's close
    exit_price = df.iloc[end_idx - 1]["close"]
    pnl = (exit_price - entry_price) / entry_price
    return "timeout", pnl


def run_backtest():
    print("=" * 70)
    print("BACKTEST: TP/SL ATR Multiplier Grid Search")
    print("=" * 70)

    client = BitunixClient()

    # Fetch data for all symbols
    dataframes = {}
    for sym in SYMBOLS:
        try:
            dataframes[sym] = fetch_data(client, sym)
        except Exception as e:
            print(f"  ERROR fetching {sym}: {e}")

    if not dataframes:
        print("No data fetched. Exiting.")
        sys.exit(1)

    print(f"\nLoaded {len(dataframes)} symbols: {list(dataframes.keys())}")
    print(f"Testing {len(TP_MULTS)} TP x {len(SL_MULTS)} SL = {len(TP_MULTS)*len(SL_MULTS)} combinations\n")

    # ── Grid search ────────────────────────────────────────────────────────
    results = []

    for tp_mult in TP_MULTS:
        for sl_mult in SL_MULTS:
            wins = 0
            losses = 0
            timeouts = 0
            total_pnl = 0.0
            all_pnls = []

            for sym, df in dataframes.items():
                for i in range(START_INDEX, len(df)):
                    # Entry condition: EMA21 > EMA100 (uptrend)
                    row = df.iloc[i]
                    if pd.isna(row.get("ema_fast")) or pd.isna(row.get("ema_slow")):
                        continue
                    if row["ema_fast"] <= row["ema_slow"]:
                        continue

                    outcome, pnl = simulate_trade(df, i, tp_mult, sl_mult)
                    if outcome is None:
                        continue

                    if outcome == "win":
                        wins += 1
                    elif outcome == "loss":
                        losses += 1
                    else:
                        timeouts += 1

                    total_pnl += pnl
                    all_pnls.append(pnl)

            total_trades = wins + losses + timeouts
            if total_trades == 0:
                continue

            win_rate = wins / total_trades * 100
            avg_pnl = total_pnl / total_trades * 100  # as percentage
            avg_win = np.mean([p for p in all_pnls if p > 0]) * 100 if any(p > 0 for p in all_pnls) else 0
            avg_loss = np.mean([p for p in all_pnls if p < 0]) * 100 if any(p < 0 for p in all_pnls) else 0

            # Expected value per trade (accounting for fee drag ~0.1% round trip)
            fee_drag = 0.10  # percent
            ev_per_trade = avg_pnl - fee_drag

            results.append({
                "tp_mult": tp_mult,
                "sl_mult": sl_mult,
                "win_rate": round(win_rate, 1),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "timeouts": timeouts,
                "avg_pnl_pct": round(avg_pnl, 4),
                "avg_win_pct": round(avg_win, 4),
                "avg_loss_pct": round(avg_loss, 4),
                "ev_after_fees": round(ev_per_trade, 4),
                "total_pnl_pct": round(total_pnl * 100, 4),
            })

    # ── Sort and display ───────────────────────────────────────────────────
    results.sort(key=lambda x: -x["win_rate"])

    print("=" * 110)
    print(f"{'TP':>5} {'SL':>5} | {'WR%':>6} {'Trades':>7} {'W':>4} {'L':>4} {'TO':>4} | "
          f"{'AvgPnL%':>8} {'AvgWin%':>8} {'AvgLoss%':>9} | {'EV%':>7} {'TotPnL%':>9}")
    print("-" * 110)

    for r in results:
        # Highlight rows with 85%+ WR
        marker = " ***" if r["win_rate"] >= 85 else ""
        print(f"{r['tp_mult']:>5.1f} {r['sl_mult']:>5.1f} | "
              f"{r['win_rate']:>5.1f}% {r['total_trades']:>7} {r['wins']:>4} {r['losses']:>4} {r['timeouts']:>4} | "
              f"{r['avg_pnl_pct']:>7.4f}% {r['avg_win_pct']:>7.4f}% {r['avg_loss_pct']:>8.4f}% | "
              f"{r['ev_after_fees']:>6.4f}% {r['total_pnl_pct']:>8.4f}%{marker}")

    # ── Find best combos ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TOP COMBOS BY WIN RATE (with positive EV after fees):")
    print("=" * 70)
    positive_ev = [r for r in results if r["ev_after_fees"] > 0]
    positive_ev.sort(key=lambda x: -x["win_rate"])
    for i, r in enumerate(positive_ev[:10]):
        print(f"  #{i+1}: TP={r['tp_mult']}x ATR, SL={r['sl_mult']}x ATR  |  "
              f"WR={r['win_rate']}%  Trades={r['total_trades']}  "
              f"EV={r['ev_after_fees']:.4f}%/trade  TotalPnL={r['total_pnl_pct']:.2f}%")

    print("\nTOP COMBOS BY EXPECTED VALUE:")
    print("=" * 70)
    by_ev = sorted(results, key=lambda x: -x["ev_after_fees"])
    for i, r in enumerate(by_ev[:10]):
        print(f"  #{i+1}: TP={r['tp_mult']}x ATR, SL={r['sl_mult']}x ATR  |  "
              f"WR={r['win_rate']}%  Trades={r['total_trades']}  "
              f"EV={r['ev_after_fees']:.4f}%/trade  TotalPnL={r['total_pnl_pct']:.2f}%")

    # ── Save results ───────────────────────────────────────────────────────
    output = {
        "symbols": SYMBOLS,
        "interval": INTERVAL,
        "candles_per_symbol": LIMIT,
        "entry_condition": "EMA21 > EMA100 (uptrend LONG only)",
        "max_walk_forward_candles": MAX_WALK,
        "fee_assumption_pct": 0.10,
        "all_results": results,
        "best_by_winrate": positive_ev[:5] if positive_ev else [],
        "best_by_ev": by_ev[:5],
    }

    out_path = "/Users/edward/Desktop/Crypto trading botttttt/backtest_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    run_backtest()
