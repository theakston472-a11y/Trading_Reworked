import itertools


# ============================================================
# QUANT STRATEGY GENERATOR
# ============================================================
#
# Creates sensible BUY and SELL strategy combinations.
#
# This file DOES NOT:
# - place trades
# - connect to MT5
# - send emails
#
# It only creates candidate strategies for the backtester.
# ============================================================


# ============================================================
# FEATURE GROUPS
# ============================================================

BUY_GROUPS = {

    "trend": [

        "ema_bullish_alignment"

    ],

    "structure": [

        "bullish_bos",

        "bullish_choch"

    ],

    "liquidity": [

        "liquidity_sweep_low",

        "previous_day_low_sweep"

    ],

    "price_action": [

        "bullish_engulfing",

        "bullish_pin_bar",

        "strong_bullish_candle"

    ],

    "fvg": [

        "bullish_fvg"

    ],

    "fibonacci": [

        "near_fib_382",

        "near_fib_500",

        "near_fib_618"

    ]

}


SELL_GROUPS = {

    "trend": [

        "ema_bearish_alignment"

    ],

    "structure": [

        "bearish_bos",

        "bearish_choch"

    ],

    "liquidity": [

        "liquidity_sweep_high",

        "previous_day_high_sweep"

    ],

    "price_action": [

        "bearish_engulfing",

        "bearish_pin_bar",

        "strong_bearish_candle"

    ],

    "fvg": [

        "bearish_fvg"

    ],

    "fibonacci": [

        "near_fib_382",

        "near_fib_500",

        "near_fib_618"

    ]

}


# ============================================================
# SESSION OPTIONS
# ============================================================

SESSIONS = [

    "All",

    "Asia",

    "London",

    "New York"

]


# ============================================================
# GENERATE COMBINATIONS
# ============================================================

def generate_strategies(
    groups,
    direction,
    min_conditions=1,
    max_conditions=4
):

    strategies = []


    group_names = list(
        groups.keys()
    )


    # --------------------------------------------------------
    # Number of feature groups used
    # --------------------------------------------------------

    for group_count in range(

        min_conditions,

        min(
            max_conditions,
            len(group_names)
        ) + 1

    ):


        # ----------------------------------------------------
        # Select different feature groups
        # ----------------------------------------------------

        selected_groups = itertools.combinations(

            group_names,

            group_count

        )


        for group_selection in selected_groups:


            # ------------------------------------------------
            # Select one feature from each group
            # ------------------------------------------------

            feature_choices = [

                groups[group]

                for group in group_selection

            ]


            for selected_features in itertools.product(

                *feature_choices

            ):


                strategy = {

                    "direction": direction,

                    "features": list(
                        selected_features
                    ),

                    "groups": list(
                        group_selection
                    )

                }


                strategies.append(
                    strategy
                )


    return strategies


# ============================================================
# GENERATE ALL STRATEGIES
# ============================================================

def generate_all_strategies():

    strategies = []


    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    buy_strategies = generate_strategies(

        BUY_GROUPS,

        "BUY"

    )


    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    sell_strategies = generate_strategies(

        SELL_GROUPS,

        "SELL"

    )


    strategies.extend(
        buy_strategies
    )

    strategies.extend(
        sell_strategies
    )


    return strategies


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(
    strategies
):

    print()

    print("=" * 60)

    print(
        "STRATEGY GENERATOR"
    )

    print("=" * 60)

    print()

    print(
        "Total strategies:",
        len(strategies)
    )

    print()


    buy_count = sum(

        1

        for strategy in strategies

        if strategy["direction"] == "BUY"

    )


    sell_count = sum(

        1

        for strategy in strategies

        if strategy["direction"] == "SELL"

    )


    print(
        "BUY strategies:",
        buy_count
    )

    print(
        "SELL strategies:",
        sell_count
    )

    print()


    print(
        "Example strategies:"
    )

    print()


    for strategy in strategies[:20]:

        print(

            strategy["direction"],

            " | ",

            " + ".join(
                strategy["features"]
            )

        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    strategies = generate_all_strategies()

    print_summary(
        strategies
    )