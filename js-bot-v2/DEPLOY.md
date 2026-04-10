# Enhanced Crypto Bot v2 - Fly.io Deployment

This is an enhanced version of the proven 94.8% WR crypto bot with additional features:

## What's New in v2
- **Market Structure Detection**: Swing points, support/resistance, order blocks, fair value gaps
- **6th Strategy (Smart Money)**: Scores entries near order blocks, FVGs, S/R levels
- **Correlation Filter**: Prevents stacking BTC+ETH or SOL+XRP same-direction positions
- **Structure-Based TP/SL**: TP snaps just before resistance, SL just past support
- **Partial Profit Taking**: Closes 50% at 1.0 ATR profit, tighter trail on rest
- **RSI Divergence Detection**: Bonus confluence for bullish/bearish divergences
- **Enhanced Session Filter**: Blocks Asian-only momentum, eases London-NY overlap

## Config
- **Bankroll**: $200 starting capital
- **Mode**: DRY_RUN (paper trading) by default
- **Leverage**: 10x default, 20x max (VIP1)
- **Fees**: Bitunix VIP1 (0.018% maker / 0.055% taker)
- **Fresh State**: PREV_WINS=0, PREV_LOSSES=0 for clean comparison

## Deploy to Fly.io

### Prerequisites
1. Install flyctl: `curl -L https://fly.io/install.sh | sh`
2. Sign in: `fly auth login`

### First-time deploy
```bash
cd js-bot-v2/
fly launch --copy-config --name bitunix-crypto-agent-v2
```
When prompted:
- Would you like to copy its configuration? **Yes**
- Choose a region: **iad** (or closest to you)
- Would you like to set up a Postgresql database? **No**
- Would you like to deploy now? **Yes**

### Set secrets (REQUIRED)
```bash
fly secrets set BITUNIX_API_KEY=your_api_key_here
fly secrets set BITUNIX_SECRET_KEY=your_secret_key_here
fly secrets set ANTHROPIC_API_KEY=your_claude_key_here  # optional for AI chat
```

### Deploy updates
```bash
fly deploy
```

### View logs
```bash
fly logs
```

### Open dashboard
```bash
fly open
```

### Scale (optional)
```bash
fly scale vm shared-cpu-1x --memory 512
```

## Comparison with v1 bot
Run this v2 alongside your existing Railway bot:
- **v1 (Railway)**: Current bot with 94.8% WR
- **v2 (Fly.io)**: Enhanced bot with Smart Money Concepts

Both will trade the same pairs with the same $200 bankroll, so you can directly compare their performance.

## Environment Variables
All configurable via `fly secrets set` or `fly.toml`:

| Variable | Default | Description |
|----------|---------|-------------|
| DRY_RUN | true | Paper trading mode |
| BANKROLL | 200 | Starting capital USDT |
| SYMBOLS | BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT | Trading pairs |
| MAX_LEVERAGE | 20 | VIP1 max |
| DEFAULT_LEVERAGE | 10 | Default per trade |
| MAX_RISK_PER_TRADE | 0.02 | 2% per trade |
| MAX_DAILY_LOSS | 0.10 | 10% daily stop |
| MIN_CONFLUENCE | 3 | Min strategies agreeing (of 6) |
| MIN_SCORE | 35 | Min composite score to trade |
| SCAN_INTERVAL | 30000 | 30 seconds between scans |
