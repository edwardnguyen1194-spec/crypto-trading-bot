const EventEmitter = require('events');
const { BitunixClient } = require('../exchange/bitunix-client');
const { BitunixWebSocket } = require('../websocket/ws-feed');
const { TechnicalAnalysis } = require('../indicators/technical');
const { StrategyEngine } = require('../strategies/strategy-engine');
const { RiskManager } = require('../core/risk-manager');
const { PositionManager } = require('../core/position-manager');

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT'];
const TIMEFRAMES = ['5m', '15m', '1h', '4h'];
const PRIMARY_TF = '5m';
const SCAN_INTERVAL = 30000; // 30 seconds

class CryptoAgent extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = {
      apiKey: config.apiKey || process.env.BITUNIX_API_KEY,
      secretKey: config.secretKey || process.env.BITUNIX_SECRET_KEY,
      bankroll: config.bankroll || 200,
      symbols: config.symbols || SYMBOLS,
      timeframes: config.timeframes || TIMEFRAMES,
      primaryTf: config.primaryTf || PRIMARY_TF,
      scanInterval: config.scanInterval || SCAN_INTERVAL,
      dryRun: config.dryRun !== undefined ? config.dryRun : true,
      maxRiskPerTrade: config.maxRiskPerTrade || 0.02,
      maxDailyLoss: config.maxDailyLoss || 0.10,
      maxLeverage: config.maxLeverage || 20,
      defaultLeverage: config.defaultLeverage || 10,
      minConfluence: config.minConfluence || 3,
      minScore: config.minScore || 35,
    };

    if (!this.config.apiKey || !this.config.secretKey) {
      throw new Error('BITUNIX_API_KEY and BITUNIX_SECRET_KEY required. Set in .env file.');
    }

    this.client = new BitunixClient(this.config.apiKey, this.config.secretKey);
    this.ws = new BitunixWebSocket(this.client);
    this.strategy = new StrategyEngine({
      minConfluence: this.config.minConfluence,
      minScore: this.config.minScore,
    });
    this.risk = new RiskManager({
      bankroll: this.config.bankroll,
      maxRiskPerTrade: this.config.maxRiskPerTrade,
      maxDailyLoss: this.config.maxDailyLoss,
      maxLeverage: this.config.maxLeverage,
      defaultLeverage: this.config.defaultLeverage,
      previousSession: {
        wins: parseInt(process.env.PREV_WINS || '0'),
        losses: parseInt(process.env.PREV_LOSSES || '0'),
        peakBalance: parseFloat(process.env.PREV_PEAK || '0') || undefined,
        consecutiveLosses: parseInt(process.env.PREV_CONSEC_LOSSES || '0'),
        maxConsecutiveLosses: parseInt(process.env.PREV_MAX_CONSEC || '0'),
      },
    });
    this.positionManager = new PositionManager(
      this.config.dryRun ? this._createDryRunClient() : this.client,
      this.risk
    );

    this.candleCache = {};
    this.analysisCache = {};
    this.tickerCache = {};
    this.scanTimer = null;
    this.isRunning = false;
    this.totalScans = 0;
    this.signalsGenerated = 0;
    this.tradesExecuted = 0;
    this.startTime = null;
  }

  _createDryRunClient() {
    const self = this;
    return new Proxy(this.client, {
      get(target, prop) {
        if (['placeOrder', 'batchOrder', 'cancelOrder', 'cancelAllOrders',
            'closeAllPositions', 'flashClosePosition', 'modifyOrder',
            'changeLeverage', 'changeMarginMode', 'placeTpSlOrder'].includes(prop)) {
          return async (...args) => {
            console.log(`[DRY RUN] ${prop}(${JSON.stringify(args).slice(0, 200)})`);
            return { orderId: `dry_${Date.now()}`, clientId: `dry_client_${Date.now()}` };
          };
        }
        return target[prop].bind(target);
      }
    });
  }

  async start() {
    console.log('\n╔══════════════════════════════════════════════════╗');
    console.log('║      BITUNIX CRYPTO TRADING AGENT v1.0          ║');
    console.log('║      God Mode: ACTIVATED                        ║');
    console.log('╠══════════════════════════════════════════════════╣');
    console.log(`║  Mode:     ${this.config.dryRun ? 'DRY RUN (paper)' : 'LIVE TRADING'}${' '.repeat(this.config.dryRun ? 18 : 20)}║`);
    console.log(`║  Bankroll: $${this.config.bankroll}${' '.repeat(37 - String(this.config.bankroll).length)}║`);
    console.log(`║  Symbols:  ${this.config.symbols.join(', ')}${' '.repeat(Math.max(0, 37 - this.config.symbols.join(', ').length))}║`);
    console.log(`║  Leverage: Up to ${this.config.maxLeverage}x${' '.repeat(31 - String(this.config.maxLeverage).length)}║`);
    console.log(`║  Risk/Trade: ${(this.config.maxRiskPerTrade * 100).toFixed(0)}%${' '.repeat(35)}║`);
    console.log('╚══════════════════════════════════════════════════╝\n');

    this.isRunning = true;
    this.startTime = Date.now();

    // Initialize candle cache
    console.log('[AGENT] Loading historical data...');
    await this._loadHistoricalData();

    // Connect WebSocket for real-time data
    console.log('[AGENT] Connecting WebSocket feeds...');
    try {
      await this.ws.connectPublic(this.config.symbols);
      if (!this.config.dryRun) {
        await this.ws.connectPrivate();
      }
    } catch (e) {
      console.log('[AGENT] WebSocket connection deferred - using REST polling');
    }

    // Set up WebSocket handlers
    this.ws.on('ticker', (data) => {
      if (data && data.symbol) {
        this.tickerCache[data.symbol] = data;
      }
    });

    this.ws.on('position_update', (data) => {
      console.log('[WS] Position update:', JSON.stringify(data).slice(0, 200));
    });

    this.ws.on('order_update', (data) => {
      console.log('[WS] Order update:', JSON.stringify(data).slice(0, 200));
    });

    // Start scanning loop
    console.log(`[AGENT] Starting scan loop (every ${this.config.scanInterval / 1000}s)...\n`);
    await this._scan();
    this.scanTimer = setInterval(() => this._scan(), this.config.scanInterval);

    // Position update loop
    setInterval(() => {
      if (this.positionManager.positions.size > 0) {
        this.positionManager.updatePositions(this.tickerCache);
      }
    }, 5000);

    // Status report every 5 minutes
    setInterval(() => this._printStatus(), 300000);
  }

  async stop() {
    console.log('\n[AGENT] Shutting down...');
    this.isRunning = false;
    if (this.scanTimer) clearInterval(this.scanTimer);

    // Close all positions
    await this.positionManager.closeAll('shutdown');

    // Disconnect WebSocket
    this.ws.disconnect();

    this._printStatus();
    console.log('[AGENT] Shutdown complete.');
  }

  async _loadHistoricalData() {
    for (const symbol of this.config.symbols) {
      this.candleCache[symbol] = {};
      for (const tf of this.config.timeframes) {
        try {
          const klines = await this.client.getKlines(symbol, tf, 200);
          this.candleCache[symbol][tf] = Array.isArray(klines) ? klines : (klines?.klineList || []);
          console.log(`  ✓ ${symbol} ${tf}: ${this.candleCache[symbol][tf].length} candles`);
        } catch (e) {
          console.log(`  ✗ ${symbol} ${tf}: ${e.message}`);
          this.candleCache[symbol][tf] = [];
        }
        // Rate limit: 10 req/s
        await this._sleep(120);
      }
    }
  }

  async _scan() {
    if (!this.isRunning) return;
    this.totalScans++;

    // Time-based mode: reduce risk during dead hours (10pm-8am ET)
    const etHour = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' })).getHours();
    this.isDeadHours = (etHour >= 22 || etHour < 8);

    // Session-aware detection (UTC hours)
    const utcHour = new Date().getUTCHours();
    // Asian session: 0-8 UTC — low volatility, prefer range-bound/mean-reversion
    // London: 7-16 UTC — full momentum
    // NY: 13-22 UTC — full momentum
    // London-NY overlap: 13-16 UTC — best liquidity, reduced confluence requirement
    this.sessionInfo = {
      isAsian: utcHour >= 0 && utcHour < 8,
      isLondon: utcHour >= 7 && utcHour < 16,
      isNY: utcHour >= 13 && utcHour < 22,
      isOverlap: utcHour >= 13 && utcHour < 16,
    };

    let sessionName;
    if (this.sessionInfo.isOverlap) sessionName = 'LDN-NY';
    else if (this.sessionInfo.isLondon) sessionName = 'LONDON';
    else if (this.sessionInfo.isNY) sessionName = 'NY';
    else if (this.sessionInfo.isAsian) sessionName = 'ASIAN';
    else sessionName = 'OFF';

    const timestamp = new Date().toLocaleTimeString();
    const mode = this.isDeadHours ? 'LOW-VOL' : 'ACTIVE';
    console.log(`\n─── Scan #${this.totalScans} @ ${timestamp} [${mode}|${sessionName}] ───`);

    for (const symbol of this.config.symbols) {
      try {
        // Refresh primary timeframe candles
        const klines = await this.client.getKlines(symbol, this.config.primaryTf, 200);
        this.candleCache[symbol][this.config.primaryTf] = Array.isArray(klines) ? klines : (klines?.klineList || []);

        // Refresh 1h candles every scan for MTF filter (critical for avoiding bad trades)
        if (this.totalScans % 4 === 0 || !this.candleCache[symbol]['1h'] || this.candleCache[symbol]['1h'].length < 52) {
          try {
            const h1Klines = await this.client.getKlines(symbol, '1h', 200);
            this.candleCache[symbol]['1h'] = Array.isArray(h1Klines) ? h1Klines : (h1Klines?.klineList || []);
            await this._sleep(120);
          } catch (e) { /* non-critical */ }
        }

        // Run analysis on primary timeframe
        const candles = this.candleCache[symbol][this.config.primaryTf];
        if (!candles || candles.length < 52) {
          console.log(`  ${symbol}: Insufficient data (${candles?.length || 0} candles)`);
          continue;
        }

        const analysis = TechnicalAnalysis.analyze(candles);
        if (!analysis) continue;

        // Multi-timeframe analysis
        const mtfAnalyses = {};
        for (const tf of this.config.timeframes) {
          if (tf === this.config.primaryTf) continue;
          const tfCandles = this.candleCache[symbol][tf];
          if (tfCandles && tfCandles.length >= 52) {
            mtfAnalyses[tf] = TechnicalAnalysis.analyze(tfCandles);
          }
        }

        // Evaluate strategies
        const signal = this.strategy.evaluate(analysis, mtfAnalyses);
        this.analysisCache[symbol] = { analysis, signal, timestamp: Date.now() };

        // Print signal
        const icon = signal.action === 'BUY' ? '🟢' : signal.action === 'SELL' ? '🔴' : '⚪';
        console.log(`  ${icon} ${symbol}: ${signal.action} | Score: ${signal.score.toFixed(1)} | Confluence: ${signal.confluence}/6`);
        if (signal.action !== 'HOLD') {
          console.log(`    RSI: ${analysis.rsi.toFixed(1)} | MACD: ${analysis.macd.histogram > 0 ? '+' : ''}${analysis.macd.histogram.toFixed(4)}`);
          console.log(`    Reasons: ${signal.reasons.slice(0, 3).join(', ')}`);
          this.signalsGenerated++;
        }

        // ═══ AUTO-REGIME DETECTION: Trend vs Chop ═══
        // ADX > 25 = trending → use momentum signal as-is (what made $881)
        // ADX < 20 = choppy → switch to mean reversion (buy low BB, sell high BB)
        // ADX 20-25 = transition → only trade strongest signals

        let tradeAllowed = false;
        let tradeDirection = signal.direction;
        let tradeStrength = signal.absScore;
        const adxValue = analysis.adx ? analysis.adx.value : 30;
        const session = this.sessionInfo;

        if (adxValue > 25) {
          // ═══ TRENDING MARKET: Momentum mode (original bot) ═══
          if (signal.action === 'BUY' || signal.action === 'SELL') {
            tradeAllowed = true;

            // Pullback entry: last candle must confirm direction
            if (candles.length >= 3) {
              const lastCandle = candles[candles.length - 1];
              const lastClose = parseFloat(lastCandle.close);
              const lastOpen = parseFloat(lastCandle.open);
              if (signal.direction === 'LONG' && lastClose < lastOpen) tradeAllowed = false;
              if (signal.direction === 'SHORT' && lastClose > lastOpen) tradeAllowed = false;
            }

            // Session rules for momentum:
            // Asian-only session: block pure momentum (range-bound bias)
            if (session.isAsian && !session.isLondon && !session.isNY) {
              tradeAllowed = false;
              console.log(`    ASIAN session — momentum blocked, waiting for London`);
            }
          }

        } else if (adxValue < 20) {
          // ═══ CHOPPY MARKET: Mean reversion mode ═══
          const price = analysis.price;
          const bbUpper = analysis.bb.upper;
          const bbLower = analysis.bb.lower;
          const bbMid = analysis.bb.middle;
          const rsi = analysis.rsi;

          // BUY at lower BB + oversold RSI (bounce play)
          if (price <= bbLower * 1.002 && rsi < 35) {
            tradeAllowed = true;
            tradeDirection = 'LONG';
            tradeStrength = 45;
            console.log(`    MEAN REV LONG — BB lower + RSI ${rsi.toFixed(1)}`);
          }
          // SELL at upper BB + overbought RSI (fade play)
          else if (price >= bbUpper * 0.998 && rsi > 65) {
            tradeAllowed = true;
            tradeDirection = 'SHORT';
            tradeStrength = 45;
            console.log(`    MEAN REV SHORT — BB upper + RSI ${rsi.toFixed(1)}`);
          }

        } else {
          // ═══ TRANSITION ZONE (ADX 20-25): Only strongest momentum signals ═══
          // During London-NY overlap, relax slightly (best liquidity)
          const minScoreRequired = session.isOverlap ? 45 : 50;
          const minConfluenceRequired = session.isOverlap ? 3 : 4;
          if ((signal.action === 'BUY' || signal.action === 'SELL') &&
              signal.absScore > minScoreRequired &&
              signal.confluence >= minConfluenceRequired) {
            tradeAllowed = true;
            if (session.isOverlap) {
              console.log(`    OVERLAP session — relaxed entry criteria`);
            }
          }
        }

        if (tradeAllowed) {
          const result = await this.positionManager.openPosition({
            symbol,
            direction: tradeDirection,
            analysis,
            signalStrength: tradeStrength,
          });
          if (result) this.tradesExecuted++;
        }

        // Rate limit
        await this._sleep(120);
      } catch (e) {
        console.error(`  ${symbol}: Error - ${e.message}`);
      }
    }

    // Update ticker cache for position management
    await this._refreshTickers();

    // Print open positions
    const positions = this.positionManager.getPositionSummary();
    if (positions.length > 0) {
      console.log('\n  Open Positions:');
      for (const pos of positions) {
        console.log(`    ${pos.direction} ${pos.symbol} @ $${pos.entry.toFixed(2)} | SL: $${pos.sl.toFixed(2)} | TP: $${pos.tp.toFixed(2)} | ${pos.leverage}x`);
      }
    }
  }

  async _refreshTickers() {
    try {
      const tickers = await this.client.getTickers();
      if (Array.isArray(tickers)) {
        for (const t of tickers) {
          if (this.config.symbols.includes(t.symbol)) {
            this.tickerCache[t.symbol] = t;
          }
        }
      }
    } catch (e) {
      // Non-critical
    }
  }

  _printStatus() {
    const metrics = this.risk.getMetrics();
    const uptime = Date.now() - this.startTime;
    const hours = Math.floor(uptime / 3600000);
    const mins = Math.floor((uptime % 3600000) / 60000);

    console.log('\n╔══════════════════════════════════════════════════╗');
    console.log('║              AGENT STATUS REPORT                ║');
    console.log('╠══════════════════════════════════════════════════╣');
    console.log(`║  Uptime:       ${hours}h ${mins}m${' '.repeat(33 - String(hours).length - String(mins).length)}║`);
    console.log(`║  Scans:        ${this.totalScans}${' '.repeat(34 - String(this.totalScans).length)}║`);
    console.log(`║  Signals:      ${this.signalsGenerated}${' '.repeat(34 - String(this.signalsGenerated).length)}║`);
    console.log(`║  Trades:       ${this.tradesExecuted}${' '.repeat(34 - String(this.tradesExecuted).length)}║`);
    console.log('╠══════════════════════════════════════════════════╣');
    console.log(`║  Balance:      $${metrics.currentBalance}${' '.repeat(32 - String(metrics.currentBalance).length)}║`);
    console.log(`║  Daily P&L:    $${metrics.dailyPnL}${' '.repeat(32 - String(metrics.dailyPnL).length)}║`);
    console.log(`║  Total P&L:    $${metrics.totalPnL}${' '.repeat(32 - String(metrics.totalPnL).length)}║`);
    console.log(`║  Win Rate:     ${metrics.winRate}%${' '.repeat(33 - String(metrics.winRate).length)}║`);
    console.log(`║  Profit Factor: ${metrics.profitFactor}${' '.repeat(32 - String(metrics.profitFactor).length)}║`);
    console.log(`║  Max Drawdown: ${metrics.maxDrawdown}%${' '.repeat(33 - String(metrics.maxDrawdown).length)}║`);
    console.log(`║  Open Pos:     ${metrics.openPositions}/${this.risk.maxOpenPositions}${' '.repeat(32 - String(metrics.openPositions).length)}║`);
    console.log('╚══════════════════════════════════════════════════╝');
  }

  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = { CryptoAgent };
