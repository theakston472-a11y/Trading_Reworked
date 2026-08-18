import pandas as pd
from pathlib import Path

INPUT = Path(r"D:\Trading\quant\top100_validation.csv")
OUTPUT = Path(r"D:\Trading\quant\high_frequency_candidates.csv")

# Load data
df = pd.read_csv(INPUT)

print(f"Loaded {len(df)} rows")
print(f"Columns: {', '.join(df.columns)}")

# Convert numeric columns
numeric_cols = [
    "trades",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
]

for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# ---------------------------------------------------------
# HIGH-FREQUENCY TARGET
#
# We want strategies producing roughly:
#   1 trade every 1-2 trading days
#
# Approximate target:
#   2020-2024: 103-520 trades
#   2025:       50-260 trades
#   2026:       50-130 trades
#
# Since the CSV contains individual period results,
# calculate a simple trade-frequency score.
# ---------------------------------------------------------

def frequency_score(trades):
    """
    Score trade frequency.
    Higher = closer to our desired high-frequency range.

    We prefer at least ~2 trades/month and ideally
    substantially more than the current low-frequency
    strategies.
    """

    if pd.isna(trades):
        return 0

    # Strong preference for 20+ trades per period
    if trades >= 40:
        return 100

    if trades >= 30:
        return 90

    if trades >= 20:
        return 80

    if trades >= 15:
        return 65

    if trades >= 10:
        return 45

    if trades >= 5:
        return 25

    return 0


df["frequency_score"] = df["trades"].apply(frequency_score)

# ---------------------------------------------------------
# Quality filters
# ---------------------------------------------------------

# Keep strategies with positive expectancy
candidates = df[
    (df["expectancy_r"] > 0)
    & (df["profit_factor"] > 1.0)
    & (df["valid"] == True)
].copy()

# Add combined score
#
# Frequency matters heavily because your objective is
# more trades, but we still want a positive edge.
candidates["candidate_score"] = (
    candidates["frequency_score"] * 0.45
    + candidates["profit_factor"].clip(upper=5) * 10
    + candidates["expectancy_r"].clip(lower=0, upper=1) * 20
    + candidates["net_r"].clip(lower=0, upper=30) * 0.5
    - candidates["max_drawdown_r"].clip(lower=0) * 0.15
)

# Sort best candidates first
candidates = candidates.sort_values(
    ["candidate_score", "trades"],
    ascending=[False, False]
)

# Save
candidates.to_csv(OUTPUT, index=False)

print()
print("=" * 70)
print("HIGH-FREQUENCY CANDIDATES")
print("=" * 70)

print(
    candidates[
        [
            "original_rank",
            "direction",
            "session",
            "conditions",
            "period",
            "trades",
            "profit_factor",
            "expectancy_r",
            "net_r",
            "max_drawdown_r",
            "valid",
            "candidate_score",
        ]
    ].head(50).to_string(index=False)
)

print()
print("=" * 70)
print(f"Saved {len(candidates)} candidates")
print(f"Output: {OUTPUT}")
print("=" * 70)