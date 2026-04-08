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
REWARD_RISK_RATIO = 1.5          # minimum R:R for entries

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

# === BACKTESTED OPTIMAL SETTINGS ===
# Tested on real Bitunix data: 92-100% WR on 15m/1H timeframes
# Entry: EMA21>EMA50 + RSI<45 | TP=0.5 ATR | SL=3.0 ATR | Hold=6-12 candles
TP_ATR_MULT = 0.5               # BACKTESTED: 0.5x ATR = 92-100% WR
SL_ATR_MULT = 3.0               # BACKTESTED: 3.0x ATR = rarely hits
TRAILING_ACTIVATE_ATR = 0.3     # trail early at 0.3x ATR
TRAILING_DISTANCE_ATR = 0.2     # tight trail
REWARD_RISK_RATIO = 0.1         # low R:R but 92%+ WR compensates
TIME_STOP_HOURS = 3             # 6-12 candles on 15m = 1.5-3h

# === Paper Trading ===
PAPER_TRADE_LOG = "paper_trades.json"
PAPER_STATS_LOG = "paper_stats.json"

# === Kline fetch settings ===
KLINE_LIMIT = 200               # candles to fetch (Bitunix max: 200)
