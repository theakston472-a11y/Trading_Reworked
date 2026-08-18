import pandas as pd
from pathlib import Path

BASE = Path(r"D:\Trading\quant")

INPUT = BASE / "next_frequency_test_results.csv"
OUTPUT = BASE / "validated_frequency_candidates.csv"
SHORTLIST = BASE / "shortlisted_strategies.csv"

df = pd.read_csv(INPUT)

print("=" * 100)
print("FREQUENCY STRATEGY VALIDATION")
print("=" * 100)

# Numeric conversion
numeric = [
    "trades",
    "trades_per_day",
    "trades_per_week",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "win_rate",
    "candidate_score",
]

for col in numeric:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ------------------------------------------------------------
# Remove duplicate strategy definitions
# ------------------------------------------------------------

key_columns = [
    "direction",
    "session",
    "conditions",
    "period",
]

before = len(df)

df = df.drop_duplicates(
    subset=key_columns
).copy()

print(f"Removed {before - len(df)} duplicate entries")
print(f"Unique strategies remaining: {len(df)}")

# ------------------------------------------------------------
# Keep strategies trading every day / every other day
# ------------------------------------------------------------

shortlist = df[
    (df["trades"] >= 30)
    &
    (df["trades_per_day"] >= 0.50)
    &
    (df["profit_factor"] >= 1.20)
    &
    (df["expectancy_r"] >= 0.10)
    &
    (df["max_drawdown_r"] <= 20)
].copy()

# ------------------------------------------------------------
# Rank them
# ------------------------------------------------------------

shortlist["validation_score"] = (
    shortlist["profit_factor"] * 35
    + shortlist["expectancy_r"] * 50
    + shortlist["trades_per_day"] * 20
    - shortlist["max_drawdown_r"] * 2
)

shortlist = shortlist.sort_values(
    "validation_score",
    ascending=False
)

# Save files
df.to_csv(OUTPUT, index=False)
shortlist.to_csv(SHORTLIST, index=False)

print()
print("=" * 100)
print("SHORTLIST")
print("=" * 100)

if len(shortlist) == 0:
    print("No strategies passed the validation filters.")
else:
    cols = [
        "direction",
        "session",
        "conditions",
        "period",
        "trades",
        "trades_per_day",
        "trades_per_week",
        "profit_factor",
        "expectancy_r",
        "net_r",
        "max_drawdown_r",
        "win_rate",
        "validation_score",
    ]

    cols = [c for c in cols if c in shortlist.columns]

    print(
        shortlist[cols]
        .head(25)
        .to_string(index=False)
    )

print()
print("=" * 100)
print(f"Saved unique candidates: {OUTPUT}")
print(f"Saved shortlist: {SHORTLIST}")
print(f"Shortlisted strategies: {len(shortlist)}")
print("=" * 100)
