from pathlib import Path
import ast
import pandas as pd
import numpy as np


BASE = Path(__file__).resolve().parent

FEATURE_FILE = BASE / "feature_database.csv"
WF_FILE = BASE / "walk_forward_summary.csv"
OUTPUT_FILE = BASE / "final_test_results.csv"

TEST_START = pd.Timestamp("2026-07-01", tz="UTC")
TEST_END = pd.Timestamp("2026-08-08", tz="UTC")

MIN_TRADES = 10


def parse_conditions(value):

    if isinstance(value, list):
        return [str(x).strip() for x in value]

    if pd.isna(value):
        return []

    text = str(value).strip()

    if text.startswith("[") and text.endswith("]"):
        try:
            result = ast.literal_eval(text)

            if isinstance(result, list):
                return [
                    str(x).strip()
                    for x in result
                ]

        except Exception:
            pass

    return [
        x.strip()
        for x in text.replace("\n", " ").split("+")
        if x.strip()
    ]


def calculate_results(trades):

    if not trades:
        return None

    arr = np.asarray(
        trades,
        dtype=float
    )

    arr = arr[np.isfinite(arr)]

    if len(arr) == 0:
        return None

    wins = arr[arr > 0]
    losses = arr[arr < 0]

    total = len(arr)

    win_rate = (
        len(wins)
        / total
        * 100
    )

    gross_profit = (
        wins.sum()
        if len(wins)
        else 0.0
    )

    gross_loss = (
        abs(losses.sum())
        if len(losses)
        else 0.0
    )

    if gross_loss == 0:

        profit_factor = (
            np.inf
            if gross_profit > 0
            else 0.0
        )

    else:

        profit_factor = (
            gross_profit
            / gross_loss
        )

    net_r = arr.sum()

    expectancy = arr.mean()

    equity = np.cumsum(arr)

    peaks = np.maximum.accumulate(
        np.concatenate(
            ([0.0], equity)
        )
    )

    dd = peaks[1:] - equity

    max_dd = (
        float(dd.max())
        if len(dd)
        else 0.0
    )

    return {
        "trades": total,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "net_r": net_r,
        "expectancy_r": expectancy,
        "max_drawdown_r": max_dd,
    }


def simulate_strategy(
    df,
    direction,
    session,
    conditions,
):

    work = df.copy()

    if session != "All":

        work = work[
            work["session"].astype(str)
            == str(session)
        ]

    if work.empty:
        return None

    missing = [
        c
        for c in conditions
        if c not in work.columns
    ]

    if missing:

        raise RuntimeError(
            "Missing strategy columns: "
            + str(missing)
        )

    mask = pd.Series(
        True,
        index=work.index
    )

    for condition in conditions:

        values = work[condition]

        if values.dtype == bool:

            mask &= values.fillna(False)

        else:

            mask &= (
                values
                .fillna(0)
                .astype(float)
                .ne(0)
            )

    signals = work.loc[mask]

    if signals.empty:
        return None

    # ---------------------------------------------------------
    # Convert condition list to the dictionary expected
    # by quant.backtester.backtest_strategy()
    # ---------------------------------------------------------

    condition_dict = {
        condition: True
        for condition in conditions
    }

    from quant.backtester import backtest_strategy

    result = backtest_strategy(
        work,
        conditions=condition_dict,
        direction=direction,
        risk_reward=2.0,
        stop_mode="atr",
        stop_multiplier=1.0,
        max_bars=48,
        session=session,
    )

    if not isinstance(result, dict):

        raise RuntimeError(
            "backtest_strategy() did not return "
            "the expected dictionary."
        )

    trades_df = result.get("trades")

    if not isinstance(
        trades_df,
        pd.DataFrame
    ):

        raise RuntimeError(
            "backtest_strategy() returned no "
            "trades DataFrame."
        )

    if trades_df.empty:
        return None

    r_column = None

    for column in [
        "r",
        "R",
        "return_r",
        "pnl_r",
    ]:

        if column in trades_df.columns:

            r_column = column
            break

    if r_column is None:

        raise RuntimeError(
            "Backtester trade DataFrame contains "
            "no R-result column.\n"
            f"Columns found: "
            f"{list(trades_df.columns)}"
        )

    r_values = (
        pd.to_numeric(
            trades_df[r_column],
            errors="coerce"
        )
        .dropna()
        .tolist()
    )

    return calculate_results(
        r_values
    )


def main():

    print()
    print(
        "# FINAL OUT-OF-SAMPLE TEST"
    )
    print()

    print(
        "Loading feature database..."
    )

    df = pd.read_csv(
        FEATURE_FILE
    )

    if "timestamp" not in df.columns:

        raise RuntimeError(
            "timestamp column not found."
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    df = (
        df
        .dropna(subset=["timestamp"])
        .copy()
    )

    df = (
        df
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    print(
        f"Candles loaded: {len(df)}"
    )

    print(
        f"Timestamp range: "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    test = df[
        (df["timestamp"] >= TEST_START)
        & (df["timestamp"] < TEST_END)
    ].copy()

    print()

    print(
        f"FINAL TEST PERIOD: "
        f"{TEST_START} -> {TEST_END}"
    )

    print(
        f"Test candles: {len(test)}"
    )

    print()

    if test.empty:

        raise RuntimeError(
            "No candles found in final "
            "test period."
        )

    print(
        "Loading walk-forward strategies..."
    )

    wf = pd.read_csv(
        WF_FILE
    )

    print(
        f"Walk-forward rows loaded: "
        f"{len(wf)}"
    )

    required = [
        "direction",
        "session",
        "conditions",
    ]

    missing = [
        c
        for c in required
        if c not in wf.columns
    ]

    if missing:

        raise RuntimeError(
            "Missing required columns "
            f"in walk-forward summary: "
            f"{missing}"
        )

    if "robustness_score" in wf.columns:

        wf = wf.sort_values(
            "robustness_score",
            ascending=False,
        )

    candidates = []

    seen = set()

    for _, row in wf.iterrows():

        direction = (
            str(row["direction"])
            .strip()
        )

        session = (
            str(row["session"])
            .strip()
        )

        conditions = parse_conditions(
            row["conditions"]
        )

        if direction not in {
            "BUY",
            "SELL",
        }:
            continue

        if not conditions:
            continue

        key = (
            direction,
            session,
            tuple(sorted(conditions)),
        )

        if key in seen:
            continue

        seen.add(key)

        candidates.append(
            {
                "direction": direction,
                "session": session,
                "conditions": conditions,
                "source_rank": row.get(
                    "strategy_rank",
                    len(candidates) + 1,
                ),
                "robustness_score": row.get(
                    "robustness_score",
                    np.nan,
                ),
            }
        )

    print(
        f"Unique walk-forward candidates: "
        f"{len(candidates)}"
    )

    print()

    results = []

    for i, candidate in enumerate(
        candidates,
        start=1,
    ):

        direction = candidate[
            "direction"
        ]

        session = candidate[
            "session"
        ]

        conditions = candidate[
            "conditions"
        ]

        result = simulate_strategy(
            test,
            direction,
            session,
            conditions,
        )

        if result is None:
            continue

        if result["trades"] < MIN_TRADES:
            continue

        results.append(
            {
                "source_rank":
                    candidate[
                        "source_rank"
                    ],

                "direction":
                    direction,

                "session":
                    session,

                "conditions":
                    " + ".join(
                        conditions
                    ),

                "condition_count":
                    len(conditions),

                "robustness_score":
                    candidate[
                        "robustness_score"
                    ],

                **result,
            }
        )

        if (
            i % 10 == 0
            or i == len(candidates)
        ):

            print(
                f"Progress: "
                f"{i} / "
                f"{len(candidates)} | "
                f"Valid final tests: "
                f"{len(results)}"
            )

    if not results:

        print()

        print(
            "No strategies produced "
            "enough final-test trades."
        )

        return

    out = pd.DataFrame(
        results
    )

    out["final_score"] = (
        out["expectancy_r"] * 10
        + np.log1p(
            out["trades"]
        ) * 0.5
        - out["max_drawdown_r"] * 0.15
    )

    out = (
        out
        .sort_values(
            [
                "final_score",
                "profit_factor",
                "expectancy_r",
            ],
            ascending=False,
        )
        .reset_index(drop=True)
    )

    out.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()

    print(
        "=" * 80
    )

    print(
        "FINAL OUT-OF-SAMPLE RESULTS"
    )

    print(
        "=" * 80
    )

    print()

    display_columns = [
        "direction",
        "session",
        "conditions",
        "trades",
        "win_rate",
        "profit_factor",
        "net_r",
        "expectancy_r",
        "max_drawdown_r",
        "final_score",
    ]

    print(
        out[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )

    print()

    print(
        "Results saved to:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    print(
        "TOP 10 FINAL CANDIDATES"
    )

    print(
        "-" * 80
    )

    for n, (_, row) in enumerate(
        out.head(10).iterrows(),
        start=1,
    ):

        print()

        print(
            f"#{n} | "
            f"{row['direction']} | "
            f"{row['session']} | "
            f"Trades: "
            f"{int(row['trades'])} | "
            f"PF: "
            f"{row['profit_factor']:.3f} | "
            f"Exp: "
            f"{row['expectancy_r']:.4f} | "
            f"Net R: "
            f"{row['net_r']:.2f} | "
            f"DD: "
            f"{row['max_drawdown_r']:.2f}"
        )

        print(
            row["conditions"]
        )

    print()

    print(
        "FINAL TEST COMPLETE."
    )


if __name__ == "__main__":
    main()