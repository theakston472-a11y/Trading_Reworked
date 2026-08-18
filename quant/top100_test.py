import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# =========================================================
# MAKE quant IMPORTABLE WHEN RUN DIRECTLY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from quant.backtester import backtest_strategy


# =========================================================
# CONFIG
# =========================================================

FEATURE_FILE = BASE_DIR / "quant" / "feature_database.csv"

# Actual file you showed
STRATEGY_FILE = (
    BASE_DIR
    / "quant"
    / "new_search"
    / "new_combination_top100.csv"
)

RESULT_FILE = (
    BASE_DIR
    / "quant"
    / "top100_validation.csv"
)

SUMMARY_FILE = (
    BASE_DIR
    / "quant"
    / "top100_robustness_summary.csv"
)

TOP_N = 100

MIN_TRADES = 10

PERIODS = {
    "2020_2024": (
        "2020-01-01",
        "2024-12-31 23:59:59",
    ),

    "2025": (
        "2025-01-01",
        "2025-12-31 23:59:59",
    ),

    "2026": (
        "2026-01-01",
        "2026-12-31 23:59:59",
    ),
}


# =========================================================
# HEADER
# =========================================================

print("=" * 80)
print("TOP 100 STRATEGY VALIDATION")
print("=" * 80)
print()

print("Base directory:")
print(BASE_DIR)
print()

print("Feature file:")
print(FEATURE_FILE)
print()

print("Strategy file:")
print(STRATEGY_FILE)
print()

print("Raw result file:")
print(RESULT_FILE)
print()

print("Summary file:")
print(SUMMARY_FILE)
print()


# =========================================================
# CHECK FILES
# =========================================================

if not FEATURE_FILE.exists():

    print("ERROR: Feature database not found:")
    print(FEATURE_FILE)
    raise SystemExit(1)


if not STRATEGY_FILE.exists():

    print("ERROR: Strategy file not found:")
    print(STRATEGY_FILE)
    raise SystemExit(1)


# =========================================================
# LOAD FEATURE DATABASE
# =========================================================

print("=" * 80)
print("LOADING FEATURE DATABASE")
print("=" * 80)
print()

df = pd.read_csv(FEATURE_FILE)

print("Candles:", len(df))
print()


# =========================================================
# LOAD STRATEGIES
# =========================================================

print("=" * 80)
print("LOADING STRATEGIES")
print("=" * 80)
print()

strategies = pd.read_csv(STRATEGY_FILE)

print("Strategies available:", len(strategies))
print()

print("Strategy columns:")
print(list(strategies.columns))
print()


# =========================================================
# TIMESTAMP
# =========================================================

if "timestamp" not in df.columns:

    print("ERROR: timestamp column missing from feature database.")
    raise SystemExit(1)


df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce",
)

df = (
    df
    .dropna(subset=["timestamp"])
    .sort_values("timestamp")
    .reset_index(drop=True)
)


# =========================================================
# STRATEGY SCORE COLUMN
# =========================================================

# Your new_combination_top100.csv has "score",
# not "strategy_score".

if "strategy_score" in strategies.columns:

    score_column = "strategy_score"

elif "score" in strategies.columns:

    score_column = "score"

else:

    print(
        "ERROR: Strategy file contains neither "
        "'strategy_score' nor 'score'."
    )

    raise SystemExit(1)


# =========================================================
# REQUIRED STRATEGY COLUMNS
# =========================================================

required_strategy_columns = [
    "direction",
    "session",
    "conditions",
]

missing_strategy_columns = [
    column
    for column in required_strategy_columns
    if column not in strategies.columns
]

if missing_strategy_columns:

    print("ERROR: Missing strategy columns:")
    print(missing_strategy_columns)
    raise SystemExit(1)


# =========================================================
# SELECT TOP N
# =========================================================

strategies = (
    strategies
    .sort_values(
        score_column,
        ascending=False,
    )
    .head(TOP_N)
    .reset_index(drop=True)
)


print(
    "Testing top",
    len(strategies),
    "strategies using score column:",
    score_column,
)

print()


# =========================================================
# PARSE CONDITIONS
# =========================================================

def parse_conditions(condition_string):

    conditions = {}

    parts = [
        part.strip()
        for part in str(condition_string).split("+")
    ]

    for feature in parts:

        if feature:

            conditions[feature] = True

    return conditions


# =========================================================
# RESULTS
# =========================================================

results = []

total_tests = (
    len(strategies)
    *
    len(PERIODS)
)

tests_completed = 0


# =========================================================
# TEST STRATEGIES
# =========================================================

for index, strategy in strategies.iterrows():

    rank = index + 1

    direction = str(
        strategy["direction"]
    ).strip().upper()

    session = str(
        strategy["session"]
    ).strip()

    if session.lower() == "all":

        session_value = None

    else:

        session_value = session


    conditions = parse_conditions(
        strategy["conditions"]
    )


    print()
    print("-" * 80)

    print(
        "STRATEGY",
        rank,
        "/",
        len(strategies),
    )

    print(
        "Direction:",
        direction,
    )

    print(
        "Session:",
        session,
    )

    print(
        "Conditions:",
        strategy["conditions"],
    )

    print(
        "Original score:",
        strategy[score_column],
    )

    print("-" * 80)


    # =====================================================
    # PERIOD TESTS
    # =====================================================

    for period_name, (
        start_date,
        end_date,
    ) in PERIODS.items():

        tests_completed += 1


        period_df = df[
            (
                df["timestamp"]
                >= pd.Timestamp(
                    start_date,
                    tz="UTC",
                )
            )
            &
            (
                df["timestamp"]
                <= pd.Timestamp(
                    end_date,
                    tz="UTC",
                )
            )
        ].copy()


        if len(period_df) == 0:

            print(
                period_name,
                ": NO DATA",
            )

            continue


        try:

            result = backtest_strategy(
                df=period_df,
                conditions=conditions,
                direction=direction,
                session=session_value,
            )


        except TypeError:

            # Compatibility fallback if the installed
            # backtester does not accept session.

            try:

                result = backtest_strategy(
                    df=period_df,
                    conditions=conditions,
                    direction=direction,
                )

            except Exception as e:

                print(
                    period_name,
                    ": ERROR",
                    repr(e),
                )

                continue


        except Exception as e:

            print(
                period_name,
                ": ERROR",
                repr(e),
            )

            continue


        if not result:

            print(
                period_name,
                ": NO RESULT",
            )

            continue


        stats = result.get(
            "stats",
            {},
        )


        trades = stats.get(
            "trades",
            0,
        )

        wins = stats.get(
            "wins",
            0,
        )

        losses = stats.get(
            "losses",
            0,
        )

        win_rate = stats.get(
            "win_rate",
            0,
        )

        profit_factor = stats.get(
            "profit_factor",
            0,
        )

        net_r = stats.get(
            "net_r",
            0,
        )

        average_r = stats.get(
            "average_r",
            0,
        )

        expectancy_r = stats.get(
            "expectancy_r",
            0,
        )

        max_drawdown_r = stats.get(
            "max_drawdown_r",
            0,
        )


        # =================================================
        # SAFE NUMERIC CONVERSION
        # =================================================

        def safe_float(value, default=0.0):

            try:

                value = float(value)

                if np.isnan(value):

                    return default

                return value

            except Exception:

                return default


        trades = int(
            safe_float(
                trades,
                0,
            )
        )

        wins = int(
            safe_float(
                wins,
                0,
            )
        )

        losses = int(
            safe_float(
                losses,
                0,
            )
        )

        win_rate = safe_float(
            win_rate,
            0,
        )

        profit_factor = safe_float(
            profit_factor,
            0,
        )

        net_r = safe_float(
            net_r,
            0,
        )

        average_r = safe_float(
            average_r,
            0,
        )

        expectancy_r = safe_float(
            expectancy_r,
            0,
        )

        max_drawdown_r = safe_float(
            max_drawdown_r,
            0,
        )


        # =================================================
        # VALID PERIOD
        # =================================================

        valid = (
            trades >= MIN_TRADES
        )


        results.append({

            "original_rank":
                rank,

            "original_score":
                safe_float(
                    strategy[score_column],
                    0,
                ),

            "direction":
                direction,

            "session":
                session,

            "conditions":
                strategy["conditions"],

            "condition_count":
                strategy.get(
                    "condition_count",
                    len(conditions),
                ),

            "period":
                period_name,

            "candles":
                len(period_df),

            "trades":
                trades,

            "wins":
                wins,

            "losses":
                losses,

            "win_rate":
                win_rate,

            "profit_factor":
                profit_factor,

            "average_r":
                average_r,

            "net_r":
                net_r,

            "expectancy_r":
                expectancy_r,

            "max_drawdown_r":
                max_drawdown_r,

            "valid":
                valid,
        })


        print(
            period_name,
            "| Trades:",
            trades,
            "| PF:",
            round(
                profit_factor,
                3,
            ),
            "| Net R:",
            round(
                net_r,
                3,
            ),
            "| Expectancy:",
            round(
                expectancy_r,
                4,
            ),
            "| DD:",
            round(
                max_drawdown_r,
                3,
            ),
            "| Valid:",
            valid,
        )


# =========================================================
# CHECK RESULTS
# =========================================================

if not results:

    print()
    print(
        "ERROR: No validation results produced."
    )

    raise SystemExit(1)


results_df = pd.DataFrame(
    results
)


# =========================================================
# SAVE RAW RESULTS
# =========================================================

results_df.to_csv(
    RESULT_FILE,
    index=False,
)


print()
print("=" * 80)
print("RAW VALIDATION RESULTS SAVED")
print("=" * 80)
print()

print(
    RESULT_FILE
)

print()


# =========================================================
# CREATE ROBUSTNESS SUMMARY
# =========================================================

summary = []


for rank in sorted(
    results_df["original_rank"].unique()
):

    strategy_rows = results_df[
        results_df["original_rank"] == rank
    ]


    original = strategies.iloc[
        rank - 1
    ]


    periods_tested = len(
        strategy_rows
    )


    valid_periods = int(
        strategy_rows["valid"].sum()
    )


    total_trades = int(
        strategy_rows["trades"].sum()
    )


    positive_periods = int(
        (
            strategy_rows["net_r"] > 0
        ).sum()
    )


    positive_expectancy_periods = int(
        (
            strategy_rows["expectancy_r"] > 0
        ).sum()
    )


    average_pf = (
        strategy_rows["profit_factor"]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .mean()
    )


    if pd.isna(average_pf):

        average_pf = 0.0


    average_expectancy = (
        strategy_rows["expectancy_r"].mean()
    )


    total_net_r = (
        strategy_rows["net_r"].sum()
    )


    worst_drawdown = (
        strategy_rows["max_drawdown_r"].max()
    )


    # =====================================================
    # ROBUSTNESS SCORE
    # =====================================================

    robustness_score = (

        positive_periods * 3.0

        +

        positive_expectancy_periods * 3.0

        +

        min(
            total_trades / 100.0,
            5.0,
        )

        +

        max(
            average_pf - 1.0,
            0,
        ) * 5.0

        +

        max(
            average_expectancy,
            0,
        ) * 10.0

        -

        max(
            worst_drawdown,
            0,
        ) * 0.10
    )


    summary.append({

        "original_rank":
            rank,

        "original_score":
            original[score_column],

        "direction":
            original["direction"],

        "session":
            original["session"],

        "conditions":
            original["conditions"],

        "periods_tested":
            periods_tested,

        "valid_periods":
            valid_periods,

        "positive_periods":
            positive_periods,

        "positive_expectancy_periods":
            positive_expectancy_periods,

        "total_trades":
            total_trades,

        "average_pf":
            average_pf,

        "average_expectancy":
            average_expectancy,

        "total_net_r":
            total_net_r,

        "worst_drawdown":
            worst_drawdown,

        "robustness_score":
            robustness_score,
    })


summary_df = pd.DataFrame(
    summary
)


# =========================================================
# SORT ROBUSTNESS
# =========================================================

summary_df = (
    summary_df
    .sort_values(
        "robustness_score",
        ascending=False,
    )
    .reset_index(drop=True)
)


# =========================================================
# SAVE SUMMARY
# =========================================================

summary_df.to_csv(
    SUMMARY_FILE,
    index=False,
)


# =========================================================
# DISPLAY TOP RESULTS
# =========================================================

print()
print("=" * 80)
print("TOP 30 MOST ROBUST STRATEGIES")
print("=" * 80)
print()


display_columns = [

    "original_rank",

    "direction",

    "session",

    "conditions",

    "periods_tested",

    "valid_periods",

    "positive_periods",

    "positive_expectancy_periods",

    "total_trades",

    "average_pf",

    "average_expectancy",

    "total_net_r",

    "worst_drawdown",

    "robustness_score",
]


print(
    summary_df[
        display_columns
    ]
    .head(30)
    .to_string(
        index=False
    )
)


# =========================================================
# FINAL STATUS
# =========================================================

print()
print("=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
print()

print("Raw results:")
print(RESULT_FILE)

print()

print("Robustness summary:")
print(SUMMARY_FILE)

print()

print(
    "Tests completed:",
    tests_completed,
    "/",
    total_tests,
)

print()

print("=" * 80)
print("DONE")
print("=" * 80)
