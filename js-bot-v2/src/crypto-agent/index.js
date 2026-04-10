#!/usr/bin/env node
require('dotenv').config();
const { CryptoAgent } = require('./core/agent');

const config = {
  apiKey: process.env.BITUNIX_API_KEY,
  secretKey: process.env.BITUNIX_SECRET_KEY,
  bankroll: parseFloat(process.env.BANKROLL || '200'),
  symbols: (process.env.SYMBOLS || 'BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT').split(','),
  timeframes: ['5m', '15m', '1h', '4h'],
  primaryTf: '5m',
  scanInterval: parseInt(process.env.SCAN_INTERVAL || '30000'),
  dryRun: process.env.DRY_RUN !== 'false',
  maxRiskPerTrade: parseFloat(process.env.MAX_RISK_PER_TRADE || '0.02'),
  maxDailyLoss: parseFloat(process.env.MAX_DAILY_LOSS || '0.10'),
  maxLeverage: parseInt(process.env.MAX_LEVERAGE || '20'),
  defaultLeverage: parseInt(process.env.DEFAULT_LEVERAGE || '10'),
  minConfluence: parseInt(process.env.MIN_CONFLUENCE || '3'),
  minScore: parseInt(process.env.MIN_SCORE || '35'),
};

// CLI arguments override
const args = process.argv.slice(2);
for (const arg of args) {
  if (arg === '--live') config.dryRun = false;
  if (arg === '--dry-run') config.dryRun = true;
  if (arg.startsWith('--bankroll=')) config.bankroll = parseFloat(arg.split('=')[1]);
  if (arg.startsWith('--leverage=')) config.defaultLeverage = parseInt(arg.split('=')[1]);
  if (arg.startsWith('--interval=')) config.scanInterval = parseInt(arg.split('=')[1]) * 1000;
  if (arg === '--help') {
    console.log(`
Bitunix Crypto Trading Agent

Usage: node src/crypto-agent/index.js [options]

Options:
  --dry-run          Paper trading mode (default)
  --live             Live trading mode (REAL MONEY)
  --bankroll=200     Starting capital
  --leverage=10      Default leverage
  --interval=30      Scan interval in seconds

Environment Variables (.env):
  BITUNIX_API_KEY     Your Bitunix API key
  BITUNIX_SECRET_KEY  Your Bitunix secret key
  DRY_RUN             true/false (default: true)
  BANKROLL            Starting capital (default: 200)
  SYMBOLS             Comma-separated pairs (default: BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT)
  MAX_LEVERAGE        Max leverage (default: 20)
  DEFAULT_LEVERAGE    Default leverage (default: 10)
  MAX_RISK_PER_TRADE  Risk per trade as decimal (default: 0.02 = 2%)
  MAX_DAILY_LOSS      Max daily loss as decimal (default: 0.10 = 10%)
  SCAN_INTERVAL       Scan interval in ms (default: 30000)
  MIN_CONFLUENCE      Min strategies agreeing (default: 3)
  MIN_SCORE           Min composite score (default: 35)
    `);
    process.exit(0);
  }
}

// Safety check for live mode
if (!config.dryRun) {
  console.log('\n⚠️  WARNING: LIVE TRADING MODE ⚠️');
  console.log('This will execute REAL trades with REAL money.');
  console.log('Press Ctrl+C within 5 seconds to cancel...\n');
}

const agent = new CryptoAgent(config);

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n\nReceived SIGINT...');
  await agent.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await agent.stop();
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  console.error('[FATAL] Uncaught exception:', err);
  agent.stop().then(() => process.exit(1));
});

// Start the agent
(async () => {
  try {
    if (!config.dryRun) {
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
    await agent.start();
  } catch (err) {
    console.error('[FATAL] Failed to start agent:', err.message);
    process.exit(1);
  }
})();
