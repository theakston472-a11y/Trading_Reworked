"""
Strategy Laboratory

Purpose
-------
Tests promoted trading strategies across an RR grid.

Features
--------
- Tests multiple candidate strategies.
- Sweeps RR from 1.0 to 7.0 (0.5 default step).
- Uses versioned SQLite caching.
- Supports yearly robustness testing.
- Handles overlapping trades with a maximum open-trade limit.
- Rejects zero-trade results.
- Measures RR stability.
- Selects only ONE best RR for each unique strategy.
- Supports next-open, signal-close and post-confirmation Fib-touch entries.
- Produces timestamp-aligned TradingView-style validation charts.

Important
---------
Signal masks always remain aligned to the full chronological period.
Session filtering is applied inside the mask rather than shortening the
dataframe. This prevents session-relative indices from being interpreted
against the wrong candles.

For Fib strategies, the default "auto" entry model waits for a Fib touch
AFTER the setup candle has closed. It intentionally does not pretend that
a completed-candle condition was known earlier inside that same candle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# Increment this whenever signal/execution logic changes.
# It is included in SQLite cache keys so corrected backtests never
# silently reuse results produced by older logic.
BACKTEST_ENGINE_VERSION = "2026-08-16-v9-directional-fib-gate"


# ============================================================
# RR GRID
# ============================================================

def rr_grid(
    start: float = 1.0,
    stop: float = 7.0,
    step: float = 0.5,
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
    entry_mode: str,
    entry_wait_bars: int,
) -> str:

    raw = (
        f"{BACKTEST_ENGINE_VERSION}|"
        f"{direction}|"
        f"{session}|"
        f"{conditions}|"
        f"{rr:.1f}|"
        f"{period}|"
        f"{max_bars}|"
        f"{max_open}|"
        f"{entry_mode}|"
        f"{entry_wait_bars}"
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
            entry_mode TEXT DEFAULT 'next_open',
            entry_wait_bars INTEGER DEFAULT 0,
            engine_version TEXT DEFAULT '',
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Existing user databases may have been created before the
    # execution-model columns existed. Migrate them in place.
    existing_columns = {
        row[1]
        for row in con.execute(
            "PRAGMA table_info(results)"
        ).fetchall()
    }

    migrations = [
        (
            "entry_mode",
            "TEXT DEFAULT 'next_open'",
        ),
        (
            "entry_wait_bars",
            "INTEGER DEFAULT 0",
        ),
        (
            "engine_version",
            "TEXT DEFAULT ''",
        ),
    ]

    for column, definition in migrations:

        if column not in existing_columns:

            con.execute(
                f"ALTER TABLE results "
                f"ADD COLUMN {column} {definition}"
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
        default=0.5,
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
        "--entry-mode",
        choices=[
            "auto",
            "next_open",
            "signal_close",
            "fib_touch",
        ],
        default="auto",
        help=(
            "Execution model. 'auto' uses a post-confirmation Fib "
            "touch for Fib strategies and next-open for non-Fib "
            "strategies. This avoids same-candle look-ahead."
        ),
    )

    parser.add_argument(
        "--entry-wait-bars",
        type=int,
        default=6,
        help=(
            "For fib_touch entries, number of bars after the signal "
            "to wait for price to touch the selected Fib level."
        ),
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

def _bool_array(
    series: pd.Series,
) -> np.ndarray:
    """
    Safe boolean conversion for CSV-loaded feature columns.

    Important: bool("False") is True in Python, so object/string
    columns must be parsed explicitly.
    """

    if pd.api.types.is_bool_dtype(
        series
    ):

        return (
            series
            .fillna(False)
            .to_numpy(dtype=bool)
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
            .to_numpy()
        )

    values = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    return values.isin(
        {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }
    ).to_numpy()


def signal_indices(
    df: pd.DataFrame,
    direction: str,
    session: str,
    conditions: str,
) -> np.ndarray:
    """
    Return positions relative to the ORIGINAL dataframe passed in.

    The previous implementation filtered the dataframe by session
    first and then returned positions inside that shortened frame.
    backtest() interpreted those positions against the unfiltered
    period dataframe, which could attach a New York signal to an
    Asia/London candle.  The mask now always stays full-length.
    """

    mask = np.ones(
        len(df),
        dtype=bool,
    )

    requested_session = str(
        session
    ).strip().lower()

    if requested_session not in (
        "",
        "all",
        "nan",
        "none",
    ):

        session_values = (
            df["session"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .to_numpy()
        )

        mask &= (
            session_values
            == requested_session
        )

    condition_list = [
        x.strip()
        for x in str(
            conditions
        ).split("+")
        if x.strip()
    ]

    for condition in condition_list:

        if condition not in df.columns:

            return np.array(
                [],
                dtype=np.int64,
            )

        mask &= _bool_array(
            df[condition]
        )

    # DIRECTIONAL FIB GATE V9
    #
    # Even generic conditions such as near_fib_382,
    # near_fib_500 or near_fib_618 must agree with
    # the requested trade direction.
    if any(
        "fib" in str(condition).lower()
        for condition in condition_list
    ):
        fib_direction_col = (
            "fib_bullish"
            if str(direction).upper().strip() == "BUY"
            else "fib_bearish"
        )

        if fib_direction_col not in df.columns:
            return np.array(
                [],
                dtype=np.int64,
            )

        mask &= _bool_array(
            df[fib_direction_col]
        )

    return np.flatnonzero(
        mask
    ).astype(
        np.int64
    )

# ============================================================
# BACKTEST

# ============================================================
# BACKTEST
# ============================================================

def _condition_names(
    conditions: str,
) -> list[str]:

    return [
        item.strip().lower()
        for item in str(
            conditions
        ).split("+")
        if item.strip()
    ]


def _fib_ratios_in_conditions(
    conditions: str,
) -> list[int]:

    names = _condition_names(
        conditions
    )

    found = []

    for ratio in (
        382,
        500,
        618,
    ):

        token = (
            f"fib_{ratio}"
        )

        if any(
            token in name
            for name in names
        ):

            found.append(
                ratio
            )

    return found


def _selected_fib_entry(
    df: pd.DataFrame,
    signal_i: int,
    conditions: str,
):

    ratios = _fib_ratios_in_conditions(
        conditions
    )

    if not ratios:
        return None

    # When a strategy references more than one Fib level,
    # use the deepest referenced retracement as the pending
    # entry.  Example: 38.2 + 50.0 -> entry at 50.0.
    ratio = max(
        ratios
    )

    column = (
        f"fib_{ratio}"
    )

    if column not in df.columns:
        return None

    try:

        price = float(
            df.iloc[
                signal_i
            ][column]
        )

    except Exception:
        return None

    if not np.isfinite(
        price
    ):
        return None

    return {
        "price": price,
        "ratio": ratio,
        "label": (
            f"FIB {ratio / 10.0:.1f}%"
        ),
    }


def _resolve_entry(
    df: pd.DataFrame,
    signal_i: int,
    conditions: str,
    entry_mode: str,
    entry_wait_bars: int,
):
    """
    Resolve a trade entry without same-candle look-ahead.

    next_open:
        Original behaviour.

    signal_close:
        Enter at the signal candle close. Trade outcome starts on
        the following candle because the close is only known when
        that signal candle has completed.

    fib_touch:
        After the signal candle has completed, place a pending
        order at the deepest Fib level referenced by the strategy.
        The order fills only when a later candle trades through it.

    auto:
        fib_touch for Fib strategies when a valid Fib level exists;
        otherwise next_open.
    """

    mode = str(
        entry_mode
    ).strip().lower()

    fib_entry = _selected_fib_entry(
        df,
        signal_i,
        conditions,
    )

    if mode == "auto":

        if fib_entry is not None:
            mode = "fib_touch"

        else:
            mode = "next_open"

    if mode == "signal_close":

        try:

            price = float(
                df.iloc[
                    signal_i
                ]["close"]
            )

        except Exception:
            return None

        if not np.isfinite(
            price
        ):
            return None

        return {
            "entry_i": int(
                signal_i
            ),
            "entry_price": price,
            "outcome_start_i": int(
                signal_i + 1
            ),
            "entry_mode": "signal_close",
            "entry_level": "SIGNAL CLOSE",
            "entry_level_ratio": None,
        }

    if mode == "fib_touch":

        if fib_entry is None:
            return None

        level = float(
            fib_entry["price"]
        )

        first_i = (
            signal_i + 1
        )

        last_i = min(
            len(df) - 1,
            signal_i
            + max(
                int(entry_wait_bars),
                1,
            ),
        )

        for entry_i in range(
            first_i,
            last_i + 1,
        ):

            try:

                low = float(
                    df.iloc[
                        entry_i
                    ]["low"]
                )

                high = float(
                    df.iloc[
                        entry_i
                    ]["high"]
                )

            except Exception:
                continue

            if (
                np.isfinite(low)
                and np.isfinite(high)
                and low <= level <= high
            ):

                return {
                    "entry_i": int(
                        entry_i
                    ),
                    "entry_price": level,
                    "outcome_start_i": int(
                        entry_i
                    ),
                    "entry_mode": "fib_touch",
                    "entry_level": fib_entry[
                        "label"
                    ],
                    "entry_level_ratio": fib_entry[
                        "ratio"
                    ],
                }

        # Setup confirmed, but no Fib retest/touch occurred in the
        # allowed entry window. This is correctly treated as no trade.
        return None

    # Original next-open model.
    entry_i = (
        signal_i + 1
    )

    if entry_i >= len(df):
        return None

    try:

        price = float(
            df.iloc[
                entry_i
            ]["open"]
        )

    except Exception:
        return None

    if not np.isfinite(
        price
    ):
        return None

    return {
        "entry_i": int(
            entry_i
        ),
        "entry_price": price,
        "outcome_start_i": int(
            entry_i
        ),
        "entry_mode": "next_open",
        "entry_level": "NEXT OPEN",
        "entry_level_ratio": None,
    }


def backtest(
    df: pd.DataFrame,
    indices: np.ndarray,
    direction: str,
    conditions: str,
    rr: float,
    max_bars: int,
    max_open: int,
    entry_mode: str = "auto",
    entry_wait_bars: int = 6,
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

        resolved = _resolve_entry(
            df,
            signal_i,
            conditions,
            entry_mode,
            entry_wait_bars,
        )

        if resolved is None:
            continue

        entry_i = int(
            resolved[
                "entry_i"
            ]
        )

        outcome_start_i = int(
            resolved[
                "outcome_start_i"
            ]
        )

        if (
            entry_i >= len(df)
            or outcome_start_i >= len(df)
        ):
            continue

        # Max-open is checked at the ACTUAL fill time, not at the
        # signal time. Pending Fib orders are not counted as open.
        active = [
            exit_i
            for exit_i in active
            if exit_i >= entry_i
        ]

        if len(active) >= max_open:
            continue

        entry = float(
            resolved[
                "entry_price"
            ]
        )

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
            outcome_start_i
            + max_bars - 1,
        )

        outcome = None

        exit_i = end_i

        reason = "TIME"

        exit_price = float(
            cl[
                exit_i
            ]
        )

        for j in range(
            outcome_start_i,
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

            # With OHLC data the exact path inside one candle is
            # unknown. If both SL and TP are possible, count SL
            # first. This is intentionally conservative.
            if stop_hit:

                outcome = -1.0

                exit_i = j

                exit_price = float(
                    sl
                )

                reason = "SL"

                break

            if target_hit:

                outcome = float(
                    rr
                )

                exit_i = j

                exit_price = float(
                    tp
                )

                reason = "TP"

                break

        if outcome is None:

            exit_price = float(
                cl[
                    exit_i
                ]
            )

            if direction_upper == "SELL":

                move = (
                    entry
                    - exit_price
                )

            else:

                move = (
                    exit_price
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
                "exit_i": int(
                    exit_i
                ),
                "entry": float(
                    entry
                ),
                "sl": float(
                    sl
                ),
                "tp": float(
                    tp
                ),
                "exit_price": float(
                    exit_price
                ),
                "outcome_r": float(
                    outcome
                ),
                "reason": reason,
                "entry_mode": resolved[
                    "entry_mode"
                ],
                "entry_level": resolved[
                    "entry_level"
                ],
                "entry_level_ratio": resolved[
                    "entry_level_ratio"
                ],
                "signal_time": str(
                    df.iloc[
                        signal_i
                    ][
                        "timestamp"
                    ]
                ),
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
    Clean TradingView-style visual validation.

    The chart is timestamp-aligned and, when the rebuilt feature
    database contains the corrected Fib anchor columns, draws the
    exact swing low/high that generated the strategy's Fib levels.
    """

    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_dir = Path(
        outdir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    work = df.copy()

    work["timestamp"] = pd.to_datetime(
        work["timestamp"],
        utc=True,
        errors="coerce",
    )

    work = (
        work
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
        "fib_tolerance",
        "fib_swing_high",
        "fib_swing_low",
        "fib_swing_high_index",
        "fib_swing_low_index",
        "liquidity_sweep_high_level",
        "liquidity_sweep_low_level",
        "liquidity_sweep_high_wick_ratio",
        "liquidity_sweep_low_wick_ratio",
        "bullish_fvg_low",
        "bullish_fvg_high",
        "bearish_fvg_low",
        "bearish_fvg_high",
        "active_bullish_order_block_low",
        "active_bullish_order_block_high",
        "active_bearish_order_block_low",
        "active_bearish_order_block_high",
        "active_bullish_breaker_low",
        "active_bullish_breaker_high",
        "active_bearish_breaker_low",
        "active_bearish_breaker_high",
    ]

    for column in numeric_columns:

        if column in work.columns:

            work[column] = pd.to_numeric(
                work[column],
                errors="coerce",
            )

    CYAN = "#00E5FF"
    GREEN = "#55DD99"
    RED = "#FF7777"

    def number(
        value,
    ):

        try:

            value = float(
                value
            )

            if np.isfinite(
                value
            ):
                return value

        except Exception:
            pass

        return None

    def boolean(
        value,
    ):

        if pd.isna(
            value
        ):
            return False

        if isinstance(
            value,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(
                value
            )

        return str(
            value
        ).strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }

    def nearest_index(
        value,
    ):

        try:

            timestamp = pd.to_datetime(
                value,
                utc=True,
                errors="coerce",
            )

            if pd.isna(
                timestamp
            ):
                return None

            differences = (
                work["timestamp"]
                - timestamp
            ).abs()

            if differences.empty:
                return None

            index = int(
                differences.idxmin()
            )

            if differences.loc[
                index
            ] > pd.Timedelta(
                minutes=20
            ):
                return None

            return index

        except Exception:
            return None

    def conditions_set(
        row,
    ):

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

    def recent_event(
        column,
        end_i,
        lookback=120,
    ):
        if column not in work.columns:
            return None

        start_i = max(
            0,
            end_i - lookback,
        )

        for i in range(
            end_i,
            start_i - 1,
            -1,
        ):
            if boolean(
                work.iloc[i].get(
                    column,
                    False,
                )
            ):
                return i

        return None

    def fib_ratios(
        conditions,
    ):

        output = []

        for ratio in (
            382,
            500,
            618,
        ):

            token = (
                f"fib_{ratio}"
            )

            if any(
                token in condition
                for condition in conditions
            ):

                output.append(
                    ratio
                )

        return output

    def find_old_style_anchor(
        signal_i,
        target_price,
        marker_column,
        price_column,
        lookback=120,
    ):
        """
        Backwards-compatible fallback for a feature DB made before
        fib_swing_* anchor columns were added.
        """

        if (
            marker_column not in work.columns
            or price_column not in work.columns
        ):
            return None

        start = max(
            0,
            signal_i - lookback,
        )

        candidates = []

        for i in range(
            start,
            signal_i + 1,
        ):

            if not boolean(
                work.iloc[
                    i
                ][
                    marker_column
                ]
            ):
                continue

            value = number(
                work.iloc[
                    i
                ][
                    price_column
                ]
            )

            if value is None:
                continue

            candidates.append(
                (
                    abs(
                        value
                        - target_price
                    ),
                    i,
                )
            )

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda item: item[0],
        )[1]

    def fib_information(
        signal_i,
        conditions,
    ):

        if not any(
            "fib" in condition
            for condition in conditions
        ):
            return None

        signal_row = work.iloc[
            signal_i
        ]

        f382 = number(
            signal_row.get(
                "fib_382"
            )
        )

        f500 = number(
            signal_row.get(
                "fib_500"
            )
        )

        f618 = number(
            signal_row.get(
                "fib_618"
            )
        )

        if None in (
            f382,
            f500,
            f618,
        ):
            return None

        bullish = boolean(
            signal_row.get(
                "fib_bullish"
            )
        )

        bearish = boolean(
            signal_row.get(
                "fib_bearish"
            )
        )

        swing_high = number(
            signal_row.get(
                "fib_swing_high"
            )
        )

        swing_low = number(
            signal_row.get(
                "fib_swing_low"
            )
        )

        high_i = number(
            signal_row.get(
                "fib_swing_high_index"
            )
        )

        low_i = number(
            signal_row.get(
                "fib_swing_low_index"
            )
        )

        if high_i is not None:
            high_i = int(
                round(
                    high_i
                )
            )

        if low_i is not None:
            low_i = int(
                round(
                    low_i
                )
            )

        # Backward-compatible reconstruction if the user has not
        # rebuilt feature_database.csv yet.
        if (
            swing_high is None
            or swing_low is None
        ):

            if bullish:

                fib_range = (
                    f382 - f618
                ) / 0.236

                swing_high = (
                    f382
                    + fib_range * 0.382
                )

                swing_low = (
                    swing_high
                    - fib_range
                )

            elif bearish:

                fib_range = (
                    f618 - f382
                ) / 0.236

                swing_low = (
                    f382
                    - fib_range * 0.382
                )

                swing_high = (
                    swing_low
                    + fib_range
                )

        if (
            swing_high is None
            or swing_low is None
            or swing_high <= swing_low
        ):
            return None

        if high_i is None:

            high_i = find_old_style_anchor(
                signal_i,
                swing_high,
                "swing_high",
                "high",
            )

        if low_i is None:

            low_i = find_old_style_anchor(
                signal_i,
                swing_low,
                "swing_low",
                "low",
            )

        # Source indices should refer to already-known pivots.
        if high_i is not None:

            if not (
                0
                <= high_i
                < len(work)
                and high_i < signal_i
            ):
                high_i = None

        if low_i is not None:

            if not (
                0
                <= low_i
                < len(work)
                and low_i < signal_i
            ):
                low_i = None

        return {
            "bullish": bullish,
            "bearish": bearish,
            "high": swing_high,
            "low": swing_low,
            "high_i": high_i,
            "low_i": low_i,
            "382": f382,
            "500": f500,
            "618": f618,
            "used_ratios": fib_ratios(
                conditions
            ),
            "tolerance": (
                number(
                    signal_row.get(
                        "fib_tolerance"
                    )
                )
                or number(
                    signal_row.get(
                        "atr14"
                    )
                )
                * 0.20
                if number(
                    signal_row.get(
                        "atr14"
                    )
                ) is not None
                else None
            ),
        }

    def choose_examples(
        trades,
        limit=2,
    ):
        """
        Prefer examples that show an actual TP and SL. If one side is
        unavailable, include TIME trades and then fill by chronology.
        """

        if not trades:
            return []

        selected = []

        for reason in (
            "TP",
            "SL",
            "TIME",
        ):

            for trade in trades:

                if str(
                    trade.get(
                        "reason",
                        "",
                    )
                ).upper() == reason:

                    if trade not in selected:

                        selected.append(
                            trade
                        )

                    break

                if len(
                    selected
                ) >= limit:
                    break

            if len(
                selected
            ) >= limit:
                break

        if len(
            selected
        ) < limit:

            for trade in trades:

                if trade not in selected:

                    selected.append(
                        trade
                    )

                if len(
                    selected
                ) >= limit:
                    break

        return selected[
            :limit
        ]

    for _, row in final_df.iterrows():

        trades = row.get(
            "_detail"
        )

        if not trades:
            continue

        conditions = conditions_set(
            row
        )

        bullish_smc_context = any(
            condition in {
                "bullish_liquidity_structure_shift",
                "bullish_liquidity_fvg_setup",
                "bullish_smc_reversal_setup",
                "bullish_smc_fvg_retest",
            }
            for condition in conditions
        )

        bearish_smc_context = any(
            condition in {
                "bearish_liquidity_structure_shift",
                "bearish_liquidity_fvg_setup",
                "bearish_smc_reversal_setup",
                "bearish_smc_fvg_retest",
            }
            for condition in conditions
        )

        direction = str(
            row.get(
                "direction",
                "",
            )
        ).upper()

        examples = choose_examples(
            trades,
            limit=2,
        )

        for trade_number, trade in enumerate(
            examples,
            start=1,
        ):

            entry_i = nearest_index(
                trade.get(
                    "entry_time"
                )
            )

            exit_i = nearest_index(
                trade.get(
                    "exit_time"
                )
            )

            signal_i = nearest_index(
                trade.get(
                    "signal_time"
                )
            )

            if entry_i is None:
                continue

            if signal_i is None:

                # Compatibility with old cached details.
                signal_i = max(
                    0,
                    entry_i - 1,
                )

            if exit_i is None:

                exit_i = min(
                    len(work) - 1,
                    entry_i + 12,
                )

            if exit_i < entry_i:

                exit_i = entry_i

            entry_price = number(
                trade.get(
                    "entry"
                )
            )

            stop_price = number(
                trade.get(
                    "sl"
                )
            )

            target_price = number(
                trade.get(
                    "tp"
                )
            )

            exit_price = number(
                trade.get(
                    "exit_price"
                )
            )

            if None in (
                entry_price,
                stop_price,
                target_price,
            ):
                continue

            fib = fib_information(
                signal_i,
                conditions,
            )

            # ==================================================
            # CHART WINDOW
            # ==================================================

            start_i = max(
                0,
                signal_i - 16,
            )

            if fib:

                anchors = [
                    i
                    for i in (
                        fib["low_i"],
                        fib["high_i"],
                    )
                    if i is not None
                ]

                if anchors:

                    earliest_anchor = min(
                        anchors
                    )

                    # Include the full actual swing when it is still
                    # readable. Otherwise keep the setup readable.
                    if (
                        signal_i
                        - earliest_anchor
                        <= 90
                    ):

                        start_i = min(
                            start_i,
                            max(
                                0,
                                earliest_anchor - 4,
                            ),
                        )

            end_i = min(
                len(work) - 1,
                max(
                    exit_i + 8,
                    entry_i + 14,
                ),
            )

            chart = (
                work.iloc[
                    start_i:end_i + 1
                ]
                .copy()
                .reset_index(
                    drop=True
                )
            )

            if chart.empty:
                continue

            signal_x = (
                signal_i
                - start_i
            )

            entry_x = (
                entry_i
                - start_i
            )

            exit_x = (
                exit_i
                - start_i
            )

            # ==================================================
            # FIGURE
            # ==================================================

            fig, ax = plt.subplots(
                figsize=(
                    18,
                    10,
                ),
                dpi=170,
            )

            fig.patch.set_facecolor(
                "black"
            )

            ax.set_facecolor(
                "black"
            )

            # ==================================================
            # FIB RETRACEMENT TOOL
            # ==================================================

            if fib:

                low_i = fib[
                    "low_i"
                ]

                high_i = fib[
                    "high_i"
                ]

                anchor_visible = (
                    low_i is not None
                    and high_i is not None
                    and start_i <= low_i <= end_i
                    and start_i <= high_i <= end_i
                )

                if fib[
                    "bullish"
                ]:

                    impulse_start_i = (
                        low_i
                    )

                    impulse_end_i = (
                        high_i
                    )

                    impulse_start_price = fib[
                        "low"
                    ]

                    impulse_end_price = fib[
                        "high"
                    ]

                    level_zero = fib[
                        "high"
                    ]

                    level_one = fib[
                        "low"
                    ]

                else:

                    impulse_start_i = (
                        high_i
                    )

                    impulse_end_i = (
                        low_i
                    )

                    impulse_start_price = fib[
                        "high"
                    ]

                    impulse_end_price = fib[
                        "low"
                    ]

                    level_zero = fib[
                        "low"
                    ]

                    level_one = fib[
                        "high"
                    ]

                if anchor_visible:

                    impulse_start_x = (
                        impulse_start_i
                        - start_i
                    )

                    impulse_end_x = (
                        impulse_end_i
                        - start_i
                    )

                    # The diagonal cyan anchor connects the TRUE
                    # swing bottom/top used by the feature engine.
                    ax.plot(
                        [
                            impulse_start_x,
                            impulse_end_x,
                        ],
                        [
                            impulse_start_price,
                            impulse_end_price,
                        ],
                        color=CYAN,
                        linewidth=1.6,
                        alpha=0.90,
                        zorder=5,
                    )

                    ax.scatter(
                        [
                            impulse_start_x,
                            impulse_end_x,
                        ],
                        [
                            impulse_start_price,
                            impulse_end_price,
                        ],
                        s=55,
                        color=CYAN,
                        edgecolors="black",
                        linewidths=0.8,
                        zorder=12,
                    )

                    fib_left = (
                        impulse_end_x
                    )

                else:

                    # Anchor is too far back for a readable chart.
                    fib_left = max(
                        0,
                        signal_x - 10,
                    )

                fib_right = min(
                    len(chart) - 0.5,
                    max(
                        entry_x + 1.2,
                        signal_x + 2.0,
                    ),
                )

                if fib_right <= fib_left:

                    fib_left = max(
                        0,
                        signal_x - 8,
                    )

                # Small cyan retracement rectangle.  This is the
                # area traders usually focus on, rather than a set
                # of full-chart horizontal lines.
                zone_low = min(
                    fib[
                        "382"
                    ],
                    fib[
                        "618"
                    ],
                )

                zone_high = max(
                    fib[
                        "382"
                    ],
                    fib[
                        "618"
                    ],
                )

                ax.add_patch(
                    Rectangle(
                        (
                            fib_left,
                            zone_low,
                        ),
                        max(
                            fib_right
                            - fib_left,
                            1.0,
                        ),
                        zone_high
                        - zone_low,
                        facecolor=CYAN,
                        edgecolor=CYAN,
                        linewidth=1.0,
                        alpha=0.075,
                        zorder=2,
                    )
                )

                levels = [
                    (
                        level_zero,
                        "0.0%",
                        None,
                    ),
                    (
                        fib["382"],
                        "38.2%",
                        382,
                    ),
                    (
                        fib["500"],
                        "50.0%",
                        500,
                    ),
                    (
                        fib["618"],
                        "61.8%",
                        618,
                    ),
                    (
                        level_one,
                        "100%",
                        None,
                    ),
                ]

                entry_ratio = trade.get(
                    "entry_level_ratio"
                )

                for price, label, ratio in levels:

                    is_entry_level = (
                        entry_ratio is not None
                        and ratio is not None
                        and int(
                            entry_ratio
                        ) == int(
                            ratio
                        )
                    )

                    is_strategy_level = (
                        ratio is not None
                        and ratio in fib[
                            "used_ratios"
                        ]
                    )

                    linewidth = (
                        1.8
                        if is_entry_level
                        else (
                            1.25
                            if is_strategy_level
                            else 0.8
                        )
                    )

                    alpha = (
                        1.0
                        if is_entry_level
                        else (
                            0.82
                            if is_strategy_level
                            else 0.48
                        )
                    )

                    linestyle = (
                        "-"
                        if is_entry_level
                        else "--"
                    )

                    ax.hlines(
                        price,
                        fib_left,
                        fib_right,
                        colors=CYAN,
                        linestyles=linestyle,
                        linewidth=linewidth,
                        alpha=alpha,
                        zorder=4,
                    )

                    suffix = ""

                    if is_entry_level:

                        suffix = (
                            "  ← ENTRY LEVEL"
                        )

                    elif is_strategy_level:

                        suffix = (
                            "  ← SETUP"
                        )

                    ax.text(
                        fib_right + 0.20,
                        price,
                        (
                            f"{label}  "
                            f"{price:.5f}"
                            f"{suffix}"
                        ),
                        color=CYAN,
                        fontsize=8.5,
                        va="center",
                        fontweight=(
                            "bold"
                            if (
                                is_entry_level
                                or is_strategy_level
                            )
                            else "normal"
                        ),
                        zorder=12,
                    )

            # ==================================================
            # RELEVANT EMA ONLY
            # ==================================================

            for ema_column, label in (
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
            ):

                if not any(
                    ema_column
                    in condition
                    for condition in conditions
                ):
                    continue

                if ema_column not in chart.columns:
                    continue

                values = pd.to_numeric(
                    chart[
                        ema_column
                    ],
                    errors="coerce",
                )

                ax.plot(
                    range(
                        len(chart)
                    ),
                    values,
                    linewidth=1.15,
                    alpha=0.80,
                    label=label,
                    zorder=3,
                )

            # ==================================================
            # RELEVANT LIQUIDITY SWEEP ONLY
            # ==================================================

            for (
                sweep_column,
                price_column,
                label,
            ) in (
                (
                    "liquidity_sweep_high",
                    "high",
                    "LIQUIDITY SWEEP HIGH",
                ),
                (
                    "liquidity_sweep_low",
                    "low",
                    "LIQUIDITY SWEEP LOW",
                ),
            ):

                show_for_smc = (
                    sweep_column == "liquidity_sweep_low"
                    and bullish_smc_context
                ) or (
                    sweep_column == "liquidity_sweep_high"
                    and bearish_smc_context
                )

                if sweep_column not in conditions and not show_for_smc:
                    continue

                found = None

                for original_i in range(
                    signal_i,
                    max(
                        -1,
                        signal_i - 9,
                    ),
                    -1,
                ):

                    if (
                        sweep_column
                        not in work.columns
                    ):
                        break

                    if boolean(
                        work.iloc[
                            original_i
                        ].get(
                            sweep_column,
                            False,
                        )
                    ):

                        found = (
                            original_i
                        )

                        break

                if found is None:
                    continue

                local_x = (
                    found
                    - start_i
                )

                level_column = (
                    "liquidity_sweep_high_level"
                    if sweep_column == "liquidity_sweep_high"
                    else "liquidity_sweep_low_level"
                )

                wick_ratio_column = (
                    "liquidity_sweep_high_wick_ratio"
                    if sweep_column == "liquidity_sweep_high"
                    else "liquidity_sweep_low_wick_ratio"
                )

                # Draw the actual liquidity pool that was taken,
                # not the wick tip itself.
                sweep_price = number(
                    work.iloc[found].get(
                        level_column
                    )
                )

                if sweep_price is None:
                    sweep_price = number(
                        work.iloc[found][price_column]
                    )

                wick_tip = number(
                    work.iloc[found][price_column]
                )

                wick_ratio = number(
                    work.iloc[found].get(
                        wick_ratio_column
                    )
                )

                if (
                    sweep_price is None
                    or wick_tip is None
                    or local_x < 0
                    or local_x >= len(chart)
                ):
                    continue

                left = max(
                    0,
                    local_x - 6,
                )

                right = min(
                    len(chart) - 1,
                    local_x + 4,
                )

                ax.hlines(
                    sweep_price,
                    left,
                    right,
                    colors="0.68",
                    linestyles=":",
                    linewidth=1.05,
                    alpha=0.80,
                    zorder=4,
                )

                # Highlight the stop-run wick through the level.
                ax.vlines(
                    local_x,
                    min(sweep_price, wick_tip),
                    max(sweep_price, wick_tip),
                    colors="0.82",
                    linewidth=2.2,
                    alpha=0.85,
                    zorder=9,
                )

                ratio_text = (
                    f"  |  WICK {wick_ratio * 100:.0f}%"
                    if wick_ratio is not None
                    else ""
                )

                ax.text(
                    left,
                    sweep_price,
                    " " + label + ratio_text,
                    color="0.72",
                    fontsize=8,
                    va=(
                        "bottom"
                        if price_column == "high"
                        else "top"
                    ),
                    zorder=10,
                )

            # ==================================================
            # SMC ZONE OVERLAYS — ONLY WHEN USED BY STRATEGY
            # ==================================================
            #
            # FVG / order-block / breaker rectangles are drawn
            # only when one of those features is part of the
            # strategy. This keeps normal charts uncluttered.
            # ==================================================

            def draw_zone(
                zone_low,
                zone_high,
                left_x,
                right_x,
                label,
                edge_color,
                alpha=0.09,
            ):
                if (
                    zone_low is None
                    or zone_high is None
                    or zone_high <= zone_low
                ):
                    return

                left_x = max(
                    0,
                    left_x,
                )

                right_x = min(
                    len(chart) - 0.5,
                    max(
                        right_x,
                        left_x + 1.0,
                    ),
                )

                ax.add_patch(
                    Rectangle(
                        (
                            left_x,
                            zone_low,
                        ),
                        right_x - left_x,
                        zone_high - zone_low,
                        facecolor=edge_color,
                        edgecolor=edge_color,
                        linewidth=1.0,
                        alpha=alpha,
                        zorder=2,
                    )
                )

                ax.text(
                    left_x + 0.2,
                    zone_high,
                    " " + label,
                    color=edge_color,
                    fontsize=8,
                    va="bottom",
                    fontweight="bold",
                    zorder=10,
                )

            # ---------------- FVG ----------------

            if (
                bullish_smc_context
                or any(
                    "bullish_fvg" in condition
                    for condition in conditions
                )
            ):
                event_i = recent_event(
                    "bullish_fvg",
                    signal_i,
                )

                zone_low = None
                zone_high = None

                if (
                    event_i is not None
                    and "bullish_fvg_low" in work.columns
                ):
                    zone_low = number(
                        work.iloc[event_i].get(
                            "bullish_fvg_low"
                        )
                    )
                    zone_high = number(
                        work.iloc[event_i].get(
                            "bullish_fvg_high"
                        )
                    )

                    draw_zone(
                        zone_low,
                        zone_high,
                        event_i - 2 - start_i,
                        signal_x + 3,
                        "BULLISH FVG",
                        "#9B8CFF",
                        alpha=0.10,
                    )

            if (
                bearish_smc_context
                or any(
                    "bearish_fvg" in condition
                    for condition in conditions
                )
            ):
                event_i = recent_event(
                    "bearish_fvg",
                    signal_i,
                )

                if (
                    event_i is not None
                    and "bearish_fvg_low" in work.columns
                ):
                    zone_low = number(
                        work.iloc[event_i].get(
                            "bearish_fvg_low"
                        )
                    )
                    zone_high = number(
                        work.iloc[event_i].get(
                            "bearish_fvg_high"
                        )
                    )

                    draw_zone(
                        zone_low,
                        zone_high,
                        event_i - 2 - start_i,
                        signal_x + 3,
                        "BEARISH FVG",
                        "#9B8CFF",
                        alpha=0.10,
                    )

            # ---------------- ORDER BLOCK ----------------

            if any(
                (
                    "bullish_order_block" in condition
                    or "demand_zone" in condition
                )
                for condition in conditions
            ):
                event_i = recent_event(
                    "bullish_order_block",
                    signal_i,
                )

                if event_i is not None:
                    zone_low = number(
                        work.iloc[event_i].get(
                            "bullish_order_block_low"
                        )
                    )
                    zone_high = number(
                        work.iloc[event_i].get(
                            "bullish_order_block_high"
                        )
                    )
                    source_i = number(
                        work.iloc[event_i].get(
                            "bullish_order_block_source_index"
                        )
                    )

                    left_x = (
                        int(source_i) - start_i
                        if source_i is not None
                        else event_i - start_i
                    )

                    draw_zone(
                        zone_low,
                        zone_high,
                        left_x,
                        signal_x + 3,
                        "BULLISH ORDER BLOCK / DEMAND",
                        "#F2C14E",
                        alpha=0.10,
                    )

            if any(
                (
                    "bearish_order_block" in condition
                    or "supply_zone" in condition
                )
                for condition in conditions
            ):
                event_i = recent_event(
                    "bearish_order_block",
                    signal_i,
                )

                if event_i is not None:
                    zone_low = number(
                        work.iloc[event_i].get(
                            "bearish_order_block_low"
                        )
                    )
                    zone_high = number(
                        work.iloc[event_i].get(
                            "bearish_order_block_high"
                        )
                    )
                    source_i = number(
                        work.iloc[event_i].get(
                            "bearish_order_block_source_index"
                        )
                    )

                    left_x = (
                        int(source_i) - start_i
                        if source_i is not None
                        else event_i - start_i
                    )

                    draw_zone(
                        zone_low,
                        zone_high,
                        left_x,
                        signal_x + 3,
                        "BEARISH ORDER BLOCK / SUPPLY",
                        "#F2C14E",
                        alpha=0.10,
                    )

            # ---------------- BREAKER BLOCK ----------------

            if any(
                "bullish_breaker" in condition
                for condition in conditions
            ):
                event_i = recent_event(
                    "bullish_breaker_block",
                    signal_i,
                )

                if event_i is not None:
                    draw_zone(
                        number(
                            work.iloc[event_i].get(
                                "bullish_breaker_low"
                            )
                        ),
                        number(
                            work.iloc[event_i].get(
                                "bullish_breaker_high"
                            )
                        ),
                        event_i - start_i,
                        signal_x + 3,
                        "BULLISH BREAKER",
                        "#FF9F43",
                        alpha=0.10,
                    )

            if any(
                "bearish_breaker" in condition
                for condition in conditions
            ):
                event_i = recent_event(
                    "bearish_breaker_block",
                    signal_i,
                )

                if event_i is not None:
                    draw_zone(
                        number(
                            work.iloc[event_i].get(
                                "bearish_breaker_low"
                            )
                        ),
                        number(
                            work.iloc[event_i].get(
                                "bearish_breaker_high"
                            )
                        ),
                        event_i - start_i,
                        signal_x + 3,
                        "BEARISH BREAKER",
                        "#FF9F43",
                        alpha=0.10,
                    )

            # ==================================================
            # BOS / CHOCH STRUCTURE LEVEL
            # ==================================================

            structure_specs = (
                (
                    "bullish_bos",
                    "bullish_structure_break_level",
                    "BULLISH BOS",
                ),
                (
                    "bearish_bos",
                    "bearish_structure_break_level",
                    "BEARISH BOS",
                ),
                (
                    "bullish_choch",
                    "bullish_structure_break_level",
                    "BULLISH CHOCH",
                ),
                (
                    "bearish_choch",
                    "bearish_structure_break_level",
                    "BEARISH CHOCH",
                ),
            )

            for (
                event_column,
                level_column,
                structure_label,
            ) in structure_specs:

                show_structure_for_smc = (
                    event_column in {"bullish_bos", "bullish_choch"}
                    and bullish_smc_context
                ) or (
                    event_column in {"bearish_bos", "bearish_choch"}
                    and bearish_smc_context
                )

                if event_column not in conditions and not show_structure_for_smc:
                    continue

                event_i = recent_event(
                    event_column,
                    signal_i,
                    lookback=40,
                )

                if event_i is None:
                    continue

                level = number(
                    work.iloc[event_i].get(
                        level_column
                    )
                )

                if level is None:
                    continue

                local_event_x = (
                    event_i - start_i
                )

                left_x = max(
                    0,
                    local_event_x - 8,
                )

                right_x = min(
                    len(chart) - 1,
                    local_event_x + 3,
                )

                ax.hlines(
                    level,
                    left_x,
                    right_x,
                    colors="0.80",
                    linestyles="--",
                    linewidth=1.15,
                    alpha=0.80,
                    zorder=4,
                )

                ax.scatter(
                    [local_event_x],
                    [level],
                    marker="D",
                    s=28,
                    facecolors="black",
                    edgecolors="white",
                    linewidths=1.0,
                    zorder=11,
                )

                ax.text(
                    left_x,
                    level,
                    " " + structure_label,
                    color="0.82",
                    fontsize=8,
                    va="bottom",
                    fontweight="bold",
                    zorder=11,
                )

            # ==================================================
            # RISK / REWARD BOXES
            # ==================================================

            box_left = (
                entry_x - 0.35
            )

            box_right = (
                exit_x + 0.45
            )

            box_width = max(
                box_right
                - box_left,
                1.5,
            )

            profit_low = min(
                entry_price,
                target_price,
            )

            profit_high = max(
                entry_price,
                target_price,
            )

            risk_low = min(
                entry_price,
                stop_price,
            )

            risk_high = max(
                entry_price,
                stop_price,
            )

            ax.add_patch(
                Rectangle(
                    (
                        box_left,
                        profit_low,
                    ),
                    box_width,
                    profit_high
                    - profit_low,
                    facecolor="#168F5B",
                    edgecolor=GREEN,
                    linewidth=1.0,
                    alpha=0.17,
                    zorder=1,
                )
            )

            ax.add_patch(
                Rectangle(
                    (
                        box_left,
                        risk_low,
                    ),
                    box_width,
                    risk_high
                    - risk_low,
                    facecolor="#9F3030",
                    edgecolor=RED,
                    linewidth=1.0,
                    alpha=0.19,
                    zorder=1,
                )
            )

            # ==================================================
            # SETUP CANDLE
            # ==================================================

            if (
                0
                <= signal_x
                < len(chart)
            ):

                signal_low = number(
                    chart.iloc[
                        signal_x
                    ][
                        "low"
                    ]
                )

                signal_high = number(
                    chart.iloc[
                        signal_x
                    ][
                        "high"
                    ]
                )

                if (
                    signal_low is not None
                    and signal_high is not None
                ):

                    ax.add_patch(
                        Rectangle(
                            (
                                signal_x
                                - 0.43,
                                signal_low,
                            ),
                            0.86,
                            max(
                                signal_high
                                - signal_low,
                                1e-8,
                            ),
                            facecolor="none",
                            edgecolor=CYAN,
                            linewidth=1.4,
                            alpha=0.90,
                            zorder=9,
                        )
                    )

                    ax.text(
                        signal_x,
                        signal_high,
                        " SETUP",
                        color=CYAN,
                        fontsize=8.5,
                        fontweight="bold",
                        ha="center",
                        va="bottom",
                        zorder=14,
                    )

            # ==================================================
            # SMC OPPOSING-LIQUIDITY TARGET
            # ==================================================

            if bullish_smc_context and "bullish_smc_target_high" in work.columns:
                target_price = number(
                    work.iloc[signal_i].get("bullish_smc_target_high")
                )
                if target_price is not None:
                    ax.hlines(
                        target_price,
                        max(0, signal_x - 10),
                        min(len(chart) - 1, signal_x + 6),
                        colors="#D8D8D8",
                        linestyles=":",
                        linewidth=1.0,
                        alpha=0.70,
                        zorder=4,
                    )
                    ax.text(
                        max(0, signal_x - 10),
                        target_price,
                        " TARGET HIGH / BUY-SIDE LIQUIDITY",
                        color="0.78",
                        fontsize=8,
                        va="bottom",
                        zorder=10,
                    )

            if bearish_smc_context and "bearish_smc_target_low" in work.columns:
                target_price = number(
                    work.iloc[signal_i].get("bearish_smc_target_low")
                )
                if target_price is not None:
                    ax.hlines(
                        target_price,
                        max(0, signal_x - 10),
                        min(len(chart) - 1, signal_x + 6),
                        colors="#D8D8D8",
                        linestyles=":",
                        linewidth=1.0,
                        alpha=0.70,
                        zorder=4,
                    )
                    ax.text(
                        max(0, signal_x - 10),
                        target_price,
                        " TARGET LOW / SELL-SIDE LIQUIDITY",
                        color="0.78",
                        fontsize=8,
                        va="top",
                        zorder=10,
                    )

            # ==================================================
            # CANDLES
            # ==================================================

            highs = []
            lows = []

            candle_width = (
                0.68
            )

            for x, candle in chart.iterrows():

                candle_open = number(
                    candle[
                        "open"
                    ]
                )

                candle_high = number(
                    candle[
                        "high"
                    ]
                )

                candle_low = number(
                    candle[
                        "low"
                    ]
                )

                candle_close = number(
                    candle[
                        "close"
                    ]
                )

                if None in (
                    candle_open,
                    candle_high,
                    candle_low,
                    candle_close,
                ):
                    continue

                highs.append(
                    candle_high
                )

                lows.append(
                    candle_low
                )

                ax.vlines(
                    x,
                    candle_low,
                    candle_high,
                    color="white",
                    linewidth=1.15,
                    zorder=8,
                )

                body_low = min(
                    candle_open,
                    candle_close,
                )

                body_height = max(
                    abs(
                        candle_close
                        - candle_open
                    ),
                    max(
                        candle_high
                        - candle_low,
                        1e-8,
                    )
                    * 0.03,
                )

                bullish_candle = (
                    candle_close
                    >= candle_open
                )

                ax.add_patch(
                    Rectangle(
                        (
                            x
                            - candle_width
                            / 2,
                            body_low,
                        ),
                        candle_width,
                        body_height,
                        facecolor=(
                            "white"
                            if bullish_candle
                            else "black"
                        ),
                        edgecolor="white",
                        linewidth=1.05,
                        zorder=10,
                    )
                )

            if not highs:
                plt.close(
                    fig
                )
                continue

            # ==================================================
            # ENTRY / STOP / TARGET
            # ==================================================

            ax.hlines(
                entry_price,
                box_left,
                box_right,
                colors="white",
                linewidth=1.45,
                zorder=12,
            )

            ax.hlines(
                stop_price,
                box_left,
                box_right,
                colors=RED,
                linestyles="--",
                linewidth=1.2,
                zorder=12,
            )

            ax.hlines(
                target_price,
                box_left,
                box_right,
                colors=GREEN,
                linestyles="--",
                linewidth=1.2,
                zorder=12,
            )

            price_label_x = (
                box_right
                + 0.25
            )

            ax.text(
                price_label_x,
                entry_price,
                (
                    f"ENTRY "
                    f"{entry_price:.5f}"
                ),
                color="white",
                fontsize=9,
                va="center",
                fontweight="bold",
                zorder=14,
            )

            ax.text(
                price_label_x,
                stop_price,
                (
                    f"SL "
                    f"{stop_price:.5f}"
                ),
                color=RED,
                fontsize=9,
                va="center",
                fontweight="bold",
                zorder=14,
            )

            ax.text(
                price_label_x,
                target_price,
                (
                    f"TP "
                    f"{target_price:.5f}"
                ),
                color=GREEN,
                fontsize=9,
                va="center",
                fontweight="bold",
                zorder=14,
            )

            # ==================================================
            # ENTRY MARKER
            # ==================================================

            visible_range = max(
                max(
                    highs
                )
                - min(
                    lows
                ),
                1e-8,
            )

            marker_offset = (
                visible_range
                * 0.035
            )

            entry_label = str(
                trade.get(
                    "entry_level",
                    "ENTRY",
                )
            )

            if direction == "BUY":

                ax.annotate(
                    (
                        "BUY\n"
                        + entry_label
                    ),
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
                    fontsize=8.5,
                    fontweight="bold",
                    ha="center",
                    va="top",
                    arrowprops=dict(
                        arrowstyle="-|>",
                        color="white",
                        linewidth=1.2,
                    ),
                    zorder=15,
                )

            else:

                ax.annotate(
                    (
                        "SELL\n"
                        + entry_label
                    ),
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
                    fontsize=8.5,
                    fontweight="bold",
                    ha="center",
                    va="bottom",
                    arrowprops=dict(
                        arrowstyle="-|>",
                        color="white",
                        linewidth=1.2,
                    ),
                    zorder=15,
                )

            # ==================================================
            # EXACT EXIT MARKER
            # ==================================================

            reason = str(
                trade.get(
                    "reason",
                    "TIME",
                )
            ).upper()

            result_r = number(
                trade.get(
                    "outcome_r"
                )
            )

            if result_r is None:
                result_r = 0.0

            if reason == "TP":

                displayed_exit = (
                    target_price
                )

                exit_label = (
                    f"TP HIT  "
                    f"{result_r:+.2f}R"
                )

                exit_color = (
                    GREEN
                )

            elif reason == "SL":

                displayed_exit = (
                    stop_price
                )

                exit_label = (
                    "SL HIT  -1.00R"
                )

                exit_color = (
                    RED
                )

            else:

                if exit_price is None:

                    exit_price = number(
                        work.iloc[
                            exit_i
                        ][
                            "close"
                        ]
                    )

                displayed_exit = (
                    exit_price
                )

                exit_label = (
                    f"TIME EXIT  "
                    f"{result_r:+.2f}R"
                )

                exit_color = (
                    "white"
                )

            if displayed_exit is not None:

                ax.scatter(
                    [
                        exit_x
                    ],
                    [
                        displayed_exit
                    ],
                    marker="X",
                    s=105,
                    color=exit_color,
                    edgecolors="black",
                    linewidths=0.9,
                    zorder=16,
                )

                ax.text(
                    exit_x
                    + 0.35,
                    displayed_exit,
                    exit_label,
                    color=exit_color,
                    fontsize=9,
                    fontweight="bold",
                    va="center",
                    zorder=16,
                )

            # ==================================================
            # AXES
            # ==================================================

            y_values = (
                highs
                + lows
                + [
                    entry_price,
                    stop_price,
                    target_price,
                ]
            )

            if fib:

                y_values.extend(
                    [
                        fib[
                            "low"
                        ],
                        fib[
                            "high"
                        ],
                    ]
                )

            y_min = min(
                y_values
            )

            y_max = max(
                y_values
            )

            y_range = max(
                y_max
                - y_min,
                1e-8,
            )

            ax.set_ylim(
                y_min
                - y_range
                * 0.07,
                y_max
                + y_range
                * 0.07,
            )

            ax.set_xlim(
                -1,
                len(chart)
                + 7,
            )

            tick_count = min(
                9,
                len(chart),
            )

            if tick_count > 1:

                positions = np.linspace(
                    0,
                    len(chart) - 1,
                    tick_count,
                    dtype=int,
                )

                labels = [
                    chart.iloc[
                        position
                    ][
                        "timestamp"
                    ].strftime(
                        "%d %b\n%H:%M"
                    )
                    for position in positions
                ]

                ax.set_xticks(
                    positions
                )

                ax.set_xticklabels(
                    labels,
                    fontsize=8,
                    color="0.75",
                )

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
            ].set_visible(
                False
            )

            ax.spines[
                "right"
            ].set_visible(
                False
            )

            ax.spines[
                "left"
            ].set_color(
                "0.30"
            )

            ax.spines[
                "bottom"
            ].set_color(
                "0.30"
            )

            ax.set_ylabel(
                "PRICE",
                color="0.70",
                fontsize=9,
            )

            # ==================================================
            # TITLE / INFO
            # ==================================================

            rank_value = int(
                row.get(
                    "rank",
                    0,
                )
            )

            rr_value = float(
                row.get(
                    "rr",
                    0,
                )
            )

            entry_mode = str(
                trade.get(
                    "entry_mode",
                    row.get(
                        "entry_mode",
                        "",
                    ),
                )
            )

            ax.set_title(
                (
                    f"RANK {rank_value}  |  "
                    f"{direction}  |  "
                    f"{row.get('session', '')}  |  "
                    f"RR {rr_value:.1f}\n"
                    f"{row.get('conditions', '')}  |  "
                    f"{reason}  |  "
                    f"{result_r:+.2f}R"
                ),
                loc="left",
                color="white",
                fontsize=13.5,
                fontweight="bold",
                pad=14,
            )

            information = (
                f"Entry: {entry_price:.5f}\n"
                f"Entry model: {entry_mode}\n"
                f"Entry level: {entry_label}\n"
                f"Stop: {stop_price:.5f}\n"
                f"Target: {target_price:.5f}\n"
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
                fontsize=9,
                bbox=dict(
                    boxstyle="round,pad=0.5",
                    facecolor="black",
                    edgecolor="0.35",
                    alpha=0.88,
                ),
                zorder=20,
            )

            handles, labels = (
                ax.get_legend_handles_labels()
            )

            if handles:

                legend = ax.legend(
                    handles,
                    labels,
                    loc="upper left",
                    frameon=False,
                    fontsize=8,
                )

                for item in legend.get_texts():

                    item.set_color(
                        "0.75"
                    )

            fig.subplots_adjust(
                left=0.07,
                right=0.88,
                top=0.88,
                bottom=0.10,
            )

            filename = (
                f"rank_"
                f"{rank_value:03d}"
                f"_trade_"
                f"{trade_number}.png"
            )

            fig.savefig(
                output_dir
                / filename,
                dpi=170,
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

    print(
        f"Entry mode: {args.entry_mode} "
        f"| Fib wait bars: {args.entry_wait_bars} "
        f"| Engine: {BACKTEST_ENGINE_VERSION}"
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
                    args.entry_mode,
                    args.entry_wait_bars,
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
                        candidate[
                            "conditions"
                        ],
                        rr,
                        args.max_bars,
                        args.max_open_trades,
                        args.entry_mode,
                        args.entry_wait_bars,
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

                        "entry_mode": args.entry_mode,
                        "entry_wait_bars": int(
                            args.entry_wait_bars
                        ),
                        "engine_version": BACKTEST_ENGINE_VERSION,

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
                "entry_mode": args.entry_mode,
                "entry_wait_bars": int(
                    args.entry_wait_bars
                ),
                "engine_version": BACKTEST_ENGINE_VERSION,
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
        "entry_mode",
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