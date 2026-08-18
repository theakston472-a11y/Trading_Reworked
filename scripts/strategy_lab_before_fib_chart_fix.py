"""
Strategy Laboratory

Purpose
-------
Tests promoted trading strategies across an RR grid.

Features
--------
- Tests multiple candidate strategies.
- Sweeps RR from 1.0 to 7.0 by default.
- Uses SQLite caching.
- Supports yearly robustness testing.
- Handles overlapping trades with a maximum open-trade limit.
- Rejects zero-trade results.
- Measures RR stability.
- Selects only ONE best RR for each unique strategy.
- Produces final rankings and diagnostic information.
- Optional trade charts for the final shortlist.

Important
---------
The dataframe is RESET after date filtering so that signal indices are
positional indices. This prevents the zero-trade bug caused by using
original dataframe indices inside filtered datasets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# RR GRID
# ============================================================

def rr_grid(
    start: float = 1.0,
    stop: float = 7.0,
    step: float = 0.1,
) -> list[float]:

    if step <= 0:
        raise ValueError(
            "RR step must be greater than zero."
        )

    if stop < start:
        raise ValueError(
            "RR stop must be greater than or equal to RR start."
        )

    count = int(
        round(
            (stop - start) / step
        )
    )

    return [
        round(
            start + i * step,
            1,
        )
        for i in range(
            count + 1
        )
    ]


# ============================================================
# DATABASE
# ============================================================

def stable_key(
    direction: str,
    session: str,
    conditions: str,
    rr: float,
    period: str,
    max_bars: int,
    max_open: int,
) -> str:

    raw = (
        f"{direction}|"
        f"{session}|"
        f"{conditions}|"
        f"{rr:.1f}|"
        f"{period}|"
        f"{max_bars}|"
        f"{max_open}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def init_db(
    path: str,
) -> sqlite3.Connection:

    con = sqlite3.connect(
        path
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS results(
            key TEXT PRIMARY KEY,
            direction TEXT,
            session TEXT,
            conditions TEXT,
            rr REAL,
            period TEXT,
            start TEXT,
            end TEXT,
            trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            win_rate REAL,
            profit_factor REAL,
            net_r REAL,
            expectancy_r REAL,
            max_drawdown_r REAL,
            avg_trades_day REAL,
            max_concurrent INTEGER,
            avg_hold_bars REAL,
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    con.commit()

    return con


def db_get(
    con: sqlite3.Connection,
    key: str,
):

    row = con.execute(
        "SELECT * FROM results WHERE key=?",
        (key,),
    ).fetchone()

    if row is None:
        return None

    cols = [
        r[1]
        for r in con.execute(
            "PRAGMA table_info(results)"
        ).fetchall()
    ]

    return dict(
        zip(
            cols,
            row,
        )
    )


def db_put(
    con: sqlite3.Connection,
    row: dict,
) -> None:

    cols = list(
        row.keys()
    )

    values = [
        row[c]
        for c in cols
    ]

    placeholders = ",".join(
        ["?"] * len(cols)
    )

    con.execute(
        f"""
        INSERT OR REPLACE INTO results
        ({",".join(cols)})
        VALUES ({placeholders})
        """,
        values,
    )


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Strategy Laboratory with RR robustness testing."
        )
    )

    parser.add_argument(
        "--data",
        default=None,
    )

    parser.add_argument(
        "--candidates",
        default=None,
    )

    parser.add_argument(
        "--db",
        default=None,
    )

    parser.add_argument(
        "--out",
        default=None,
    )

    parser.add_argument(
        "--start",
        default="2025-01-01",
    )

    parser.add_argument(
        "--end",
        default=None,
    )

    parser.add_argument(
        "--rr-start",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--rr-stop",
        type=float,
        default=7.0,
    )

    parser.add_argument(
        "--rr-step",
        type=float,
        default=0.1,
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--all-candidates",
        action="store_true",
    )

    parser.add_argument(
        "--max-bars",
        type=int,
        default=48,
    )

    parser.add_argument(
        "--max-open-trades",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--frequency-target",
        type=float,
        default=0.75,
        help="Trades/day target for full frequency score.",
    )

    parser.add_argument(
        "--min-trades",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--min-trades-per-day",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--final-n",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--charts",
        action="store_true",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore SQLite cache and recalculate everything.",
    )

    return parser.parse_args()


# ============================================================
# DEFAULT PATHS
# ============================================================

def defaults(
    args,
):

    base = Path(
        __file__
    ).resolve().parents[1]

    args.data = (
        args.data
        or str(
            base
            / "quant"
            / "feature_database.csv"
        )
    )

    args.candidates = (
        args.candidates
        or str(
            base
            / "quant"
            / "top100_candidates.csv"
        )
    )

    args.db = (
        args.db
        or str(
            base
            / "results"
            / "strategy_lab.sqlite"
        )
    )

    args.out = (
        args.out
        or str(
            base
            / "results"
            / "strategy_lab"
        )
    )

    Path(
        args.db
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    Path(
        args.out
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return args


# ============================================================
# DATA LOADING
# ============================================================

def load_data(
    path: str,
) -> pd.DataFrame:

    print(
        f"Loading data: {path}"
    )

    df = pd.read_csv(
        path
    )

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "atr14",
        "session",
    ]

    missing = [
        c
        for c in required
        if c not in df.columns
    ]

    if missing:

        raise ValueError(
            "Feature database is missing required columns: "
            + ", ".join(
                missing
            )
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    df = (
        df
        .dropna(
            subset=[
                "timestamp"
            ]
        )
        .sort_values(
            "timestamp"
        )
        .reset_index(
            drop=True
        )
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "atr14",
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["session"] = (
        df["session"]
        .astype(str)
        .str.strip()
    )

    return df


# ============================================================
# PERIODS
# ============================================================

def get_periods(
    df: pd.DataFrame,
    start,
    end,
):

    start_ts = pd.Timestamp(
        start,
        tz="UTC",
    )

    if end:

        end_ts = pd.Timestamp(
            end,
            tz="UTC",
        )

    else:

        end_ts = df[
            "timestamp"
        ].max()

    periods = {
        "ALL": (
            start_ts,
            end_ts,
        )
    }

    for year in range(
        start_ts.year,
        end_ts.year + 1,
    ):

        year_start = pd.Timestamp(
            f"{year}-01-01",
            tz="UTC",
        )

        year_end = pd.Timestamp(
            f"{year}-12-31 23:59:59",
            tz="UTC",
        )

        period_start = max(
            start_ts,
            year_start,
        )

        period_end = min(
            end_ts,
            year_end,
        )

        if period_start <= period_end:

            periods[str(year)] = (
                period_start,
                period_end,
            )

    return periods


# ============================================================
# SIGNAL DETECTION
# ============================================================

def signal_indices(
    df: pd.DataFrame,
    direction: str,
    session: str,
    conditions: str,
) -> np.ndarray:

    work = df

    requested_session = str(
        session
    ).strip().lower()

    if requested_session not in (
        "",
        "all",
        "nan",
        "none",
    ):

        work = work[
            work["session"]
            .astype(str)
            .str.strip()
            .str.lower()
            == requested_session
        ]

    if work.empty:

        return np.array(
            [],
            dtype=np.int64,
        )

    mask = np.ones(
        len(work),
        dtype=bool,
    )

    condition_list = [
        x.strip()
        for x in str(
            conditions
        ).split("+")
        if x.strip()
    ]

    for condition in condition_list:

        if condition not in work.columns:

            return np.array(
                [],
                dtype=np.int64,
            )

        values = work[
            condition
        ]

        if values.dtype != bool:

            values = (
                values
                .fillna(False)
                .astype(bool)
            )

        mask &= values.to_numpy()

    positions = np.flatnonzero(
        mask
    )

    return positions.astype(
        np.int64
    )


# ============================================================
# BACKTEST
# ============================================================

def backtest(
    df: pd.DataFrame,
    indices: np.ndarray,
    direction: str,
    rr: float,
    max_bars: int,
    max_open: int,
):

    if len(indices) == 0:
        return None

    op = df[
        "open"
    ].to_numpy(
        dtype=float
    )

    hi = df[
        "high"
    ].to_numpy(
        dtype=float
    )

    lo = df[
        "low"
    ].to_numpy(
        dtype=float
    )

    cl = df[
        "close"
    ].to_numpy(
        dtype=float
    )

    atr = df[
        "atr14"
    ].to_numpy(
        dtype=float
    )

    results = []

    trades = []

    active = []

    max_concurrent = 0

    direction_upper = str(
        direction
    ).upper()

    for signal_i in indices:

        signal_i = int(
            signal_i
        )

        entry_i = signal_i + 1

        if entry_i >= len(df):
            continue

        active = [
            exit_i
            for exit_i in active
            if exit_i >= entry_i
        ]

        if len(active) >= max_open:
            continue

        entry = op[
            entry_i
        ]

        atr_value = atr[
            signal_i
        ]

        candle_distance = abs(
            hi[signal_i]
            - lo[signal_i]
        )

        if np.isfinite(
            atr_value
        ):

            distance = max(
                atr_value,
                candle_distance,
            )

        else:

            distance = candle_distance

        if (
            not np.isfinite(
                distance
            )
            or distance <= 0
            or not np.isfinite(
                entry
            )
        ):
            continue

        if direction_upper == "SELL":

            sl = (
                entry
                + distance
            )

            tp = (
                entry
                - distance * rr
            )

        else:

            sl = (
                entry
                - distance
            )

            tp = (
                entry
                + distance * rr
            )

        end_i = min(
            len(df) - 1,
            entry_i + max_bars - 1,
        )

        outcome = None

        exit_i = end_i

        reason = "TIME"

        for j in range(
            entry_i,
            end_i + 1,
        ):

            if direction_upper == "SELL":

                stop_hit = (
                    hi[j] >= sl
                )

                target_hit = (
                    lo[j] <= tp
                )

            else:

                stop_hit = (
                    lo[j] <= sl
                )

                target_hit = (
                    hi[j] >= tp
                )

            if stop_hit:

                outcome = -1.0

                exit_i = j

                reason = "SL"

                break

            if target_hit:

                outcome = float(
                    rr
                )

                exit_i = j

                reason = "TP"

                break

        if outcome is None:

            if direction_upper == "SELL":

                move = (
                    entry
                    - cl[exit_i]
                )

            else:

                move = (
                    cl[exit_i]
                    - entry
                )

            outcome = float(
                move / distance
            )

        results.append(
            outcome
        )

        active.append(
            exit_i
        )

        max_concurrent = max(
            max_concurrent,
            len(active),
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
                "entry_time": str(
                    df.iloc[
                        entry_i
                    ][
                        "timestamp"
                    ]
                ),
                "exit_time": str(
                    df.iloc[
                        exit_i
                    ][
                        "timestamp"
                    ]
                ),
            }
        )

    if not results:
        return None

    arr = np.asarray(
        results,
        dtype=float,
    )

    wins = arr[
        arr > 0
    ]

    losses = arr[
        arr < 0
    ]

    gross_profit = (
        float(
            wins.sum()
        )
        if len(wins)
        else 0.0
    )

    gross_loss = (
        float(
            abs(
                losses.sum()
            )
        )
        if len(losses)
        else 0.0
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            / gross_loss
        )

    elif gross_profit > 0:

        profit_factor = 999.0

    else:

        profit_factor = 0.0

    equity = np.cumsum(
        arr
    )

    running_max = np.maximum.accumulate(
        np.r_[
            0.0,
            equity,
        ]
    )[1:]

    drawdown = (
        running_max
        - equity
    )

    max_drawdown = (
        float(
            drawdown.max()
        )
        if len(drawdown)
        else 0.0
    )

    first_time = df[
        "timestamp"
    ].iloc[0]

    last_time = df[
        "timestamp"
    ].iloc[-1]

    days = max(
        (
            last_time
            - first_time
        ).total_seconds()
        / 86400.0,
        1.0,
    )

    return {
        "trades": int(
            len(arr)
        ),
        "wins": int(
            len(wins)
        ),
        "losses": int(
            len(losses)
        ),
        "win_rate": float(
            len(wins)
            / len(arr)
            * 100.0
        ),
        "profit_factor": float(
            profit_factor
        ),
        "net_r": float(
            arr.sum()
        ),
        "expectancy_r": float(
            arr.mean()
        ),
        "max_drawdown_r": float(
            max_drawdown
        ),
        "avg_trades_day": float(
            len(arr)
            / days
        ),
        "max_concurrent": int(
            max_concurrent
        ),
        "avg_hold_bars": float(
            np.mean(
                [
                    t["exit_i"]
                    - t["entry_i"]
                    + 1
                    for t in trades
                ]
            )
        ),
        "trades_detail": trades,
    }


# ============================================================
# SCORE
# ============================================================

def robust_score(
    row,
    min_trades: int,
    frequency_target: float,
) -> float:

    trades = float(
        row["trades"]
    )

    if trades <= 0:
        return 0.0

    expectancy = float(
        row["expectancy_r"]
    )

    profit_factor = float(
        row["profit_factor"]
    )

    drawdown = float(
        row["max_drawdown_r"]
    )

    frequency = float(
        row["avg_trades_day"]
    )

    sample_score = min(
        trades
        / max(
            min_trades,
            1,
        ),
        2.0,
    ) / 2.0

    expectancy_score = max(
        min(
            expectancy,
            1.0,
        ),
        0.0,
    )

    pf_score = min(
        max(
            profit_factor,
            0.0,
        ),
        5.0,
    ) / 5.0

    drawdown_score = (
        1.0
        / (
            1.0
            + max(
                drawdown,
                0.0,
            )
        )
    )

    frequency_score = min(
        frequency
        / max(
            frequency_target,
            1e-9,
        ),
        1.0,
    )

    score = 100.0 * (
        0.30
        * expectancy_score
        + 0.20
        * pf_score
        + 0.20
        * drawdown_score
        + 0.15
        * frequency_score
        + 0.15
        * sample_score
    )

    return float(
        score
    )


# ============================================================
# CHARTS
# ============================================================

# ============================================================
# CHARTS
# ============================================================

# ============================================================
# CHARTS
# ============================================================

# ============================================================
# CHARTS
# ============================================================

def save_trade_charts(
    df: pd.DataFrame,
    final_df: pd.DataFrame,
    outdir: str,
):
    """
    TradingView-style trade charts.

    IMPORTANT FIX:
    ----------------
    Trade indices in result_json were created on filtered/reset
    dataframes, so they cannot safely be reused against the full
    feature dataframe.

    This function locates the real historical candles using:
        trade["entry_time"]
        trade["exit_time"]

    Features:
    - Correct candle/trade alignment using timestamps
    - Black background
    - White bullish candles
    - Black bearish candles with white outline
    - Horizontal ENTRY / SL / TP
    - Green reward box
    - Red risk box
    - Candles remain visible over boxes
    - Relevant Fibonacci levels
    - Relevant EMA only when strategy uses it
    - Relevant liquidity sweep only
    - Clean zoom around the actual historical trade
    """

    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_dir = Path(outdir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # SETTINGS
    # ========================================================

    BARS_BEFORE_ENTRY = 18
    BARS_AFTER_EXIT = 10

    # If a trade lasts a long time, still show the complete
    # trade, but don't add huge amounts of extra empty context.
    MIN_BARS_AFTER_ENTRY = 12

    FIG_WIDTH = 18
    FIG_HEIGHT = 10
    DPI = 170

    CANDLE_WIDTH = 0.68

    # ========================================================
    # PREPARE FULL DATAFRAME
    # ========================================================

    work_df = df.copy()

    work_df["timestamp"] = pd.to_datetime(
        work_df["timestamp"],
        utc=True,
        errors="coerce",
    )

    work_df = (
        work_df
        .dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "ema20",
        "ema50",
        "ema100",
        "ema200",
        "fib_382",
        "fib_500",
        "fib_618",
        "previous_day_high",
        "previous_day_low",
        "session_high",
        "session_low",
    ]

    for column in numeric_columns:

        if column in work_df.columns:

            work_df[column] = pd.to_numeric(
                work_df[column],
                errors="coerce",
            )

    # ========================================================
    # HELPERS
    # ========================================================

    def finite_number(value):

        try:

            value = float(value)

            if np.isfinite(value):
                return value

        except Exception:
            pass

        return None

    def parse_trade_time(value):

        try:

            timestamp = pd.to_datetime(
                value,
                utc=True,
                errors="coerce",
            )

            if pd.isna(timestamp):
                return None

            return timestamp

        except Exception:
            return None

    def find_nearest_index(timestamp):

        """
        Find the nearest candle in the FULL dataframe by timestamp.
        """

        if timestamp is None:
            return None

        differences = (
            work_df["timestamp"]
            - timestamp
        ).abs()

        if differences.empty:
            return None

        index = int(
            differences.idxmin()
        )

        # Safety check:
        # the nearest candle should normally be within 15 minutes.
        difference = differences.loc[index]

        if difference > pd.Timedelta(
            minutes=20
        ):
            return None

        return index

    def strategy_conditions(row):

        return {
            item.strip().lower()
            for item in str(
                row.get(
                    "conditions",
                    "",
                )
            ).split("+")
            if item.strip()
        }

    def uses_any(
        conditions,
        fragments,
    ):

        for condition in conditions:

            for fragment in fragments:

                if fragment in condition:
                    return True

        return False

    def bool_value(value):

        if pd.isna(value):
            return False

        if isinstance(
            value,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(value)

        try:

            return bool(
                int(value)
            )

        except Exception:

            text = str(
                value
            ).strip().lower()

            return text in {
                "true",
                "yes",
                "y",
                "1",
            }

    # ========================================================
    # PROCESS STRATEGIES
    # ========================================================

    for _, row in final_df.iterrows():

        trades = row.get(
            "_detail"
        )

        if not trades:
            continue

        conditions = strategy_conditions(
            row
        )

        direction = str(
            row.get(
                "direction",
                "",
            )
        ).upper()

        # Keep first two examples as before.
        for trade_number, trade in enumerate(
            trades[:2],
            start=1,
        ):

            # =================================================
            # FIND THE REAL CANDLE USING TIMESTAMPS
            # =================================================

            entry_time = parse_trade_time(
                trade.get(
                    "entry_time"
                )
            )

            exit_time = parse_trade_time(
                trade.get(
                    "exit_time"
                )
            )

            entry_i = find_nearest_index(
                entry_time
            )

            exit_i = find_nearest_index(
                exit_time
            )

            if entry_i is None:

                print(
                    f"WARNING: Could not locate entry candle "
                    f"for rank {row.get('rank')} "
                    f"trade {trade_number}: "
                    f"{trade.get('entry_time')}"
                )

                continue

            if exit_i is None:

                exit_i = min(
                    len(work_df) - 1,
                    entry_i + MIN_BARS_AFTER_ENTRY,
                )

            if exit_i < entry_i:

                exit_i = entry_i

            # Signal is normally the candle immediately before entry.
            signal_i = max(
                0,
                entry_i - 1,
            )

            # =================================================
            # CHART WINDOW
            # =================================================

            start_i = max(
                0,
                entry_i - BARS_BEFORE_ENTRY,
            )

            end_i = min(
                len(work_df) - 1,
                max(
                    exit_i + BARS_AFTER_EXIT,
                    entry_i + MIN_BARS_AFTER_ENTRY,
                ),
            )

            chart_data = (
                work_df.iloc[
                    start_i:end_i + 1
                ]
                .copy()
                .reset_index(drop=True)
            )

            if chart_data.empty:
                continue

            entry_x = (
                entry_i - start_i
            )

            exit_x = (
                exit_i - start_i
            )

            signal_x = (
                signal_i - start_i
            )

            # =================================================
            # TRADE PRICES
            # =================================================

            entry_price = finite_number(
                trade.get(
                    "entry"
                )
            )

            stop_price = finite_number(
                trade.get(
                    "sl"
                )
            )

            target_price = finite_number(
                trade.get(
                    "tp"
                )
            )

            if None in (
                entry_price,
                stop_price,
                target_price,
            ):
                continue

            # =================================================
            # SANITY CHECK
            # =================================================
            #
            # The entry should now be close to the candle's
            # actual historical open.
            # =================================================

            actual_entry_open = finite_number(
                work_df.iloc[
                    entry_i
                ]["open"]
            )

            if actual_entry_open is not None:

                difference = abs(
                    actual_entry_open
                    - entry_price
                )

                normal_move = abs(
                    finite_number(
                        work_df.iloc[
                            signal_i
                        ]["high"]
                    )
                    - finite_number(
                        work_df.iloc[
                            signal_i
                        ]["low"]
                    )
                )

                if normal_move > 0:

                    if difference > (
                        normal_move * 3
                    ):

                        print()
                        print(
                            "WARNING: Trade/candle price mismatch"
                        )

                        print(
                            f"Rank: {row.get('rank')}"
                        )

                        print(
                            f"Entry time: {entry_time}"
                        )

                        print(
                            f"Stored entry: {entry_price}"
                        )

                        print(
                            f"Candle open: {actual_entry_open}"
                        )

                        print()

            # =================================================
            # FIGURE
            # =================================================

            fig, ax = plt.subplots(
                figsize=(
                    FIG_WIDTH,
                    FIG_HEIGHT,
                ),
                dpi=DPI,
            )

            fig.patch.set_facecolor(
                "black"
            )

            ax.set_facecolor(
                "black"
            )

            # =================================================
            # TRADE BOXES FIRST
            # =================================================

            box_left = (
                entry_x - 0.35
            )

            box_right = (
                exit_x + 0.45
            )

            box_width = max(
                box_right - box_left,
                1.5,
            )

            # -----------------------------------------------
            # PROFIT BOX
            # -----------------------------------------------

            profit_low = min(
                entry_price,
                target_price,
            )

            profit_high = max(
                entry_price,
                target_price,
            )

            profit_height = (
                profit_high
                - profit_low
            )

            if profit_height > 0:

                profit_box = Rectangle(
                    (
                        box_left,
                        profit_low,
                    ),
                    box_width,
                    profit_height,
                    facecolor="#168f5b",
                    edgecolor="#42d392",
                    linewidth=1.0,
                    alpha=0.20,
                    zorder=1,
                )

                ax.add_patch(
                    profit_box
                )

            # -----------------------------------------------
            # RISK BOX
            # -----------------------------------------------

            risk_low = min(
                entry_price,
                stop_price,
            )

            risk_high = max(
                entry_price,
                stop_price,
            )

            risk_height = (
                risk_high
                - risk_low
            )

            if risk_height > 0:

                risk_box = Rectangle(
                    (
                        box_left,
                        risk_low,
                    ),
                    box_width,
                    risk_height,
                    facecolor="#9f3030",
                    edgecolor="#ff6868",
                    linewidth=1.0,
                    alpha=0.22,
                    zorder=1,
                )

                ax.add_patch(
                    risk_box
                )

            # =================================================
            # RELEVANT EMA ONLY
            # =================================================

            ema_definitions = [
                (
                    "ema20",
                    "EMA 20",
                ),
                (
                    "ema50",
                    "EMA 50",
                ),
                (
                    "ema100",
                    "EMA 100",
                ),
                (
                    "ema200",
                    "EMA 200",
                ),
            ]

            for ema_column, ema_label in ema_definitions:

                if ema_column not in work_df.columns:
                    continue

                # Only display if strategy actually uses it.
                if not uses_any(
                    conditions,
                    [
                        ema_column,
                    ],
                ):
                    continue

                values = pd.to_numeric(
                    chart_data[
                        ema_column
                    ],
                    errors="coerce",
                )

                if values.notna().sum() < 2:
                    continue

                ax.plot(
                    range(
                        len(chart_data)
                    ),
                    values,
                    linewidth=1.2,
                    alpha=0.75,
                    label=ema_label,
                    zorder=3,
                )

            # =================================================
            # RELEVANT FIB
            # =================================================

            uses_fib = uses_any(
                conditions,
                [
                    "fib",
                ],
            )

            if uses_fib:

                signal_row = work_df.iloc[
                    signal_i
                ]

                fib_definitions = [
                    (
                        "fib_382",
                        "FIB 38.2%",
                    ),
                    (
                        "fib_500",
                        "FIB 50.0%",
                    ),
                    (
                        "fib_618",
                        "FIB 61.8%",
                    ),
                ]

                for fib_column, fib_label in fib_definitions:

                    if fib_column not in work_df.columns:
                        continue

                    value = finite_number(
                        signal_row[
                            fib_column
                        ]
                    )

                    if value is None:
                        continue

                    ax.axhline(
                        value,
                        linestyle=":",
                        linewidth=1.0,
                        color="0.65",
                        alpha=0.60,
                        zorder=2,
                    )

                    ax.text(
                        0.25,
                        value,
                        f" {fib_label}  {value:.5f}",
                        fontsize=8.5,
                        color="0.70",
                        va="bottom",
                        zorder=4,
                    )

            # =================================================
            # RELEVANT LIQUIDITY SWEEP ONLY
            # =================================================

            wants_high_sweep = (
                "liquidity_sweep_high"
                in conditions
            )

            wants_low_sweep = (
                "liquidity_sweep_low"
                in conditions
            )

            sweep_window_start = max(
                0,
                signal_i - 8,
            )

            sweep_window_end = min(
                len(work_df) - 1,
                signal_i + 2,
            )

            if wants_high_sweep:

                for original_i in range(
                    signal_i,
                    sweep_window_start - 1,
                    -1,
                ):

                    if (
                        "liquidity_sweep_high"
                        not in work_df.columns
                    ):
                        break

                    if not bool_value(
                        work_df.iloc[
                            original_i
                        ][
                            "liquidity_sweep_high"
                        ]
                    ):
                        continue

                    local_x = (
                        original_i
                        - start_i
                    )

                    sweep_price = finite_number(
                        work_df.iloc[
                            original_i
                        ]["high"]
                    )

                    if (
                        sweep_price is None
                        or local_x < 0
                        or local_x
                        >= len(chart_data)
                    ):
                        continue

                    line_left = max(
                        0,
                        local_x - 5,
                    )

                    line_right = min(
                        len(chart_data) - 1,
                        local_x + 4,
                    )

                    ax.hlines(
                        sweep_price,
                        line_left,
                        line_right,
                        colors="0.60",
                        linestyles=":",
                        linewidth=1.0,
                        alpha=0.65,
                        zorder=3,
                    )

                    ax.text(
                        line_left,
                        sweep_price,
                        " LIQUIDITY SWEEP HIGH",
                        fontsize=8,
                        color="0.65",
                        va="bottom",
                        zorder=5,
                    )

                    break

            if wants_low_sweep:

                for original_i in range(
                    signal_i,
                    sweep_window_start - 1,
                    -1,
                ):

                    if (
                        "liquidity_sweep_low"
                        not in work_df.columns
                    ):
                        break

                    if not bool_value(
                        work_df.iloc[
                            original_i
                        ][
                            "liquidity_sweep_low"
                        ]
                    ):
                        continue

                    local_x = (
                        original_i
                        - start_i
                    )

                    sweep_price = finite_number(
                        work_df.iloc[
                            original_i
                        ]["low"]
                    )

                    if (
                        sweep_price is None
                        or local_x < 0
                        or local_x
                        >= len(chart_data)
                    ):
                        continue

                    line_left = max(
                        0,
                        local_x - 5,
                    )

                    line_right = min(
                        len(chart_data) - 1,
                        local_x + 4,
                    )

                    ax.hlines(
                        sweep_price,
                        line_left,
                        line_right,
                        colors="0.60",
                        linestyles=":",
                        linewidth=1.0,
                        alpha=0.65,
                        zorder=3,
                    )

                    ax.text(
                        line_left,
                        sweep_price,
                        " LIQUIDITY SWEEP LOW",
                        fontsize=8,
                        color="0.65",
                        va="top",
                        zorder=5,
                    )

                    break

            # =================================================
            # CANDLES LAST
            # =================================================

            candle_width = CANDLE_WIDTH

            visible_highs = []

            visible_lows = []

            for x, candle_row in chart_data.iterrows():

                o = finite_number(
                    candle_row["open"]
                )

                h = finite_number(
                    candle_row["high"]
                )

                l = finite_number(
                    candle_row["low"]
                )

                c = finite_number(
                    candle_row["close"]
                )

                if None in (
                    o,
                    h,
                    l,
                    c,
                ):
                    continue

                visible_highs.append(
                    h
                )

                visible_lows.append(
                    l
                )

                # Wick
                ax.vlines(
                    x,
                    l,
                    h,
                    color="white",
                    linewidth=1.15,
                    zorder=7,
                )

                body_low = min(
                    o,
                    c,
                )

                body_height = abs(
                    c - o
                )

                candle_range = max(
                    h - l,
                    1e-8,
                )

                body_height = max(
                    body_height,
                    candle_range * 0.03,
                )

                if c >= o:

                    face_color = "white"
                    edge_color = "white"

                else:

                    face_color = "black"
                    edge_color = "white"

                body = Rectangle(
                    (
                        x
                        - candle_width / 2,
                        body_low,
                    ),
                    candle_width,
                    body_height,
                    facecolor=face_color,
                    edgecolor=edge_color,
                    linewidth=1.05,
                    zorder=8,
                )

                ax.add_patch(
                    body
                )

            # =================================================
            # ENTRY / SL / TP
            # =================================================

            ax.hlines(
                entry_price,
                box_left,
                box_right,
                color="white",
                linewidth=1.4,
                zorder=10,
            )

            ax.hlines(
                stop_price,
                box_left,
                box_right,
                color="#ff6868",
                linestyle="--",
                linewidth=1.2,
                zorder=10,
            )

            ax.hlines(
                target_price,
                box_left,
                box_right,
                color="#42d392",
                linestyle="--",
                linewidth=1.2,
                zorder=10,
            )

            label_x = (
                box_right + 0.30
            )

            ax.text(
                label_x,
                entry_price,
                f"ENTRY {entry_price:.5f}",
                color="white",
                fontsize=9.5,
                va="center",
                fontweight="bold",
                zorder=12,
            )

            ax.text(
                label_x,
                stop_price,
                f"SL {stop_price:.5f}",
                color="#ff7777",
                fontsize=9,
                va="center",
                fontweight="bold",
                zorder=12,
            )

            ax.text(
                label_x,
                target_price,
                f"TP {target_price:.5f}",
                color="#55dd99",
                fontsize=9,
                va="center",
                fontweight="bold",
                zorder=12,
            )

            # =================================================
            # ENTRY MARKER
            # =================================================

            if (
                0
                <= entry_x
                < len(chart_data)
            ):

                marker_offset = max(
                    (
                        max(visible_highs)
                        - min(visible_lows)
                    )
                    * 0.04,
                    abs(
                        entry_price
                        - stop_price
                    )
                    * 0.20,
                )

                if direction == "BUY":

                    ax.annotate(
                        "BUY",
                        xy=(
                            entry_x,
                            entry_price,
                        ),
                        xytext=(
                            entry_x,
                            entry_price
                            - marker_offset,
                        ),
                        color="white",
                        fontsize=9,
                        fontweight="bold",
                        ha="center",
                        va="top",
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color="white",
                            linewidth=1.2,
                        ),
                        zorder=13,
                    )

                else:

                    ax.annotate(
                        "SELL",
                        xy=(
                            entry_x,
                            entry_price,
                        ),
                        xytext=(
                            entry_x,
                            entry_price
                            + marker_offset,
                        ),
                        color="white",
                        fontsize=9,
                        fontweight="bold",
                        ha="center",
                        va="bottom",
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color="white",
                            linewidth=1.2,
                        ),
                        zorder=13,
                    )

            # =================================================
            # EXIT MARKER
            # =================================================

            reason = str(
                trade.get(
                    "reason",
                    "EXIT",
                )
            ).upper()

            if reason == "TP":

                displayed_exit_price = (
                    target_price
                )

            elif reason == "SL":

                displayed_exit_price = (
                    stop_price
                )

            else:

                displayed_exit_price = (
                    finite_number(
                        work_df.iloc[
                            exit_i
                        ]["close"]
                    )
                )

            if (
                displayed_exit_price is not None
                and 0
                <= exit_x
                < len(chart_data)
            ):

                ax.scatter(
                    [exit_x],
                    [displayed_exit_price],
                    marker="x",
                    s=70,
                    color="white",
                    linewidths=1.6,
                    zorder=13,
                )

                ax.text(
                    exit_x + 0.3,
                    displayed_exit_price,
                    f"EXIT {reason}",
                    fontsize=8.5,
                    color="white",
                    va="center",
                    zorder=13,
                )

            # =================================================
            # Y AXIS
            # =================================================
            #
            # Now candle prices and trade prices are from the
            # SAME historical period, so scaling should be sane.
            # =================================================

            y_prices = (
                visible_highs
                + visible_lows
                + [
                    entry_price,
                    stop_price,
                    target_price,
                ]
            )

            y_min = min(
                y_prices
            )

            y_max = max(
                y_prices
            )

            y_range = max(
                y_max - y_min,
                1e-8,
            )

            padding = (
                y_range * 0.08
            )

            ax.set_ylim(
                y_min - padding,
                y_max + padding,
            )

            # =================================================
            # X AXIS
            # =================================================

            ax.set_xlim(
                -1,
                len(chart_data) + 4,
            )

            tick_count = min(
                9,
                len(chart_data),
            )

            if tick_count > 1:

                positions = np.linspace(
                    0,
                    len(chart_data) - 1,
                    tick_count,
                    dtype=int,
                )

                labels = []

                for position in positions:

                    timestamp = chart_data.iloc[
                        position
                    ]["timestamp"]

                    labels.append(
                        timestamp.strftime(
                            "%d %b\n%H:%M"
                        )
                    )

                ax.set_xticks(
                    positions
                )

                ax.set_xticklabels(
                    labels,
                    fontsize=8.5,
                    color="0.75",
                )

            # =================================================
            # STYLE
            # =================================================

            ax.grid(
                True,
                linestyle=":",
                linewidth=0.55,
                alpha=0.10,
                color="white",
            )

            ax.tick_params(
                axis="y",
                colors="0.75",
                labelsize=9,
            )

            ax.tick_params(
                axis="x",
                colors="0.75",
            )

            ax.spines[
                "top"
            ].set_visible(False)

            ax.spines[
                "right"
            ].set_visible(False)

            ax.spines[
                "left"
            ].set_color("0.30")

            ax.spines[
                "bottom"
            ].set_color("0.30")

            ax.set_ylabel(
                "PRICE",
                color="0.70",
                fontsize=9,
            )

            # =================================================
            # TITLE
            # =================================================

            rank_value = int(
                row.get(
                    "rank",
                    0,
                )
            )

            rr_value = float(
                row.get(
                    "rr",
                    0.0,
                )
            )

            result_r = finite_number(
                trade.get(
                    "outcome_r"
                )
            )

            if result_r is None:
                result_r = 0.0

            title = (
                f"RANK {rank_value}  |  "
                f"{direction}  |  "
                f"{row.get('session', '')}  |  "
                f"RR {rr_value:.1f}"
            )

            subtitle = (
                f"{row.get('conditions', '')}  |  "
                f"TRADE {trade_number}  |  "
                f"{reason}  |  "
                f"{result_r:+.2f}R"
            )

            ax.set_title(
                title
                + "\n"
                + subtitle,
                loc="left",
                color="white",
                fontsize=13.5,
                fontweight="bold",
                pad=14,
            )

            # =================================================
            # INFO BOX
            # =================================================

            information = (
                f"Entry: {entry_price:.5f}\n"
                f"Stop:  {stop_price:.5f}\n"
                f"Target: {target_price:.5f}\n"
                f"RR: {rr_value:.1f}\n"
                f"Result: {result_r:+.2f}R"
            )

            ax.text(
                0.985,
                0.975,
                information,
                transform=ax.transAxes,
                ha="right",
                va="top",
                color="white",
                fontsize=9.5,
                bbox=dict(
                    boxstyle="round,pad=0.5",
                    facecolor="black",
                    edgecolor="0.35",
                    alpha=0.88,
                ),
                zorder=20,
            )

            # =================================================
            # LEGEND
            # =================================================

            handles, labels = (
                ax.get_legend_handles_labels()
            )

            if handles:

                legend = ax.legend(
                    handles,
                    labels,
                    loc="upper left",
                    frameon=False,
                    fontsize=8.5,
                )

                for text in legend.get_texts():

                    text.set_color(
                        "0.75"
                    )

            # =================================================
            # MARGINS
            # =================================================

            fig.subplots_adjust(
                left=0.07,
                right=0.90,
                top=0.88,
                bottom=0.10,
            )

            # =================================================
            # SAVE
            # =================================================

            filename = (
                f"rank_"
                f"{rank_value:03d}"
                f"_trade_"
                f"{trade_number}.png"
            )

            fig.savefig(
                output_dir / filename,
                dpi=DPI,
                facecolor="black",
                edgecolor="none",
            )

            plt.close(
                fig
            )

    print(
        f"Trade charts saved to: "
        f"{output_dir}"
    )

# ============================================================
# MAIN
# ============================================================

def main():

    args = defaults(
        parse_args()
    )

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    df = load_data(
        args.data
    )

    print(
        f"Data: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        "Sessions found:"
    )

    print(
        df["session"]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    # --------------------------------------------------------
    # PERIODS
    # --------------------------------------------------------

    periods = get_periods(
        df,
        args.start,
        args.end,
    )

    print(
        "\nPeriods:"
    )

    for name, (
        start,
        end,
    ) in periods.items():

        print(
            f"  {name}: "
            f"{start} -> {end}"
        )

    # --------------------------------------------------------
    # LOAD CANDIDATES
    # --------------------------------------------------------

    print(
        f"\nLoading candidates: "
        f"{args.candidates}"
    )

    candidates = pd.read_csv(
        args.candidates
    )

    required_candidate_columns = [
        "direction",
        "session",
        "conditions",
    ]

    missing_candidate_columns = [
        c
        for c in required_candidate_columns
        if c not in candidates.columns
    ]

    if missing_candidate_columns:

        raise ValueError(
            "Candidate file is missing required columns: "
            + ", ".join(
                missing_candidate_columns
            )
        )

    candidates["direction"] = (
        candidates[
            "direction"
        ]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    candidates["session"] = (
        candidates[
            "session"
        ]
        .astype(str)
        .str.strip()
    )

    candidates["conditions"] = (
        candidates[
            "conditions"
        ]
        .astype(str)
        .str.strip()
    )

    candidates = (
        candidates
        .drop_duplicates(
            [
                "direction",
                "session",
                "conditions",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    if not args.all_candidates:

        candidates = candidates.head(
            args.max_candidates
        )

    print(
        f"\nUnique candidates: "
        f"{len(candidates)}"
    )

    print(
        f"RRs: "
        f"{rr_grid(args.rr_start, args.rr_stop, args.rr_step)}"
    )

    # --------------------------------------------------------
    # DIAGNOSTIC COLUMNS
    # --------------------------------------------------------

    print(
        "\nChecking candidate conditions..."
    )

    available_columns = set(
        df.columns
    )

    valid_condition_candidates = 0

    invalid_condition_candidates = 0

    for _, candidate in candidates.iterrows():

        condition_list = [
            x.strip()
            for x in str(
                candidate[
                    "conditions"
                ]
            ).split("+")
            if x.strip()
        ]

        missing = [
            condition
            for condition in condition_list
            if condition not in available_columns
        ]

        if missing:

            invalid_condition_candidates += 1

        else:

            valid_condition_candidates += 1

    print(
        f"Candidates with valid condition columns: "
        f"{valid_condition_candidates}"
    )

    print(
        f"Candidates with missing condition columns: "
        f"{invalid_condition_candidates}"
    )

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    con = init_db(
        args.db
    )

    period_rows = []

    rrs = rr_grid(
        args.rr_start,
        args.rr_stop,
        args.rr_step,
    )

    total_signal_count = 0

    total_trade_count = 0

    candidates_with_signals = 0

    candidates_with_trades = 0

    # --------------------------------------------------------
    # RUN CANDIDATES
    # --------------------------------------------------------

    for ci, candidate in candidates.iterrows():

        candidate_signal_count = 0

        candidate_trade_count = 0

        for period, (
            start,
            end,
        ) in periods.items():

            sub = df[
                (df["timestamp"] >= start)
                & (df["timestamp"] <= end)
            ].copy().reset_index(
                drop=True
            )

            indices = signal_indices(
                sub,
                candidate[
                    "direction"
                ],
                candidate[
                    "session"
                ],
                candidate[
                    "conditions"
                ],
            )

            candidate_signal_count += len(
                indices
            )

            for rr in rrs:

                key = stable_key(
                    candidate[
                        "direction"
                    ],
                    candidate[
                        "session"
                    ],
                    candidate[
                        "conditions"
                    ],
                    rr,
                    period,
                    args.max_bars,
                    args.max_open_trades,
                )

                cached = None

                if not args.force:

                    cached = db_get(
                        con,
                        key,
                    )

                if cached is not None:

                    row = cached

                else:

                    result = backtest(
                        sub,
                        indices,
                        candidate[
                            "direction"
                        ],
                        rr,
                        args.max_bars,
                        args.max_open_trades,
                    )

                    if result is None:

                        result = {
                            "trades": 0,
                            "wins": 0,
                            "losses": 0,
                            "win_rate": 0.0,
                            "profit_factor": 0.0,
                            "net_r": 0.0,
                            "expectancy_r": 0.0,
                            "max_drawdown_r": 0.0,
                            "avg_trades_day": 0.0,
                            "max_concurrent": 0,
                            "avg_hold_bars": 0.0,
                            "trades_detail": [],
                        }

                    row = {
                        "key": key,
                        "direction": candidate[
                            "direction"
                        ],
                        "session": candidate[
                            "session"
                        ],
                        "conditions": candidate[
                            "conditions"
                        ],
                        "rr": float(
                            rr
                        ),
                        "period": period,
                        "start": str(
                            start
                        ),
                        "end": str(
                            end
                        ),

                        **{
                            k: v
                            for k, v
                            in result.items()
                            if k != "trades_detail"
                        },

                        "result_json": json.dumps(
                            result[
                                "trades_detail"
                            ]
                        ),
                    }

                    db_put(
                        con,
                        row
                    )

                    con.commit()

                period_rows.append(
                    row
                )

                candidate_trade_count += int(
                    row["trades"]
                )

        total_signal_count += (
            candidate_signal_count
        )

        total_trade_count += (
            candidate_trade_count
        )

        if candidate_signal_count > 0:

            candidates_with_signals += 1

        if candidate_trade_count > 0:

            candidates_with_trades += 1

        if candidate_signal_count == 0:

            print(
                f"Candidate "
                f"{ci + 1}/"
                f"{len(candidates)} "
                f"-> SIGNALS: 0 "
                f"| {candidate['direction']} "
                f"| {candidate['session']} "
                f"| {candidate['conditions']}"
            )

        elif candidate_trade_count == 0:

            print(
                f"Candidate "
                f"{ci + 1}/"
                f"{len(candidates)} "
                f"-> SIGNALS: "
                f"{candidate_signal_count} "
                f"| TRADES: 0 "
                f"| {candidate['direction']} "
                f"| {candidate['session']}"
            )

        elif (
            (ci + 1) % 10 == 0
            or ci == len(candidates) - 1
        ):

            print(
                f"Processed "
                f"{ci + 1}/"
                f"{len(candidates)} "
                f"candidates "
                f"| signals="
                f"{candidate_signal_count} "
                f"| trades="
                f"{candidate_trade_count}"
            )

    # --------------------------------------------------------
    # GLOBAL DIAGNOSTICS
    # --------------------------------------------------------

    print(
        "\n============================================================"
    )

    print(
        "DIAGNOSTICS"
    )

    print(
        "============================================================"
    )

    print(
        f"Candidates tested: "
        f"{len(candidates)}"
    )

    print(
        f"Candidates with signals: "
        f"{candidates_with_signals}"
    )

    print(
        f"Candidates with trades: "
        f"{candidates_with_trades}"
    )

    print(
        f"Total signals: "
        f"{total_signal_count:,}"
    )

    print(
        f"Total trades: "
        f"{total_trade_count:,}"
    )

    print(
        "============================================================"
    )

    # --------------------------------------------------------
    # SAVE PERIOD RESULTS
    # --------------------------------------------------------

    if not period_rows:

        print(
            "\nNo period results were generated."
        )

        con.close()

        return

    p = pd.DataFrame(
        period_rows
    )

    p.to_csv(
        str(args.out)
        + "_periods.csv",
        index=False,
    )

    # --------------------------------------------------------
    # BUILD RR SUMMARIES
    # --------------------------------------------------------

    summaries = []

    grouped = p.groupby(
        [
            "direction",
            "session",
            "conditions",
            "rr",
        ],
        sort=False,
    )

    for keys, group in grouped:

        (
            direction,
            session,
            conditions,
            rr,
        ) = keys

        all_rows = group[
            group["period"] == "ALL"
        ]

        if all_rows.empty:
            continue

        all_row = all_rows.iloc[0]

        if int(
            all_row["trades"]
        ) <= 0:
            continue

        year_rows = group[
            group["period"] != "ALL"
        ]

        if len(year_rows):

            positive_years = int(
                (
                    year_rows[
                        "net_r"
                    ]
                    > 0
                ).sum()
            )

            enough_years = int(
                (
                    year_rows[
                        "trades"
                    ]
                    >= max(
                        5,
                        args.min_trades / 2,
                    )
                ).sum()
            )

            worst_year_pf = float(
                year_rows[
                    "profit_factor"
                ].min()
            )

            avg_year_expectancy = float(
                year_rows[
                    "expectancy_r"
                ].mean()
            )

        else:

            positive_years = 0

            enough_years = 0

            worst_year_pf = float(
                all_row[
                    "profit_factor"
                ]
            )

            avg_year_expectancy = float(
                all_row[
                    "expectancy_r"
                ]
            )

        score = robust_score(
            all_row,
            args.min_trades,
            args.frequency_target,
        )

        if len(year_rows):

            score *= (
                0.65
                + 0.35
                * (
                    positive_years
                    / max(
                        len(year_rows),
                        1,
                    )
                )
            )

            if (
                enough_years
                < len(year_rows)
            ):

                score *= 0.75

        summaries.append(
            {
                "direction": direction,
                "session": session,
                "conditions": conditions,
                "rr": float(
                    rr
                ),
                "trades": int(
                    all_row[
                        "trades"
                    ]
                ),
                "net_r": float(
                    all_row[
                        "net_r"
                    ]
                ),
                "expectancy_r": float(
                    all_row[
                        "expectancy_r"
                    ]
                ),
                "profit_factor": float(
                    all_row[
                        "profit_factor"
                    ]
                ),
                "max_drawdown_r": float(
                    all_row[
                        "max_drawdown_r"
                    ]
                ),
                "win_rate": float(
                    all_row[
                        "win_rate"
                    ]
                ),
                "avg_trades_day": float(
                    all_row[
                        "avg_trades_day"
                    ]
                ),
                "max_concurrent": int(
                    all_row[
                        "max_concurrent"
                    ]
                ),
                "avg_hold_bars": float(
                    all_row[
                        "avg_hold_bars"
                    ]
                ),
                "positive_years": (
                    positive_years
                ),
                "years_tested": int(
                    len(year_rows)
                ),
                "worst_year_pf": (
                    worst_year_pf
                ),
                "avg_year_expectancy_r": (
                    avg_year_expectancy
                ),
                "base_score": float(
                    score
                ),
            }
        )

    s = pd.DataFrame(
        summaries
    )

    # --------------------------------------------------------
    # ZERO-TRADE PROTECTION
    # --------------------------------------------------------

    if s.empty:

        print(
            "\nNo non-zero-trade results found."
        )

        print(
            "\nThe diagnostic information above "
            "shows whether the problem is:"
        )

        print(
            "  1. No matching signals"
        )

        print(
            "  2. Missing condition columns"
        )

        print(
            "  3. Signals but no executable trades"
        )

        print(
            "  4. Candidate/session mismatch"
        )

        con.close()

        return

    # --------------------------------------------------------
    # RR STABILITY
    # --------------------------------------------------------

    s["rr_stability"] = 0.0

    strategy_groups = s.groupby(
        [
            "direction",
            "session",
            "conditions",
        ],
        sort=False,
    )

    for strategy_key, group in strategy_groups:

        best_score = float(
            group[
                "base_score"
            ].max()
        )

        if best_score <= 0:
            continue

        best_index = group[
            "base_score"
        ].idxmax()

        best_rr = float(
            group.loc[
                best_index,
                "rr",
            ]
        )

        nearby = group[
            abs(
                group["rr"]
                - best_rr
            ) <= 0.5
        ]

        if len(nearby):

            stability = float(
                nearby[
                    "base_score"
                ].mean()
                / best_score
            )

        else:

            stability = 0.0

        stability = max(
            0.0,
            min(
                stability,
                1.0,
            ),
        )

        s.loc[
            group.index,
            "rr_stability",
        ] = stability

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    s["robust_score"] = (
        s["base_score"]
        * (
            0.75
            + 0.25
            * s["rr_stability"]
        )
    )

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    s["meets_sample"] = (
        s["trades"]
        >= args.min_trades
    )

    s["meets_frequency"] = (
        s["avg_trades_day"]
        >= args.min_trades_per_day
    )

    eligible = s[
        s["meets_sample"]
        & s["meets_frequency"]
    ].copy()

    # --------------------------------------------------------
    # IF NOTHING PASSES
    # --------------------------------------------------------

    if eligible.empty:

        print(
            "\nNo strategies passed "
            "the minimum sample/frequency "
            "requirements."
        )

        diagnostic = (
            s.sort_values(
                [
                    "trades",
                    "net_r",
                    "robust_score",
                ],
                ascending=False,
            )
            .reset_index(
                drop=True
            )
        )

        diagnostic.insert(
            0,
            "rank",
            range(
                1,
                len(diagnostic) + 1,
            ),
        )

        diagnostic.to_csv(
            str(args.out)
            + "_final.csv",
            index=False,
        )

        pd.DataFrame().to_csv(
            str(args.out)
            + "_top_final.csv",
            index=False,
        )

        print(
            "\nBest available results "
            "before minimum filters:"
        )

        print(
            diagnostic[
                [
                    "rank",
                    "direction",
                    "session",
                    "conditions",
                    "rr",
                    "trades",
                    "net_r",
                    "profit_factor",
                    "robust_score",
                ]
            ]
            .head(
                args.final_n
            )
            .to_string(
                index=False
            )
        )

        con.close()

        return

    # --------------------------------------------------------
    # ONE BEST RR PER UNIQUE STRATEGY
    # --------------------------------------------------------

    best_per_strategy = (
        eligible
        .sort_values(
            [
                "robust_score",
                "net_r",
                "profit_factor",
                "trades",
            ],
            ascending=False,
        )
        .drop_duplicates(
            [
                "direction",
                "session",
                "conditions",
            ],
            keep="first",
        )
        .copy()
    )

    best_per_strategy = (
        best_per_strategy
        .sort_values(
            [
                "robust_score",
                "net_r",
                "profit_factor",
                "trades",
            ],
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    best_per_strategy.insert(
        0,
        "rank",
        range(
            1,
            len(
                best_per_strategy
            ) + 1,
        ),
    )

    # --------------------------------------------------------
    # SAVE ALL RR RESULTS
    # --------------------------------------------------------

    s = (
        s.sort_values(
            [
                "meets_sample",
                "meets_frequency",
                "robust_score",
                "net_r",
            ],
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    s.insert(
        0,
        "overall_rank",
        range(
            1,
            len(s) + 1,
        ),
    )

    s.to_csv(
        str(args.out)
        + "_final.csv",
        index=False,
    )

    # --------------------------------------------------------
    # TOP FINAL
    # --------------------------------------------------------

    top = best_per_strategy.head(
        args.final_n
    ).copy()

    top.to_csv(
        str(args.out)
        + "_top_final.csv",
        index=False,
    )

    # --------------------------------------------------------
    # CHARTS
    # --------------------------------------------------------

    if args.charts and len(top):

        details = []

        for _, row in top.iterrows():

            matching = p[
                (p["period"] == "ALL")
                & (
                    p["direction"]
                    == row["direction"]
                )
                & (
                    p["session"]
                    == row["session"]
                )
                & (
                    p["conditions"]
                    == row["conditions"]
                )
                & (
                    np.isclose(
                        p["rr"],
                        row["rr"],
                    )
                )
            ]

            if matching.empty:

                details.append(
                    []
                )

                continue

            result_row = matching.iloc[
                0
            ]

            try:

                details.append(
                    json.loads(
                        result_row[
                            "result_json"
                        ]
                    )
                )

            except Exception:

                details.append(
                    []
                )

        top_with_details = (
            top.copy()
        )

        top_with_details[
            "_detail"
        ] = details

        save_trade_charts(
            df,
            top_with_details,
            str(args.out)
            + "_charts",
        )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    print(
        "\n============================================================"
    )

    print(
        "TOP FINAL"
    )

    print(
        "============================================================"
    )

    display_columns = [
        "rank",
        "direction",
        "session",
        "conditions",
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "avg_trades_day",
        "positive_years",
        "years_tested",
        "rr_stability",
        "robust_score",
    ]

    print(
        top[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        f"\nUnique strategies passing filters: "
        f"{len(best_per_strategy)}"
    )

    print(
        f"Saved: "
        f"{args.out}_final.csv"
    )

    print(
        f"Saved: "
        f"{args.out}_top_final.csv"
    )

    print(
        f"Saved: "
        f"{args.out}_periods.csv"
    )

    print(
        f"Cache: "
        f"{args.db}"
    )

    if args.charts:

        print(
            f"Charts: "
            f"{args.out}_charts"
        )

    con.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()