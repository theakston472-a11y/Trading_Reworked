import pandas as pd
import itertools

from quant.backtester import backtest_strategy


# ============================================================
# QUANT STRATEGY SEARCH ENGINE
# ============================================================

FEATURE_FILE = "quant/feature_database.csv"

RESULT_FILE = "quant/strategy_results.csv"


# ============================================================
# SEARCH SETTINGS
# ============================================================

RISK_REWARD = 2.0

STOP_MODE = "atr"

STOP_MULTIPLIER = 1.0

MAX_BARS = 48


# Minimum number of trades required before
# a strategy is considered meaningful.

MIN_TRADES = 5


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 70)

print("QUANT STRATEGY SEARCH ENGINE")

print("=" * 70)

print()

print("Loading feature database...")

df = pd.read_csv(
    FEATURE_FILE
)

df["timestamp"] = pd.to_datetime(
    df["timestamp"]
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


# ============================================================
# STRATEGY FEATURE GROUPS
# ============================================================

FEATURE_GROUPS = {

    "trend": [

        "ema_bullish_alignment",

        "ema_bearish_alignment"

    ],


    "structure": [

        "bullish_bos",

        "bearish_bos",

        "bullish_choch",

        "bearish_choch"

    ],


    "liquidity": [

        "liquidity_sweep_low",

        "liquidity_sweep_high",

        "previous_day_low_sweep",

        "previous_day_high_sweep"

    ],


    "price_action": [

        "bullish_engulfing",

        "bearish_engulfing",

        "bullish_pin_bar",

        "bearish_pin_bar",

        "strong_bullish_candle",

        "strong_bearish_candle"

    ],


    "fvg": [

        "bullish_fvg",

        "bearish_fvg"

    ],


    "fibonacci": [

        "near_fib_382",

        "near_fib_500",

        "near_fib_618"

    ]

}


# ============================================================
# BUILD BUY CONDITIONS
# ============================================================

BUY_FEATURES = [

    "ema_bullish_alignment",

    "bullish_bos",

    "bullish_choch",

    "liquidity_sweep_low",

    "previous_day_low_sweep",

    "bullish_engulfing",

    "bullish_pin_bar",

    "strong_bullish_candle",

    "bullish_fvg",

    "near_fib_382",

    "near_fib_500",

    "near_fib_618"

]


# ============================================================
# BUILD SELL CONDITIONS
# ============================================================

SELL_FEATURES = [

    "ema_bearish_alignment",

    "bearish_bos",

    "bearish_choch",

    "liquidity_sweep_high",

    "previous_day_high_sweep",

    "bearish_engulfing",

    "bearish_pin_bar",

    "strong_bearish_candle",

    "bearish_fvg",

    "near_fib_382",

    "near_fib_500",

    "near_fib_618"

]


# ============================================================
# SESSION OPTIONS
# ============================================================

SESSIONS = [

    None,

    "Asia",

    "London",

    "New York"

]


# ============================================================
# SEARCH RESULTS
# ============================================================

results = []


# ============================================================
# TEST COMBINATION
# ============================================================

def test_combination(
    features,
    direction,
    session
):

    conditions = {}

    for feature in features:

        conditions[feature] = True


    result = backtest_strategy(

        df=df,

        conditions=conditions,

        direction=direction,

        risk_reward=RISK_REWARD,

        stop_mode=STOP_MODE,

        stop_multiplier=STOP_MULTIPLIER,

        max_bars=MAX_BARS,

        session=session

    )


    stats = result["stats"]


    if stats["trades"] < MIN_TRADES:

        return


    results.append({

        "direction": direction,

        "session": (
            session
            if session
            else "All"
        ),

        "conditions": " + ".join(
            features
        ),

        "feature_count": len(
            features
        ),

        "trades": stats["trades"],

        "wins": stats["wins"],

        "losses": stats["losses"],

        "win_rate": stats["win_rate"],

        "profit_factor": stats["profit_factor"],

        "net_r": stats["net_r"],

        "average_r": stats["average_r"],

        "expectancy_r": stats["expectancy_r"],

        "max_drawdown_r": stats[
            "max_drawdown_r"
        ]

    })


# ============================================================
# SEARCH
# ============================================================

total_tests = 0


for direction in [

    "BUY",

    "SELL"

]:

    if direction == "BUY":

        feature_list = BUY_FEATURES

    else:

        feature_list = SELL_FEATURES


    print()

    print("=" * 70)

    print(
        "SEARCHING",
        direction
    )

    print("=" * 70)


    # --------------------------------------------------------
    # Test combinations of 1 to 4 conditions
    # --------------------------------------------------------

    for combination_size in range(
        1,
        5
    ):

        print()

        print(
            "Testing",
            combination_size,
            "condition combinations..."
        )


        combinations = itertools.combinations(

            feature_list,

            combination_size

        )


        for combination in combinations:

            for session in SESSIONS:

                total_tests += 1

                test_combination(

                    combination,

                    direction,

                    session

                )


# ============================================================
# SAVE RESULTS
# ============================================================

results_df = pd.DataFrame(
    results
)


if results_df.empty:

    print()

    print(
        "No strategies met the minimum trade requirement."
    )

    raise SystemExit


# ============================================================
# RANKING
# ============================================================

results_df = results_df.sort_values(

    by=[

        "profit_factor",

        "expectancy_r",

        "net_r"

    ],

    ascending=False

)


# ============================================================
# SAVE
# ============================================================

results_df.to_csv(

    RESULT_FILE,

    index=False

)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 70)

print("SEARCH COMPLETE")

print("=" * 70)

print()

print(
    "Tests performed:",
    total_tests
)

print(
    "Strategies with enough trades:",
    len(results_df)
)

print()

print(
    "Saved:"
)

print(
    RESULT_FILE
)

print()

print("=" * 70)

print("TOP STRATEGIES")

print("=" * 70)

print()


columns = [

    "direction",

    "session",

    "conditions",

    "trades",

    "win_rate",

    "profit_factor",

    "net_r",

    "expectancy_r",

    "max_drawdown_r"

]


print(

    results_df[
        columns
    ]
    .head(20)
    .to_string(
        index=False
    )

)


print()

print("=" * 70)

print("SEARCH FINISHED")

print("=" * 70)