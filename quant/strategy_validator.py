import os
import pandas as pd

from quant.backtester import backtest_strategy


FEATURE_FILE = "quant/feature_database.csv"
STRATEGY_FILE = "quant/strategy_scores.csv"
RESULT_FILE = "quant/validated_strategies.csv"

MIN_ORIGINAL_TRADES = 100
TOP_CANDIDATES = 30

PERIODS = {
    "Development_2020_2024": (
        "2020-01-01",
        "2024-12-31 23:59:59"
    ),
    "Validation_2025": (
        "2025-01-01",
        "2025-12-31 23:59:59"
    ),
    "OOS_2026": (
        "2026-01-01",
        "2026-12-31 23:59:59"
    )
}


def load_data():

    print("=" * 70)
    print("QUANT STRATEGY VALIDATION")
    print("=" * 70)
    print()

    print("Loading feature database...")

    df = pd.read_csv(
        FEATURE_FILE
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    print(
        "Candles:",
        len(df)
    )

    print()

    return df


def load_candidates():

    print(
        "Loading strategy candidates..."
    )

    strategies = pd.read_csv(
        STRATEGY_FILE
    )

    print(
        "Strategies available:",
        len(strategies)
    )

    print()

    # Remove very small samples.

    strategies = strategies[
        strategies["trades"]
        >= MIN_ORIGINAL_TRADES
    ].copy()

    # Prefer strategies with useful
    # historical profit factor.

    strategies = strategies[
        strategies["profit_factor"]
        >= 1.10
    ].copy()

    # Sort by the original score.

    strategies = strategies.sort_values(
        "strategy_score",
        ascending=False
    )

    strategies = strategies.head(
        TOP_CANDIDATES
    ).copy()

    print(
        "Candidates selected:",
        len(strategies)
    )

    print()

    return strategies


def parse_conditions(condition_text):

    conditions = {}

    parts = [
        x.strip()
        for x in str(
            condition_text
        ).split("+")
    ]

    for feature in parts:

        if feature:

            conditions[
                feature
            ] = True

    return conditions


def run_period(
    df,
    strategy,
    start_date,
    end_date
):

    start = pd.Timestamp(
        start_date,
        tz="UTC"
    )

    end = pd.Timestamp(
        end_date,
        tz="UTC"
    )

    period_df = df[
        (df["timestamp"] >= start)
        &
        (df["timestamp"] <= end)
    ].copy()

    if len(period_df) < 100:

        return None

    conditions = parse_conditions(
        strategy["conditions"]
    )

    direction = str(
        strategy["direction"]
    ).upper()

    session = strategy["session"]

    if pd.isna(session):

        session = None

    elif str(session).strip().lower() == "all":

        session = None

    else:

        session = str(
            session
        ).strip()

    try:

        result = backtest_strategy(
            df=period_df,
            conditions=conditions,
            direction=direction,
            risk_reward=2.0,
            stop_mode="atr",
            stop_multiplier=1.0,
            max_bars=48,
            session=session
        )

    except Exception as e:

        print()
        print(
            "BACKTEST ERROR:"
        )
        print(e)

        return None

    return result


def get_stat(
    result,
    key
):

    if not result:

        return 0.0

    stats = result.get(
        "stats",
        {}
    )

    return stats.get(
        key,
        0.0
    )


def main():

    df = load_data()

    candidates = load_candidates()

    if candidates.empty:

        print(
            "No suitable candidates found."
        )

        return

    results = []

    total = len(
        candidates
    )

    print(
        "=" * 70
    )

    print(
        "TESTING CANDIDATE STRATEGIES"
    )

    print(
        "=" * 70
    )

    print()

    for index, (_, strategy) in enumerate(
        candidates.iterrows(),
        start=1
    ):

        print(
            f"Strategy {index} / {total}"
        )

        print(
            strategy["direction"],
            "|",
            strategy["session"],
            "|",
            strategy["conditions"]
        )

        row = {

            "original_rank":
                index,

            "direction":
                strategy["direction"],

            "session":
                strategy["session"],

            "conditions":
                strategy["conditions"],

            "condition_count":
                strategy["condition_count"],

            "original_trades":
                strategy["trades"],

            "original_win_rate":
                strategy["win_rate"],

            "original_profit_factor":
                strategy["profit_factor"],

            "original_net_r":
                strategy["net_r"],

            "original_expectancy_r":
                strategy["expectancy_r"],

            "original_drawdown_r":
                strategy["max_drawdown_r"]

        }

        for period_name, (
            start_date,
            end_date
        ) in PERIODS.items():

            print(
                " ",
                period_name,
                "..."
            )

            result = run_period(
                df=df,
                strategy=strategy,
                start_date=start_date,
                end_date=end_date
            )

            prefix = period_name

            if result is None:

                row[
                    f"{prefix}_trades"
                ] = 0

                row[
                    f"{prefix}_win_rate"
                ] = 0.0

                row[
                    f"{prefix}_profit_factor"
                ] = 0.0

                row[
                    f"{prefix}_net_r"
                ] = 0.0

                row[
                    f"{prefix}_expectancy_r"
                ] = 0.0

                row[
                    f"{prefix}_drawdown_r"
                ] = 0.0

            else:

                row[
                    f"{prefix}_trades"
                ] = get_stat(
                    result,
                    "trades"
                )

                row[
                    f"{prefix}_win_rate"
                ] = get_stat(
                    result,
                    "win_rate"
                )

                row[
                    f"{prefix}_profit_factor"
                ] = get_stat(
                    result,
                    "profit_factor"
                )

                row[
                    f"{prefix}_net_r"
                ] = get_stat(
                    result,
                    "net_r"
                )

                row[
                    f"{prefix}_expectancy_r"
                ] = get_stat(
                    result,
                    "expectancy_r"
                )

                row[
                    f"{prefix}_drawdown_r"
                ] = get_stat(
                    result,
                    "max_drawdown_r"
                )

        results.append(
            row
        )

        print()

    results_df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # ROBUSTNESS SCORE
    # --------------------------------------------------------

    def validation_score(row):

        validation_pf = row[
            "Validation_2025_profit_factor"
        ]

        oos_pf = row[
            "OOS_2026_profit_factor"
        ]

        validation_exp = row[
            "Validation_2025_expectancy_r"
        ]

        oos_exp = row[
            "OOS_2026_expectancy_r"
        ]

        validation_trades = row[
            "Validation_2025_trades"
        ]

        oos_trades = row[
            "OOS_2026_trades"
        ]

        validation_dd = row[
            "Validation_2025_drawdown_r"
        ]

        oos_dd = row[
            "OOS_2026_drawdown_r"
        ]

        score = 0.0

        # Validation PF

        score += min(
            max(
                validation_pf,
                0
            ),
            3
        ) * 2

        # OOS PF

        score += min(
            max(
                oos_pf,
                0
            ),
            3
        ) * 3

        # Validation expectancy

        score += (
            validation_exp
            * 10
        )

        # OOS expectancy receives
        # heavier weighting.

        score += (
            oos_exp
            * 15
        )

        # Evidence.

        score += min(
            validation_trades / 50,
            2
        )

        score += min(
            oos_trades / 50,
            3
        )

        # Penalise drawdown.

        score -= (
            max(
                validation_dd,
                0
            )
            * 0.10
        )

        score -= (
            max(
                oos_dd,
                0
            )
            * 0.15
        )

        return score

    results_df[
        "validation_score"
    ] = results_df.apply(
        validation_score,
        axis=1
    )

    # --------------------------------------------------------
    # PASS / FAIL
    # --------------------------------------------------------

    def determine_status(row):

        validation_trades = row[
            "Validation_2025_trades"
        ]

        oos_trades = row[
            "OOS_2026_trades"
        ]

        validation_pf = row[
            "Validation_2025_profit_factor"
        ]

        oos_pf = row[
            "OOS_2026_profit_factor"
        ]

        validation_exp = row[
            "Validation_2025_expectancy_r"
        ]

        oos_exp = row[
            "OOS_2026_expectancy_r"
        ]

        if (
            validation_trades >= 30
            and
            oos_trades >= 20
            and
            validation_pf >= 1.10
            and
            oos_pf >= 1.10
            and
            validation_exp > 0
            and
            oos_exp > 0
        ):

            return "PASS"

        if (
            oos_trades >= 10
            and
            oos_pf >= 1.00
            and
            oos_exp >= 0
        ):

            return "WATCH"

        return "FAIL"

    results_df[
        "status"
    ] = results_df.apply(
        determine_status,
        axis=1
    )

    results_df = results_df.sort_values(
        "validation_score",
        ascending=False
    )

    results_df.to_csv(
        RESULT_FILE,
        index=False
    )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print()

    print(
        "=" * 70
    )

    print(
        "VALIDATION COMPLETE"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Saved:"
    )

    print(
        RESULT_FILE
    )

    print()

    display_columns = [

        "status",

        "direction",

        "session",

        "conditions",

        "Validation_2025_trades",

        "Validation_2025_win_rate",

        "Validation_2025_profit_factor",

        "Validation_2025_expectancy_r",

        "OOS_2026_trades",

        "OOS_2026_win_rate",

        "OOS_2026_profit_factor",

        "OOS_2026_expectancy_r",

        "validation_score"

    ]

    print(
        results_df[
            display_columns
        ]
        .head(30)
        .to_string(
            index=False
        )
    )

    print()

    print(
        "=" * 70
    )

    print(
        "STATUS COUNTS"
    )

    print(
        "=" * 70
    )

    print(
        results_df[
            "status"
        ].value_counts()
    )

    print()


if __name__ == "__main__":

    main()