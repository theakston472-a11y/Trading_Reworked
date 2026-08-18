import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================
# HIGH-FREQUENCY TEST
#
# Reads strategy_scores.csv and ranks the strategies that
# have already been tested.
#
# This script DOES NOT generate new strategies.
# ============================================================

BASE = Path("quant")

INPUT_FILE = BASE / "strategy_scores.csv"
OUTPUT_FILE = BASE / "high_frequency_results.csv"

# ============================================================
# SETTINGS
# ============================================================

TOP_N = 100

# Minimum total trades across the whole dataset
MIN_TOTAL_TRADES = 500

# Ranking weights
TRADE_WEIGHT = 0.40
PF_WEIGHT = 0.25
EXPECTANCY_WEIGHT = 0.20
CONSISTENCY_WEIGHT = 0.15

# ============================================================
# LOAD DATA
# ============================================================

print()
print("=" * 70)
print("HIGH-FREQUENCY STRATEGY TEST")
print("=" * 70)
print()

print("Loading strategy results...")

if not INPUT_FILE.exists():
    print()
    print("ERROR:")
    print(f"Could not find {INPUT_FILE}")
    print()
    print("Make sure strategy_scores.csv exists in:")
    print(r"D:\Trading\quant")
    raise SystemExit

df = pd.read_csv(INPUT_FILE)

print(f"Strategies loaded: {len(df)}")
print()

# ============================================================
# CLEAN DATA
# ============================================================

required_columns = [
    "direction",
    "session",
    "conditions",
    "trades",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
]

missing = [c for c in required_columns if c not in df.columns]

if missing:
    print("ERROR: Missing columns:")
    print(missing)
    print()
    print("Columns found:")
    print(list(df.columns))
    raise SystemExit

for col in [
    "trades",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# ============================================================
# FILTER FOR HIGH-FREQUENCY STRATEGIES
# ============================================================

print("Filtering for high-frequency strategies...")
print()

hf = df[df["trades"] >= MIN_TOTAL_TRADES].copy()

print(
    f"Strategies with at least "
    f"{MIN_TOTAL_TRADES} trades: {len(hf)}"
)

if len(hf) == 0:
    print()
    print("No strategies passed the minimum trade filter.")
    print("Lower MIN_TOTAL_TRADES if necessary.")
    raise SystemExit

# ============================================================
# NORMALISE TRADE COUNT
# ============================================================

# More trades = higher score.
#
# Log scaling prevents extremely high trade counts from
# completely dominating the ranking.

hf["trade_score"] = np.log1p(hf["trades"])

max_trade_score = hf["trade_score"].max()

if max_trade_score > 0:
    hf["trade_score"] = (
        hf["trade_score"] / max_trade_score
    )

# ============================================================
# PROFIT FACTOR SCORE
# ============================================================

# PF around 1.0 = breakeven
# PF > 1.0 = profitable
#
# Cap PF so tiny-sample outliers cannot dominate.

hf["pf_capped"] = hf["profit_factor"].clip(upper=2.0)

hf["pf_score"] = (
    (hf["pf_capped"] - 0.8) / 1.2
).clip(0, 1)

# ============================================================
# EXPECTANCY SCORE
# ============================================================

# 0.10R per trade is treated as a very strong expectancy.

hf["expectancy_score"] = (
    hf["expectancy_r"] / 0.10
).clip(0, 1)

# ============================================================
# CONSISTENCY SCORE
# ============================================================

# Penalise large drawdowns relative to total profit.

hf["drawdown_abs"] = hf["max_drawdown_r"].abs()

hf["consistency_score"] = np.where(
    hf["net_r"] > 0,
    hf["net_r"]
    / (
        hf["net_r"]
        + hf["drawdown_abs"]
        + 1
    ),
    0,
)

hf["consistency_score"] = (
    hf["consistency_score"].clip(0, 1)
)

# ============================================================
# FINAL HIGH-FREQUENCY SCORE
# ============================================================

hf["high_frequency_score"] = (
    hf["trade_score"] * TRADE_WEIGHT
    + hf["pf_score"] * PF_WEIGHT
    + hf["expectancy_score"] * EXPECTANCY_WEIGHT
    + hf["consistency_score"] * CONSISTENCY_WEIGHT
)

hf = hf.sort_values(
    "high_frequency_score",
    ascending=False
)

# ============================================================
# TOP 100
# ============================================================

top100 = hf.head(TOP_N).copy()

top100.insert(
    0,
    "high_frequency_rank",
    range(1, len(top100) + 1)
)

# ============================================================
# SAVE RESULTS
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

top100.to_csv(
    OUTPUT_FILE,
    index=False
)

# ============================================================
# DISPLAY RESULTS
# ============================================================

print()
print("=" * 70)
print("TOP HIGH-FREQUENCY STRATEGIES")
print("=" * 70)
print()

display_columns = [
    "high_frequency_rank",
    "direction",
    "session",
    "conditions",
    "trades",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "high_frequency_score",
]

print(
    top100[display_columns]
    .to_string(index=False)
)

# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()

print(f"Strategies tested: {len(df)}")
print(f"High-frequency candidates: {len(hf)}")
print(f"Top strategies saved: {len(top100)}")
print()

if len(top100) > 0:

    print("Top 10 by high-frequency score:")
    print()

    for _, row in top100.head(10).iterrows():

        print(
            f"#{int(row['high_frequency_rank']):3d} | "
            f"{str(row['direction']):4s} | "
            f"{str(row['session']):9s} | "
            f"Trades: {int(row['trades']):5d} | "
            f"PF: {row['profit_factor']:.3f} | "
            f"Exp: {row['expectancy_r']:.4f} | "
            f"Net R: {row['net_r']:.2f}"
        )

print()
print("=" * 70)
print(f"Saved to: {OUTPUT_FILE}")
print("=" * 70)
print()