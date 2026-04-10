const EventEmitter = require('events');
const https = require('https');

/**
 * Position Manager - handles order execution, trailing stops, funding, and position lifecycle
 */
class PositionManager extends EventEmitter {
  constructor(client, riskManager) {
    super();
    this.client = client;
    this.risk = riskManager;
    this.positions = new Map();
    this.pendingOrders = new Map();
    this.trailingStops = new Map();
    this.checkInterval = null;
    this.tradeHistory = [];
    this.fundingRates = {};
    this.lastFundingTime = 0;
    this.totalFundingPaid = 0;
    // Per-symbol entry cooldown (prevents spam re-entry within same candle)
    this.lastEntryTime = new Map();

    // Check funding every 30 minutes
    setInterval(() => this._updateFundingRates(), 30 * 60 * 1000);
    // Apply funding every 8 hours (Bitunix schedule: 00:00, 08:00, 16:00 UTC)
    setInterval(() => this._applyFunding(), 60 * 1000); // check every minute
    this._updateFundingRates();
  }

  async _updateFundingRates() {
    for (const symbol of ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']) {
      try {
        const data = await this._fetchFundingRate(symbol);
        if (data) this.fundingRates[symbol] = data;
      } catch (e) { /* non-critical */ }
    }
  }

  _fetchFundingRate(symbol) {
    return new Promise((resolve) => {
      try {
        https.get(`https://fapi.bitunix.com/api/v1/futures/market/funding_rate?symbol=${symbol}`, (res) => {
          let data = '';
          res.on('data', d => data += d);
          res.on('end', () => {
            try {
              const parsed = JSON.parse(data);
              if (parsed.code === 0 && parsed.data) {
                resolve({
                  rate: parseFloat(parsed.data.fundingRate || parsed.data.lastFundingRate || 0),
                  nextTime: parseInt(parsed.data.nextFundingTime || 0),
                });
              } else resolve(null);
            } catch { resolve(null); }
          });
        }).on('error', () => resolve(null));
      } catch { resolve(null); }
    });
  }

  _applyFunding() {
    const now = Date.now();
    // Funding applies every 8 hours — check if we crossed a funding time
    // Bitunix funding at 00:00, 08:00, 16:00 UTC
    const hourUTC = new Date().getUTCHours();
    const minuteUTC = new Date().getUTCMinutes();
    const isFundingTime = (hourUTC % 8 === 0) && (minuteUTC === 0);

    if (!isFundingTime) return;
    if (now - this.lastFundingTime < 7 * 60 * 60 * 1000) return; // prevent double-charge
    this.lastFundingTime = now;

    for (const [symbol, position] of this.positions) {
      const fundingData = this.fundingRates[symbol];
      if (!fundingData || fundingData.rate === 0) continue;

      const rate = fundingData.rate;
      const notional = position.quantity * position.entryPrice;
      // Longs pay when rate is positive, shorts pay when rate is negative
      const isLong = position.direction === 'LONG';
      let fundingPayment;
      if (isLong) {
        fundingPayment = rate > 0 ? -Math.abs(notional * rate) : Math.abs(notional * rate);
      } else {
        fundingPayment = rate < 0 ? -Math.abs(notional * rate) : Math.abs(notional * rate);
      }

      this.totalFundingPaid += fundingPayment;
      this.risk.currentBalance += fundingPayment;
      this.risk.bankroll = this.risk.currentBalance;
      this.risk.dailyPnL += fundingPayment;

      const direction = fundingPayment >= 0 ? 'received' : 'paid';
      console.log(`[FUNDING] ${symbol} ${direction} $${Math.abs(fundingPayment).toFixed(4)} (rate: ${(rate * 100).toFixed(4)}%)`);
    }
  }

  async openPosition({ symbol, direction, analysis, signalStrength }) {
    // Check if trading is allowed
    const canTrade = this.risk.canTrade();
    if (!canTrade.allowed) {
      console.log(`[PM] Trade blocked: ${canTrade.reasons.join(', ')}`);
      return null;
    }

    // Correlation filter — prevent over-exposure in correlated assets
    if (typeof this.risk.checkCorrelation === 'function') {
      const corr = this.risk.checkCorrelation(symbol, direction, this.positions);
      if (!corr.allowed) {
        console.log(`[PM] Trade blocked: ${corr.reason}`);
        return null;
      }
    }

    // Check if already in position for this symbol
    if (this.positions.has(symbol)) {
      console.log(`[PM] Already in position for ${symbol}`);
      return null;
    }

    // Candle-bar cooldown: don't re-enter the same symbol within the same
    // primary candle (prevents spam entries on stale signals between scans)
    const candleCooldownMs = 15 * 60 * 1000; // 15m candle window
    const lastEntry = this.lastEntryTime?.get?.(symbol) || 0;
    if (Date.now() - lastEntry < candleCooldownMs) {
      const waitMin = Math.ceil((candleCooldownMs - (Date.now() - lastEntry)) / 60000);
      console.log(`[PM] Candle cooldown on ${symbol} (${waitMin}m remaining) — skipping re-entry`);
      return null;
    }

    // ── CRITICAL: Fetch LIVE ticker price at moment of entry ──────────────
    // Using analysis.price (the stale candle close) was causing fake TP hits
    // when the live market had already moved past the computed TP level.
    // Live price ensures entry reflects actual fillable market price.
    let livePrice = null;
    try {
      const ticker = await this.client.getTicker(symbol);
      const t = Array.isArray(ticker) ? ticker[0] : ticker;
      livePrice = parseFloat(t?.lastPrice || t?.last || t?.markPrice || 0);
    } catch (e) {
      console.log(`[PM] Live ticker fetch failed for ${symbol}: ${e.message}`);
    }
    if (!livePrice || !isFinite(livePrice) || livePrice <= 0) {
      // Fallback: use analysis.price, but warn loudly
      console.log(`[PM] ⚠ Falling back to candle-close price for ${symbol} — live ticker unavailable`);
      livePrice = analysis.price;
    }

    // Sanity check: if live price has drifted more than 1.5% from candle close,
    // the signal is stale and TP/SL levels based on old price would be wrong.
    const drift = Math.abs(livePrice - analysis.price) / analysis.price;
    if (drift > 0.015) {
      console.log(`[PM] ${symbol} signal rejected: live price $${livePrice.toFixed(4)} drifted ${(drift*100).toFixed(2)}% from candle close $${analysis.price.toFixed(4)}`);
      return null;
    }

    const price = livePrice;  // ← use live market price, not analysis.price
    const atr = analysis.atr;

    // Calculate optimal leverage
    const leverage = this.risk.calculateLeverage(atr, price);

    // Calculate position size
    const sizing = this.risk.calculatePositionSize(price, atr, signalStrength, leverage);
    if (!sizing) {
      console.log(`[PM] Position too small for ${symbol}`);
      return null;
    }

    // Calculate TP/SL — pass structure levels for refinement
    const levels = this.risk.calculateLevels(
      price,
      atr,
      direction,
      signalStrength,
      analysis.structureLevels || []
    );

    // Set leverage on exchange
    try {
      await this.client.changeLeverage(symbol, leverage);
    } catch (e) {
      console.log(`[PM] Leverage change note: ${e.message}`);
    }

    // Apply realistic slippage (0.05% adverse)
    const SLIPPAGE = 0.0005;
    const slippedPrice = direction === 'LONG'
      ? price * (1 + SLIPPAGE)   // buy slightly higher
      : price * (1 - SLIPPAGE);  // sell slightly lower

    // Place order
    const side = direction === 'LONG' ? 'BUY' : 'SELL';
    const clientId = `agent_${symbol}_${Date.now()}`;

    try {
      const order = await this.client.placeOrder({
        symbol,
        side,
        orderType: 'MARKET',
        qty: this._formatQty(sizing.quantity, symbol),
        tradeSide: 'OPEN',
        tpPrice: levels.takeProfit,
        slPrice: levels.stopLoss,
        clientId,
      });

      const position = {
        symbol,
        direction,
        side,
        entryPrice: slippedPrice,
        quantity: sizing.quantity,
        originalQuantity: sizing.quantity,
        leverage,
        margin: sizing.margin,
        originalMargin: sizing.margin,
        stopLoss: levels.stopLoss,
        takeProfit: levels.takeProfit,
        breakEvenTrigger: levels.breakEvenTrigger,
        trailingStop: levels.trailingStop,
        partialTpTrigger: levels.partialTpTrigger,
        tightTrailingStop: levels.tightTrailingStop,
        partialTaken: false,
        rrRatio: levels.rrRatio,
        orderId: order.orderId,
        clientId,
        openTime: Date.now(),
        highestPnL: 0,
        status: 'open',
        structureLevels: analysis.structureLevels || [],
        atr,
      };

      this.positions.set(symbol, position);
      this.risk.addPosition(symbol, { margin: sizing.margin });
      // Stamp cooldown — blocks re-entry on this symbol within the candle window
      this.lastEntryTime.set(symbol, Date.now());

      console.log(`[PM] ✓ OPENED ${direction} ${symbol}`);
      console.log(`    Entry: $${price.toFixed(2)} (live) | Size: ${sizing.quantity.toFixed(6)}`);
      console.log(`    Lev: ${leverage}x | Margin: $${sizing.margin.toFixed(2)}`);
      console.log(`    SL: $${levels.stopLoss.toFixed(2)} | TP: $${levels.takeProfit.toFixed(2)} (${levels.rrRatio.toFixed(1)}:1 R:R)`);

      this.emit('position_opened', position);
      return position;
    } catch (e) {
      console.error(`[PM] Order failed for ${symbol}: ${e.message}`);
      return null;
    }
  }

  async closePosition(symbol, reason = 'manual') {
    const position = this.positions.get(symbol);
    if (!position) return null;

    try {
      const closeSide = position.direction === 'LONG' ? 'SELL' : 'BUY';
      await this.client.placeOrder({
        symbol,
        side: closeSide,
        orderType: 'MARKET',
        qty: this._formatQty(position.quantity, symbol),
        tradeSide: 'CLOSE',
        reduceOnly: true,
      });

      position.status = 'closed';
      position.closeTime = Date.now();
      position.closeReason = reason;

      this.positions.delete(symbol);
      this.trailingStops.delete(symbol);

      console.log(`[PM] ✓ CLOSED ${position.direction} ${symbol} - Reason: ${reason}`);
      this._recordTrade(position, reason);
      this.emit('position_closed', position);
      return position;
    } catch (e) {
      console.error(`[PM] Close failed for ${symbol}: ${e.message}`);
      // Try flash close as fallback
      try {
        await this.client.closeAllPositions(symbol);
        this.positions.delete(symbol);
        console.log(`[PM] Flash closed ${symbol}`);
      } catch (e2) {
        console.error(`[PM] Flash close also failed: ${e2.message}`);
      }
      return null;
    }
  }

  /**
   * Update trailing stops and check breakeven
   */
  async updatePositions(tickerData) {
    let totalUnrealizedPnL = 0;

    for (const [symbol, position] of this.positions) {
      const ticker = tickerData[symbol];
      if (!ticker) continue;

      const currentPrice = parseFloat(ticker.lastPrice || ticker.close || ticker);
      const isLong = position.direction === 'LONG';
      const pnlPercent = isLong
        ? (currentPrice - position.entryPrice) / position.entryPrice
        : (position.entryPrice - currentPrice) / position.entryPrice;

      const pnlDollar = pnlPercent * position.margin * position.leverage;

      // Store current unrealized P&L on position
      position.unrealizedPnL = pnlDollar;
      position.currentPrice = currentPrice;
      position.pnlPercent = pnlPercent * 100;
      totalUnrealizedPnL += pnlDollar;

      // Track highest PnL for trailing
      if (pnlDollar > position.highestPnL) {
        position.highestPnL = pnlDollar;
      }

      // Move stop to breakeven after trigger
      if (!position.breakEvenMoved) {
        const triggerHit = isLong
          ? currentPrice >= position.breakEvenTrigger
          : currentPrice <= position.breakEvenTrigger;

        if (triggerHit) {
          position.stopLoss = position.entryPrice + (isLong ? 1 : -1) * (position.entryPrice * 0.001);
          position.breakEvenMoved = true;
          console.log(`[PM] ↑ ${symbol} stop moved to breakeven: $${position.stopLoss.toFixed(2)}`);

          // Update TP/SL on exchange
          try {
            const positions = await this.client.getPendingPositions(symbol);
            if (positions && positions.length > 0) {
              await this.client.placeTpSlOrder({
                symbol,
                positionId: positions[0].positionId,
                slPrice: position.stopLoss,
                tpPrice: position.takeProfit,
              });
            }
          } catch (e) {
            // Non-critical - exchange SL still active
          }
        }
      }

      // Partial profit taking: close 50% at 1 ATR profit
      if (!position.partialTaken && position.partialTpTrigger) {
        const partialHit = isLong
          ? currentPrice >= position.partialTpTrigger
          : currentPrice <= position.partialTpTrigger;

        if (partialHit) {
          try {
            const halfQty = position.originalQuantity * 0.5;
            const closeSide = isLong ? 'SELL' : 'BUY';
            // Attempt partial close on exchange
            try {
              await this.client.placeOrder({
                symbol,
                side: closeSide,
                orderType: 'MARKET',
                qty: this._formatQty(halfQty, symbol),
                tradeSide: 'CLOSE',
                reduceOnly: true,
              });
            } catch (e) {
              // Non-critical in dry run
            }

            // Realize partial PnL
            const partialPnl = Math.abs((currentPrice - position.entryPrice) / position.entryPrice)
              * (position.originalMargin * 0.5) * position.leverage;
            const partialNotional = halfQty * currentPrice;
            this.risk.updateBalance(partialPnl, partialNotional);

            // Shrink position
            position.quantity = position.originalQuantity * 0.5;
            position.margin = position.originalMargin * 0.5;
            position.partialTaken = true;

            // Tighten trailing stop on remainder
            if (position.tightTrailingStop) {
              position.trailingStop = position.tightTrailingStop;
            }

            // Ensure breakeven is set (lock remainder)
            if (!position.breakEvenMoved) {
              position.stopLoss = position.entryPrice + (isLong ? 1 : -1) * (position.entryPrice * 0.001);
              position.breakEvenMoved = true;
            }

            console.log(`[PM] PARTIAL TP ${symbol} +$${partialPnl.toFixed(2)} (50% closed, trailing tightened)`);
          } catch (e) {
            console.log(`[PM] Partial TP error: ${e.message}`);
          }
        }
      }

      // Trailing stop after breakeven
      if (position.breakEvenMoved && position.trailingStop) {
        const trailPrice = isLong
          ? currentPrice - position.trailingStop
          : currentPrice + position.trailingStop;

        const shouldTrail = isLong
          ? trailPrice > position.stopLoss
          : trailPrice < position.stopLoss;

        if (shouldTrail) {
          position.stopLoss = trailPrice;
        }

        // Structure-aware trailing: if price has cleared a structure level, snap SL to it
        if (position.structureLevels && position.structureLevels.length > 0) {
          for (const level of position.structureLevels) {
            if (!level || typeof level.price !== 'number') continue;
            if (isLong && level.type === 'resistance' && currentPrice > level.price) {
              // Cleared resistance — turns into support. Move SL up to it.
              if (level.price > position.stopLoss && level.price < currentPrice) {
                position.stopLoss = level.price;
              }
            }
            if (!isLong && level.type === 'support' && currentPrice < level.price) {
              // Cleared support — turns into resistance. Move SL down to it.
              if (level.price < position.stopLoss && level.price > currentPrice) {
                position.stopLoss = level.price;
              }
            }
          }
        }
      }

      // Check if manual close needed (trailing stop hit)
      const stopHit = isLong
        ? currentPrice <= position.stopLoss
        : currentPrice >= position.stopLoss;

      const notional = position.quantity * currentPrice;

      if (stopHit && position.breakEvenMoved) {
        await this.closePosition(symbol, 'trailing_stop');
        this.risk.removePosition(symbol, pnlDollar, notional);
      }

      // Auto-close on TP/SL hit in dry run
      const tpHit = isLong
        ? currentPrice >= position.takeProfit
        : currentPrice <= position.takeProfit;
      const slHitHard = isLong
        ? currentPrice <= position.stopLoss
        : currentPrice >= position.stopLoss;

      if (tpHit) {
        // Apply exit slippage — TP fills slightly worse than exact level
        const EXIT_SLIP = 0.0003; // 0.03% exit slippage
        const slippedTP = isLong
          ? position.takeProfit * (1 - EXIT_SLIP)  // sell slightly lower
          : position.takeProfit * (1 + EXIT_SLIP); // buy back slightly higher
        const tpPnl = Math.abs((slippedTP - position.entryPrice) / position.entryPrice) * position.margin * position.leverage;
        console.log(`[PM] 🎯 TP HIT ${symbol} +$${tpPnl.toFixed(2)} (slippage applied)`);
        this._recordTrade({ ...position, currentPrice: slippedTP }, 'take_profit', tpPnl);
        this.positions.delete(symbol);
        this.risk.removePosition(symbol, tpPnl, notional);
        this.emit('position_closed', { ...position, closeReason: 'take_profit', pnl: tpPnl });
      } else if (slHitHard && !position.breakEvenMoved) {
        // Apply exit slippage — SL fills slightly worse than exact level
        const EXIT_SLIP = 0.0003;
        const slippedSL = isLong
          ? position.stopLoss * (1 - EXIT_SLIP)   // sell even lower
          : position.stopLoss * (1 + EXIT_SLIP);  // buy back even higher
        const slPnl = -Math.abs((position.entryPrice - slippedSL) / position.entryPrice) * position.margin * position.leverage;
        console.log(`[PM] 🛑 SL HIT ${symbol} -$${Math.abs(slPnl).toFixed(2)} (slippage applied)`);
        this._recordTrade({ ...position, currentPrice: slippedSL }, 'stop_loss', slPnl);
        this.positions.delete(symbol);
        this.risk.removePosition(symbol, slPnl, notional);
        this.emit('position_closed', { ...position, closeReason: 'stop_loss', pnl: slPnl });
      }
    }

    // Update unrealized P&L on risk manager for display
    this.risk.unrealizedPnL = totalUnrealizedPnL;
  }

  _recordTrade(position, reason, pnlOverride) {
    const pnl = pnlOverride !== undefined ? pnlOverride : (position.unrealizedPnL || 0);
    this.tradeHistory.push({
      symbol: position.symbol,
      direction: position.direction,
      entry: position.entryPrice,
      exit: position.currentPrice || position.entryPrice,
      leverage: position.leverage,
      margin: position.margin,
      pnl: parseFloat(pnl.toFixed(2)),
      pnlPercent: position.entryPrice ? parseFloat(((position.currentPrice - position.entryPrice) / position.entryPrice * 100 * (position.direction === 'LONG' ? 1 : -1)).toFixed(2)) : 0,
      reason,
      openTime: position.openTime,
      closeTime: Date.now(),
      duration: Date.now() - (position.openTime || Date.now()),
    });
    if (this.tradeHistory.length > 100) this.tradeHistory.shift();
  }

  getTradeHistory(limit = 50) {
    return this.tradeHistory.slice(-limit).reverse();
  }

  _formatQty(qty, symbol) {
    // Different precision for different coins
    if (symbol.startsWith('BTC')) return qty.toFixed(5);
    if (symbol.startsWith('ETH')) return qty.toFixed(4);
    if (symbol.startsWith('SOL')) return qty.toFixed(2);
    if (symbol.startsWith('XRP')) return qty.toFixed(1);
    return qty.toFixed(4);
  }

  getPositionSummary() {
    const summary = [];
    for (const [symbol, pos] of this.positions) {
      summary.push({
        symbol,
        direction: pos.direction,
        entry: pos.entryPrice,
        currentPrice: pos.currentPrice || pos.entryPrice,
        sl: pos.stopLoss,
        tp: pos.takeProfit,
        leverage: pos.leverage,
        margin: pos.margin,
        rrRatio: pos.rrRatio,
        openTime: pos.openTime,
        breakEvenMoved: !!pos.breakEvenMoved,
        unrealizedPnL: pos.unrealizedPnL || 0,
        pnlPercent: pos.pnlPercent || 0,
      });
    }
    return summary;
  }

  getTotalUnrealizedPnL() {
    let total = 0;
    for (const [, pos] of this.positions) {
      total += pos.unrealizedPnL || 0;
    }
    return total;
  }

  async closeAll(reason = 'shutdown') {
    const symbols = [...this.positions.keys()];
    for (const symbol of symbols) {
      await this.closePosition(symbol, reason);
    }
  }
}

module.exports = { PositionManager };
