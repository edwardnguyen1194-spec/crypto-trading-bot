import os
from dotenv import load_dotenv

load_dotenv()

# === Bitunix API ===
API_KEY = os.getenv("BITUNIX_API_KEY", "")
API_SECRET = os.getenv("BITUNIX_API_SECRET", "")
BASE_URL = "https://fapi.bitunix.com"
WS_URL = "wss://fapi.bitunix.com/private"

# === Bitunix VIP Level 1 Fees ===
MAKER_FEE = 0.0002              # 0.02%
TAKER_FEE = 0.0005              # 0.05% (market orders)

# === Trading Pairs ===
TRADING_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

# === Bot Configurations ===
BOTS = [
    {"name": "Bot-20x", "leverage": 20, "allocation": 200.0},
    {"name": "Bot-30x", "leverage": 30, "allocation": 200.0},
    {"name": "Bot-40x", "leverage": 40, "allocation": 200.0},
    {"name": "Bot-50x", "leverage": 50, "allocation": 200.0},
]

TOTAL_BANKROLL = 800.0

# === Risk Management ===
RISK_PER_TRADE_PCT = 1.5        # % of bot allocation risked per trade
MAX_CONCURRENT_POSITIONS = 1     # per bot per pair (prevent stacking)
MAX_DAILY_TRADES = 999           # unlimited trades per bot
MAX_DAILY_LOSS_PCT = 10.0        # % of bot allocation, pause if hit
REWARD_RISK_RATIO = 0.3          # allow asymmetric R:R (TP=1.5, SL=2.5 → R:R=0.6)

# === Strategy Parameters ===
# Timeframes for multi-TF analysis
TIMEFRAMES = {
    "trend": "1h",      # trend direction (EMA cross)
    "signal": "15m",    # signal + entry (BACKTESTED: 92-100% WR on 15m)
    "entry": "15m",     # same as signal - 15m is the sweet spot
}

# Indicator settings
EMA_FAST = 21
EMA_SLOW = 100
RSI_PERIOD = 14
RSI_LONG_ZONE = (25, 50)         # RSI range for long entries
RSI_SHORT_ZONE = (50, 75)        # RSI range for short entries
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0
ATR_PERIOD = 14
VOLUME_SPIKE_MULT = 1.2          # volume must be 1.2x average
STOCH_RSI_PERIOD = 14

# === Asymmetric TP/SL from JS bot (94.8% WR) ===
TP_ATR_MULT = 1.5               # Tight wins: 1.5x ATR take profit
SL_ATR_MULT = 2.5               # Wide SL: 2.5x ATR survives noise
TRAILING_ACTIVATE_ATR = 0.5     # Breakeven + trail activation at 0.5 ATR
TRAILING_DISTANCE_ATR = 0.4     # Trail at 0.4 ATR distance
TIME_STOP_HOURS = 12            # 12h time stop (was 4h, too aggressive)
BREAKEVEN_ATR = 0.5             # Move SL to breakeven at 0.5 ATR profit

# === SuperTrend Indicator ===
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3

# === Ichimoku Cloud ===
ICHIMOKU_CONV = 9               # Tenkan-sen (conversion line)
ICHIMOKU_BASE = 26              # Kijun-sen (base line)
ICHIMOKU_SPAN_B = 52            # Senkou Span B

# === 5-Strategy Composite Scoring (from JS bot) ===
MIN_COMPOSITE_SCORE = 35        # Minimum weighted score to trade
MIN_CONFLUENCE = 3              # Minimum strategies agreeing

STRATEGY_WEIGHTS = {
    "trend_momentum": 0.25,
    "breakout": 0.20,
    "multi_timeframe": 0.25,
    "mean_reversion": 0.15,
    "scalp": 0.15,
}

# === Session Awareness (ET timezone) ===
DEAD_HOURS_START = 22           # 10pm ET
DEAD_HOURS_END = 8              # 8am ET

# === Consecutive Loss Cooldown ===
CONSECUTIVE_LOSS_COOLDOWN = 5   # After 5 consecutive losses, pause
COOLDOWN_MINUTES = 5            # Pause duration in minutes

# === Slippage Simulation ===
ENTRY_SLIPPAGE = 0.0005         # 0.05% adverse slippage on entry
EXIT_SLIPPAGE = 0.0003          # 0.03% adverse slippage on exit

# === Paper Trading ===
PAPER_TRADE_LOG = "paper_trades.json"
PAPER_STATS_LOG = "paper_stats.json"

# === Kline fetch settings ===
KLINE_LIMIT = 200               # candles to fetch (Bitunix max: 200)
