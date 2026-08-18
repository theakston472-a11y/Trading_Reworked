# save_strategy.py
from pathlib import Path
import json
from datetime import datetime, timezone

STRATEGY = {
    "name": "SELL_NY_LIQUIDITY_SWEEP_BEARISH_CONFIRMATION",
    "direction": "SELL",
    "session": "New York",
    "conditions": [
        "liquidity_sweep_high",
        "bearish_candle",
        "bearish_engulfing",
    ],
    "risk_per_trade": 0.01,
    "one_position_at_a_time": True,
    "historical_best_rr_recent_period": 1.8,
    "notes": (
        "Strategy discovered and tested using the quant research pipeline. "
        "Recent-period test covered 2025-01-01 through 2026-08-31, "
        "with actual available data through 2026-08-07."
    ),
    "saved_at_utc": datetime.now(timezone.utc).isoformat(),
}

OUTPUT = Path("quant/saved_strategies.json")

if OUTPUT.exists():
    try:
        strategies = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        strategies = []
else:
    strategies = []

if not isinstance(strategies, list):
    strategies = []

# Replace an existing copy of the same strategy.
strategies = [
    s for s in strategies
    if s.get("name") != STRATEGY["name"]
]

strategies.append(STRATEGY)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(strategies, indent=2),
    encoding="utf-8"
)

print("=" * 80)
print("STRATEGY SAVED")
print("=" * 80)
print()
print(f"Name:        {STRATEGY['name']}")
print(f"Direction:   {STRATEGY['direction']}")
print(f"Session:     {STRATEGY['session']}")
print(f"Conditions:  {' + '.join(STRATEGY['conditions'])}")
print(f"Risk:        {STRATEGY['risk_per_trade']:.2%}")
print(f"Best RR:     {STRATEGY['historical_best_rr_recent_period']}R")
print()
print(f"Saved to:    {OUTPUT}")
