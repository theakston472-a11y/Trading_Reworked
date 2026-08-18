"""
FULL-HISTORY PORTFOLIO TESTER

Purpose
-------
Take the selected strategies from:

    results/strategy_lab_top_final.csv

and test them across the ENTIRE available dataset.

This is a separate validation stage from strategy_lab.py.

It:

1. Loads the selected Top-100 strategies.
2. Uses the selected RR for each strategy.
3. Tests every strategy across the complete data history.
4. Produces individual strategy results.
5. Produces yearly results.
6. Builds a combined portfolio trade stream.
7. Tracks overlapping signals.
8. Tracks maximum simultaneous positions.
9. Calculates portfolio R, drawdown, win rate and profit factor.
10. Ranks strategies by contribution to the combined portfolio.
11. Produces CSV files for further analysis.

No machine-specific paths are hard-coded.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Full-history Top-100 strategy portfolio tester"
    )

    parser.add_argument(
        "--data",
        default=None,
        help="Feature database CSV"
    )

    parser.add_argument(
        "--strategies",
        default=None,
        help="Top strategy CSV"
    )

    parser.add_argument(
        "--out",
        default=None,
        help="Output directory"
    )

    parser.add_argument(
        "--start",
        default=None,
        help="Start date. Default: first candle in data"
    )

    parser.add_argument(
        "--end",
        default=None,
        help="End date. Default: last candle in data"
    )

    parser.add_argument(
        "--max-open-trades",
        type=int,
        default=5,
        help="Maximum simultaneous portfolio positions"
    )

    parser.add_argument(
        "--max-bars",
        type=int,
        default=48,
        help="Maximum bars a trade can remain open"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reserved for future cache behaviour"
    )

    return parser.parse_args()


# ============================================================
# PATHS
# ============================================================

def set_defaults(args):
    base = Path(__file__).resolve().parents[1]

    if args.data is None:
        args.data = str(
            base / "quant" / "feature_database.csv"
        )

    if args.strategies is None:
        args.strategies = str(
            base / "results" / "strategy_lab_top_final.csv"
        )

    if args.out is None:
        args.out = str(
            base / "results" / "portfolio_test"
        )

    Path(args.out).mkdir(
        parents=True,
        exist_ok=True
    )

    return args


# ============================================================
# LOAD DATA
# ============================================================

def load_data(path):
    print()
    print("=" * 70)
    print("LOADING MARKET DATA")
    print("=" * 70)

    df = pd.read_csv(path)

    if "timestamp" not in df.columns:
        raise ValueError(
            "Data file does not contain a 'timestamp' column."
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce"
    )

    df = (
        df
        .dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    required = [
        "open",
        "high",
        "low",
        "close",
        "atr14",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            "Data file is missing required columns: "
            + ", ".join(missing)
        )

    for column in required:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Data: {df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    return df


# ============================================================
# LOAD STRATEGIES
# ============================================================

def load_strategies(path):
    print()
    print("=" * 70)
    print("LOADING SELECTED STRATEGIES")
    print("=" * 70)

    strategies = pd.read_csv(path)

    required = [
        "direction",
        "session",
        "conditions",
        "rr",
    ]

    missing = [
        c for c in required
        if c not in strategies.columns
    ]

    if missing:
        raise ValueError(
            "Strategy file is missing required columns: "
            + ", ".join(missing)
        )

    strategies["direction"] = (
        strategies["direction"]
        .astype(str)
        .str.upper()
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

    strategies["rr"] = pd.to_numeric(
        strategies["rr"],
        errors="coerce"
    )

    strategies = strategies.dropna(
        subset=["rr"]
    ).copy()

    # Remove accidental duplicates.
    strategies = (
        strategies
        .drop_duplicates(
            [
                "direction",
                "session",
                "conditions",
            ]
        )
        .reset_index(drop=True)
    )

    strategies.insert(
        0,
        "strategy_id",
        range(1, len(strategies) + 1)
    )

    print(
        f"Strategies loaded: {len(strategies)}"
    )

    return strategies


# ============================================================
# DATE RANGE
# ============================================================

def apply_date_range(df, start, end):
    start_ts = (
        pd.Timestamp(start, tz="UTC")
        if start
        else df["timestamp"].min()
    )

    end_ts = (
        pd.Timestamp(end, tz="UTC")
        if end
        else df["timestamp"].max()
    )

    if start_ts > end_ts:
        raise ValueError(
            "Start date is after end date."
        )

    result = df[
        (df["timestamp"] >= start_ts)
        &
        (df["timestamp"] <= end_ts)
    ].copy()

    result = (
        result
        .reset_index(drop=True)
    )

    print()
    print("=" * 70)
    print("FULL HISTORY TEST PERIOD")
    print("=" * 70)

    print(
        f"Start: {result['timestamp'].min()}"
    )

    print(
        f"End:   {result['timestamp'].max()}"
    )

    print(
        f"Rows:  {len(result):,}"
    )

    return result


# ============================================================
# SIGNAL FINDER
# ============================================================

def get_signal_indices(
    df,
    direction,
    session,
    conditions
):
    work = df

    session_value = str(
        session
    ).strip().lower()

    if session_value not in (
        "",
        "all",
        "nan",
        "none",
    ):
        if "session" not in work.columns:
            return np.array(
                [],
                dtype=np.int64
            )

        work = work[
            work["session"]
            .astype(str)
            .str.lower()
            == session_value
        ]

    if work.empty:
        return np.array(
            [],
            dtype=np.int64
        )

    mask = np.ones(
        len(work),
        dtype=bool
    )

    condition_list = [
        x.strip()
        for x in str(conditions).split("+")
        if x.strip()
    ]

    for condition in condition_list:

        if condition not in work.columns:
            return np.array(
                [],
                dtype=np.int64
            )

        values = work[condition]

        if values.dtype != bool:
            values = (
                values
                .fillna(False)
                .astype(bool)
            )

        mask &= values.to_numpy()

    return work.index.to_numpy()[mask]


# ============================================================
# INDIVIDUAL STRATEGY BACKTEST
# ============================================================

def backtest_strategy(
    df,
    signal_indices,
    direction,
    rr,
    max_bars
):
    if len(signal_indices) == 0:
        return []

    opens = df["open"].to_numpy(float)
    highs = df["high"].to_numpy(float)
    lows = df["low"].to_numpy(float)
    closes = df["close"].to_numpy(float)
    atrs = df["atr14"].to_numpy(float)

    trades = []

    direction = str(
        direction
    ).upper()

    for signal_i in signal_indices:

        signal_i = int(signal_i)

        entry_i = signal_i + 1

        if entry_i >= len(df):
            continue

        entry = opens[entry_i]

        atr_value = atrs[signal_i]

        candle_range = abs(
            highs[signal_i]
            -
            lows[signal_i]
        )

        distance = max(
            atr_value
            if np.isfinite(atr_value)
            else 0.0,
            candle_range
        )

        if (
            not np.isfinite(entry)
            or not np.isfinite(distance)
            or distance <= 0
        ):
            continue

        if direction == "SELL":

            sl = (
                entry
                +
                distance
            )

            tp = (
                entry
                -
                distance * rr
            )

        else:

            sl = (
                entry
                -
                distance
            )

            tp = (
                entry
                +
                distance * rr
            )

        final_i = min(
            len(df) - 1,
            entry_i + max_bars - 1
        )

        outcome = None
        exit_i = final_i
        reason = "TIME"

        for j in range(
            entry_i,
            final_i + 1
        ):

            if direction == "SELL":

                stop_hit = (
                    highs[j] >= sl
                )

                target_hit = (
                    lows[j] <= tp
                )

            else:

                stop_hit = (
                    lows[j] <= sl
                )

                target_hit = (
                    highs[j] >= tp
                )

            # Conservative assumption:
            # if SL and TP happen on the
            # same candle, count SL first.

            if stop_hit:

                outcome = -1.0
                exit_i = j
                reason = "SL"
                break

            if target_hit:

                outcome = float(rr)
                exit_i = j
                reason = "TP"
                break

        if outcome is None:

            if direction == "SELL":

                move = (
                    entry
                    -
                    closes[exit_i]
                )

            else:

                move = (
                    closes[exit_i]
                    -
                    entry
                )

            outcome = float(
                move / distance
            )

        trades.append(
            {
                "signal_i": signal_i,
                "entry_i": entry_i,
                "exit_i": int(exit_i),
                "entry": float(entry),
                "sl": float(sl),
                "tp": float(tp),
                "outcome_r": float(outcome),
                "reason": reason,
                "entry_time": df.iloc[
                    entry_i
                ]["timestamp"],
                "exit_time": df.iloc[
                    exit_i
                ]["timestamp"],
            }
        )

    return trades


# ============================================================
# TRADE STATISTICS
# ============================================================

def calculate_stats(trades):
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_r": 0.0,
            "expectancy_r": 0.0,
            "max_drawdown_r": 0.0,
            "avg_trades_day": 0.0,
            "avg_hold_bars": 0.0,
        }

    values = np.asarray(
        [
            t["outcome_r"]
            for t in trades
        ],
        dtype=float
    )

    wins = values[
        values > 0
    ]

    losses = values[
        values < 0
    ]

    gross_profit = (
        float(wins.sum())
        if len(wins)
        else 0.0
    )

    gross_loss = (
        abs(float(losses.sum()))
        if len(losses)
        else 0.0
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            /
            gross_loss
        )

    elif gross_profit > 0:

        profit_factor = 999.0

    else:

        profit_factor = 0.0

    equity = np.cumsum(
        values
    )

    running_max = np.maximum.accumulate(
        np.r_[0.0, equity]
    )[1:]

    drawdown = (
        running_max
        -
        equity
    )

    max_drawdown = (
        float(drawdown.max())
        if len(drawdown)
        else 0.0
    )

    first_time = min(
        t["entry_time"]
        for t in trades
    )

    last_time = max(
        t["exit_time"]
        for t in trades
    )

    days = max(
        (
            last_time
            -
            first_time
        ).total_seconds()
        /
        86400.0,
        1.0
    )

    avg_hold = np.mean(
        [
            t["exit_i"]
            -
            t["entry_i"]
            +
            1
            for t in trades
        ]
    )

    return {
        "trades": int(len(values)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": float(
            len(wins)
            /
            len(values)
            *
            100.0
        ),
        "profit_factor": float(
            profit_factor
        ),
        "net_r": float(
            values.sum()
        ),
        "expectancy_r": float(
            values.mean()
        ),
        "max_drawdown_r": max_drawdown,
        "avg_trades_day": float(
            len(values)
            /
            days
        ),
        "avg_hold_bars": float(
            avg_hold
        ),
    }


# ============================================================
# YEARLY STATISTICS
# ============================================================

def yearly_stats(
    trades,
    strategy_id
):
    if not trades:
        return []

    rows = []

    by_year = {}

    for trade in trades:

        year = pd.Timestamp(
            trade["entry_time"]
        ).year

        by_year.setdefault(
            year,
            []
        ).append(trade)

    for year, year_trades in sorted(
        by_year.items()
    ):

        stats = calculate_stats(
            year_trades
        )

        rows.append(
            {
                "strategy_id": strategy_id,
                "year": int(year),
                **stats,
            }
        )

    return rows


# ============================================================
# PORTFOLIO TRADE COMBINATION
# ============================================================

def build_portfolio(
    all_strategy_trades,
    max_open_trades
):
    """
    Combine every strategy's trades into one
    chronological portfolio.

    The portfolio uses one R unit per position.

    When the maximum number of open trades is
    reached, later signals are skipped.

    Trades are processed chronologically by
    entry time.

    If multiple trades enter at exactly the
    same time, strategy ID breaks the tie.
    """

    candidates = []

    for strategy_id, trades in (
        all_strategy_trades.items()
    ):

        for trade in trades:

            candidates.append(
                {
                    **trade,
                    "strategy_id": strategy_id,
                }
            )

    if not candidates:
        return [], []

    candidates.sort(
        key=lambda x: (
            x["entry_time"],
            x["strategy_id"],
        )
    )

    active = []

    accepted = []
    rejected = []

    max_concurrent = 0

    for trade in candidates:

        entry_time = trade[
            "entry_time"
        ]

        # Remove trades that have
        # already exited before this
        # new trade enters.

        active = [
            x for x in active
            if x["exit_time"] > entry_time
        ]

        if len(active) >= max_open_trades:

            rejected.append(
                {
                    "strategy_id":
                        trade["strategy_id"],
                    "entry_time":
                        trade["entry_time"],
                    "exit_time":
                        trade["exit_time"],
                    "outcome_r":
                        trade["outcome_r"],
                    "reason":
                        "MAX_OPEN_TRADES",
                }
            )

            continue

        accepted.append(
            trade
        )

        active.append(
            trade
        )

        max_concurrent = max(
            max_concurrent,
            len(active)
        )

    return accepted, rejected


# ============================================================
# PORTFOLIO EQUITY / DRAWDOWN
# ============================================================

def portfolio_equity(
    trades
):
    if not trades:
        return pd.DataFrame()

    rows = []

    running_r = 0.0
    peak_r = 0.0

    for number, trade in enumerate(
        sorted(
            trades,
            key=lambda x: (
                x["exit_time"],
                x["strategy_id"],
            )
        ),
        start=1
    ):

        running_r += (
            trade["outcome_r"]
        )

        peak_r = max(
            peak_r,
            running_r
        )

        drawdown = (
            peak_r
            -
            running_r
        )

        rows.append(
            {
                "trade_number": number,
                "strategy_id":
                    trade["strategy_id"],
                "entry_time":
                    trade["entry_time"],
                "exit_time":
                    trade["exit_time"],
                "outcome_r":
                    trade["outcome_r"],
                "cumulative_r":
                    running_r,
                "drawdown_r":
                    drawdown,
                "reason":
                    trade["reason"],
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# STRATEGY CONTRIBUTION
# ============================================================

def strategy_contribution(
    trades,
    rejected
):
    if not trades:
        return pd.DataFrame()

    rows = []

    accepted_df = pd.DataFrame(
        trades
    )

    rejected_df = (
        pd.DataFrame(rejected)
        if rejected
        else pd.DataFrame()
    )

    for strategy_id in sorted(
        set(
            accepted_df[
                "strategy_id"
            ].tolist()
        )
        |
        (
            set(
                rejected_df[
                    "strategy_id"
                ].tolist()
            )
            if not rejected_df.empty
            else set()
        )
    ):

        accepted = accepted_df[
            accepted_df[
                "strategy_id"
            ] == strategy_id
        ]

        if not rejected_df.empty:

            skipped = rejected_df[
                rejected_df[
                    "strategy_id"
                ] == strategy_id
            ]

            skipped_count = len(
                skipped
            )

        else:

            skipped_count = 0

        stats = calculate_stats(
            accepted.to_dict(
                "records"
            )
        )

        rows.append(
            {
                "strategy_id":
                    strategy_id,
                "accepted_trades":
                    stats["trades"],
                "skipped_trades":
                    skipped_count,
                "total_signals":
                    stats["trades"]
                    +
                    skipped_count,
                "net_r":
                    stats["net_r"],
                "profit_factor":
                    stats["profit_factor"],
                "win_rate":
                    stats["win_rate"],
                "expectancy_r":
                    stats["expectancy_r"],
                "max_drawdown_r":
                    stats["max_drawdown_r"],
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# OVERLAP ANALYSIS
# ============================================================

def calculate_overlap(
    all_strategy_trades
):
    """
    Determine how often strategies generate
    trades that overlap in time.

    This helps identify redundant strategies.
    """

    ids = sorted(
        all_strategy_trades.keys()
    )

    rows = []

    for i, strategy_a in enumerate(
        ids
    ):

        trades_a = all_strategy_trades[
            strategy_a
        ]

        for strategy_b in ids[
            i + 1:
        ]:

            trades_b = all_strategy_trades[
                strategy_b
            ]

            overlaps = 0

            for a in trades_a:

                for b in trades_b:

                    if (
                        a["entry_time"]
                        <
                        b["exit_time"]
                        and
                        b["entry_time"]
                        <
                        a["exit_time"]
                    ):

                        overlaps += 1

            if overlaps > 0:

                rows.append(
                    {
                        "strategy_a":
                            strategy_a,
                        "strategy_b":
                            strategy_b,
                        "overlapping_trades":
                            overlaps,
                    }
                )

    return pd.DataFrame(
        rows
    )


# ============================================================
# MAIN
# ============================================================

def main():

    args = set_defaults(
        parse_args()
    )

    print()
    print("=" * 70)
    print("FULL-HISTORY TOP-100 PORTFOLIO TEST")
    print("=" * 70)

    print()
    print(
        "This is a validation test."
    )

    print(
        "It does NOT change strategy_lab.py."
    )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    df = load_data(
        args.data
    )

    strategies = load_strategies(
        args.strategies
    )

    df = apply_date_range(
        df,
        args.start,
        args.end
    )

    # --------------------------------------------------------
    # STORAGE
    # --------------------------------------------------------

    all_strategy_trades = {}

    individual_rows = []

    yearly_rows = []

    # --------------------------------------------------------
    # TEST EVERY STRATEGY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("TESTING STRATEGIES ACROSS FULL HISTORY")
    print("=" * 70)

    for position, strategy in strategies.iterrows():

        strategy_id = int(
            strategy["strategy_id"]
        )

        direction = strategy[
            "direction"
        ]

        session = strategy[
            "session"
        ]

        conditions = strategy[
            "conditions"
        ]

        rr = float(
            strategy["rr"]
        )

        signals = get_signal_indices(
            df,
            direction,
            session,
            conditions
        )

        trades = backtest_strategy(
            df,
            signals,
            direction,
            rr,
            args.max_bars
        )

        all_strategy_trades[
            strategy_id
        ] = trades

        stats = calculate_stats(
            trades
        )

        individual_rows.append(
            {
                "strategy_id":
                    strategy_id,
                "direction":
                    direction,
                "session":
                    session,
                "conditions":
                    conditions,
                "rr":
                    rr,
                "signals":
                    len(signals),
                **stats,
            }
        )

        yearly_rows.extend(
            yearly_stats(
                trades,
                strategy_id
            )
        )

        if (
            (position + 1) % 10 == 0
            or
            position == len(strategies) - 1
        ):

            print(
                f"Processed "
                f"{position + 1}/"
                f"{len(strategies)} strategies"
            )

    individual = pd.DataFrame(
        individual_rows
    )

    yearly = pd.DataFrame(
        yearly_rows
    )

    # --------------------------------------------------------
    # SAVE INDIVIDUAL RESULTS
    # --------------------------------------------------------

    individual = individual.sort_values(
        [
            "net_r",
            "profit_factor",
            "expectancy_r",
        ],
        ascending=False
    ).reset_index(drop=True)

    individual.insert(
        0,
        "rank",
        range(
            1,
            len(individual) + 1
        )
    )

    individual_path = (
        Path(args.out)
        /
        "individual_results.csv"
    )

    individual.to_csv(
        individual_path,
        index=False
    )

    yearly_path = (
        Path(args.out)
        /
        "yearly_results.csv"
    )

    yearly.to_csv(
        yearly_path,
        index=False
    )

    # --------------------------------------------------------
    # COMBINED PORTFOLIO
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("BUILDING COMBINED PORTFOLIO")
    print("=" * 70)

    portfolio_trades, rejected_trades = (
        build_portfolio(
            all_strategy_trades,
            args.max_open_trades
        )
    )

    portfolio_stats = calculate_stats(
        portfolio_trades
    )

    equity = portfolio_equity(
        portfolio_trades
    )

    contribution = strategy_contribution(
        portfolio_trades,
        rejected_trades
    )

    # --------------------------------------------------------
    # PORTFOLIO YEARLY RESULTS
    # --------------------------------------------------------

    portfolio_yearly_rows = []

    if portfolio_trades:

        by_year = {}

        for trade in portfolio_trades:

            year = pd.Timestamp(
                trade["entry_time"]
            ).year

            by_year.setdefault(
                year,
                []
            ).append(trade)

        for year, trades in sorted(
            by_year.items()
        ):

            stats = calculate_stats(
                trades
            )

            portfolio_yearly_rows.append(
                {
                    "year": int(year),
                    **stats,
                }
            )

    portfolio_yearly = pd.DataFrame(
        portfolio_yearly_rows
    )

    # --------------------------------------------------------
    # OVERLAP
    # --------------------------------------------------------

    print()
    print(
        "Calculating strategy overlap..."
    )

    overlap = calculate_overlap(
        all_strategy_trades
    )

    # --------------------------------------------------------
    # SAVE PORTFOLIO FILES
    # --------------------------------------------------------

    portfolio_trades_path = (
        Path(args.out)
        /
        "portfolio_trades.csv"
    )

    if portfolio_trades:

        portfolio_trade_df = (
            pd.DataFrame(
                portfolio_trades
            )
        )

        portfolio_trade_df.to_csv(
            portfolio_trades_path,
            index=False
        )

    else:

        pd.DataFrame().to_csv(
            portfolio_trades_path,
            index=False
        )

    rejected_path = (
        Path(args.out)
        /
        "rejected_trades.csv"
    )

    if rejected_trades:

        pd.DataFrame(
            rejected_trades
        ).to_csv(
            rejected_path,
            index=False
        )

    else:

        pd.DataFrame().to_csv(
            rejected_path,
            index=False
        )

    equity_path = (
        Path(args.out)
        /
        "portfolio_equity.csv"
    )

    equity.to_csv(
        equity_path,
        index=False
    )

    contribution_path = (
        Path(args.out)
        /
        "strategy_contribution.csv"
    )

    contribution.to_csv(
        contribution_path,
        index=False
    )

    portfolio_yearly_path = (
        Path(args.out)
        /
        "portfolio_yearly.csv"
    )

    portfolio_yearly.to_csv(
        portfolio_yearly_path,
        index=False
    )

    overlap_path = (
        Path(args.out)
        /
        "strategy_overlap.csv"
    )

    overlap.to_csv(
        overlap_path,
        index=False
    )

    # --------------------------------------------------------
    # PORTFOLIO SUMMARY
    # --------------------------------------------------------

    summary = {
        "data_start":
            str(df["timestamp"].min()),
        "data_end":
            str(df["timestamp"].max()),
        "strategies_tested":
            int(len(strategies)),
        "portfolio_max_open_trades":
            int(args.max_open_trades),
        "max_bars":
            int(args.max_bars),
        "portfolio_trades":
            portfolio_stats["trades"],
        "portfolio_wins":
            portfolio_stats["wins"],
        "portfolio_losses":
            portfolio_stats["losses"],
        "portfolio_win_rate":
            portfolio_stats["win_rate"],
        "portfolio_profit_factor":
            portfolio_stats["profit_factor"],
        "portfolio_net_r":
            portfolio_stats["net_r"],
        "portfolio_expectancy_r":
            portfolio_stats["expectancy_r"],
        "portfolio_max_drawdown_r":
            portfolio_stats["max_drawdown_r"],
        "portfolio_avg_trades_day":
            portfolio_stats["avg_trades_day"],
        "portfolio_avg_hold_bars":
            portfolio_stats["avg_hold_bars"],
        "accepted_trades":
            len(portfolio_trades),
        "rejected_trades":
            len(rejected_trades),
    }

    summary_path = (
        Path(args.out)
        /
        "portfolio_summary.json"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            indent=4
        )

    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FULL-HISTORY PORTFOLIO RESULTS")
    print("=" * 70)

    print(
        f"Strategies tested: "
        f"{len(strategies)}"
    )

    print(
        f"History: "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    print(
        f"Portfolio trades: "
        f"{portfolio_stats['trades']}"
    )

    print(
        f"Wins: "
        f"{portfolio_stats['wins']}"
    )

    print(
        f"Losses: "
        f"{portfolio_stats['losses']}"
    )

    print(
        f"Win rate: "
        f"{portfolio_stats['win_rate']:.2f}%"
    )

    print(
        f"Profit factor: "
        f"{portfolio_stats['profit_factor']:.3f}"
    )

    print(
        f"Net R: "
        f"{portfolio_stats['net_r']:.3f}"
    )

    print(
        f"Expectancy R: "
        f"{portfolio_stats['expectancy_r']:.4f}"
    )

    print(
        f"Max drawdown R: "
        f"{portfolio_stats['max_drawdown_r']:.3f}"
    )

    print(
        f"Average trades/day: "
        f"{portfolio_stats['avg_trades_day']:.4f}"
    )

    print(
        f"Accepted trades: "
        f"{len(portfolio_trades)}"
    )

    print(
        f"Rejected by max-open limit: "
        f"{len(rejected_trades)}"
    )

    # --------------------------------------------------------
    # TOP INDIVIDUAL STRATEGIES
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("TOP INDIVIDUAL STRATEGIES")
    print("=" * 70)

    display_columns = [
        "rank",
        "strategy_id",
        "direction",
        "session",
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "expectancy_r",
    ]

    print(
        individual[
            display_columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # TOP PORTFOLIO CONTRIBUTORS
    # --------------------------------------------------------

    if not contribution.empty:

        contribution = (
            contribution
            .sort_values(
                [
                    "net_r",
                    "profit_factor",
                ],
                ascending=False
            )
            .reset_index(drop=True)
        )

        contribution.insert(
            0,
            "rank",
            range(
                1,
                len(contribution) + 1
            )
        )

        contribution.to_csv(
            contribution_path,
            index=False
        )

        print()
        print("=" * 70)
        print("TOP PORTFOLIO CONTRIBUTORS")
        print("=" * 70)

        print(
            contribution[
                [
                    "rank",
                    "strategy_id",
                    "accepted_trades",
                    "skipped_trades",
                    "net_r",
                    "profit_factor",
                    "win_rate",
                    "expectancy_r",
                ]
            ]
            .head(20)
            .to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # YEARLY PORTFOLIO
    # --------------------------------------------------------

    if not portfolio_yearly.empty:

        print()
        print("=" * 70)
        print("PORTFOLIO YEARLY RESULTS")
        print("=" * 70)

        print(
            portfolio_yearly[
                [
                    "year",
                    "trades",
                    "net_r",
                    "profit_factor",
                    "max_drawdown_r",
                    "win_rate",
                ]
            ].to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FILES SAVED")
    print("=" * 70)

    print(
        individual_path
    )

    print(
        yearly_path
    )

    print(
        portfolio_trades_path
    )

    print(
        rejected_path
    )

    print(
        equity_path
    )

    print(
        contribution_path
    )

    print(
        portfolio_yearly_path
    )

    print(
        overlap_path
    )

    print(
        summary_path
    )

    print()
    print("=" * 70)
    print("PORTFOLIO TEST COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()