/**
 * Technical Analysis Engine
 * RSI, MACD, EMA, SMA, Bollinger Bands, ATR, VWAP, Stochastic, ADX, OBV
 */

class TechnicalAnalysis {
  static SMA(data, period) {
    const result = [];
    for (let i = period - 1; i < data.length; i++) {
      const slice = data.slice(i - period + 1, i + 1);
      result.push(slice.reduce((a, b) => a + b, 0) / period);
    }
    return result;
  }

  static EMA(data, period) {
    const k = 2 / (period + 1);
    const result = [data[0]];
    for (let i = 1; i < data.length; i++) {
      result.push(data[i] * k + result[i - 1] * (1 - k));
    }
    return result;
  }

  static RSI(closes, period = 14) {
    const changes = [];
    for (let i = 1; i < closes.length; i++) {
      changes.push(closes[i] - closes[i - 1]);
    }

    let avgGain = 0, avgLoss = 0;
    for (let i = 0; i < period; i++) {
      if (changes[i] > 0) avgGain += changes[i];
      else avgLoss += Math.abs(changes[i]);
    }
    avgGain /= period;
    avgLoss /= period;

    const rsi = [avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss))];

    for (let i = period; i < changes.length; i++) {
      const gain = changes[i] > 0 ? changes[i] : 0;
      const loss = changes[i] < 0 ? Math.abs(changes[i]) : 0;
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      rsi.push(avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss)));
    }
    return rsi;
  }

  static MACD(closes, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
    const fastEMA = this.EMA(closes, fastPeriod);
    const slowEMA = this.EMA(closes, slowPeriod);

    const macdLine = [];
    for (let i = 0; i < closes.length; i++) {
      macdLine.push(fastEMA[i] - slowEMA[i]);
    }

    const signalLine = this.EMA(macdLine, signalPeriod);
    const histogram = macdLine.map((v, i) => v - signalLine[i]);

    return { macd: macdLine, signal: signalLine, histogram };
  }

  static BollingerBands(closes, period = 20, stdDev = 2) {
    const sma = this.SMA(closes, period);
    const upper = [], lower = [], bandwidth = [];

    for (let i = period - 1; i < closes.length; i++) {
      const slice = closes.slice(i - period + 1, i + 1);
      const mean = sma[i - period + 1];
      const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
      const sd = Math.sqrt(variance) * stdDev;
      upper.push(mean + sd);
      lower.push(mean - sd);
      bandwidth.push((2 * sd) / mean * 100);
    }

    return { upper, middle: sma, lower, bandwidth };
  }

  static ATR(highs, lows, closes, period = 14) {
    const tr = [highs[0] - lows[0]];
    for (let i = 1; i < closes.length; i++) {
      tr.push(Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      ));
    }
    return this.EMA(tr, period);
  }

  static Stochastic(highs, lows, closes, kPeriod = 14, dPeriod = 3) {
    const k = [];
    for (let i = kPeriod - 1; i < closes.length; i++) {
      const highSlice = highs.slice(i - kPeriod + 1, i + 1);
      const lowSlice = lows.slice(i - kPeriod + 1, i + 1);
      const hh = Math.max(...highSlice);
      const ll = Math.min(...lowSlice);
      k.push(hh === ll ? 50 : ((closes[i] - ll) / (hh - ll)) * 100);
    }
    const d = this.SMA(k, dPeriod);
    return { k, d };
  }

  static ADX(highs, lows, closes, period = 14) {
    const plusDM = [], minusDM = [], tr = [];
    for (let i = 1; i < closes.length; i++) {
      const upMove = highs[i] - highs[i - 1];
      const downMove = lows[i - 1] - lows[i];
      plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
      minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
      tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
    }

    const smoothTR = this.EMA(tr, period);
    const smoothPlusDM = this.EMA(plusDM, period);
    const smoothMinusDM = this.EMA(minusDM, period);

    const plusDI = smoothPlusDM.map((v, i) => (v / smoothTR[i]) * 100);
    const minusDI = smoothMinusDM.map((v, i) => (v / smoothTR[i]) * 100);
    const dx = plusDI.map((v, i) => (Math.abs(v - minusDI[i]) / (v + minusDI[i])) * 100);
    const adx = this.EMA(dx, period);

    return { adx, plusDI, minusDI };
  }

  static OBV(closes, volumes) {
    const obv = [0];
    for (let i = 1; i < closes.length; i++) {
      if (closes[i] > closes[i - 1]) obv.push(obv[i - 1] + volumes[i]);
      else if (closes[i] < closes[i - 1]) obv.push(obv[i - 1] - volumes[i]);
      else obv.push(obv[i - 1]);
    }
    return obv;
  }

  static VWAP(highs, lows, closes, volumes) {
    const vwap = [];
    let cumVolume = 0, cumVP = 0;
    for (let i = 0; i < closes.length; i++) {
      const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
      cumVolume += volumes[i];
      cumVP += typicalPrice * volumes[i];
      vwap.push(cumVolume === 0 ? typicalPrice : cumVP / cumVolume);
    }
    return vwap;
  }

  static SuperTrend(highs, lows, closes, period = 10, multiplier = 3) {
    const atr = this.ATR(highs, lows, closes, period);
    const supertrend = [];
    const direction = [];

    for (let i = 0; i < closes.length; i++) {
      const hl2 = (highs[i] + lows[i]) / 2;
      const upperBand = hl2 + multiplier * (atr[i] || atr[0]);
      const lowerBand = hl2 - multiplier * (atr[i] || atr[0]);

      if (i === 0) {
        supertrend.push(upperBand);
        direction.push(-1);
        continue;
      }

      const prevST = supertrend[i - 1];
      const prevDir = direction[i - 1];

      if (prevDir === -1 && closes[i] > prevST) {
        supertrend.push(lowerBand);
        direction.push(1);
      } else if (prevDir === 1 && closes[i] < prevST) {
        supertrend.push(upperBand);
        direction.push(-1);
      } else if (prevDir === 1) {
        supertrend.push(Math.max(lowerBand, prevST));
        direction.push(1);
      } else {
        supertrend.push(Math.min(upperBand, prevST));
        direction.push(-1);
      }
    }
    return { supertrend, direction };
  }

  static IchimokuCloud(highs, lows, closes, convPeriod = 9, basePeriod = 26, spanBPeriod = 52) {
    const highestHigh = (arr, start, period) => {
      const slice = arr.slice(Math.max(0, start - period + 1), start + 1);
      return Math.max(...slice);
    };
    const lowestLow = (arr, start, period) => {
      const slice = arr.slice(Math.max(0, start - period + 1), start + 1);
      return Math.min(...slice);
    };

    const tenkan = [], kijun = [], spanA = [], spanB = [];
    for (let i = 0; i < closes.length; i++) {
      const t = (highestHigh(highs, i, convPeriod) + lowestLow(lows, i, convPeriod)) / 2;
      const k = (highestHigh(highs, i, basePeriod) + lowestLow(lows, i, basePeriod)) / 2;
      tenkan.push(t);
      kijun.push(k);
      spanA.push((t + k) / 2);
      spanB.push((highestHigh(highs, i, spanBPeriod) + lowestLow(lows, i, spanBPeriod)) / 2);
    }
    return { tenkan, kijun, spanA, spanB };
  }

  /**
   * Detect swing highs and swing lows
   */
  static findSwingPoints(highs, lows, lookback = 5) {
    const swingHighs = [];
    const swingLows = [];

    for (let i = lookback; i < highs.length - lookback; i++) {
      let isSwingHigh = true;
      let isSwingLow = true;

      for (let j = 1; j <= lookback; j++) {
        if (highs[i] <= highs[i - j] || highs[i] <= highs[i + j]) {
          isSwingHigh = false;
        }
        if (lows[i] >= lows[i - j] || lows[i] >= lows[i + j]) {
          isSwingLow = false;
        }
      }

      if (isSwingHigh) swingHighs.push({ index: i, price: highs[i] });
      if (isSwingLow) swingLows.push({ index: i, price: lows[i] });
    }

    return { swingHighs, swingLows };
  }

  /**
   * Find key support/resistance levels from swing points
   */
  static findSupportResistance(highs, lows, closes, lookback = 50) {
    const len = highs.length;
    const start = Math.max(0, len - lookback);
    const recentHighs = highs.slice(start);
    const recentLows = lows.slice(start);

    const swings = this.findSwingPoints(recentHighs, recentLows, 3);
    const currentPrice = closes[closes.length - 1];
    const levels = [];

    // Collect all swing points as potential S/R
    for (const sh of swings.swingHighs) {
      levels.push({ price: sh.price, type: 'resistance', touches: 1, recency: sh.index });
    }
    for (const sl of swings.swingLows) {
      levels.push({ price: sl.price, type: 'support', touches: 1, recency: sl.index });
    }

    // Cluster nearby levels (within 0.5% of each other)
    const clustered = [];
    const used = new Set();

    for (let i = 0; i < levels.length; i++) {
      if (used.has(i)) continue;
      let cluster = { price: levels[i].price, type: levels[i].type, touches: levels[i].touches, recency: levels[i].recency };
      let count = 1;
      let priceSum = levels[i].price;

      for (let j = i + 1; j < levels.length; j++) {
        if (used.has(j)) continue;
        if (Math.abs(levels[j].price - levels[i].price) / levels[i].price < 0.005) {
          used.add(j);
          cluster.touches++;
          priceSum += levels[j].price;
          count++;
          cluster.recency = Math.max(cluster.recency, levels[j].recency);
        }
      }

      cluster.price = priceSum / count;
      // Re-classify based on current price
      cluster.type = cluster.price > currentPrice ? 'resistance' : 'support';
      // Score by touches and recency
      cluster.strength = cluster.touches * 2 + (cluster.recency / recentHighs.length) * 3;
      clustered.push(cluster);
    }

    // Sort by strength descending and return top 5
    clustered.sort((a, b) => b.strength - a.strength);
    return clustered.slice(0, 5);
  }

  /**
   * Find order blocks (institutional supply/demand zones)
   */
  static findOrderBlocks(opens, highs, lows, closes, atr, minMoveAtr = 1.5) {
    const orderBlocks = [];
    const len = closes.length;
    const currentAtr = atr[atr.length - 1] || atr[0];

    for (let i = 1; i < len - 1; i++) {
      const localAtr = atr[i] || currentAtr;
      const move = closes[i + 1] - closes[i];

      // Bullish OB: last bearish candle before a strong up-move
      if (move > localAtr * minMoveAtr && closes[i] < opens[i]) {
        orderBlocks.push({
          high: highs[i],
          low: lows[i],
          type: 'bullish',
          index: i,
        });
      }

      // Bearish OB: last bullish candle before a strong down-move
      if (move < -localAtr * minMoveAtr && closes[i] > opens[i]) {
        orderBlocks.push({
          high: highs[i],
          low: lows[i],
          type: 'bearish',
          index: i,
        });
      }
    }

    // Return only most recent order blocks (last 10)
    return orderBlocks.slice(-10);
  }

  /**
   * Find fair value gaps (imbalances)
   */
  static findFairValueGaps(highs, lows, atr, minGapAtr = 0.3) {
    const gaps = [];
    const len = highs.length;

    for (let i = 2; i < len; i++) {
      const localAtr = atr[i] || atr[atr.length - 1];

      // Bullish FVG: low of current candle > high of 2 candles ago
      if (lows[i] > highs[i - 2]) {
        const gapSize = lows[i] - highs[i - 2];
        if (gapSize > localAtr * minGapAtr) {
          gaps.push({
            upper: lows[i],
            lower: highs[i - 2],
            type: 'bullish',
            index: i,
          });
        }
      }

      // Bearish FVG: high of current candle < low of 2 candles ago
      if (highs[i] < lows[i - 2]) {
        const gapSize = lows[i - 2] - highs[i];
        if (gapSize > localAtr * minGapAtr) {
          gaps.push({
            upper: lows[i - 2],
            lower: highs[i],
            type: 'bearish',
            index: i,
          });
        }
      }
    }

    // Return only most recent gaps (last 10)
    return gaps.slice(-10);
  }

  /**
   * Detect RSI divergence
   */
  static detectDivergence(closes, rsiValues, lookback = 20) {
    const result = { bullish: false, bearish: false };
    if (closes.length < lookback || rsiValues.length < lookback) return result;

    const len = closes.length;
    const rsiLen = rsiValues.length;

    // Find recent price lows and highs within lookback
    let recentPriceLow = Infinity, recentPriceHigh = -Infinity;
    let prevPriceLow = Infinity, prevPriceHigh = -Infinity;
    let recentRsiLow = Infinity, recentRsiHigh = -Infinity;
    let prevRsiLow = Infinity, prevRsiHigh = -Infinity;

    const half = Math.floor(lookback / 2);

    // Recent half (more recent)
    for (let i = len - half; i < len; i++) {
      const rsiIdx = rsiLen - (len - i);
      if (rsiIdx < 0) continue;
      if (closes[i] < recentPriceLow) recentPriceLow = closes[i];
      if (closes[i] > recentPriceHigh) recentPriceHigh = closes[i];
      if (rsiValues[rsiIdx] < recentRsiLow) recentRsiLow = rsiValues[rsiIdx];
      if (rsiValues[rsiIdx] > recentRsiHigh) recentRsiHigh = rsiValues[rsiIdx];
    }

    // Previous half (older)
    for (let i = len - lookback; i < len - half; i++) {
      const rsiIdx = rsiLen - (len - i);
      if (rsiIdx < 0) continue;
      if (closes[i] < prevPriceLow) prevPriceLow = closes[i];
      if (closes[i] > prevPriceHigh) prevPriceHigh = closes[i];
      if (rsiValues[rsiIdx] < prevRsiLow) prevRsiLow = rsiValues[rsiIdx];
      if (rsiValues[rsiIdx] > prevRsiHigh) prevRsiHigh = rsiValues[rsiIdx];
    }

    // Bullish divergence: price makes lower low but RSI makes higher low
    if (recentPriceLow < prevPriceLow && recentRsiLow > prevRsiLow) {
      result.bullish = true;
    }

    // Bearish divergence: price makes higher high but RSI makes lower high
    if (recentPriceHigh > prevPriceHigh && recentRsiHigh < prevRsiHigh) {
      result.bearish = true;
    }

    return result;
  }

  /**
   * Compute full analysis snapshot for a candle set
   */
  static analyze(candles) {
    if (candles.length < 52) return null;

    const closes = candles.map(c => parseFloat(c.close));
    const opens = candles.map(c => parseFloat(c.open));
    const highs = candles.map(c => parseFloat(c.high));
    const lows = candles.map(c => parseFloat(c.low));
    const volumes = candles.map(c => parseFloat(c.quoteVol || c.baseVol || 0));

    const rsi = this.RSI(closes);
    const macd = this.MACD(closes);
    const bb = this.BollingerBands(closes);
    const atr = this.ATR(highs, lows, closes);
    const stoch = this.Stochastic(highs, lows, closes);
    const adx = this.ADX(highs, lows, closes);
    const obv = this.OBV(closes, volumes);
    const vwap = this.VWAP(highs, lows, closes, volumes);
    const supertrend = this.SuperTrend(highs, lows, closes);
    const ema9 = this.EMA(closes, 9);
    const ema21 = this.EMA(closes, 21);
    const ema50 = this.EMA(closes, 50);
    const ichimoku = this.IchimokuCloud(highs, lows, closes);

    // Market structure (SMC)
    let structureLevels = [];
    let orderBlocks = [];
    let fairValueGaps = [];
    let divergence = { bullish: false, bearish: false };
    try {
      structureLevels = this.findSupportResistance(highs, lows, closes, 50);
      orderBlocks = this.findOrderBlocks(opens, highs, lows, closes, atr, 1.5);
      fairValueGaps = this.findFairValueGaps(highs, lows, atr, 0.3);
      divergence = this.detectDivergence(closes, rsi, 20);
    } catch (e) { /* non-critical */ }

    const last = closes.length - 1;
    return {
      price: closes[last],
      rsi: rsi[rsi.length - 1],
      macd: {
        value: macd.macd[last],
        signal: macd.signal[last],
        histogram: macd.histogram[last],
      },
      bb: {
        upper: bb.upper[bb.upper.length - 1],
        middle: bb.middle[bb.middle.length - 1],
        lower: bb.lower[bb.lower.length - 1],
        bandwidth: bb.bandwidth[bb.bandwidth.length - 1],
      },
      atr: atr[last],
      stochastic: { k: stoch.k[stoch.k.length - 1], d: stoch.d[stoch.d.length - 1] },
      adx: {
        value: adx.adx[adx.adx.length - 1],
        plusDI: adx.plusDI[adx.plusDI.length - 1],
        minusDI: adx.minusDI[adx.minusDI.length - 1],
      },
      obv: obv[last],
      vwap: vwap[last],
      supertrend: {
        value: supertrend.supertrend[last],
        direction: supertrend.direction[last],
      },
      ema: { ema9: ema9[last], ema21: ema21[last], ema50: ema50[last] },
      ichimoku: {
        tenkan: ichimoku.tenkan[last],
        kijun: ichimoku.kijun[last],
        spanA: ichimoku.spanA[last],
        spanB: ichimoku.spanB[last],
      },
      volume: volumes[last],
      avgVolume: volumes.slice(-20).reduce((a, b) => a + b, 0) / 20,
      structureLevels,
      orderBlocks,
      fairValueGaps,
      divergence,
    };
  }
}

module.exports = { TechnicalAnalysis };
