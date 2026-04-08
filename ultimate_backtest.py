"""
ULTIMATE BACKTEST - Test EVERYTHING, find what ACTUALLY works.
Tests 500+ combinations across multiple strategies and timeframes.
"""
import numpy as np
import talib
import json
from bitunix_client import BitunixClient
from indicators import build_dataframe

client = BitunixClient()

results = []

for tf in ['15m', '1h']:
    for sym in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']:
        raw = client.get_klines(sym, tf, 200)
        df = build_dataframe(raw)
        if len(df) < 100:
            continue

        o = df['open'].values.astype(np.float64)
        h = df['high'].values.astype(np.float64)
        l = df['low'].values.astype(np.float64)
        c = df['close'].values.astype(np.float64)
        v = df['volume'].values.astype(np.float64)

        atr = talib.ATR(h, l, c, timeperiod=14)
        rsi = talib.RSI(c, timeperiod=14)
        ema9 = talib.EMA(c, timeperiod=9)
        ema21 = talib.EMA(c, timeperiod=21)
        ema50 = talib.EMA(c, timeperiod=50)
        bb_upper, bb_mid, bb_lower = talib.BBANDS(c, timeperiod=20)
        adx = talib.ADX(h, l, c, timeperiod=14)
        plus_di = talib.PLUS_DI(h, l, c, timeperiod=14)
        minus_di = talib.MINUS_DI(h, l, c, timeperiod=14)
        macd, macd_sig, macd_hist = talib.MACD(c)
        vol_ma = talib.SMA(v, timeperiod=20)

        # Candlestick patterns
        hammer = talib.CDLHAMMER(o, h, l, c)
        engulfing = talib.CDLENGULFING(o, h, l, c)
        doji = talib.CDLDOJI(o, h, l, c)

        strategies = {
            # === MEAN REVERSION STRATEGIES ===
            'mr_bb_rsi30': lambda i: c[i] <= bb_lower[i]*1.002 and rsi[i] < 30 and adx[i] < 25,
            'mr_bb_rsi35': lambda i: c[i] <= bb_lower[i]*1.002 and rsi[i] < 35 and adx[i] < 25,
            'mr_bb_rsi40': lambda i: c[i] <= bb_lower[i]*1.005 and rsi[i] < 40 and adx[i] < 22,
            'mr_bb_rsi45': lambda i: c[i] <= bb_lower[i]*1.005 and rsi[i] < 45 and adx[i] < 20,
            'mr_bb_vol': lambda i: c[i] <= bb_lower[i]*1.002 and rsi[i] < 40 and v[i] > vol_ma[i]*1.3,
            'mr_bb_hammer': lambda i: c[i] <= bb_lower[i]*1.005 and hammer[i] > 0,
            'mr_bb_engulf': lambda i: c[i] <= bb_lower[i]*1.005 and engulfing[i] > 0,
            'mr_rsi_only25': lambda i: rsi[i] < 25 and adx[i] < 25,
            'mr_rsi_only30': lambda i: rsi[i] < 30 and adx[i] < 22,

            # === TREND PULLBACK STRATEGIES ===
            'tp_ema21_rsi40': lambda i: ema21[i]>ema50[i] and c[i]<=ema21[i]*1.003 and rsi[i]<45 and adx[i]>20,
            'tp_ema21_rsi45': lambda i: ema21[i]>ema50[i] and c[i]<=ema21[i]*1.005 and rsi[i]<50 and adx[i]>20,
            'tp_ema9_rsi40': lambda i: ema9[i]>ema21[i]>ema50[i] and c[i]<=ema9[i]*1.002 and rsi[i]<45,
            'tp_ema_macd': lambda i: ema21[i]>ema50[i] and macd_hist[i]>0 and macd_hist[i-1]<=0 and adx[i]>20,
            'tp_adx30_rsi': lambda i: adx[i]>30 and plus_di[i]>minus_di[i] and rsi[i]<45,

            # === MOMENTUM STRATEGIES ===
            'mom_3green': lambda i: c[i]>o[i] and c[i-1]>o[i-1] and c[i-2]>o[i-2] and rsi[i]<60,
            'mom_vol_break': lambda i: v[i]>vol_ma[i]*2.0 and c[i]>o[i] and c[i]>c[i-1] and adx[i]>20,
            'mom_ema_cross': lambda i: ema9[i]>ema21[i] and ema9[i-1]<=ema21[i-1] and adx[i]>15,

            # === SCALP: TINY TP ===
            'scalp_any_green': lambda i: c[i]>o[i] and v[i]>vol_ma[i]*1.2 and ema21[i]>ema50[i],
            'scalp_rsi_bounce': lambda i: rsi[i]>rsi[i-1] and rsi[i-1]<rsi[i-2] and rsi[i]<50 and ema21[i]>ema50[i],
        }

        for tp_mult in [0.2, 0.3, 0.5, 0.8, 1.0, 1.5]:
            for sl_mult in [0.5, 1.0, 1.5, 2.0, 3.0]:
                for hold in [4, 8, 16]:
                    for strat_name, entry_fn in strategies.items():
                        wins = 0
                        losses = 0
                        total = 0

                        for i in range(55, len(df) - hold - 1):
                            if np.isnan(atr[i]) or atr[i] <= 0:
                                continue
                            if np.isnan(rsi[i]) or np.isnan(adx[i]):
                                continue

                            try:
                                if not entry_fn(i):
                                    continue
                            except:
                                continue

                            total += 1
                            tp_price = c[i] + tp_mult * atr[i]
                            sl_price = c[i] - sl_mult * atr[i]

                            hit_tp = False
                            hit_sl = False
                            for j in range(i+1, min(i+hold+1, len(df))):
                                if h[j] >= tp_price:
                                    hit_tp = True
                                    break
                                if l[j] <= sl_price:
                                    hit_sl = True
                                    break

                            if hit_tp:
                                wins += 1
                            elif hit_sl:
                                losses += 1
                            # else: timeout, count as loss
                            else:
                                losses += 1

                        if total >= 5:
                            wr = wins / total * 100
                            # Calculate EV
                            avg_win = tp_mult  # in ATR units
                            avg_loss = sl_mult
                            ev = (wr/100 * avg_win) - ((100-wr)/100 * avg_loss)
                            fee_drag = 0.001 * total  # rough fee estimate

                            results.append({
                                'symbol': sym,
                                'tf': tf,
                                'strategy': strat_name,
                                'tp': tp_mult,
                                'sl': sl_mult,
                                'hold': hold,
                                'trades': total,
                                'wins': wins,
                                'wr': round(wr, 1),
                                'ev_atr': round(ev, 4),
                            })

# Sort by WR, then by EV
results.sort(key=lambda x: (-x['wr'], -x['ev_atr']))

print(f'\n{"="*90}')
print(f'ULTIMATE BACKTEST RESULTS - {len(results)} combinations tested')
print(f'{"="*90}')
print(f'\nTOP 30 BY WIN RATE (minimum 5 trades):')
print(f'{"Strategy":<25} {"Sym":<8} {"TF":<4} {"TP":>4} {"SL":>4} {"Hold":>4} {"Trades":>6} {"WR%":>6} {"EV":>7}')
print('-'*85)

shown = 0
for r in results:
    if r['wr'] >= 80 and r['ev_atr'] > -0.5 and shown < 30:
        ev_str = f"+{r['ev_atr']:.3f}" if r['ev_atr'] > 0 else f"{r['ev_atr']:.3f}"
        marker = ' ***' if r['wr'] >= 88 and r['ev_atr'] > 0 else ''
        print(f"{r['strategy']:<25} {r['symbol']:<8} {r['tf']:<4} {r['tp']:>4} {r['sl']:>4} {r['hold']:>4} {r['trades']:>6} {r['wr']:>5.1f}% {ev_str:>7}{marker}")
        shown += 1

# Show PROFITABLE combos (positive EV)
print(f'\n{"="*90}')
print(f'TOP 20 PROFITABLE (positive EV + WR >= 70%):')
print(f'{"="*90}')
profitable = [r for r in results if r['ev_atr'] > 0 and r['wr'] >= 70]
profitable.sort(key=lambda x: -x['ev_atr'])
for r in profitable[:20]:
    print(f"{r['strategy']:<25} {r['symbol']:<8} {r['tf']:<4} TP={r['tp']} SL={r['sl']} hold={r['hold']} trades={r['trades']} WR={r['wr']}% EV={r['ev_atr']:.3f} ***")

# Save best results
best = [r for r in results if r['wr'] >= 80]
with open('ultimate_backtest_results.json', 'w') as f:
    json.dump({'total_tested': len(results), 'above_80wr': len(best), 'best': best[:50]}, f, indent=2)

print(f'\n{len(best)} combos with 80%+ WR found. Saved to ultimate_backtest_results.json')
