const fs = require('fs');
const path = require('path');

class Logger {
  constructor(logDir) {
    this.logDir = logDir || path.join(__dirname, '..', '..', '..', 'logs', 'crypto-agent');
    this.ensureDir();
    this.tradeLog = path.join(this.logDir, 'trades.jsonl');
    this.signalLog = path.join(this.logDir, 'signals.jsonl');
    this.errorLog = path.join(this.logDir, 'errors.log');
  }

  ensureDir() {
    if (!fs.existsSync(this.logDir)) {
      fs.mkdirSync(this.logDir, { recursive: true });
    }
  }

  logTrade(trade) {
    const entry = { ...trade, timestamp: new Date().toISOString() };
    fs.appendFileSync(this.tradeLog, JSON.stringify(entry) + '\n');
  }

  logSignal(signal) {
    const entry = { ...signal, timestamp: new Date().toISOString() };
    fs.appendFileSync(this.signalLog, JSON.stringify(entry) + '\n');
  }

  logError(error, context = '') {
    const entry = `[${new Date().toISOString()}] ${context}: ${error.message}\n${error.stack}\n\n`;
    fs.appendFileSync(this.errorLog, entry);
  }

  getTradeHistory(limit = 50) {
    if (!fs.existsSync(this.tradeLog)) return [];
    const lines = fs.readFileSync(this.tradeLog, 'utf8').trim().split('\n');
    return lines.slice(-limit).map(l => JSON.parse(l));
  }

  getDailyStats() {
    const trades = this.getTradeHistory(1000);
    const today = new Date().toDateString();
    const todayTrades = trades.filter(t => new Date(t.timestamp).toDateString() === today);

    const wins = todayTrades.filter(t => t.pnl > 0);
    const losses = todayTrades.filter(t => t.pnl <= 0);

    return {
      total: todayTrades.length,
      wins: wins.length,
      losses: losses.length,
      winRate: todayTrades.length > 0 ? ((wins.length / todayTrades.length) * 100).toFixed(1) : '0.0',
      totalPnL: todayTrades.reduce((s, t) => s + (t.pnl || 0), 0).toFixed(2),
    };
  }
}

module.exports = { Logger };
