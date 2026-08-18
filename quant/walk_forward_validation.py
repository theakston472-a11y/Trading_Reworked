import pandas as pd
from pathlib import Path

BASE = Path(r"D:\Trading\quant")

INPUT = BASE / "shortlisted_strategies.csv"
SOURCE = BASE / "frequency_test_results.csv"

OUTPUT = BASE / "walk_forward_validation_results.csv"
SURVIVORS = BASE / "walk_forward_survivors.csv"

print("=" * 110)
print("WALK-FORWARD VALIDATION")
print("=" * 110)

# ------------------------------------------------------------
# Load shortlist
# ------------------------------------------------------------

shortlist = pd.read_csv(INPUT)

print(f"Loaded {len(shortlist)} shortlisted strategies")

if len(shortlist) == 0:
    print("No shortlisted strategies found.")
    raise SystemExit

# ------------------------------------------------------------
# Load original candidate results
# ------------------------------------------------------------

source = pd.read_csv(SOURCE)

print(f"Loaded {len(source)} original candidate results")

# ------------------------------------------------------------
# Numeric conversion
# ------------------------------------------------------------

numeric_columns = [
    "trades",
    "trades_per_year",
    "trades_per_month",
    "trades_per_week",
    "trades_per_day",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "win_rate",
]

for df in [shortlist, source]:
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

# ------------------------------------------------------------
# Match shortlisted strategies against source data
# ------------------------------------------------------------

keys = [
    "direction",
    "session",
    "conditions",
]

for col in keys:
    if col not in shortlist.columns or col not in source.columns:
        print(f"Missing required column: {col}")
        raise SystemExit

results = []

for _, strategy in shortlist.iterrows():

    direction = strategy["direction"]
    session = strategy["session"]
    conditions = strategy["conditions"]

    matches = source[
        (source["direction"] == direction)
        &
        (source["session"] == session)
        &
        (source["conditions"] == conditions)
    ].copy()

    if len(matches) == 0:
        continue

    print()
    print("-" * 110)
    print("STRATEGY")
    print(f"Direction : {direction}")
    print(f"Session   : {session}")
    print(f"Conditions: {conditions}")
    print("-" * 110)

    # --------------------------------------------------------
    # Evaluate every available period separately
    # --------------------------------------------------------

    for period, group in matches.groupby("period"):

        trades = group["trades"].max()
        pf = group["profit_factor"].max()
        expectancy = group["expectancy_r"].max()
        net_r = group["net_r"].max()
        drawdown = group["max_drawdown_r"].max()
        win_rate = group["win_rate"].max()

        trades_per_day = (
            group["trades_per_day"].max()
            if "trades_per_day" in group.columns
            else None
        )

        results.append({
            "direction": direction,
            "session": session,
            "conditions": conditions,
            "period": period,
            "trades": trades,
            "trades_per_day": trades_per_day,
            "profit_factor": pf,
            "expectancy_r": expectancy,
            "net_r": net_r,
            "max_drawdown_r": drawdown,
            "win_rate": win_rate,
        })

        print(
            f"{period}: "
            f"trades={trades}, "
            f"PF={pf}, "
            f"expectancy={expectancy}, "
            f"netR={net_r}, "
            f"DD={drawdown}"
        )

# ------------------------------------------------------------
# Create validation dataframe
# ------------------------------------------------------------

if len(results) == 0:
    print()
    print("No matching strategy-period results found.")
    raise SystemExit

validation = pd.DataFrame(results)

# ------------------------------------------------------------
# Determine robustness
# ------------------------------------------------------------

summary = []

for (direction, session, conditions), group in validation.groupby(
    ["direction", "session", "conditions"]
):

    periods_tested = len(group)

    profitable_periods = int(
        (group["net_r"] > 0).sum()
    )

    positive_expectancy_periods = int(
        (group["expectancy_r"] > 0).sum()
    )

    acceptable_pf_periods = int(
        (group["profit_factor"] >= 1.10).sum()
    )

    total_trades = group["trades"].sum()

    avg_pf = group["profit_factor"].mean()
    avg_expectancy = group["expectancy_r"].mean()
    total_net_r = group["net_r"].sum()
    worst_drawdown = group["max_drawdown_r"].max()

    robust = (
        periods_tested >= 2
        and profitable_periods >= 2
        and positive_expectancy_periods >= 2
        and acceptable_pf_periods >= 2
    )

    summary.append({
        "direction": direction,
        "session": session,
        "conditions": conditions,
        "periods_tested": periods_tested,
        "profitable_periods": profitable_periods,
        "positive_expectancy_periods": positive_expectancy_periods,
        "acceptable_pf_periods": acceptable_pf_periods,
        "total_trades": total_trades,
        "average_profit_factor": avg_pf,
        "average_expectancy_r": avg_expectancy,
        "total_net_r": total_net_r,
        "worst_drawdown_r": worst_drawdown,
        "robust": robust,
    })

summary_df = pd.DataFrame(summary)

# ------------------------------------------------------------
# Save results
# ------------------------------------------------------------

validation.to_csv(OUTPUT, index=False)

survivors = summary_df[
    summary_df["robust"] == True
].copy()

survivors = survivors.sort_values(
    [
        "average_profit_factor",
        "average_expectancy_r",
        "total_net_r"
    ],
    ascending=False
)

survivors.to_csv(SURVIVORS, index=False)

# ------------------------------------------------------------
# Display
# ------------------------------------------------------------

print()
print("=" * 110)
print("WALK-FORWARD SUMMARY")
print("=" * 110)

print(
    summary_df.to_string(index=False)
)

print()
print("=" * 110)
print(f"Detailed validation: {OUTPUT}")
print(f"Robust survivors   : {SURVIVORS}")
print(f"Survivors           : {len(survivors)}")
print("=" * 110)

if len(survivors) == 0:
    print()
    print("WARNING:")
    print("No strategy passed the robustness test.")
    print("This does NOT mean the strategy is bad.")
    print("It means the available summary data is insufficient")
    print("to establish multi-period robustness.")
else:
    print()
    print("ROBUST STRATEGIES FOUND:")
    print(survivors.to_string(index=False))
