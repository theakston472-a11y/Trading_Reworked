import pandas as pd
from pathlib import Path

INPUT = Path(r"D:\Trading\quant\high_frequency_candidates.csv")
OUTPUT = Path(r"D:\Trading\quant\frequency_test_results.csv")

df = pd.read_csv(INPUT)

print(f"Loaded {len(df)} candidates")
print("Columns:", ", ".join(df.columns))

# Score candidates for trade frequency while still rewarding quality.
# Higher trades/day and trades/week are better, but poor PF/expectancy
# are penalized.

if "trades" not in df.columns:
    raise KeyError("Missing required column: trades")

if "period" not in df.columns:
    raise KeyError("Missing required column: period")

if "profit_factor" not in df.columns:
    raise KeyError("Missing required column: profit_factor")

if "expectancy_r" not in df.columns:
    raise KeyError("Missing required column: expectancy_r")

if "net_r" not in df.columns:
    raise KeyError("Missing required column: net_r")

# Estimate trading frequency.
# The current test data is annual, so trades/year is the main frequency measure.
df["trades_per_year"] = df["trades"] / 1.0
df["trades_per_month"] = df["trades_per_year"] / 12.0
df["trades_per_week"] = df["trades_per_year"] / 52.0
df["trades_per_day"] = df["trades_per_year"] / 252.0

# Frequency score:
# We want strategies producing roughly every day/every other day,
# without accepting low-quality strategies just because they trade often.
frequency_score = (
    df["trades_per_year"] * 1.5
    + df["profit_factor"] * 15
    + df["expectancy_r"] * 25
    + df["net_r"] * 1.0
)

# Penalise very low-quality candidates.
frequency_score = frequency_score.where(
    (df["profit_factor"] >= 1.20) &
    (df["expectancy_r"] > 0),
    frequency_score * 0.25
)

df["frequency_score"] = frequency_score

# Rank highest frequency-quality combinations first.
df = df.sort_values(
    ["frequency_score", "trades_per_year"],
    ascending=[False, False]
)

# Keep the most useful columns first.
preferred_columns = [
    "original_rank",
    "direction",
    "session",
    "conditions",
    "period",
    "trades",
    "trades_per_year",
    "trades_per_month",
    "trades_per_week",
    "trades_per_day",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "valid",
    "frequency_score",
]

columns = [c for c in preferred_columns if c in df.columns]
remaining = [c for c in df.columns if c not in columns]

df = df[columns + remaining]

print()
print("=" * 110)
print("NEXT FREQUENCY TEST")
print("=" * 110)

print(
    df.head(50).to_string(
        index=False,
        max_colwidth=80
    )
)

df.to_csv(OUTPUT, index=False)

print()
print("=" * 110)
print(f"Saved {len(df)} results")
print(f"Output: {OUTPUT}")
print("=" * 110)