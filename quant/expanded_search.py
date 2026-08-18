import itertools
import hashlib
import os
import sys
import pandas as pd
import numpy as np

from quant.backtester import backtest_strategy

EXPANDED_SEARCH_ENGINE_VERSION = "2026-08-14-v5-smc-sequences"


# ============================================================
# EXPANDED STRATEGY SEARCH
# ============================================================
#
# Purpose:
# Search NEW strategy combinations without deliberately
# repeating combinations already tested by:
#
#   quant/strategy_scores.csv
#   quant/fib_strategy_scores.csv
#   quant/expanded_strategy_scores.csv
#
# The search is deliberately constrained so we don't create
# millions of useless combinations.
#
# ============================================================


BASE = "quant"

FEATURE_FILE = os.path.join(BASE, "feature_database.csv")

OLD_RESULTS_1 = os.path.join(
    BASE,
    "strategy_scores.csv"
)

OLD_RESULTS_2 = os.path.join(
    BASE,
    "fib_strategy_scores.csv"
)

OUTPUT_FILE = os.path.join(
    BASE,
    "expanded_strategy_scores.csv"
)

CHECKPOINT_FILE = os.path.join(
    BASE,
    "expanded_search_checkpoint.csv"
)


# ============================================================
# SETTINGS
# ============================================================

MIN_TRADES = 30

MAX_CONDITIONS = 4

CHECKPOINT_EVERY = 100

SESSIONS = [
    None,
    "Asia",
    "London",
    "New York",
]


# ============================================================
# FEATURES
# ============================================================
#
# These are features that actually exist in your database.
#
# We intentionally leave out raw numeric columns such as:
#
#   open
#   high
#   low
#   close
#   EMA values
#   ATR
#   range
#
# because those are not boolean strategy conditions.
#
# ============================================================


BUY_FEATURES = [

    # Trend / structure
    "ema_bullish_alignment",
    "bullish_bos",
    "bullish_choch",

    # Liquidity
    "liquidity_sweep_low",
    "equal_low_liquidity_sweep",
    "bullish_liquidity_structure_shift",

    # Candles
    "bullish_candle",
    "bullish_engulfing",
    "bullish_pin_bar",
    "strong_bullish_candle",

    # Previous day
    "previous_day_low_sweep",

    # Fair value gap / SMC sequence
    "bullish_fvg",
    "bullish_fvg_displacement",
    "bullish_fvg_retest",
    "bullish_liquidity_fvg_setup",
    "bullish_smc_reversal_setup",
    "bullish_smc_fvg_retest",

    # Validated order blocks / breakers
    "bullish_order_block_retest",
    "bullish_breaker_retest",
    "bullish_order_block_manipulation",
    "bullish_order_block_pin_bar",
    "bullish_order_block_engulfing",
    "bullish_order_block_indecision",
    "bullish_order_block_marubozu",
    "bullish_order_block_star",
    "bullish_ob_fib_confluence",

    # Fibonacci
    "fib_bullish",
    "near_fib_382",
    "near_fib_500",
    "near_fib_618",

    "bullish_fib_382_rejection",
    "bullish_fib_500_rejection",
    "bullish_fib_618_rejection",

    "bullish_bos_fib_382",
    "bullish_bos_fib_500",
    "bullish_bos_fib_618",

    "bullish_fib_liquidity",
]


SELL_FEATURES = [

    # Trend / structure
    "ema_bearish_alignment",
    "bearish_bos",
    "bearish_choch",

    # Liquidity
    "liquidity_sweep_high",
    "equal_high_liquidity_sweep",
    "bearish_liquidity_structure_shift",

    # Candles
    "bearish_candle",
    "bearish_engulfing",
    "bearish_pin_bar",
    "strong_bearish_candle",

    # Previous day
    "previous_day_high_sweep",

    # Fair value gap / SMC sequence
    "bearish_fvg",
    "bearish_fvg_displacement",
    "bearish_fvg_retest",
    "bearish_liquidity_fvg_setup",
    "bearish_smc_reversal_setup",
    "bearish_smc_fvg_retest",

    # Validated order blocks / breakers
    "bearish_order_block_retest",
    "bearish_breaker_retest",
    "bearish_order_block_manipulation",
    "bearish_order_block_pin_bar",
    "bearish_order_block_engulfing",
    "bearish_order_block_indecision",
    "bearish_order_block_marubozu",
    "bearish_order_block_star",
    "bearish_ob_fib_confluence",

    # Fibonacci
    "fib_bearish",
    "near_fib_382",
    "near_fib_500",
    "near_fib_618",

    "bearish_fib_382_rejection",
    "bearish_fib_500_rejection",
    "bearish_fib_618_rejection",

    "bearish_bos_fib_382",
    "bearish_bos_fib_500",
    "bearish_bos_fib_618",

    "bearish_fib_liquidity",
]


# ============================================================
# PRINT HEADER
# ============================================================

print()
print("=" * 75)
print("EXPANDED STRATEGY SEARCH")
print("=" * 75)
print()

print("This search is designed to discover NEW strategies.")
print("Existing strategy combinations will be skipped.")
print()


# ============================================================
# LOAD DATABASE
# ============================================================

print("Loading feature database...")

df = pd.read_csv(
    FEATURE_FILE
)

print(
    f"Candles loaded: {len(df):,}"
)

print(
    f"Columns loaded: {len(df.columns)}"
)

print()


# ============================================================
# CHECK FEATURES
# ============================================================

all_features = sorted(
    set(BUY_FEATURES + SELL_FEATURES)
)

missing = [
    feature
    for feature in all_features
    if feature not in df.columns
]

if missing:

    print("ERROR: These features are missing:")

    for feature in missing:
        print(
            "  -",
            feature
        )

    sys.exit(1)


# ============================================================
# CONVERT FEATURES TO BOOLEAN
# ============================================================

print("Preparing boolean features...")

def _safe_feature_bool(series):

    if pd.api.types.is_bool_dtype(
        series
    ):

        return (
            series
            .fillna(False)
            .astype(bool)
        )

    if pd.api.types.is_numeric_dtype(
        series
    ):

        return (
            pd.to_numeric(
                series,
                errors="coerce",
            )
            .fillna(0)
            .astype(bool)
        )

    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(
            {
                "true",
                "1",
                "yes",
                "y",
                "on",
            }
        )
    )


for feature in all_features:

    df[feature] = _safe_feature_bool(
        df[feature]
    )


# ============================================================
# TIMESTAMP
# ============================================================

if "timestamp" in df.columns:

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )


# ============================================================
# STRATEGY IDENTIFIER
# ============================================================

def strategy_id(
    direction,
    session,
    conditions
):

    session_name = (
        session
        if session
        else "All"
    )

    condition_text = "|".join(
        sorted(conditions)
    )

    raw = (
        EXPANDED_SEARCH_ENGINE_VERSION
        + "|"
        + direction
        + "|"
        + session_name
        + "|"
        + condition_text
    )

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# LOAD ALREADY TESTED STRATEGIES
# ============================================================

tested = set()


def load_previous_results(
    filename
):

    if not os.path.exists(filename):

        return 0

    try:

        old = pd.read_csv(
            filename
        )

    except Exception as e:

        print(
            f"WARNING: Could not read {filename}"
        )

        print(e)

        return 0

    count = 0

    if (
        "engine_version" not in old.columns
        or not (
            old["engine_version"]
            .astype(str)
            ==
            EXPANDED_SEARCH_ENGINE_VERSION
        ).any()
    ):

        print(
            f"Ignoring legacy results from {filename}: "
            "execution engine changed."
        )

        return 0

    old = old[
        old["engine_version"]
        .astype(str)
        ==
        EXPANDED_SEARCH_ENGINE_VERSION
    ].copy()

    required = [
        "direction",
        "session",
        "conditions",
    ]

    if not all(
        c in old.columns
        for c in required
    ):

        print(
            f"WARNING: {filename} does not contain "
            "the expected strategy columns."
        )

        return 0

    for _, row in old.iterrows():

        direction = str(
            row["direction"]
        )

        session = str(
            row["session"]
        )

        if session == "nan":
            session = "All"

        conditions_text = str(
            row["conditions"]
        )

        conditions = [
            x.strip()
            for x in conditions_text.split("+")
        ]

        sid = strategy_id(
            direction,
            None if session == "All" else session,
            conditions
        )

        tested.add(sid)

        count += 1

    return count


print("Checking previous strategy results...")

old_count_1 = load_previous_results(
    OLD_RESULTS_1
)

old_count_2 = load_previous_results(
    OLD_RESULTS_2
)

print(
    f"Previous strategy rows found: "
    f"{old_count_1 + old_count_2:,}"
)

print(
    f"Unique strategies already known: "
    f"{len(tested):,}"
)

print()


# ============================================================
# LOAD CHECKPOINT
# ============================================================

if os.path.exists(
    CHECKPOINT_FILE
):

    print(
        "Loading search checkpoint..."
    )

    try:

        checkpoint = pd.read_csv(
            CHECKPOINT_FILE
        )

        if (
            "engine_version"
            in checkpoint.columns
        ):

            checkpoint = checkpoint[
                checkpoint[
                    "engine_version"
                ].astype(str)
                ==
                EXPANDED_SEARCH_ENGINE_VERSION
            ].copy()

        else:

            checkpoint = checkpoint.iloc[
                0:0
            ].copy()

        for _, row in checkpoint.iterrows():

            sid = str(
                row["strategy_id"]
            )

            tested.add(
                sid
            )

        print(
            f"Current-engine checkpoint strategies loaded: "
            f"{len(checkpoint):,}"
        )

    except Exception as e:

        print(
            "WARNING: Could not load checkpoint."
        )

        print(e)

print()


# ============================================================
# GENERATE COMBINATIONS
# ============================================================

def generate_combinations(
    features
):

    combinations = []

    for count in range(
        1,
        MAX_CONDITIONS + 1
    ):

        print(
            f"Generating {count}-condition combinations..."
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
    f"BUY combinations: "
    f"{len(buy_combinations):,}"
)

print(
    f"SELL combinations: "
    f"{len(sell_combinations):,}"
)

print()


# ============================================================
# CREATE NEW TEST LIST
# ============================================================

tests = []

for direction, combinations in [

    ("BUY", buy_combinations),
    ("SELL", sell_combinations),

]:

    for combination in combinations:

        for session in SESSIONS:

            sid = strategy_id(
                direction,
                session,
                combination
            )

            if sid in tested:
                continue

            tests.append(
                (
                    sid,
                    direction,
                    session,
                    combination
                )
            )


print("=" * 75)
print("NEW SEARCH SPACE")
print("=" * 75)

print(
    f"New strategies to test: "
    f"{len(tests):,}"
)

print()


if not tests:

    print(
        "NO NEW STRATEGIES FOUND."
    )

    print(
        "Everything in this search space "
        "has already been tested."
    )

    sys.exit(0)


# ============================================================
# RESULTS
# ============================================================

results = []


# ============================================================
# CHECKPOINT FUNCTION
# ============================================================

def save_checkpoint():

    if not results:
        return

    checkpoint_rows = []

    for row in results:

        checkpoint_rows.append(
            {
                "strategy_id":
                    row["strategy_id"],

                "engine_version":
                    EXPANDED_SEARCH_ENGINE_VERSION,

                "direction":
                    row["direction"],

                "session":
                    row["session"],

                "conditions":
                    row["conditions"],
            }
        )

    checkpoint_df = pd.DataFrame(
        checkpoint_rows
    )

    checkpoint_df.to_csv(
        CHECKPOINT_FILE,
        index=False
    )


# ============================================================
# RUN TESTS
# ============================================================

print("=" * 75)
print("STARTING EXPANDED SEARCH")
print("=" * 75)
print()

completed = 0

new_strategies = 0

total_tests = len(tests)


for (
    sid,
    direction,
    session,
    combination
) in tests:

    completed += 1

    conditions = {
        feature: True
        for feature in combination
    }

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
            print(
                "BACKTEST ERROR:"
            )
            print(e)

            continue

    except Exception as e:

        print()
        print(
            "BACKTEST ERROR:"
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


    if trades < MIN_TRADES:

        continue


    session_name = (
        session
        if session
        else "All"
    )


    row = {

        "strategy_id":
            sid,

        "engine_version":
            EXPANDED_SEARCH_ENGINE_VERSION,

        "direction":
            direction,

        "session":
            session_name,

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
            ),
    }


    results.append(
        row
    )

    new_strategies += 1


    # --------------------------------------------------------
    # PROGRESS
    # --------------------------------------------------------

    if (
        completed == 1
        or completed % 100 == 0
        or completed == total_tests
    ):

        percent = (
            completed
            /
            total_tests
            *
            100
        )

        print(
            f"Progress: "
            f"{completed:,}/{total_tests:,} "
            f"({percent:.1f}%) | "
            f"Strategies found: "
            f"{new_strategies:,}"
        )


    # --------------------------------------------------------
    # CHECKPOINT
    # --------------------------------------------------------

    if (
        completed % CHECKPOINT_EVERY == 0
    ):

        save_checkpoint()


# ============================================================
# SAVE RESULTS
# ============================================================

print()
print("=" * 75)
print("SEARCH COMPLETE")
print("=" * 75)
print()

print(
    f"Tests completed: {completed:,}"
)

print(
    f"New strategies found: {new_strategies:,}"
)

print()


if not results:

    print(
        "No new strategies produced "
        f"at least {MIN_TRADES} trades."
    )

    print()

    save_checkpoint()

    sys.exit(0)


results_df = pd.DataFrame(
    results
)


# ============================================================
# SCORE STRATEGIES
# ============================================================

def calculate_score(
    row
):

    trades = float(
        row["trades"]
    )

    pf = float(
        row["profit_factor"]
    )

    expectancy = float(
        row["expectancy_r"]
    )

    net_r = float(
        row["net_r"]
    )

    drawdown = abs(
        float(
            row["max_drawdown_r"]
        )
    )


    trade_score = min(
        np.log1p(trades) / np.log1p(5000),
        1.0
    )


    pf_score = np.clip(
        (pf - 0.9) / 0.6,
        0,
        1
    )


    expectancy_score = np.clip(
        expectancy / 0.10,
        0,
        1
    )


    if net_r > 0:

        consistency = (
            net_r
            /
            (
                net_r
                +
                drawdown
                +
                1
            )
        )

    else:

        consistency = 0


    return (

        trade_score * 0.35

        +

        pf_score * 0.30

        +

        expectancy_score * 0.20

        +

        consistency * 0.15

    )


results_df[
    "expanded_score"
] = results_df.apply(
    calculate_score,
    axis=1
)


# ============================================================
# SORT
# ============================================================

results_df = results_df.sort_values(
    "expanded_score",
    ascending=False
)


# ============================================================
# SAVE
# ============================================================

results_df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# FINAL CHECKPOINT
# ============================================================

save_checkpoint()


# ============================================================
# DISPLAY TOP 50
# ============================================================

print()
print("=" * 75)
print("TOP 50 NEW STRATEGIES")
print("=" * 75)
print()

display_columns = [

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
    "expanded_score",

]


print(
    results_df[
        display_columns
    ]
    .head(50)
    .to_string(
        index=False
    )
)


# ============================================================
# TOP 10
# ============================================================

print()
print("=" * 75)
print("TOP 10 NEW STRATEGIES")
print("=" * 75)
print()


for number, (_, row) in enumerate(
    results_df.head(10).iterrows(),
    start=1
):

    print(
        f"#{number:2d} | "
        f"{row['direction']:4s} | "
        f"{str(row['session']):9s} | "
        f"Trades: {int(row['trades']):6d} | "
        f"PF: {float(row['profit_factor']):.3f} | "
        f"Exp: {float(row['expectancy_r']):.4f} | "
        f"Net R: {float(row['net_r']):.2f}"
    )

    print(
        f"     {row['conditions']}"
    )

    print()


# ============================================================
# FINISHED
# ============================================================

print("=" * 75)
print("DONE")
print("=" * 75)
print()

print(
    f"Saved results to:"
)

print(
    OUTPUT_FILE
)

print()

print(
    "Checkpoint:"
)

print(
    CHECKPOINT_FILE
)

print()