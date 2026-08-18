import itertools
import pandas as pd
import numpy as np

from quant.backtester import backtest_strategy


# =========================================================
# CONFIG
# =========================================================

FEATURE_FILE = "quant/feature_database.csv"
RESULT_FILE = "quant/fib_strategy_scores.csv"

MIN_TRADES = 30
MAX_CONDITIONS = 4

SESSIONS = [
    None,
    "Asia",
    "London",
    "New York"
]


# =========================================================
# TARGETED FEATURES
# =========================================================

BUY_FEATURES = [
    "bullish_bos",
    "bullish_fib_382_rejection",
    "bullish_fib_500_rejection",
    "bullish_fib_618_rejection",
    "bullish_fib_liquidity",
]

SELL_FEATURES = [
    "bearish_bos",
    "bearish_fib_382_rejection",
    "bearish_fib_500_rejection",
    "bearish_fib_618_rejection",
    "bearish_fib_liquidity",
]


# =========================================================
# HEADER
# =========================================================

print("=" * 70)
print("TARGETED FIBONACCI STRATEGY SEARCH")
print("=" * 70)
print()


# =========================================================
# LOAD DATA
# =========================================================

print("Loading feature database...")

df = pd.read_csv(
    FEATURE_FILE
)

print(
    "Candles:",
    len(df)
)

print(
    "Features:",
    len(df.columns)
)

print()


# =========================================================
# CHECK FEATURES
# =========================================================

required_features = (
    BUY_FEATURES
    +
    SELL_FEATURES
)

missing_features = [
    feature
    for feature in required_features
    if feature not in df.columns
]

if missing_features:

    print("ERROR: Missing features:")

    for feature in missing_features:
        print(" -", feature)

    raise SystemExit


# =========================================================
# CONVERT FEATURES TO BOOLEAN
# =========================================================

for feature in required_features:

    df[feature] = (
        df[feature]
        .fillna(False)
        .astype(bool)
    )


# =========================================================
# TIMESTAMP
# =========================================================

if "timestamp" in df.columns:

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )


# =========================================================
# GENERATE COMBINATIONS
# =========================================================

def generate_combinations(features):

    combinations = []

    for count in range(
        1,
        MAX_CONDITIONS + 1
    ):

        print(
            "Generating",
            count,
            "condition combinations..."
        )

        combinations.extend(
            itertools.combinations(
                features,
                count
            )
        )

    return combinations


print("Generating BUY combinations...")

buy_combinations = generate_combinations(
    BUY_FEATURES
)

print()

print("Generating SELL combinations...")

sell_combinations = generate_combinations(
    SELL_FEATURES
)

print()

print(
    "BUY combinations:",
    len(buy_combinations)
)

print(
    "SELL combinations:",
    len(sell_combinations)
)

print()


# =========================================================
# TOTAL TESTS
# =========================================================

TOTAL_TESTS = (
    len(buy_combinations)
    +
    len(sell_combinations)
) * len(SESSIONS)

print(
    "Total tests:",
    TOTAL_TESTS
)

print()


# =========================================================
# RESULTS
# =========================================================

results = []

tests_completed = 0


# =========================================================
# SEARCH
# =========================================================

def run_search(
    combinations,
    direction
):

    global tests_completed

    total = len(combinations)

    print()
    print("=" * 70)
    print(
        "TESTING",
        direction,
        "FIB COMBINATIONS"
    )
    print("=" * 70)
    print()

    for number, combination in enumerate(
        combinations,
        start=1
    ):

        conditions = {
            feature: True
            for feature in combination
        }

        for session in SESSIONS:

            tests_completed += 1

            try:

                result = backtest_strategy(
                    df=df,
                    conditions=conditions,
                    direction=direction,
                    session=session
                )

            except TypeError:

                try:

                    result = backtest_strategy(
                        df=df,
                        conditions=conditions,
                        direction=direction
                    )

                except Exception as e:

                    print()
                    print("BACKTEST ERROR:")
                    print(e)

                    continue

            except Exception as e:

                print()
                print("BACKTEST ERROR:")
                print(e)

                continue

            if not result:
                continue

            stats = result.get(
                "stats",
                {}
            )

            trades = stats.get(
                "trades",
                0
            )

            if trades < MIN_TRADES:
                continue

            results.append({

                "direction":
                    direction,

                "session":
                    session
                    if session
                    else "All",

                "conditions":
                    " + ".join(
                        combination
                    ),

                "condition_count":
                    len(combination),

                "trades":
                    trades,

                "wins":
                    stats.get(
                        "wins",
                        0
                    ),

                "losses":
                    stats.get(
                        "losses",
                        0
                    ),

                "win_rate":
                    stats.get(
                        "win_rate",
                        0
                    ),

                "profit_factor":
                    stats.get(
                        "profit_factor",
                        0
                    ),

                "net_r":
                    stats.get(
                        "net_r",
                        0
                    ),

                "average_r":
                    stats.get(
                        "average_r",
                        0
                    ),

                "expectancy_r":
                    stats.get(
                        "expectancy_r",
                        0
                    ),

                "max_drawdown_r":
                    stats.get(
                        "max_drawdown_r",
                        0
                    )
            })

        if (
            number == 1
            or number % 5 == 0
            or number == total
        ):

            print(
                direction,
                "progress:",
                number,
                "/",
                total,
                "| Tests:",
                tests_completed,
                "/",
                TOTAL_TESTS,
                "| Strategies:",
                len(results)
            )


# =========================================================
# RUN
# =========================================================

run_search(
    buy_combinations,
    "BUY"
)

run_search(
    sell_combinations,
    "SELL"
)


# =========================================================
# SEARCH COMPLETE
# =========================================================

print()
print("=" * 70)
print("SEARCH COMPLETE")
print("=" * 70)
print()

print(
    "Tests performed:",
    tests_completed
)

print(
    "Strategies with enough trades:",
    len(results)
)

print()


# =========================================================
# NO RESULTS
# =========================================================

if not results:

    print(
        "No Fib strategies produced enough trades."
    )

    raise SystemExit


# =========================================================
# DATAFRAME
# =========================================================

results_df = pd.DataFrame(
    results
)


# =========================================================
# STRATEGY SCORE
# =========================================================

def calculate_score(row):

    trades = float(
        row["trades"]
    )

    profit_factor = float(
        row["profit_factor"]
    )

    expectancy = float(
        row["expectancy_r"]
    )

    net_r = float(
        row["net_r"]
    )

    drawdown = float(
        row["max_drawdown_r"]
    )

    trade_score = min(
        trades / 50.0,
        3.0
    )

    pf_score = min(
        max(
            profit_factor,
            0.0
        ),
        3.0
    )

    expectancy_score = (
        expectancy * 5.0
    )

    net_score = (
        net_r * 0.10
    )

    drawdown_penalty = (
        max(
            drawdown,
            0.0
        )
        * 0.25
    )

    return (
        trade_score
        +
        pf_score * 2.0
        +
        expectancy_score
        +
        net_score
        -
        drawdown_penalty
    )


results_df[
    "strategy_score"
] = results_df.apply(
    calculate_score,
    axis=1
)


# =========================================================
# SORT
# =========================================================

results_df = results_df.sort_values(
    "strategy_score",
    ascending=False
)


# =========================================================
# SAVE
# =========================================================

results_df.to_csv(
    RESULT_FILE,
    index=False
)


print()
print("Saved:")
print(RESULT_FILE)
print()


# =========================================================
# TOP STRATEGIES
# =========================================================

print("=" * 70)
print("TOP 30 FIB STRATEGIES")
print("=" * 70)
print()


columns = [
    "direction",
    "session",
    "conditions",
    "condition_count",
    "trades",
    "win_rate",
    "profit_factor",
    "net_r",
    "expectancy_r",
    "max_drawdown_r",
    "strategy_score"
]


print(
    results_df[
        columns
    ]
    .head(30)
    .to_string(
        index=False
    )
)


print()
print("=" * 70)
print("DONE")
print("=" * 70)