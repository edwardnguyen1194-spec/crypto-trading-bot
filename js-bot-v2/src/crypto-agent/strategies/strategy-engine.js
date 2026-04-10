const { TechnicalAnalysis: TA } = require('../indicators/technical');

/**
 * Signal strength: -100 (strong sell) to +100 (strong buy)
 * Each strategy returns { signal, confidence, reason }
 */

class StrategyEngine {
  constructor(config = {}) {
    this.strategies = [
      { name: 'trend_momentum', weight: 0.20, fn: this.trendMomentum },
      { name: 'mean_reversion', weight: 0.15, fn: this.meanReversion },
      { name: 'breakout', weight: 0.15, fn: this.breakoutStrategy },
      { name: 'scalp', weight: 0.10, fn: this.scalpStrategy },
      { name: 'multi_timeframe', weight: 0.25, fn: this.multiTimeframeConfluence },
      { name: 'smart_money', weight: 0.15, fn: this.smartMoney },
    ];
    this.minConfluence = config.minConfluence || 3;
    this.minScore = config.minScore || 35;
  }

  /**
   * Strategy 1: Trend + Momentum
   * EMA crossover + ADX strength + MACD confirmation
   */
  trendMomentum(analysis) {
    let score = 0;
    const reasons = [];

    // EMA alignment
    if (analysis.ema.ema9 > analysis.ema.ema21 && analysis.ema.ema21 > analysis.ema.ema50) {
      score += 25;
      reasons.push('EMA bullish alignment');
    } else if (analysis.ema.ema9 < analysis.ema.ema21 && analysis.ema.ema21 < analysis.ema.ema50) {
      score -= 25;
      reasons.push('EMA bearish alignment');
    }

    // ADX trend strength
    if (analysis.adx.value > 25) {
      const direction = analysis.adx.plusDI > analysis.adx.minusDI ? 1 : -1;
      score += direction * 20;
      reasons.push(`ADX strong trend ${direction > 0 ? 'bull' : 'bear'}: ${analysis.adx.value.toFixed(1)}`);
    }

    // MACD confirmation
    if (analysis.macd.histogram > 0 && analysis.macd.value > analysis.macd.signal) {
      score += 20;
      reasons.push('MACD bullish crossover');
    } else if (analysis.macd.histogram < 0 && analysis.macd.value < analysis.macd.signal) {
      score -= 20;
      reasons.push('MACD bearish crossover');
    }

    // SuperTrend confirmation
    if (analysis.supertrend.direction === 1) {
      score += 15;
      reasons.push('SuperTrend bullish');
    } else {
      score -= 15;
      reasons.push('SuperTrend bearish');
    }

    // Volume confirmation
    if (analysis.volume > analysis.avgVolume * 1.5) {
      score += Math.sign(score) * 10;
      reasons.push('High volume confirms');
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Strategy 2: Mean Reversion (Bollinger + RSI)
   */
  meanReversion(analysis) {
    let score = 0;
    const reasons = [];

    // RSI extremes
    if (analysis.rsi < 30) {
      score += 30 + (30 - analysis.rsi);
      reasons.push(`RSI oversold: ${analysis.rsi.toFixed(1)}`);
    } else if (analysis.rsi > 70) {
      score -= 30 + (analysis.rsi - 70);
      reasons.push(`RSI overbought: ${analysis.rsi.toFixed(1)}`);
    }

    // Bollinger Band touch
    if (analysis.price <= analysis.bb.lower) {
      score += 25;
      reasons.push('Price at lower BB');
    } else if (analysis.price >= analysis.bb.upper) {
      score -= 25;
      reasons.push('Price at upper BB');
    }

    // Stochastic confirmation
    if (analysis.stochastic.k < 20 && analysis.stochastic.d < 20) {
      score += 20;
      reasons.push('Stoch oversold');
    } else if (analysis.stochastic.k > 80 && analysis.stochastic.d > 80) {
      score -= 20;
      reasons.push('Stoch overbought');
    }

    // Price vs VWAP
    const vwapDist = ((analysis.price - analysis.vwap) / analysis.vwap) * 100;
    if (Math.abs(vwapDist) > 2) {
      score += vwapDist < 0 ? 15 : -15;
      reasons.push(`VWAP deviation: ${vwapDist.toFixed(2)}%`);
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Strategy 3: Breakout
   * Bollinger squeeze + volume explosion
   */
  breakoutStrategy(analysis) {
    let score = 0;
    const reasons = [];

    // Bollinger squeeze (low bandwidth = compression)
    if (analysis.bb.bandwidth < 3) {
      // Squeeze detected - predict direction from momentum
      if (analysis.macd.histogram > 0) {
        score += 35;
        reasons.push('BB squeeze + bullish momentum');
      } else {
        score -= 35;
        reasons.push('BB squeeze + bearish momentum');
      }
    }

    // Price breaking above/below BB
    if (analysis.price > analysis.bb.upper) {
      score += 25;
      reasons.push('Breaking above upper BB');
    } else if (analysis.price < analysis.bb.lower) {
      score -= 25;
      reasons.push('Breaking below lower BB');
    }

    // Volume spike confirmation
    if (analysis.volume > analysis.avgVolume * 2) {
      score += Math.sign(score) * 20;
      reasons.push(`Volume spike ${(analysis.volume / analysis.avgVolume).toFixed(1)}x`);
    }

    // ADX rising = strengthening trend
    if (analysis.adx.value > 20 && analysis.adx.value < 40) {
      score += Math.sign(score) * 15;
      reasons.push('ADX confirming new trend');
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Strategy 4: Scalp (quick entries on momentum shifts)
   */
  scalpStrategy(analysis) {
    let score = 0;
    const reasons = [];

    // RSI momentum zones
    if (analysis.rsi > 50 && analysis.rsi < 65) {
      score += 20;
      reasons.push('RSI bullish momentum zone');
    } else if (analysis.rsi < 50 && analysis.rsi > 35) {
      score -= 20;
      reasons.push('RSI bearish momentum zone');
    }

    // Stochastic crossover
    if (analysis.stochastic.k > analysis.stochastic.d && analysis.stochastic.k < 50) {
      score += 25;
      reasons.push('Stoch bullish cross from low');
    } else if (analysis.stochastic.k < analysis.stochastic.d && analysis.stochastic.k > 50) {
      score -= 25;
      reasons.push('Stoch bearish cross from high');
    }

    // Price vs EMA9 for quick momentum
    const ema9Dist = ((analysis.price - analysis.ema.ema9) / analysis.ema.ema9) * 100;
    if (ema9Dist > 0 && ema9Dist < 0.5) {
      score += 15;
      reasons.push('Price just above EMA9 - pullback entry');
    } else if (ema9Dist < 0 && ema9Dist > -0.5) {
      score -= 15;
      reasons.push('Price just below EMA9 - pullback short');
    }

    // MACD histogram direction
    if (analysis.macd.histogram > 0) {
      score += 10;
    } else {
      score -= 10;
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Strategy 5: Multi-Timeframe Confluence
   * Requires analyses from multiple timeframes
   */
  multiTimeframeConfluence(analysis, mtfAnalyses = {}) {
    let score = 0;
    const reasons = [];
    let agreements = 0;

    // Current timeframe trend
    const currentTrend = analysis.ema.ema9 > analysis.ema.ema21 ? 1 : -1;
    score += currentTrend * 15;

    // Higher timeframe confirmations
    for (const [tf, tfAnalysis] of Object.entries(mtfAnalyses)) {
      if (!tfAnalysis) continue;
      const tfTrend = tfAnalysis.ema.ema9 > tfAnalysis.ema.ema21 ? 1 : -1;
      if (tfTrend === currentTrend) {
        agreements++;
        score += currentTrend * 15;
        reasons.push(`${tf} confirms ${currentTrend > 0 ? 'bull' : 'bear'}`);
      } else {
        reasons.push(`${tf} conflicts`);
      }
    }

    // Ichimoku cloud on current tf
    if (analysis.price > analysis.ichimoku.spanA && analysis.price > analysis.ichimoku.spanB) {
      score += 20;
      reasons.push('Above Ichimoku cloud');
    } else if (analysis.price < analysis.ichimoku.spanA && analysis.price < analysis.ichimoku.spanB) {
      score -= 20;
      reasons.push('Below Ichimoku cloud');
    }

    // Tenkan/Kijun cross
    if (analysis.ichimoku.tenkan > analysis.ichimoku.kijun) {
      score += 10;
    } else {
      score -= 10;
    }

    if (agreements >= 2) {
      score += currentTrend * 15;
      reasons.push(`Strong MTF confluence: ${agreements} timeframes agree`);
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Strategy 6: Smart Money Concepts
   * Order blocks, FVGs, and structure-based S/R
   */
  smartMoney(analysis) {
    let score = 0;
    const reasons = [];

    // Price at order block
    if (analysis.orderBlocks) {
      for (const ob of analysis.orderBlocks) {
        if (ob.type === 'bullish' && analysis.price >= ob.low && analysis.price <= ob.high) {
          score += 30;
          reasons.push('Price at bullish order block');
        }
        if (ob.type === 'bearish' && analysis.price >= ob.low && analysis.price <= ob.high) {
          score -= 30;
          reasons.push('Price at bearish order block');
        }
      }
    }

    // Price filling FVG
    if (analysis.fairValueGaps) {
      for (const fvg of analysis.fairValueGaps) {
        if (fvg.type === 'bullish' && analysis.price >= fvg.lower && analysis.price <= fvg.upper) {
          score += 25;
          reasons.push('Price filling bullish FVG');
        }
        if (fvg.type === 'bearish' && analysis.price >= fvg.lower && analysis.price <= fvg.upper) {
          score -= 25;
          reasons.push('Price filling bearish FVG');
        }
      }
    }

    // Price near support/resistance
    if (analysis.structureLevels) {
      for (const level of analysis.structureLevels.slice(0, 3)) {
        const dist = Math.abs(analysis.price - level.price) / analysis.atr;
        if (dist < 0.5) {
          if (level.type === 'support') {
            score += 20;
            reasons.push(`Near support $${level.price.toFixed(2)}`);
          } else {
            score -= 20;
            reasons.push(`Near resistance $${level.price.toFixed(2)}`);
          }
        }
      }
    }

    return { signal: Math.max(-100, Math.min(100, score)), confidence: Math.abs(score), reasons };
  }

  /**
   * Run all strategies and produce a composite signal
   */
  evaluate(analysis, mtfAnalyses = {}) {
    const results = {};
    let weightedScore = 0;
    let totalWeight = 0;
    let bullCount = 0, bearCount = 0, neutralCount = 0;
    const allReasons = [];

    for (const strategy of this.strategies) {
      const result = strategy.fn.call(this, analysis, mtfAnalyses);
      results[strategy.name] = result;

      weightedScore += result.signal * strategy.weight;
      totalWeight += strategy.weight;

      if (result.signal > 10) bullCount++;
      else if (result.signal < -10) bearCount++;
      else neutralCount++;

      allReasons.push(...result.reasons.map(r => `[${strategy.name}] ${r}`));
    }

    let compositeScore = weightedScore / totalWeight;

    // RSI divergence bonus confluence
    if (analysis.divergence) {
      if (analysis.divergence.bullish && compositeScore > 0) {
        compositeScore = Math.min(100, compositeScore + 10);
        allReasons.push('[divergence] Bullish RSI divergence confirms');
      } else if (analysis.divergence.bearish && compositeScore < 0) {
        compositeScore = Math.max(-100, compositeScore - 10);
        allReasons.push('[divergence] Bearish RSI divergence confirms');
      }
    }

    const confluence = Math.max(bullCount, bearCount);
    const direction = compositeScore > 0 ? 'LONG' : compositeScore < 0 ? 'SHORT' : 'NEUTRAL';

    // Determine action
    let action = 'HOLD';
    if (Math.abs(compositeScore) >= this.minScore && confluence >= this.minConfluence) {
      action = direction === 'LONG' ? 'BUY' : 'SELL';
    }

    return {
      action,
      direction,
      score: compositeScore,
      absScore: Math.abs(compositeScore),
      confluence,
      bullStrategies: bullCount,
      bearStrategies: bearCount,
      neutralStrategies: neutralCount,
      strategies: results,
      reasons: allReasons,
      timestamp: Date.now(),
    };
  }
}

module.exports = { StrategyEngine };
