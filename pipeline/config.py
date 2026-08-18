from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUANT = ROOT / "quant"
RESULTS = ROOT / "results"

FEATURE_FILE = QUANT / "feature_database.csv"
DISCOVERY_FILE = RESULTS / "discovery_all.csv"

TOP100_DIR = RESULTS / "top100"
DEEP_DIR = RESULTS / "top100_tests"
WINNERS_DIR = RESULTS / "winners"

POOLS = {
    "london_buy": ("London", "BUY"),
    "london_sell": ("London", "SELL"),
    "new_york_buy": ("New York", "BUY"),
    "new_york_sell": ("New York", "SELL"),
}

RR_START = 1.0
RR_STOP = 7.0
RR_STEP = 0.1
MAX_OPEN_TRADES = 5
MIN_TRADES = 20
FREQUENCY_TARGET = 0.75
FINAL_N = 20

# The pipeline deliberately keeps the existing system intact.
# It calls the existing strategy_lab.py when available.
STRATEGY_LAB = ROOT / "scripts" / "strategy_lab.py"
PROMOTE_TOP100 = ROOT / "scripts" / "promote_top100.py"

# Visual validation.
VISUAL_EXAMPLES = 6
CHART_BARS_BEFORE = 80
CHART_BARS_AFTER = 100
