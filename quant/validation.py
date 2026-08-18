import pandas as pd
import numpy as np

from quant.backtester import backtest_strategy


# =========================================================
# CONFIG
# =========================================================

FEATURE_FILE = "quant/feature_database.csv"
STRATEGY_FILE = "quant/validation_results.csv"
RESULT_FILE = "quant/walk_forward_results.csv"
SUMMARY_FILE = "quant/walk_forward_summary.csv"

# Number of validated candidates to test
TOP_STRATEGIES = 100

# Minimum trades required in an individual period
MIN_TRADES_PER_PERIOD = 20

# Minimum total trades across all periods
MIN_TOTAL_TRADES = 80

# =========================================================
# WALK-FORWARD PERIODS
# =========================================================

PERIODS = [
    (
        "2024",
        "2024-01-01",
        "2025-01-01"
    ),
    (
        "2025_H1",
        "2025-01-01",
        "2025-07-01"
    ),
    (
        "2025_H2",
        "2025-07-01",
        "2026-01-01"
    ),
    (
        "2026_H1",
        "2026-01-01",
        "2026-07-01"
    )
]


# =========================================================
# HEADER
# =========================================================

print("=" * 80)
print("MULTI-PERIOD WALK-FORWARD ROBUSTNESS TEST")
print("=" * 80)
print()


# =========================================================
# LOAD FEATURE DATABASE
# =========================================================

print("Loading feature database...")

df = pd.read_csv(
    FEATURE_FILE
)

print(
    "Candles loaded:",
    len(df)
)

print()


# =========================================================
# NORMALIZE TIMESTAMP
# =========================================================

if "timestamp" not in df.columns:

    print("ERROR: timestamp column missing.")

    raise SystemExit(1)


df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce"
)

df = df.dropna(
    subset=["timestamp"]
).copy()

df = df.sort_values(
    "timestamp"
).reset_index(
    drop=True
)


print(
    "Timestamp range:",
    df["timestamp"].min(),
    "->",
    df["timestamp"].max()
)

print()


# =========================================================
# LOAD VALIDATED STRATEGIES
# =========================================================

print("Loading validated strategies...")

strategies = pd.read_csv(
    STRATEGY_FILE
)

print(
    "Validated strategies loaded:",
    len(strategies)
)

print()


# =========================================================
# CHECK COLUMNS
# =========================================================

required_columns = [
    "direction",
    "session",
    "conditions"
]

missing_columns = [
    column
    for column in required_columns
    if column not in strategies.columns
]

if missing_columns:

    print("ERROR: Missing strategy columns:")

    for column in missing_columns:
        print(" -", column)

    raise SystemExit(1)


# =========================================================
# REMOVE DUPLICATE STRATEGIES
# =========================================================

print("Removing duplicate-equivalent condition sets...")

strategies["direction"] = (
    strategies["direction"]
    .astype(str)
    .str.strip()
)

strategies["session"] = (
    strategies["session"]
    .astype(str)
    .str.strip()
)

strategies["conditions"] = (
    strategies["conditions"]
    .astype(str)
    .str.strip()
)


def normalize_conditions(value):

    conditions = [
        item.strip()
        for item in value.split("+")
        if item.strip()
    ]

    return " + ".join(
        sorted(
            set(conditions)
        )
    )


strategies["normalized_conditions"] = (
    strategies["conditions"]
    .apply(normalize_conditions)
)


strategies = strategies.drop_duplicates(
    subset=[
        "direction",
        "session",
        "normalized_conditions"
    ]
)


# =========================================================
# SORT BY ORIGINAL VALIDATION SCORE
# =========================================================

if "validation_score" in strategies.columns:

    strategies = strategies.sort_values(
        "validation_score",
        ascending=False
    )

else:

    strategies = strategies.sort_values(
        "profit_factor",
        ascending=False
    )


strategies = strategies.head(
    TOP_STRATEGIES
).reset_index(
    drop=True
)


print(
    "Unique candidates selected:",
    len(strategies)
)

print()


# =========================================================
# PERIOD DATASETS
# =========================================================

period_data = {}


for period_name, start_date, end_date in PERIODS:

    start = pd.Timestamp(
        start_date,
        tz="UTC"
    )

    end = pd.Timestamp(
        end_date,
        tz="UTC"
    )

    mask = (
        (df["timestamp"] >= start)
        &
        (df["timestamp"] < end)
    )

    period_df = df.loc[
        mask
    ].copy()

    period_data[
        period_name
    ] = period_df

    print(
        period_name,
        ":",
        len(period_df),
        "candles |",
        start,
        "->",
        end
    )


print()


# =========================================================
# VALIDATE PERIOD AVAILABILITY
# =========================================================

available_periods = [
    name
    for name, data in period_data.items()
    if len(data) > 0
]

if len(available_periods) < 2:

    print(
        "ERROR: Not enough walk-forward periods available."
    )

    raise SystemExit(1)


# =========================================================
# RESULTS
# =========================================================

results = []

total_tests = (
    len(strategies)
    *
    len(available_periods)
)

completed_tests = 0


# =========================================================
# RUN WALK-FORWARD
# =========================================================

print("=" * 80)
print("RUNNING WALK-FORWARD TEST")
print("=" * 80)
print()


for strategy_number, strategy in strategies.iterrows():

    direction = str(
        strategy["direction"]
    ).strip()

    session_value = str(
        strategy["session"]
    ).strip()

    if session_value.lower() in (
        "all",
        "none",
        "nan"
    ):
        session = None
    else:
        session = session_value

    condition_string = str(
        strategy["conditions"]
    ).strip()

    conditions = {}

    for condition in condition_string.split("+"):

        condition = condition.strip()

        if condition:
            conditions[
                condition
            ] = True


    for period_name in available_periods:

        period_df = period_data[
            period_name
        ]

        completed_tests += 1

        try:

            result = backtest_strategy(
                df=period_df,
                conditions=conditions,
                direction=direction,
                session=session
            )

        except TypeError:

            try:

                result = backtest_strategy(
                    df=period_df,
                    conditions=conditions,
                    direction=direction
                )

            except Exception as e:

                print()
                print(
                    "BACKTEST ERROR:",
                    strategy_number + 1,
                    period_name
                )
                print(e)

                continue

        except Exception as e:

            print()
            print(
                "BACKTEST ERROR:",
                strategy_number + 1,
                period_name
            )
            print(e)

            continue


        if not result:

            continue


        stats = result.get(
            "stats",
            {}
        )


        trades = int(
            stats.get(
                "trades",
                0
            )
        )


        wins = int(
            stats.get(
                "wins",
                0
            )
        )


        losses = int(
            stats.get(
                "losses",
                0
            )
        )


        win_rate = float(
            stats.get(
                "win_rate",
                0
            )
        )


        profit_factor = float(
            stats.get(
                "profit_factor",
                0
            )
        )


        net_r = float(
            stats.get(
                "net_r",
                0
            )
        )


        average_r = float(
            stats.get(
                "average_r",
                0
            )
        )


        expectancy_r = float(
            stats.get(
                "expectancy_r",
                0
            )
        )


        max_drawdown_r = float(
            stats.get(
                "max_drawdown_r",
                0
            )
        )


        results.append({

            "strategy_rank":
                strategy_number + 1,

            "direction":
                direction,

            "session":
                session
                if session
                else "All",

            "conditions":
                condition_string,

            "period":
                period_name,

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

            "net_r":
                net_r,

            "average_r":
                average_r,

            "expectancy_r":
                expectancy_r,

            "max_drawdown_r":
                max_drawdown_r
        })


    if (
        strategy_number == 0
        or (strategy_number + 1) % 10 == 0
        or strategy_number + 1 == len(strategies)
    ):

        print(
            "Progress:",
            strategy_number + 1,
            "/",
            len(strategies),
            "| Tests:",
            completed_tests,
            "/",
            total_tests
        )


# =========================================================
# NO RESULTS
# =========================================================

print()

if not results:

    print(
        "No walk-forward results generated."
    )

    raise SystemExit(0)


# =========================================================
# RAW RESULTS DATAFRAME
# =========================================================

results_df = pd.DataFrame(
    results
)


# =========================================================
# SAVE RAW RESULTS
# =========================================================

results_df.to_csv(
    RESULT_FILE,
    index=False
)


print(
    "Raw walk-forward results saved:"
)

print(
    RESULT_FILE
)

print()


# =========================================================
# STRATEGY SUMMARY
# =========================================================

summary_rows = []


for (
    strategy_rank,
    direction,
    session,
    conditions
), group in results_df.groupby(
    [
        "strategy_rank",
        "direction",
        "session",
        "conditions"
    ]
):

    group = group.copy()

    total_trades = int(
        group["trades"].sum()
    )

    total_net_r = float(
        group["net_r"].sum()
    )

    total_wins = int(
        group["wins"].sum()
    )

    total_losses = int(
        group["losses"].sum()
    )

    periods_tested = len(
        group
    )

    profitable_periods = int(
        (
            group["net_r"] > 0
        ).sum()
    )

    positive_expectancy_periods = int(
        (
            group["expectancy_r"] > 0
        ).sum()
    )

    profitable_period_ratio = (
        profitable_periods
        /
        periods_tested
        if periods_tested
        else 0
    )

    positive_expectancy_ratio = (
        positive_expectancy_periods
        /
        periods_tested
        if periods_tested
        else 0
    )

    if (
        total_wins + total_losses
    ) > 0:

        combined_win_rate = (
            total_wins
            /
            (
                total_wins
                +
                total_losses
            )
            *
            100
        )

    else:

        combined_win_rate = 0


    # -----------------------------------------------------
    # COMBINED PROFIT FACTOR
    # -----------------------------------------------------

    # If individual profit factors are available but gross
    # profit/loss are not exposed by the backtester, use
    # weighted expectancy as a conservative aggregate proxy.

    weighted_expectancy = (
        (
            group["expectancy_r"]
            *
            group["trades"]
        ).sum()
        /
        total_trades
        if total_trades
        else 0
    )


    # -----------------------------------------------------
    # WORST PERIOD
    # -----------------------------------------------------

    worst_period_row = group.loc[
        group["net_r"].idxmin()
    ]

    worst_period = worst_period_row[
        "period"
    ]

    worst_period_net_r = float(
        worst_period_row[
            "net_r"
        ]
    )

    worst_drawdown = float(
        group["max_drawdown_r"].max()
    )


    # -----------------------------------------------------
    # MINIMUM PERIOD TRADES
    # -----------------------------------------------------

    minimum_period_trades = int(
        group["trades"].min()
    )


    # -----------------------------------------------------
    # ROBUSTNESS SCORE
    # -----------------------------------------------------

    trade_score = min(
        total_trades / 300.0,
        2.0
    )

    consistency_score = (
        profitable_period_ratio
        *
        4.0
    )

    expectancy_score = (
        max(
            weighted_expectancy,
            0.0
        )
        *
        5.0
    )

    net_score = (
        max(
            total_net_r,
            0.0
        )
        *
        0.05
    )

    drawdown_penalty = (
        max(
            worst_drawdown,
            0.0
        )
        *
        0.10
    )


    robustness_score = (
        trade_score
        +
        consistency_score
        +
        expectancy_score
        +
        net_score
        -
        drawdown_penalty
    )


    # -----------------------------------------------------
    # PASS / FAIL
    # -----------------------------------------------------

    passes_trade_requirement = (
        total_trades
        >=
        MIN_TOTAL_TRADES
    )

    passes_period_requirement = (
        minimum_period_trades
        >=
        MIN_TRADES_PER_PERIOD
    )

    passes_consistency = (
        profitable_periods
        >=
        max(
            2,
            int(
                np.ceil(
                    periods_tested
                    *
                    0.75
                )
            )
        )
    )

    passes_expectancy = (
        positive_expectancy_periods
        >=
        max(
            2,
            int(
                np.ceil(
                    periods_tested
                    *
                    0.75
                )
            )
        )
    )

    robust = (
        passes_trade_requirement
        and
        passes_period_requirement
        and
        passes_consistency
        and
        passes_expectancy
    )


    summary_rows.append({

        "strategy_rank":
            strategy_rank,

        "direction":
            direction,

        "session":
            session,

        "conditions":
            conditions,

        "periods_tested":
            periods_tested,

        "profitable_periods":
            profitable_periods,

        "profitable_period_ratio":
            profitable_period_ratio,

        "positive_expectancy_periods":
            positive_expectancy_periods,

        "positive_expectancy_ratio":
            positive_expectancy_ratio,

        "total_trades":
            total_trades,

        "minimum_period_trades":
            minimum_period_trades,

        "wins":
            total_wins,

        "losses":
            total_losses,

        "combined_win_rate":
            combined_win_rate,

        "weighted_expectancy_r":
            weighted_expectancy,

        "total_net_r":
            total_net_r,

        "worst_period":
            worst_period,

        "worst_period_net_r":
            worst_period_net_r,

        "worst_max_drawdown_r":
            worst_drawdown,

        "robustness_score":
            robustness_score,

        "robust":
            robust
    })


# =========================================================
# SUMMARY DATAFRAME
# =========================================================

summary_df = pd.DataFrame(
    summary_rows
)


# =========================================================
# SORT
# =========================================================

summary_df = summary_df.sort_values(
    [
        "robust",
        "robustness_score",
        "total_net_r"
    ],
    ascending=[
        False,
        False,
        False
    ]
)


# =========================================================
# SAVE SUMMARY
# =========================================================

summary_df.to_csv(
    SUMMARY_FILE,
    index=False
)


print(
    "Walk-forward summary saved:"
)

print(
    SUMMARY_FILE
)

print()


# =========================================================
# ROBUST STRATEGIES
# =========================================================

robust_df = summary_df[
    summary_df["robust"] == True
].copy()


print("=" * 80)
print("ROBUST STRATEGIES")
print("=" * 80)
print()

print(
    "Robust strategies:",
    len(robust_df)
)

print()


# =========================================================
# TOP ROBUST STRATEGIES
# =========================================================

if not robust_df.empty:

    display_columns = [
        "strategy_rank",
        "direction",
        "session",
        "conditions",
        "periods_tested",
        "profitable_periods",
        "total_trades",
        "combined_win_rate",
        "weighted_expectancy_r",
        "total_net_r",
        "worst_period",
        "worst_period_net_r",
        "worst_max_drawdown_r",
        "robustness_score"
    ]

    print(
        robust_df[
            display_columns
        ]
        .head(30)
        .to_string(
            index=False
        )
    )

else:

    print(
        "No strategies passed the full robustness test."
    )

    print()

    print(
        "Showing strongest candidates instead:"
    )

    print()

    display_columns = [
        "strategy_rank",
        "direction",
        "session",
        "conditions",
        "periods_tested",
        "profitable_periods",
        "total_trades",
        "combined_win_rate",
        "weighted_expectancy_r",
        "total_net_r",
        "worst_period",
        "worst_period_net_r",
        "worst_max_drawdown_r",
        "robustness_score"
    ]

    print(
        summary_df[
            display_columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )


# =========================================================
# PERIOD-BY-PERIOD BREAKDOWN
# =========================================================

print()
print("=" * 80)
print("PERIOD PERFORMANCE OF TOP CANDIDATES")
print("=" * 80)
print()


top_ranks = summary_df[
    "strategy_rank"
].head(
    min(
        10,
        len(summary_df)
    )
).tolist()


for rank in top_ranks:

    strategy_results = results_df[
        results_df[
            "strategy_rank"
        ] == rank
    ].copy()

    if strategy_results.empty:
        continue

    first = strategy_results.iloc[0]

    print(
        f"#{int(rank)} | "
        f"{first['direction']} | "
        f"{first['session']} | "
        f"{first['conditions']}"
    )

    for _, period_row in strategy_results.iterrows():

        print(
            f"  {period_row['period']:<8} | "
            f"Trades: {int(period_row['trades']):4d} | "
            f"PF: {period_row['profit_factor']:.3f} | "
            f"Exp: {period_row['expectancy_r']:.4f} | "
            f"Net R: {period_row['net_r']:.2f} | "
            f"DD: {period_row['max_drawdown_r']:.2f}"
        )

    print()


# =========================================================
# FINAL
# =========================================================

print("=" * 80)
print("WALK-FORWARD TEST COMPLETE")
print("=" * 80)
print()

print(
    "Raw results:",
    RESULT_FILE
)

print(
    "Summary:",
    SUMMARY_FILE
)

print(
    "Robust strategies:",
    len(robust_df)
)

print()