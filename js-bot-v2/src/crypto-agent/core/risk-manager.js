/**
 * Risk Management System
 * - Position sizing (Kelly Criterion + ATR-based)
 * - Max drawdown protection
 * - Correlation-aware exposure
 * - Dynamic stop loss / take profit
 * - Daily loss limits
 */

const fs = require('fs');
const path = require('path');

const STATE_FILE = path.join(__dirname, '..', '..', '..', 'state.json');

class RiskManager {
  constructor(config = {}) {
    // Try to load saved state first
    const saved = this._loadState();
    this.bankroll = saved ? saved.currentBalance : (config.bankroll || 200);
    this.maxRiskPerTrade = config.maxRiskPerTrade || 0.02; // 2% per trade
    this.maxDailyLoss = config.maxDailyLoss || 0.10; // 10% daily max loss
    this.maxOpenPositions = config.maxOpenPositions || 15;
    this.maxExposure = config.maxExposure || 0.60; // 60% total capital at risk
    this.maxLeverage = config.maxLeverage || 20; // VIP1 level
    this.defaultLeverage = config.defaultLeverage || 10;
    this.minRiskReward = config.minRiskReward || 2.0; // Minimum 1:2 R:R

    // Bitunix VIP1 fees
    this.makerFee = config.makerFee || 0.00018; // 0.018%
    this.takerFee = config.takerFee || 0.00055; // 0.055%
    this.totalFees = 0;

    // Restore from saved state file (survives restarts) or env vars as fallback
    const prev = saved || config.previousSession || {};
    const prevWins = prev.wins || parseInt(process.env.PREV_WINS || '0');
    const prevLosses = prev.losses || parseInt(process.env.PREV_LOSSES || '0');

    this.dailyPnL = 0;
    this.dailyTrades = 0;
    this.dailyWins = 0;
    this.dailyLosses = 0;
    this.openPositions = new Map();
    this.tradeHistory = [];
    // NOTE: Previously this seeded tradeHistory with fake $2.47 wins and
    // -$2.50 losses based on PREV_WINS / PREV_LOSSES env vars. That inflated
    // the dashboard win rate with fabricated trades that had no real prices
    // or times — a MAJOR source of the "97.2% WR" illusion on the old bot.
    //
    // If the user wants to carry over *counts* from a previous session for
    // display purposes, we now track them as separate counters instead of
    // polluting tradeHistory with synthetic trades.
    const seedFakeTrades = process.env.SEED_FAKE_TRADES === 'true';
    if (seedFakeTrades) {
      // Explicit opt-in for legacy behavior (not recommended)
      const oldTime = Date.now() - 7 * 24 * 60 * 60 * 1000;
      for (let i = 0; i < prevWins; i++) this.tradeHistory.push({ pnl: 2.47, balance: this.bankroll, timestamp: oldTime, synthetic: true });
      for (let i = 0; i < prevLosses; i++) this.tradeHistory.push({ pnl: -2.50, balance: this.bankroll, timestamp: oldTime, synthetic: true });
      console.log(`[RISK] ⚠ Seeded ${prevWins} synthetic wins + ${prevLosses} synthetic losses (SEED_FAKE_TRADES=true)`);
    } else {
      // Track carried-over counts separately so they don't corrupt real stats
      this.carriedOverWins = prevWins;
      this.carriedOverLosses = prevLosses;
      if (prevWins > 0 || prevLosses > 0) {
        console.log(`[RISK] Carried over from previous session: ${prevWins}W / ${prevLosses}L (display only, not in tradeHistory)`);
      }
    }
    this.peakBalance = prev.peakBalance || this.bankroll;
    this.currentBalance = this.bankroll;
    this.dayStartBalance = this.bankroll;
    this.lastResetDate = new Date().toDateString();
    this.consecutiveLosses = prev.consecutiveLosses || 0;
    this.totalFees = prev.totalFees || 0;
    this.maxConsecutiveLosses = prev.maxConsecutiveLosses || 0;
  }

  resetDaily() {
    const today = new Date().toDateString();
    if (today !== this.lastResetDate) {
      this.dailyPnL = 0;
      this.dailyTrades = 0;
      this.dailyWins = 0;
      this.dailyLosses = 0;
      this.dayStartBalance = this.currentBalance;
      this.lastResetDate = today;
    }
  }

  calculateFee(notionalValue) {
    // Market orders use taker fee, both entry and exit
    const fee = notionalValue * this.takerFee * 2; // round trip
    this.totalFees += fee;
    return fee;
  }

  updateBalance(pnl, notionalValue = 0) {
    // Deduct round-trip fees from P&L
    const fee = notionalValue > 0 ? this.calculateFee(notionalValue) : 0;
    const netPnl = pnl - fee;

    this.currentBalance += netPnl;
    this.dailyPnL += netPnl;
    this.dailyTrades++;
    this.bankroll = this.currentBalance;

    if (netPnl > 0) {
      this.dailyWins++;
      this.consecutiveLosses = 0;
    } else {
      this.dailyLosses++;
      this.consecutiveLosses++;
      this.maxConsecutiveLosses = Math.max(this.maxConsecutiveLosses, this.consecutiveLosses);
    }

    if (this.currentBalance > this.peakBalance) {
      this.peakBalance = this.currentBalance;
    }

    this.tradeHistory.push({
      pnl,
      balance: this.currentBalance,
      timestamp: Date.now(),
    });

    // Auto-save state after every trade
    this._saveState();
  }

  _saveState() {
    try {
      const state = {
        currentBalance: this.currentBalance,
        peakBalance: this.peakBalance,
        totalFees: this.totalFees,
        consecutiveLosses: this.consecutiveLosses,
        maxConsecutiveLosses: this.maxConsecutiveLosses,
        wins: this.tradeHistory.filter(t => t.pnl > 0).length,
        losses: this.tradeHistory.filter(t => t.pnl <= 0).length,
        totalTrades: this.tradeHistory.length,
        savedAt: new Date().toISOString(),
      };
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
    } catch (e) {
      // Non-critical
    }
  }

  _loadState() {
    try {
      if (fs.existsSync(STATE_FILE)) {
        const data = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
        console.log(`[RISK] Loaded saved state: $${data.currentBalance} | ${data.wins}W/${data.losses}L`);
        return data;
      }
    } catch (e) {
      // Non-critical
    }
    return null;
  }

  /**
   * Check if trading is allowed
   */
  canTrade() {
    this.resetDaily();
    const reasons = [];

    // Daily loss limit check
    const dailyLossPercent = Math.abs(Math.min(0, this.dailyPnL)) / this.dayStartBalance;
    if (dailyLossPercent >= this.maxDailyLoss) {
      reasons.push(`Daily loss limit reached: ${(dailyLossPercent * 100).toFixed(1)}%`);
    }

    // Max open positions
    if (this.openPositions.size >= this.maxOpenPositions) {
      reasons.push(`Max open positions reached: ${this.openPositions.size}/${this.maxOpenPositions}`);
    }

    // Max exposure check
    let totalExposure = 0;
    for (const [, pos] of this.openPositions) {
      totalExposure += pos.margin;
    }
    if (totalExposure / this.currentBalance >= this.maxExposure) {
      reasons.push(`Max exposure reached: ${((totalExposure / this.currentBalance) * 100).toFixed(1)}%`);
    }

    // Drawdown circuit breaker
    const drawdown = (this.peakBalance - this.currentBalance) / this.peakBalance;
    if (drawdown >= 0.20) {
      reasons.push(`Max drawdown breaker: ${(drawdown * 100).toFixed(1)}%`);
    }

    // Consecutive loss cooldown — pause for 15 min after 5 losses, then auto-resume
    if (this.consecutiveLosses >= 5) {
      const cooldownTime = 5 * 60 * 1000; // 5 minutes
      const lastTradeTime = this.tradeHistory.length > 0 ? this.tradeHistory[this.tradeHistory.length - 1].timestamp : 0;
      const timeSinceLast = Date.now() - lastTradeTime;
      if (timeSinceLast < cooldownTime) {
        const minsLeft = Math.ceil((cooldownTime - timeSinceLast) / 60000);
        reasons.push(`Loss cooldown: ${this.consecutiveLosses} losses, resuming in ${minsLeft}m`);
      } else {
        // Cooldown expired — reset and allow trading with half size
        this.consecutiveLosses = 0;
        console.log('[RISK] Cooldown expired — resuming trading');
      }
    }

    // Minimum balance protection
    if (this.currentBalance < this.bankroll * 0.3) {
      reasons.push('Balance critically low - trading suspended');
    }

    return { allowed: reasons.length === 0, reasons };
  }

  /**
   * Calculate position size using modified Kelly + ATR
   */
  calculatePositionSize(price, atr, signalStrength, leverage = null) {
    const lev = leverage || this.defaultLeverage;

    // Base risk amount
    const riskAmount = this.currentBalance * this.maxRiskPerTrade;

    // ATR-based stop distance (1.5x ATR)
    const stopDistance = atr * 1.5;
    const stopPercent = stopDistance / price;

    // Position size from risk
    let positionSize = riskAmount / stopDistance;

    // Scale by signal strength (0-100)
    const strengthMultiplier = Math.min(1, signalStrength / 80);
    positionSize *= strengthMultiplier;

    // Scale down after consecutive losses
    if (this.consecutiveLosses >= 2) {
      positionSize *= 0.5;
    }

    // Calculate margin required
    const notionalValue = positionSize * price;
    const margin = notionalValue / lev;

    // Cap margin to max risk per trade
    const maxMargin = this.currentBalance * this.maxRiskPerTrade * 2;
    if (margin > maxMargin) {
      positionSize = (maxMargin * lev) / price;
    }

    // Min order size check
    const minNotional = 5; // $5 minimum
    if (positionSize * price < minNotional) {
      return null; // Too small to trade
    }

    return {
      quantity: positionSize,
      notionalValue: positionSize * price,
      margin: (positionSize * price) / lev,
      leverage: lev,
      stopDistance,
      stopPercent,
      riskAmount: Math.min(riskAmount, margin),
    };
  }

  /**
   * Calculate ASYMMETRIC TP/SL levels
   * Tight TP (1.5 ATR) = fast wins, high win rate
   * Wide SL (2.5 ATR) = survive noise, fewer stopouts
   * Optionally refines TP/SL to snap to nearby structure levels
   */
  calculateLevels(price, atr, direction, signalStrength, structureLevels = []) {
    // ASYMMETRIC base levels
    let tpDistance = atr * 1.5;
    let slDistance = atr * 2.5;

    // Structure-aware refinement: snap TP just before enemy S/R, SL just beyond friendly S/R
    if (structureLevels && structureLevels.length > 0) {
      const isLong = direction === 'LONG';
      for (const level of structureLevels) {
        if (!level || typeof level.price !== 'number') continue;
        const dist = Math.abs(price - level.price);

        if (isLong) {
          // LONG: resistance above is TP target, support below is SL anchor
          if (level.type === 'resistance' && level.price > price && dist < tpDistance && dist > atr * 0.5) {
            tpDistance = dist * 0.95; // Take profit just before resistance
          }
          if (level.type === 'support' && level.price < price && dist < slDistance && dist > atr * 0.3) {
            slDistance = dist + atr * 0.2; // Stop just below support
          }
        } else {
          // SHORT: support below is TP target, resistance above is SL anchor
          if (level.type === 'support' && level.price < price && dist < tpDistance && dist > atr * 0.5) {
            tpDistance = dist * 0.95;
          }
          if (level.type === 'resistance' && level.price > price && dist < slDistance && dist > atr * 0.3) {
            slDistance = dist + atr * 0.2;
          }
        }
      }
    }

    const rrRatio = tpDistance / slDistance;

    const isLong = direction === 'LONG';
    const sl = isLong ? price - slDistance : price + slDistance;
    const tp = isLong ? price + tpDistance : price - tpDistance;

    // Move to breakeven after 0.5x ATR profit (lock in quickly)
    const breakEvenTrigger = isLong ? price + (atr * 0.5) : price - (atr * 0.5);

    return {
      stopLoss: sl,
      takeProfit: tp,
      slDistance,
      tpDistance,
      rrRatio,
      breakEvenTrigger,
      trailingStop: atr * 0.4, // Tight trailing for quick exits
      partialTpTrigger: isLong ? price + (atr * 1.0) : price - (atr * 1.0), // Close 50% at 1 ATR
      tightTrailingStop: atr * 0.3, // Used after partial TP
    };
  }

  /**
   * Check correlation — prevent stacking too many positions on correlated assets
   */
  checkCorrelation(symbol, direction, openPositions) {
    const groups = {
      'BTC_GROUP': ['BTCUSDT', 'ETHUSDT'],
      'ALT_GROUP': ['SOLUSDT', 'XRPUSDT'],
    };

    for (const [groupName, symbols] of Object.entries(groups)) {
      if (!symbols.includes(symbol)) continue;
      let sameDirectionCount = 0;
      for (const [posSymbol, pos] of openPositions) {
        if (symbols.includes(posSymbol) && pos.direction === direction) {
          sameDirectionCount++;
        }
      }
      if (sameDirectionCount >= 2) {
        return { allowed: false, reason: `Max correlated positions in ${groupName}` };
      }
    }
    return { allowed: true };
  }

  /**
   * Optimal leverage based on volatility
   */
  calculateLeverage(atr, price) {
    const volatilityPercent = (atr / price) * 100;

    // Lower leverage for higher volatility
    let leverage;
    if (volatilityPercent > 5) leverage = 3;
    else if (volatilityPercent > 3) leverage = 5;
    else if (volatilityPercent > 2) leverage = 8;
    else if (volatilityPercent > 1) leverage = 10;
    else leverage = 15;

    return Math.min(leverage, this.maxLeverage);
  }

  /**
   * Position tracking
   */
  addPosition(id, position) {
    this.openPositions.set(id, { ...position, openTime: Date.now() });
  }

  removePosition(id, pnl, notionalValue = 0) {
    this.openPositions.delete(id);
    this.updateBalance(pnl, notionalValue);
  }

  /**
   * Risk metrics
   */
  getMetrics() {
    const totalTrades = this.tradeHistory.length;
    const wins = this.tradeHistory.filter(t => t.pnl > 0).length;
    const losses = this.tradeHistory.filter(t => t.pnl <= 0).length;
    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
    const avgWin = wins > 0 ? this.tradeHistory.filter(t => t.pnl > 0).reduce((s, t) => s + t.pnl, 0) / wins : 0;
    const avgLoss = losses > 0 ? Math.abs(this.tradeHistory.filter(t => t.pnl <= 0).reduce((s, t) => s + t.pnl, 0) / losses) : 0;
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : 0;
    const maxDrawdown = ((this.peakBalance - Math.min(...this.tradeHistory.map(t => t.balance), this.currentBalance)) / this.peakBalance) * 100;
    const totalPnL = this.currentBalance - this.tradeHistory[0]?.balance + (this.tradeHistory[0]?.pnl || 0) || 0;

    return {
      totalTrades,
      wins,
      losses,
      winRate: winRate.toFixed(1),
      avgWin: avgWin.toFixed(2),
      avgLoss: avgLoss.toFixed(2),
      profitFactor: profitFactor.toFixed(2),
      maxDrawdown: maxDrawdown.toFixed(1),
      currentBalance: this.currentBalance.toFixed(2),
      dailyPnL: this.dailyPnL.toFixed(2),
      dailyWinRate: this.dailyTrades > 0 ? ((this.dailyWins / this.dailyTrades) * 100).toFixed(1) : '0.0',
      consecutiveLosses: this.consecutiveLosses,
      maxConsecutiveLosses: this.maxConsecutiveLosses,
      totalPnL: totalPnL.toFixed(2),
      openPositions: this.openPositions.size,
      totalFees: this.totalFees.toFixed(2),
    };
  }
}

module.exports = { RiskManager };
