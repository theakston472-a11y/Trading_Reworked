
from __future__ import annotations

import argparse
import hashlib
import itertools
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# PERSISTENT STRATEGY DISCOVERY
# ============================================================
#
# Research/discovery only.
#
# This script:
#   - loads the feature database
#   - searches combinations of features
#   - tests them over 2025 and 2026
#   - uses SQLite to avoid repeating tested combinations
#   - saves candidates into separate session/direction files
#   - preserves previous candidates already saved
#
# It does NOT:
#   - modify strategy_lab.py
#   - place trades
#
# Output structure:
#
# results/
#   discovery/
#       london/
#           buy_candidates.csv
#           sell_candidates.csv
#       new_york/
#           buy_candidates.csv
#           sell_candidates.csv
#
# ============================================================


FEATURES = [
    "liquidity_sweep_high",
    "previous_day_high_sweep",

    "bearish_candle",
    "bearish_engulfing",
    "bearish_pin_bar",
    "strong_bearish_candle",

    "bearish_bos",
    "bearish_choch",

    "lower_high",
    "lower_low",
    "equal_high",

    "bearish_fvg",

    "bearish_fib_liquidity",
    "bearish_fib_382_rejection",
    "bearish_fib_500_rejection",
    "bearish_fib_618_rejection",

    "bearish_bos_fib_382",
    "bearish_bos_fib_500",
    "bearish_bos_fib_618",

    "near_fib_382",
    "near_fib_500",
    "near_fib_618",

    "small_range",
    "large_range",

    "above_ema20",
    "above_ema50",
    "above_ema100",
    "above_ema200",
]


DEFAULT_MAX_CONDITIONS = 4
DEFAULT_MIN_TRADES = 20
DEFAULT_MAX_NEW = 5000
DEFAULT_RR = 2.0
DEFAULT_MAX_OPEN = 5
DEFAULT_MAX_BARS = 48

DEFAULT_DIRECTION = "SELL"
DEFAULT_SESSION = "New York"


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Persistent strategy discovery engine"
    )

    parser.add_argument(
        "--data",
        default=None,
        help="Feature database CSV",
    )

    parser.add_argument(
        "--db",
        default=None,
        help="Strategy discovery registry SQLite database",
    )

    parser.add_argument(
        "--out",
        default=None,
        help="Optional explicit discovery candidate CSV",
    )

    parser.add_argument(
        "--direction",
        default=DEFAULT_DIRECTION,
        choices=["BUY", "SELL"],
        help="Strategy direction",
    )

    parser.add_argument(
        "--session",
        default=DEFAULT_SESSION,
        help="Trading session. Use 'all' to search every session.",
    )

    parser.add_argument(
        "--max-conditions",
        type=int,
        default=DEFAULT_MAX_CONDITIONS,
        help="Maximum number of conditions per strategy",
    )

    parser.add_argument(
        "--min-trades",
        type=int,
        default=DEFAULT_MIN_TRADES,
        help="Minimum trades required per validation period",
    )

    parser.add_argument(
        "--max-new",
        type=int,
        default=DEFAULT_MAX_NEW,
        help="Maximum NEW combinations to test this run",
    )

    parser.add_argument(
        "--rr",
        type=float,
        default=DEFAULT_RR,
        help="Risk/reward used for discovery screening",
    )

    parser.add_argument(
        "--max-open",
        type=int,
        default=DEFAULT_MAX_OPEN,
        help="Maximum simultaneous trades",
    )

    parser.add_argument(
        "--max-bars",
        type=int,
        default=DEFAULT_MAX_BARS,
        help="Maximum bars a trade remains open",
    )

    parser.add_argument(
        "--retest",
        action="store_true",
        help=(
            "Retest combinations already present in the registry. "
            "Use deliberately when recovering/rebuilding result files."
        ),
    )

    return parser.parse_args()


# ============================================================
# PATHS
# ============================================================

def set_defaults(args):
    """
    IMPORTANT:
    Use args.session and args.direction here.

    The previous broken version referenced undefined variables
    named session and direction, causing NameError.
    """

    base = Path(__file__).resolve().parents[1]

    if args.data is None:
        args.data = str(
            base
            / "quant"
            / "feature_database.csv"
        )

    if args.db is None:
        args.db = str(
            base
            / "results"
            / "strategy_registry.sqlite"
        )

    if args.out is None:
        session_name = (
            str(args.session)
            .strip()
            .lower()
            .replace(" ", "_")
        )

        direction_name = (
            str(args.direction)
            .strip()
            .lower()
        )

        args.out = str(
            base
            / "results"
            / "discovery"
            / session_name
            / f"{direction_name}_candidates.csv"
        )

    Path(args.out).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    Path(args.db).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return args


# ============================================================
# PERIODS
# ============================================================

def build_periods(df):
    timestamps = df["timestamp"]

    minimum = timestamps.min()
    maximum = timestamps.max()

    periods = []

    p1_start = pd.Timestamp(
        "2025-01-01",
        tz="UTC",
    )

    p1_end = pd.Timestamp(
        "2025-12-31 23:59:59",
        tz="UTC",
    )

    if p1_start <= maximum and p1_end >= minimum:
        periods.append(
            (
                "2025",
                max(p1_start, minimum),
                min(p1_end, maximum),
            )
        )

    p2_start = pd.Timestamp(
        "2026-01-01",
        tz="UTC",
    )

    p2_end = maximum

    if p2_start <= maximum:
        periods.append(
            (
                "2026",
                max(p2_start, minimum),
                p2_end,
            )
        )

    if not periods:
        midpoint = (
            minimum
            + (maximum - minimum) / 2
        )

        periods = [
            (
                "period_1",
                minimum,
                midpoint,
            ),
            (
                "period_2",
                midpoint,
                maximum,
            ),
        ]

    return periods


# ============================================================
# CANONICAL CONDITIONS
# ============================================================

def canonical_conditions(conditions):
    values = [
        str(x).strip()
        for x in str(conditions).split("+")
        if str(x).strip()
    ]

    values = sorted(
        set(values),
        key=str.lower,
    )

    return "+".join(values)


# ============================================================
# STRATEGY FINGERPRINT
# ============================================================

def strategy_fingerprint(
    direction,
    session,
    conditions,
    rr,
):
    canonical = canonical_conditions(
        conditions
    )

    text = (
        f"{str(direction).upper().strip()}|"
        f"{str(session).lower().strip()}|"
        f"{canonical.lower()}|"
        f"{float(rr):.4f}"
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# ============================================================
# REGISTRY
# ============================================================

def open_registry(path):
    connection = sqlite3.connect(path)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS discoveries (
            fingerprint TEXT PRIMARY KEY,
            direction TEXT NOT NULL,
            session TEXT NOT NULL,
            conditions TEXT NOT NULL,
            rr REAL NOT NULL,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.commit()

    return connection


def already_tested(
    connection,
    fingerprint,
):
    result = connection.execute(
        """
        SELECT 1
        FROM discoveries
        WHERE fingerprint = ?
        LIMIT 1
        """,
        (fingerprint,),
    ).fetchone()

    return result is not None


def register_strategy(
    connection,
    fingerprint,
    direction,
    session,
    conditions,
    rr,
):
    connection.execute(
        """
        INSERT OR IGNORE INTO discoveries (
            fingerprint,
            direction,
            session,
            conditions,
            rr
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            fingerprint,
            direction,
            session,
            conditions,
            float(rr),
        ),
    )


# ============================================================
# LOAD DATA
# ============================================================

def load_data(path):
    print()
    print("=" * 70)
    print("LOADING MARKET DATA")
    print("=" * 70)

    print(f"File: {path}")

    df = pd.read_csv(path)

    if "timestamp" not in df.columns:
        raise RuntimeError(
            "Feature database does not contain 'timestamp'."
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
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
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Feature database is missing: "
            + ", ".join(missing)
        )

    for column in required:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    if "session" not in df.columns:
        raise RuntimeError(
            "Feature database does not contain 'session'."
        )

    df["session"] = (
        df["session"]
        .astype(str)
        .str.strip()
    )

    print(f"Rows: {len(df):,}")

    print(
        f"Data: "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    return df


# ============================================================
# FEATURE BOOLEAN CONVERSION
# ============================================================

def to_bool_series(series):
    """
    Safely convert feature columns to booleans.

    This avoids the Python problem where:
        bool("False") == True
    """

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    if pd.api.types.is_numeric_dtype(series):
        return (
            pd.to_numeric(
                series,
                errors="coerce",
            )
            .fillna(0)
            .astype(bool)
        )

    values = (
        series
        .astype(str)
        .str.strip()
        .str.lower()
    )

    true_values = {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }

    return values.isin(true_values)


# ============================================================
# PREPARE FEATURES
# ============================================================

def prepare_features(df):
    available = []

    for feature in FEATURES:
        if feature not in df.columns:
            continue

        df[feature] = to_bool_series(
            df[feature]
        )

        available.append(feature)

    print()
    print("=" * 70)
    print("DISCOVERY FEATURES")
    print("=" * 70)

    print(
        f"Requested features: {len(FEATURES)}"
    )

    print(
        f"Available features: {len(available)}"
    )

    missing = [
        feature
        for feature in FEATURES
        if feature not in available
    ]

    if missing:
        print("Missing features:")

        for feature in missing:
            print(f"  - {feature}")

    if not available:
        raise RuntimeError(
            "None of the discovery features exist in the database."
        )

    return df, available


# ============================================================
# BACKTEST
# ============================================================

def _fib_ratios_from_conditions(
    conditions,
):
    names = [
        item.strip().lower()
        for item in str(
            conditions
        ).split("+")
        if item.strip()
    ]

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


def _resolve_discovery_entry(
    df,
    signal_i,
    conditions,
    entry_mode,
    entry_wait_bars,
):
    mode = str(
        entry_mode
    ).strip().lower()

    ratios = _fib_ratios_from_conditions(
        conditions
    )

    fib_entry = None

    if ratios:

        ratio = max(
            ratios
        )

        column = (
            f"fib_{ratio}"
        )

        if column in df.columns:

            try:

                price = float(
                    df.iloc[
                        signal_i
                    ][column]
                )

            except Exception:

                price = np.nan

            if np.isfinite(
                price
            ):

                fib_entry = {
                    "price": price,
                    "ratio": ratio,
                }

    if mode == "auto":

        mode = (
            "fib_touch"
            if fib_entry is not None
            else "next_open"
        )

    if mode == "signal_close":

        price = float(
            df.iloc[
                signal_i
            ]["close"]
        )

        if not np.isfinite(
            price
        ):
            return None

        return {
            "entry_i": signal_i,
            "entry": price,
            "outcome_start_i": (
                signal_i + 1
            ),
        }

    if mode == "fib_touch":

        if fib_entry is None:
            return None

        level = float(
            fib_entry[
                "price"
            ]
        )

        first_i = (
            signal_i + 1
        )

        last_i = min(
            len(df) - 1,
            signal_i
            + max(
                int(
                    entry_wait_bars
                ),
                1,
            ),
        )

        for entry_i in range(
            first_i,
            last_i + 1,
        ):

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

            if (
                np.isfinite(
                    low
                )
                and np.isfinite(
                    high
                )
                and low
                <= level
                <= high
            ):

                return {
                    "entry_i": entry_i,
                    "entry": level,
                    "outcome_start_i": entry_i,
                }

        return None

    entry_i = (
        signal_i + 1
    )

    if entry_i >= len(
        df
    ):
        return None

    entry = float(
        df.iloc[
            entry_i
        ]["open"]
    )

    if not np.isfinite(
        entry
    ):
        return None

    return {
        "entry_i": entry_i,
        "entry": entry,
        "outcome_start_i": entry_i,
    }


def backtest(
    df,
    signal,
    direction,
    conditions,
    rr,
    max_bars,
    max_open,
    entry_mode="auto",
    entry_wait_bars=6,
):
    indices = np.flatnonzero(
        signal
    )

    if len(indices) == 0:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "drawdown_r": 0.0,
            "avg_trades_day": 0.0,
        }

    opens = df[
        "open"
    ].to_numpy(
        dtype=float
    )

    highs = df[
        "high"
    ].to_numpy(
        dtype=float
    )

    lows = df[
        "low"
    ].to_numpy(
        dtype=float
    )

    closes = df[
        "close"
    ].to_numpy(
        dtype=float
    )

    atrs = df[
        "atr14"
    ].to_numpy(
        dtype=float
    )

    active_exits = []

    results = []

    direction = (
        str(
            direction
        )
        .upper()
        .strip()
    )

    for signal_i in indices:

        signal_i = int(
            signal_i
        )

        resolved = _resolve_discovery_entry(
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
            entry_i >= len(
                df
            )
            or outcome_start_i
            >= len(
                df
            )
        ):
            continue

        active_exits = [
            exit_i
            for exit_i
            in active_exits
            if exit_i
            >= entry_i
        ]

        if len(
            active_exits
        ) >= max_open:
            continue

        entry = float(
            resolved[
                "entry"
            ]
        )

        atr_value = atrs[
            signal_i
        ]

        candle_range = abs(
            highs[
                signal_i
            ]
            - lows[
                signal_i
            ]
        )

        if np.isfinite(
            atr_value
        ):

            distance = max(
                candle_range,
                atr_value,
            )

        else:

            distance = (
                candle_range
            )

        if (
            not np.isfinite(
                entry
            )
            or not np.isfinite(
                distance
            )
            or distance <= 0
        ):
            continue

        if direction == "SELL":

            sl = (
                entry
                + distance
            )

            tp = (
                entry
                - distance
                * rr
            )

        else:

            sl = (
                entry
                - distance
            )

            tp = (
                entry
                + distance
                * rr
            )

        final_i = min(
            len(df) - 1,
            outcome_start_i
            + max_bars - 1,
        )

        outcome = None

        exit_i = final_i

        for j in range(
            outcome_start_i,
            final_i + 1,
        ):

            if direction == "SELL":

                stop_hit = (
                    highs[
                        j
                    ] >= sl
                )

                target_hit = (
                    lows[
                        j
                    ] <= tp
                )

            else:

                stop_hit = (
                    lows[
                        j
                    ] <= sl
                )

                target_hit = (
                    highs[
                        j
                    ] >= tp
                )

            if stop_hit:

                outcome = -1.0

                exit_i = j

                break

            if target_hit:

                outcome = float(
                    rr
                )

                exit_i = j

                break

        if outcome is None:

            if direction == "SELL":

                movement = (
                    entry
                    - closes[
                        exit_i
                    ]
                )

            else:

                movement = (
                    closes[
                        exit_i
                    ]
                    - entry
                )

            outcome = float(
                movement
                / distance
            )

        results.append(
            outcome
        )

        active_exits.append(
            exit_i
        )

    arr = np.asarray(
        results,
        dtype=float,
    )

    if len(arr) == 0:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "drawdown_r": 0.0,
            "avg_trades_day": 0.0,
        }

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
        if len(
            wins
        )
        else 0.0
    )

    gross_loss = (
        float(
            abs(
                losses.sum()
            )
        )
        if len(
            losses
        )
        else 0.0
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            / gross_loss
        )

    elif gross_profit > 0:

        profit_factor = (
            999.0
        )

    else:

        profit_factor = (
            0.0
        )

    equity = np.cumsum(
        arr
    )

    running_max = (
        np.maximum.accumulate(
            np.r_[
                0.0,
                equity,
            ]
        )[1:]
    )

    drawdown = (
        running_max
        - equity
    )

    max_drawdown = (
        float(
            drawdown.max()
        )
        if len(
            drawdown
        )
        else 0.0
    )

    first_time = df[
        "timestamp"
    ].iloc[
        0
    ]

    last_time = df[
        "timestamp"
    ].iloc[
        -1
    ]

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
            len(
                arr
            )
        ),
        "wins": int(
            len(
                wins
            )
        ),
        "losses": int(
            len(
                losses
            )
        ),
        "win_rate": float(
            len(
                wins
            )
            / len(
                arr
            )
            * 100.0
        ),
        "net_r": float(
            arr.sum()
        ),
        "expectancy_r": float(
            arr.mean()
        ),
        "profit_factor": float(
            profit_factor
        ),
        "drawdown_r": float(
            max_drawdown
        ),
        "avg_trades_day": float(
            len(
                arr
            )
            / days
        ),
    }

# ============================================================
# SCORE CANDIDATE

# ============================================================
# SCORE CANDIDATE
# ============================================================

def score_candidate(
    metrics,
    min_trades,
):
    if not metrics:
        return None

    trade_counts = [
        period["trades"]
        for period in metrics
    ]

    if min(trade_counts) < min_trades:
        return None

    net_values = [
        period["net_r"]
        for period in metrics
    ]

    expectancy_values = [
        period["expectancy_r"]
        for period in metrics
    ]

    pf_values = [
        period["profit_factor"]
        for period in metrics
    ]

    drawdown_values = [
        period["drawdown_r"]
        for period in metrics
    ]

    frequency_values = [
        period["avg_trades_day"]
        for period in metrics
    ]

    positive_periods = sum(
        value > 0
        for value in net_values
    )

    total_trades = sum(trade_counts)
    total_net_r = sum(net_values)

    average_expectancy = float(
        np.mean(expectancy_values)
    )

    minimum_pf = float(
        min(pf_values)
    )

    worst_drawdown = float(
        max(drawdown_values)
    )

    average_frequency = float(
        np.mean(frequency_values)
    )

    expectancy_component = max(
        min(
            average_expectancy / 0.30,
            1.0,
        ),
        0.0,
    )

    pf_component = max(
        min(
            (minimum_pf - 1.0) / 1.5,
            1.0,
        ),
        0.0,
    )

    drawdown_component = (
        1.0
        /
        (
            1.0
            +
            max(
                worst_drawdown / 50.0,
                0.0,
            )
        )
    )

    frequency_component = max(
        min(
            average_frequency / 0.75,
            1.0,
        ),
        0.0,
    )

    consistency_component = (
        positive_periods / len(metrics)
    )

    trade_component = max(
        min(
            total_trades / 500.0,
            1.0,
        ),
        0.0,
    )

    positive_net_component = (
        1.0
        -
        np.exp(
            -max(total_net_r, 0.0) / 150.0
        )
    )

    score = 100.0 * (
        0.25 * positive_net_component
        + 0.20 * expectancy_component
        + 0.15 * pf_component
        + 0.15 * drawdown_component
        + 0.10 * frequency_component
        + 0.10 * consistency_component
        + 0.05 * trade_component
    )

    return {
        "score": float(score),
        "trades": int(total_trades),
        "net_r": float(total_net_r),
        "expectancy_r": float(
            average_expectancy
        ),
        "min_profit_factor": float(
            minimum_pf
        ),
        "worst_drawdown_r": float(
            worst_drawdown
        ),
        "avg_trades_day": float(
            average_frequency
        ),
        "positive_periods": int(
            positive_periods
        ),
        "periods_tested": int(
            len(metrics)
        ),
    }


# ============================================================
# DISCOVER
# ============================================================

def discover(
    df,
    features,
    connection,
    direction,
    session,
    max_conditions,
    min_trades,
    max_new,
    rr,
    max_open,
    max_bars,
    entry_mode="auto",
    entry_wait_bars=6,
    retest=False,
):
    periods = build_periods(df)

    print()
    print("=" * 70)
    print("DISCOVERY PERIODS")
    print("=" * 70)

    for name, start, end in periods:
        print(
            f"{name}: {start} -> {end}"
        )

    session_lower = (
        str(session)
        .strip()
        .lower()
    )

    if session_lower not in (
        "",
        "all",
        "none",
        "nan",
    ):

        session_count = int(
            (
                df["session"]
                .astype(str)
                .str.strip()
                .str.lower()
                == session_lower
            ).sum()
        )

    else:

        session_count = len(
            df
        )

    print()
    print(
        f"Rows matching signal session: "
        f"{session_count:,}"
    )

    if session_count == 0:

        raise RuntimeError(
            "No market data matches the requested signal session."
        )

    # Keep the FULL chronological period dataframe.  Session is
    # applied only to the signal mask so entry/exit bars remain
    # real consecutive market bars.  The older code removed all
    # non-session rows before backtesting, making 'next bar' and
    # max-bars behave differently from Strategy Lab.
    period_data = []

    for name, start, end in periods:

        period_df = df[
            (df["timestamp"] >= start)
            &
            (df["timestamp"] <= end)
        ].copy()

        period_df = (
            period_df
            .reset_index(
                drop=True
            )
        )

        period_data.append(
            (
                name,
                period_df,
            )
        )

    rows = []

    examined = 0
    skipped = 0
    added = 0

    for condition_count in range(
        1,
        max_conditions + 1,
    ):
        print()
        print(
            f"Searching "
            f"{condition_count}-condition "
            f"combinations..."
        )

        for combo in itertools.combinations(
            features,
            condition_count,
        ):
            if added >= max_new:
                break

            conditions = canonical_conditions(
                "+".join(combo)
            )

            fingerprint = strategy_fingerprint(
                direction,
                session,
                conditions,
                rr,
                entry_mode,
                entry_wait_bars,
            )

            exists = already_tested(
                connection,
                fingerprint,
            )

            if exists and not retest:
                skipped += 1
                continue

            examined += 1

            metrics = []
            valid = True

            for period_name, period_df in period_data:
                if period_df.empty:
                    valid = False
                    break

                signal = np.ones(
                    len(period_df),
                    dtype=bool,
                )

                if session_lower not in (
                    "",
                    "all",
                    "none",
                    "nan",
                ):

                    signal &= (
                        period_df["session"]
                        .astype(str)
                        .str.strip()
                        .str.lower()
                        .to_numpy()
                        == session_lower
                    )

                for feature in combo:

                    signal &= (
                        period_df[
                            feature
                        ]
                        .to_numpy(
                            dtype=bool
                        )
                    )

                result = backtest(
                    period_df,
                    signal,
                    direction,
                    conditions,
                    rr,
                    max_bars,
                    max_open,
                    entry_mode,
                    entry_wait_bars,
                )

                result["period"] = period_name

                metrics.append(result)

            register_strategy(
                connection,
                fingerprint,
                direction,
                session,
                conditions,
                rr,
            )

            connection.commit()

            if not valid:
                continue

            scored = score_candidate(
                metrics,
                min_trades,
            )

            if scored is None:
                continue

            row = {
                "strategy_fingerprint": fingerprint,
                "direction": direction,
                "session": session,
                "conditions": conditions,
                "condition_count": condition_count,
                "rr": float(rr),
                "score": scored["score"],
                "trades": scored["trades"],
                "net_r": scored["net_r"],
                "expectancy_r": scored["expectancy_r"],
                "min_profit_factor": scored[
                    "min_profit_factor"
                ],
                "worst_drawdown_r": scored[
                    "worst_drawdown_r"
                ],
                "avg_trades_day": scored[
                    "avg_trades_day"
                ],
                "positive_periods": scored[
                    "positive_periods"
                ],
                "periods_tested": scored[
                    "periods_tested"
                ],
            }

            for period in metrics:
                prefix = period["period"]

                row[f"{prefix}_trades"] = period[
                    "trades"
                ]

                row[f"{prefix}_net_r"] = period[
                    "net_r"
                ]

                row[
                    f"{prefix}_expectancy_r"
                ] = period[
                    "expectancy_r"
                ]

                row[
                    f"{prefix}_profit_factor"
                ] = period[
                    "profit_factor"
                ]

                row[
                    f"{prefix}_drawdown_r"
                ] = period[
                    "drawdown_r"
                ]

                row[f"{prefix}_win_rate"] = period[
                    "win_rate"
                ]

            rows.append(row)
            added += 1

        if added >= max_new:
            break

    return (
        rows,
        examined,
        skipped,
        added,
    )


# ============================================================
# SAVE / MERGE RESULTS
# ============================================================

def save_results(
    rows,
    output_path,
):
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    new_result = pd.DataFrame(rows)

    if output_path.exists():
        try:
            old_result = pd.read_csv(
                output_path
            )
        except Exception:
            old_result = pd.DataFrame()
    else:
        old_result = pd.DataFrame()

    if new_result.empty and old_result.empty:
        empty_columns = [
            "strategy_fingerprint",
            "direction",
            "session",
            "conditions",
            "condition_count",
            "rr",
            "score",
            "trades",
            "net_r",
            "expectancy_r",
            "min_profit_factor",
            "worst_drawdown_r",
            "avg_trades_day",
            "positive_periods",
            "periods_tested",
        ]

        pd.DataFrame(
            columns=empty_columns
        ).to_csv(
            output_path,
            index=False,
        )

        return pd.DataFrame()

    if new_result.empty:
        result = old_result.copy()
    elif old_result.empty:
        result = new_result.copy()
    else:
        result = pd.concat(
            [
                old_result,
                new_result,
            ],
            ignore_index=True,
        )

    result = result.drop_duplicates(
        subset=[
            "direction",
            "session",
            "conditions",
            "rr",
        ],
        keep="last",
    )

    numeric_columns = [
        "score",
        "positive_periods",
        "trades",
        "net_r",
        "expectancy_r",
        "min_profit_factor",
        "worst_drawdown_r",
        "avg_trades_day",
        "condition_count",
        "rr",
    ]

    for column in numeric_columns:
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

    sort_columns = [
        column
        for column in [
            "score",
            "positive_periods",
            "trades",
            "net_r",
            "expectancy_r",
            "min_profit_factor",
        ]
        if column in result.columns
    ]

    if sort_columns:
        result = result.sort_values(
            sort_columns,
            ascending=False,
            kind="stable",
        )

    result = result.reset_index(
        drop=True
    )

    if "rank" in result.columns:
        result = result.drop(
            columns=["rank"]
        )

    result.insert(
        0,
        "rank",
        range(
            1,
            len(result) + 1,
        ),
    )

    result.to_csv(
        output_path,
        index=False,
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    args = set_defaults(
        parse_args()
    )

    print()
    print("=" * 70)
    print("PERSISTENT STRATEGY DISCOVERY")
    print("=" * 70)

    print()
    print(
        "This is a research/discovery process."
    )

    print(
        "It does NOT modify strategy_lab.py."
    )

    print(
        "It does NOT place trades."
    )

    print()
    print(
        f"Direction:       {args.direction}"
    )

    print(
        f"Session:         {args.session}"
    )

    print(
        f"Max conditions:  {args.max_conditions}"
    )

    print(
        f"Minimum trades:  {args.min_trades}"
    )

    print(
        f"Maximum new:     {args.max_new}"
    )

    print(
        f"Discovery RR:     {args.rr}"
    )

    print(
        f"Max open trades: {args.max_open}"
    )

    print(
        f"Max bars:        {args.max_bars}"
    )

    print(
        f"Entry mode:      {args.entry_mode}"
    )

    print(
        f"Fib wait bars:   {args.entry_wait_bars}"
    )

    print(
        f"Engine:          {DISCOVERY_ENGINE_VERSION}"
    )

    print(
        f"Retest:          {args.retest}"
    )

    data_path = Path(args.data)
    registry_path = Path(args.db)
    output_path = Path(args.out)

    print()
    print("=" * 70)
    print("PATHS")
    print("=" * 70)

    print(f"Data:     {data_path}")
    print(f"Registry: {registry_path}")
    print(f"Output:   {output_path}")

    df = load_data(
        data_path
    )

    df, available_features = prepare_features(
        df
    )

    if args.max_conditions > len(
        available_features
    ):
        args.max_conditions = len(
            available_features
        )

    connection = open_registry(
        registry_path
    )

    try:
        (
            rows,
            examined,
            skipped,
            added,
        ) = discover(
            df=df,
            features=available_features,
            connection=connection,
            direction=args.direction,
            session=args.session,
            max_conditions=args.max_conditions,
            min_trades=args.min_trades,
            max_new=args.max_new,
            rr=args.rr,
            max_open=args.max_open,
            max_bars=args.max_bars,
            entry_mode=args.entry_mode,
            entry_wait_bars=args.entry_wait_bars,
            retest=args.retest,
        )
    finally:
        connection.close()

    result = save_results(
        rows,
        output_path,
    )

    print()
    print("=" * 70)
    print("DISCOVERY COMPLETE")
    print("=" * 70)

    print()
    print(
        f"New combinations examined: "
        f"{examined:,}"
    )

    print(
        f"Already tested/skipped: "
        f"{skipped:,}"
    )

    print(
        f"New candidates found: "
        f"{added:,}"
    )

    print(
        f"Candidate CSV: "
        f"{output_path}"
    )

    print(
        f"Registry: "
        f"{registry_path}"
    )

    print(
        f"Candidates currently saved in this pool: "
        f"{len(result):,}"
    )

    if not result.empty:
        print()
        print("=" * 70)
        print("TOP DISCOVERY CANDIDATES")
        print("=" * 70)

        display_columns = [
            "rank",
            "direction",
            "session",
            "conditions",
            "condition_count",
            "rr",
            "score",
            "trades",
            "net_r",
            "expectancy_r",
            "min_profit_factor",
            "worst_drawdown_r",
            "positive_periods",
        ]

        display_columns = [
            column
            for column in display_columns
            if column in result.columns
        ]

        print(
            result[
                display_columns
            ]
            .head(25)
            .to_string(index=False)
        )
    else:
        print()
        print(
            "No candidates are currently saved "
            "for this pool."
        )

    print()
    print("=" * 70)
    print("IMPORTANT")
    print("=" * 70)

    print(
        "This script does not modify strategy_lab.py."
    )

    print(
        "This script does not place trades."
    )

    print(
        "The discovery registry is only used to "
        "prevent accidental repeat testing."
    )

    if not args.retest:
        print(
            "Use --retest only when deliberately "
            "rebuilding/recovering a result pool."
        )


if __name__ == "__main__":
    main()
