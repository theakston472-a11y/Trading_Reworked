import pandas as pd
from pathlib import Path

BASE_DIR = Path(r"D:\Trading\quant")

INPUT_FILE = BASE_DIR / "frequency_test_results.csv"
OUTPUT_FILE = BASE_DIR / "next_frequency_test_results.csv"
DECENT_FILE = BASE_DIR / "decent_strategies.csv"

print("=" * 110)
print("NEXT FREQUENCY TEST")
print("=" * 110)

df = pd.read_csv(INPUT_FILE)

print(f"Loaded {len(df)} candidates")
print(f"Columns: {', '.join(df.columns)}")

# Convert numeric columns
numeric_columns = [
    "trades",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "frequency_score",
    "candidate_score",
    "original_score",
    "condition_count",
    "candles",
    "wins",
    "losses",
    "win_rate",
]

for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Calculate frequency metrics
if "trades_per_year" not in df.columns:
    df["trades_per_year"] = df["trades"]

if "trades_per_month" not in df.columns:
    df["trades_per_month"] = df["trades_per_year"] / 12

if "trades_per_week" not in df.columns:
    df["trades_per_week"] = df["trades_per_year"] / 52

if "trades_per_day" not in df.columns:
    df["trades_per_day"] = df["trades_per_year"] / 252

# Quality score
df["quality_score"] = (
    df["profit_factor"].fillna(0) * 30
    + df["expectancy_r"].fillna(0) * 40
    + df["trades_per_day"].fillna(0) * 20
    + df["win_rate"].fillna(0) * 0.10
    - df["max_drawdown_r"].fillna(999) * 2
)

# Decent strategy filters
decent = df[
    (df["valid"].astype(str).str.lower() == "true")
    & (df["trades"] >= 20)
    & (df["trades_per_day"] >= 0.50)
    & (df["profit_factor"] >= 1.20)
    & (df["expectancy_r"] >= 0.10)
].copy()

# Sort best first
decent = decent.sort_values(
    [
        "quality_score",
        "trades_per_day",
        "profit_factor",
        "expectancy_r"
    ],
    ascending=False
)

df = df.sort_values(
    ["quality_score", "trades_per_day"],
    ascending=False
)

# Save all results
df.to_csv(OUTPUT_FILE, index=False)

# Save decent strategies
decent.to_csv(DECENT_FILE, index=False)

print()
print("=" * 110)
print("DECENT STRATEGIES")
print("=" * 110)

if len(decent) == 0:
    print("No strategies passed the filters.")
else:
    display_columns = [
        "original_rank",
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
        "quality_score"
    ]

    display_columns = [
        c for c in display_columns
        if c in decent.columns
    ]

    print(
        decent[display_columns]
        .head(50)
        .to_string(index=False)
    )

print()
print("=" * 110)
print(f"Saved {len(df)} total results")
print(f"Output: {OUTPUT_FILE}")
print()
print(f"Saved {len(decent)} decent strategies")
print(f"Output: {DECENT_FILE}")
print("=" * 110)
