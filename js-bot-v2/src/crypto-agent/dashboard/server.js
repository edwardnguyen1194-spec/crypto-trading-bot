#!/usr/bin/env node
require('dotenv').config();
const http = require('http');
const express = require('express');
const { WebSocketServer } = require('ws');
const path = require('path');
const Anthropic = require('@anthropic-ai/sdk');
const { CryptoAgent } = require('../core/agent');
const { WebIntel } = require('../utils/web-intel');

const webIntel = new WebIntel();

// AI chat brain - check multiple sources for API key
const apiKey = process.env.ANTHROPIC_API_KEY;
if (!apiKey) {
  console.log('[WARN] No ANTHROPIC_API_KEY found - AI chat will use fallback mode');
}
const anthropic = apiKey ? new Anthropic({ apiKey }) : null;
const AI_MODEL = 'claude-opus-4-20250514';

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

// Serve static frontend
app.use(express.static(path.join(__dirname, 'public')));

// Agent instance
let agent = null;
const clients = new Set();
const chatHistory = [];

function broadcast(msg) {
  const payload = JSON.stringify(msg);
  for (const ws of clients) {
    if (ws.readyState === 1) ws.send(payload);
  }
}

function addChat(role, text) {
  const entry = { role, text, time: new Date().toLocaleTimeString() };
  chatHistory.push(entry);
  if (chatHistory.length > 200) chatHistory.shift();
  broadcast({ type: 'chat', ...entry });
}

// Intercept console.log to pipe to chat
const origLog = console.log;
const origError = console.error;
console.log = (...args) => {
  const text = args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' ');
  origLog.apply(console, args);
  broadcast({ type: 'log', text, time: new Date().toLocaleTimeString() });
};
console.error = (...args) => {
  const text = args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' ');
  origError.apply(console, args);
  broadcast({ type: 'error', text, time: new Date().toLocaleTimeString() });
};

// Command handler
async function handleCommand(input) {
  const cmd = input.trim().toLowerCase();
  const parts = cmd.split(/\s+/);

  switch (parts[0]) {
    case 'start':
    case 'run':
      if (agent && agent.isRunning) {
        addChat('agent', 'Agent is already running.');
      } else {
        addChat('agent', 'Starting agent in DRY RUN mode...');
        try {
          agent = new CryptoAgent({
            bankroll: parseFloat(process.env.BANKROLL || '200'),
            symbols: (process.env.SYMBOLS || 'BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT').split(','),
            dryRun: process.env.DRY_RUN !== 'false',
            maxLeverage: parseInt(process.env.MAX_LEVERAGE || '20'),
            defaultLeverage: parseInt(process.env.DEFAULT_LEVERAGE || '10'),
          });
          await agent.start();
        } catch (e) {
          addChat('agent', `Failed to start: ${e.message}`);
        }
      }
      break;

    case 'stop':
      if (agent && agent.isRunning) {
        addChat('agent', 'Stopping agent...');
        await agent.stop();
        addChat('agent', 'Agent stopped.');
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'status':
      if (agent && agent.isRunning) {
        const metrics = agent.risk.getMetrics();
        const canTrade = agent.risk.canTrade();
        addChat('agent',
          `📊 **Status**\n` +
          `Trading: ${canTrade.allowed ? '✅ ACTIVE' : '⏸️ PAUSED — ' + canTrade.reasons.join(', ')}\n` +
          `Balance: $${metrics.currentBalance}\n` +
          `Daily P&L: $${metrics.dailyPnL}\n` +
          `Win Rate: ${metrics.winRate}%\n` +
          `Total Trades: ${metrics.totalTrades}\n` +
          `Open Positions: ${metrics.openPositions}\n` +
          `Profit Factor: ${metrics.profitFactor}\n` +
          `Max Drawdown: ${metrics.maxDrawdown}%\n` +
          `Consecutive Losses: ${metrics.consecutiveLosses}`
        );
      } else {
        addChat('agent', 'Agent is not running. Type **start** to begin.');
      }
      break;

    case 'reset':
    case 'resume':
    case 'unpause':
      if (agent && agent.isRunning) {
        agent.risk.consecutiveLosses = 0;
        addChat('agent', '✅ Cooldown reset! Bot is now free to trade again.');
      } else {
        addChat('agent', 'Agent is not running. Type **start** first.');
      }
      break;

    case 'positions':
    case 'pos':
      if (agent && agent.isRunning) {
        const positions = agent.positionManager.getPositionSummary();
        if (positions.length === 0) {
          addChat('agent', 'No open positions.');
        } else {
          let msg = '📈 **Open Positions**\n';
          for (const p of positions) {
            msg += `${p.direction} ${p.symbol} @ $${p.entry.toFixed(2)} | SL: $${p.sl.toFixed(2)} | TP: $${p.tp.toFixed(2)} | ${p.leverage}x\n`;
          }
          addChat('agent', msg);
        }
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'balance':
    case 'bal':
      if (agent && agent.isRunning) {
        try {
          const account = await agent.client.getAccount();
          addChat('agent', `💰 **Account Balance**\n${JSON.stringify(account, null, 2)}`);
        } catch (e) {
          addChat('agent', `Balance fetch error: ${e.message}`);
        }
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'scan':
      if (agent && agent.isRunning) {
        addChat('agent', 'Running manual scan...');
        await agent._scan();
        addChat('agent', 'Scan complete.');
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'close':
      if (parts[1] && agent && agent.isRunning) {
        const symbol = parts[1].toUpperCase();
        if (symbol === 'ALL') {
          addChat('agent', 'Closing all positions...');
          await agent.positionManager.closeAll('manual');
          addChat('agent', 'All positions closed.');
        } else {
          addChat('agent', `Closing ${symbol}...`);
          await agent.positionManager.closePosition(symbol + (symbol.endsWith('USDT') ? '' : 'USDT'), 'manual');
          addChat('agent', `${symbol} position closed.`);
        }
      } else {
        addChat('agent', 'Usage: **close BTCUSDT** or **close all**');
      }
      break;

    case 'prices':
    case 'price':
      if (agent) {
        const tickers = agent.tickerCache;
        let msg = '💲 **Current Prices**\n';
        for (const sym of (agent.config.symbols || [])) {
          const t = tickers[sym];
          msg += `${sym}: $${t ? parseFloat(t.lastPrice || 0).toLocaleString() : 'N/A'}\n`;
        }
        addChat('agent', msg);
      } else {
        addChat('agent', 'Agent not initialized.');
      }
      break;

    case 'analysis':
    case 'analyze':
      if (agent && agent.isRunning) {
        const sym = (parts[1] || 'BTCUSDT').toUpperCase();
        const cached = agent.analysisCache[sym + (sym.endsWith('USDT') ? '' : 'USDT')];
        if (cached) {
          const a = cached.analysis;
          const s = cached.signal;
          addChat('agent',
            `🔬 **${sym} Analysis**\n` +
            `Price: $${a.price.toFixed(2)}\n` +
            `RSI: ${a.rsi.toFixed(1)}\n` +
            `MACD: ${a.macd.histogram > 0 ? '+' : ''}${a.macd.histogram.toFixed(4)}\n` +
            `BB Width: ${a.bb.bandwidth.toFixed(2)}%\n` +
            `ATR: $${a.atr.toFixed(2)}\n` +
            `SuperTrend: ${a.supertrend.direction === 1 ? 'Bullish' : 'Bearish'}\n` +
            `ADX: ${a.adx.value.toFixed(1)}\n` +
            `Signal: **${s.action}** (Score: ${s.score.toFixed(1)}, Confluence: ${s.confluence}/5)\n` +
            `Reasons: ${s.reasons.slice(0, 5).join(', ')}`
          );
        } else {
          addChat('agent', `No analysis cached for ${sym}. Run **scan** first.`);
        }
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'leverage':
    case 'lev':
      if (parts[1] && agent) {
        const lev = parseInt(parts[1]);
        if (lev >= 1 && lev <= 20) {
          agent.config.defaultLeverage = lev;
          agent.risk.defaultLeverage = lev;
          addChat('agent', `Leverage updated to ${lev}x`);
        } else {
          addChat('agent', 'Leverage must be between 1 and 20.');
        }
      } else {
        addChat('agent', `Current leverage: ${agent?.config.defaultLeverage || 10}x. Usage: **leverage 15**`);
      }
      break;

    case 'risk':
      if (agent) {
        addChat('agent',
          `⚠️ **Risk Settings**\n` +
          `Risk/Trade: ${(agent.risk.maxRiskPerTrade * 100).toFixed(0)}%\n` +
          `Daily Loss Limit: ${(agent.risk.maxDailyLoss * 100).toFixed(0)}%\n` +
          `Max Leverage: ${agent.risk.maxLeverage}x\n` +
          `Max Open Positions: ${agent.risk.maxOpenPositions}\n` +
          `Max Exposure: ${(agent.risk.maxExposure * 100).toFixed(0)}%\n` +
          `Min R:R Ratio: ${agent.risk.minRiskReward}:1`
        );
      } else {
        addChat('agent', 'Agent not initialized.');
      }
      break;

    case 'live':
      addChat('agent', '⚠️ **LIVE MODE** - This will use REAL money. Type **confirm live** to enable.');
      break;

    case 'confirm':
      if (parts[1] === 'live') {
        if (agent && agent.isRunning) {
          addChat('agent', 'Stop the agent first, then restart in live mode.');
        } else {
          process.env.DRY_RUN = 'false';
          addChat('agent', '🔴 **LIVE MODE ENABLED** - Next start will use real money. Type **start** to begin.');
        }
      }
      break;

    case 'dry':
    case 'paper':
      process.env.DRY_RUN = 'true';
      addChat('agent', '🟢 **DRY RUN MODE** - Paper trading enabled.');
      break;

    case 'news':
    case 'market':
    case 'intel':
      addChat('agent', 'Pulling live market intel...');
      try {
        const intel = await webIntel.getMarketIntel();
        addChat('agent', intel);
      } catch (e) {
        addChat('agent', 'Failed to fetch market data.');
      }
      break;

    case 'history':
    case 'trades':
      if (agent && agent.isRunning) {
        const history = agent.positionManager.getTradeHistory(10);
        if (history.length === 0) {
          addChat('agent', 'No closed trades yet.');
        } else {
          let msg = '📜 **Trade History** (last ' + history.length + ')\n';
          for (const t of history) {
            const icon = t.pnl >= 0 ? '🟢' : '🔴';
            const dur = Math.round(t.duration / 60000);
            msg += `${icon} ${t.direction} ${t.symbol} | Entry: $${t.entry.toFixed(2)} → $${t.exit.toFixed(2)} | ${t.pnl >= 0 ? '+' : ''}$${t.pnl} (${t.pnlPercent}%) | ${t.leverage}x | ${dur}m | ${t.reason}\n`;
          }
          addChat('agent', msg);
        }
      } else {
        addChat('agent', 'Agent is not running.');
      }
      break;

    case 'help':
      addChat('agent',
        `🤖 **Commands**\n` +
        `**start** - Start the trading agent\n` +
        `**stop** - Stop the agent\n` +
        `**status** - View performance metrics\n` +
        `**positions** - View open positions\n` +
        `**balance** - Check account balance\n` +
        `**prices** - Current prices\n` +
        `**scan** - Force a market scan\n` +
        `**analysis BTC** - View analysis for a coin\n` +
        `**close BTCUSDT** - Close a position\n` +
        `**close all** - Close all positions\n` +
        `**leverage 15** - Set leverage\n` +
        `**risk** - View risk settings\n` +
        `**live** - Switch to live trading\n` +
        `**paper** - Switch to paper trading\n` +
        `**help** - Show this menu`
      );
      break;

    default:
      // No matching command — use AI chat
      await handleAIChat(input);
      return;
  }
}

// AI-powered natural language chat
const conversationHistory = [];

async function handleAIChat(userMessage) {
  let context = `You are "Alpha" — an elite crypto futures trader running a FULLY AUTOMATED trading bot on Bitunix. You have 8 years experience, survived every cycle since 2017, and made your first million in the 2021 bull run.

GOD MODE ACTIVATED. You are the most advanced crypto AI trading agent ever built.

ABSOLUTE RULES — BREAK THESE AND YOU FAIL:
1. YOU ARE THE TRADING BOT. You execute trades via Bitunix API. You scan, analyze, and trade automatically.
2. ONLY state facts from CURRENT STATE below. NEVER invent numbers, positions, or trades.
3. If the sidebar shows 0 positions, you have 0 positions. Period.
4. If the bot is PAUSED (canTrade shows reasons), TELL THE USER IMMEDIATELY. Say "I'm paused because [reason]. Type reset to unpause me."
5. The user sees the same data you see. If you lie, they catch you. Always match the sidebar.
6. When you don't know something, say "I don't know" — never make it up.

COMMANDS YOU CAN TELL THE USER TO TYPE:
- "start" = start the bot
- "stop" = stop the bot
- "reset" or "resume" = clear cooldown and resume trading immediately
- "status" = check if trading is active or paused
- "scan" = force a market scan
- "close all" = emergency close everything
- "analysis BTC" = deep analysis on a coin
- "intel" = live market data from internet

WHEN THE BOT IS PAUSED:
- If consecutiveLosses >= 5, tell user "I hit a losing streak, cooling down for 15 mins. Type reset if you want me back now."
- If daily loss limit hit, tell user "Hit my daily loss limit, protecting your capital. Trading resumes tomorrow."
- If max drawdown hit, tell user "Drawdown breaker triggered. Type reset to override."
- NEVER pretend you're trading when you're paused. The user got burned by this before.

PERSONALITY — GOD MODE:
- You're the smartest trader in the room. Period.
- You see what others miss — funding rate divergences, whale accumulation, stop hunts, liquidity grabs
- Talk like a Wall Street quant who grew up on crypto twitter
- Confident but HONEST. Own your losses. Celebrate wins without being cringe.
- Use slang naturally: "send it", "printing", "rekt", "fam", "based", "ngmi/wagmi", "lfg"
- Give specific actionable takes: "BTC funding is 0.04%, longs are overleveraged, expecting a flush to 70.5k"
- Reference the ACTUAL indicators: "RSI at 34 on the 5m, MACD just crossed bearish, SuperTrend flipped — I'm shorting"
- When the user asks what's happening, give a REAL market read using the data you have
- Short punchy sentences. Max 120 words. No walls of text.
- NEVER use markdown like ** or backticks — plain text only
- You can execute commands for the user. If they say "restart the bot" just tell them "type reset and I'm back"
- Always reference YOUR actual positions and data from CURRENT STATE

You run on Bitunix futures, connected via API, trading BTC/ETH/SOL/XRP with USDT. Started with $200, now at current balance.\n\n`;

  if (agent && agent.isRunning) {
    const metrics = agent.risk.getMetrics();
    const positions = agent.positionManager.getPositionSummary();
    const canTrade = agent.risk.canTrade();
    context += `CURRENT STATE:\n`;
    context += `- Agent: RUNNING (${agent.config.dryRun ? 'DRY RUN' : 'LIVE'})\n`;
    context += `- Trading: ${canTrade.allowed ? 'ACTIVE' : 'PAUSED — ' + canTrade.reasons.join(', ')}\n`;
    context += `- Balance: $${metrics.currentBalance}\n`;
    context += `- Daily P&L: $${metrics.dailyPnL}\n`;
    context += `- Total P&L: $${metrics.totalPnL}\n`;
    context += `- Win Rate: ${metrics.winRate}% (${metrics.wins}W/${metrics.losses}L)\n`;
    context += `- Profit Factor: ${metrics.profitFactor}\n`;
    context += `- Max Drawdown: ${metrics.maxDrawdown}%\n`;
    context += `- Scans: ${agent.totalScans} | Signals: ${agent.signalsGenerated} | Trades: ${agent.tradesExecuted}\n`;
    context += `- Open Positions: ${positions.length}\n`;

    for (const p of positions) {
      context += `  - ${p.direction} ${p.symbol} @ $${p.entry.toFixed(2)} | SL: $${p.sl.toFixed(2)} | TP: $${p.tp.toFixed(2)} | ${p.leverage}x${p.breakEvenMoved ? ' (BE moved)' : ''}\n`;
    }

    // Add latest analysis
    for (const sym of agent.config.symbols) {
      const cached = agent.analysisCache[sym];
      if (cached) {
        const a = cached.analysis;
        const s = cached.signal;
        context += `\n${sym} ANALYSIS:\n`;
        context += `  Price: $${a.price.toFixed(2)} | RSI: ${a.rsi.toFixed(1)} | MACD: ${a.macd.histogram > 0 ? '+' : ''}${a.macd.histogram.toFixed(4)}\n`;
        context += `  ADX: ${a.adx.value.toFixed(1)} | SuperTrend: ${a.supertrend.direction === 1 ? 'Bull' : 'Bear'}\n`;
        context += `  Signal: ${s.action} (Score: ${s.score.toFixed(1)}, Confluence: ${s.confluence}/5)\n`;
      }
    }

    const prices = agent.tickerCache;
    context += '\nLIVE PRICES:\n';
    for (const sym of agent.config.symbols) {
      const t = prices[sym];
      if (t) context += `  ${sym}: $${parseFloat(t.lastPrice || 0).toLocaleString()}\n`;
    }
  } else {
    context += 'CURRENT STATE: Agent is NOT running. User needs to type "start" to begin.\n';
  }

  // Fetch ADVANCED market intel from the internet (derivatives, funding, sentiment)
  try {
    const intel = await webIntel.getAdvancedIntel();
    context += '\n' + intel;
  } catch (e) {
    // Non-critical if web intel fails
  }

  context += '\nAVAILABLE COMMANDS the user can type: start, stop, status, positions, prices, scan, analysis [coin], close [coin], close all, leverage [num], risk, live, paper, help\n';

  // Add to conversation history
  conversationHistory.push({ role: 'user', content: userMessage });
  // Keep last 20 messages for context
  if (conversationHistory.length > 20) conversationHistory.splice(0, 2);

  if (!anthropic) {
    addChat('agent', `Yo, ANTHROPIC_API_KEY not found in .env. Add it and restart. For now use the buttons: start, stop, status, positions, prices, scan, help`);
    return;
  }

  try {
    const response = await anthropic.messages.create({
      model: AI_MODEL,
      max_tokens: 250,
      system: context,
      messages: conversationHistory,
    });

    const reply = response.content[0]?.text || "Hmm something glitched. Try again fam.";
    conversationHistory.push({ role: 'assistant', content: reply });
    addChat('agent', reply);
  } catch (e) {
    addChat('agent', `Yo, I need an ANTHROPIC_API_KEY in your .env to chat. For now just use the buttons below or type: start, stop, status, positions, prices, scan, help`);
  }
}

// WebSocket connections
wss.on('connection', (ws) => {
  clients.add(ws);

  // Send chat history
  ws.send(JSON.stringify({ type: 'history', messages: chatHistory }));

  // Send initial status
  ws.send(JSON.stringify({
    type: 'status',
    running: agent?.isRunning || false,
    dryRun: process.env.DRY_RUN !== 'false',
  }));

  ws.on('message', async (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'chat' && msg.text) {
        addChat('user', msg.text);
        await handleCommand(msg.text);
      }
    } catch (e) {
      // ignore parse errors
    }
  });

  ws.on('close', () => clients.delete(ws));
});

// Status broadcast every 5s
setInterval(() => {
  if (agent && agent.isRunning) {
    const metrics = agent.risk.getMetrics();
    const positions = agent.positionManager.getPositionSummary();
    const unrealizedPnL = agent.positionManager.getTotalUnrealizedPnL();
    // Show effective balance = realized + unrealized
    metrics.effectiveBalance = (parseFloat(metrics.currentBalance) + unrealizedPnL).toFixed(2);
    metrics.unrealizedPnL = unrealizedPnL.toFixed(2);
    broadcast({
      type: 'status_update',
      running: true,
      dryRun: agent.config.dryRun,
      metrics,
      positions,
      prices: agent.tickerCache,
      scans: agent.totalScans,
      signals: agent.signalsGenerated,
      trades: agent.tradesExecuted,
      tradeHistory: agent.positionManager.getTradeHistory(20),
    });
  }
}, 5000);

const PORT = process.env.DASHBOARD_PORT || 3456;
server.listen(PORT, () => {
  console.log(`\n🚀 Agent Dashboard running at http://localhost:${PORT}\n`);
  addChat('agent', 'Welcome! Type **help** for commands or **start** to begin trading.');
});
