from __future__ import annotations

import argparse
import hashlib
import itertools
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# STRATEGY DISCOVERY
# ============================================================
#
# Research/discovery only.
#
# Does NOT modify strategy_lab.py.
# Does NOT place trades.
#
# The SQLite registry remembers every strategy combination
# tested, so repeated runs search for genuinely new strategies.
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


# ============================================================
# DEFAULT CONFIGURATION
# ============================================================

DEFAULT_MAX_CONDITIONS = 4
DEFAULT_MIN_TRADES = 20
DEFAULT_MAX_NEW = 5000
DEFAULT_RR = 2.0
DEFAULT_MAX_OPEN = 5
DEFAULT_MAX_BARS = 48

DEFAULT_DIRECTION = "SELL"
DEFAULT_SESSION = "New York"


# ============================================================
# PERIODS
# ============================================================

def build_periods(df):
    timestamps = df["timestamp"]

    minimum = timestamps.min()
    maximum = timestamps.max()

    periods = []

    p1_start = pd.Timestamp("2025-01-01", tz="UTC")
    p1_end = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")

    if p1_start <= maximum and p1_end >= minimum:
        periods.append(
            (
                "2025",
                max(p1_start, minimum),
                min(p1_end, maximum),
            )
        )

    p2_start = pd.Timestamp("2026-01-01", tz="UTC")
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
        midpoint = minimum + (maximum - minimum) / 2

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
        help="Discovery candidate CSV",
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

    return parser.parse_args()


# ============================================================
# PATHS
# ============================================================

def set_defaults(args):

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

    # IMPORTANT:
    # Build the output filename from args.session and
    # args.direction. Never use undefined variables here.
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
            / (
                f"{session_name}_"
                f"{direction_name}_"
                f"candidates.csv"
            )
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
# LOAD MARKET DATA
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
# PREPARE FEATURES
# ============================================================

def prepare_features(df):

    available = []

    for feature in FEATURES:

        if feature not in df.columns:
            continue

        df[feature] = (
            df[feature]
            .fillna(False)
            .astype(bool)
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

def backtest(
    df,
    signal,
    direction,
    rr,
    max_bars,
    max_open,
):

    indices = np.flatnonzero(signal)

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

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    atrs = df["atr14"].to_numpy(dtype=float)

    active_exits = []
    results = []

    direction = str(direction).upper().strip()

    for signal_i in indices:

        signal_i = int(signal_i)
        entry_i = signal_i + 1

        if entry_i >= len(df):
            continue

        active_exits = [
            exit_i
            for exit_i in active_exits
            if exit_i > entry_i
        ]

        if len(active_exits) >= max_open:
            continue

        entry = opens[entry_i]
        atr_value = atrs[signal_i]

        candle_range = abs(
            highs[signal_i] - lows[signal_i]
        )

        if np.isfinite(atr_value):
            distance = max(
                candle_range,
                atr_value,
            )
        else:
            distance = candle_range

        if (
            not np.isfinite(entry)
            or not np.isfinite(distance)
            or distance <= 0
        ):
            continue

        if direction == "SELL":

            sl = entry + distance
            tp = entry - distance * rr

        else:

            sl = entry - distance
            tp = entry + distance * rr

        final_i = min(
            len(df) - 1,
            entry_i + max_bars - 1,
        )

        outcome = None
        exit_i = final_i

        for j in range(
            entry_i,
            final_i + 1,
        ):

            if direction == "SELL":

                stop_hit = highs[j] >= sl
                target_hit = lows[j] <= tp

            else:

                stop_hit = lows[j] <= sl
                target_hit = highs[j] >= tp

            # Conservative same-candle assumption:
            # SL takes priority if both are hit.

            if stop_hit:

                outcome = -1.0
                exit_i = j
                break

            if target_hit:

                outcome = float(rr)
                exit_i = j
                break

        if outcome is None:

            if direction == "SELL":

                movement = entry - closes[exit_i]

            else:

                movement = closes[exit_i] - entry

            outcome = movement / distance

        results.append(
            {
                "entry_i": entry_i,
                "exit_i": exit_i,
                "outcome_r": float(outcome),
            }
        )

        active_exits.append(exit_i)

    if not results:

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

    values = np.asarray(
        [
            result["outcome_r"]
            for result in results
        ],
        dtype=float,
    )

    wins = values[values > 0]
    losses = values[values < 0]

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
            gross_profit / gross_loss
        )

    elif gross_profit > 0:

        profit_factor = 999.0

    else:

        profit_factor = 0.0

    equity = np.cumsum(values)

    running_max = np.maximum.accumulate(
        np.r_[0.0, equity]
    )[1:]

    drawdown = running_max - equity

    max_drawdown = (
        float(drawdown.max())
        if len(drawdown)
        else 0.0
    )

    first_time = df.iloc[
        results[0]["entry_i"]
    ]["timestamp"]

    last_time = df.iloc[
        results[-1]["exit_i"]
    ]["timestamp"]

    days = max(
        (
            last_time - first_time
        ).total_seconds()
        / 86400.0,
        1.0,
    )

    return {
        "trades": int(len(values)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": float(
            len(wins)
            / len(values)
            * 100.0
        ),
        "net_r": float(values.sum()),
        "expectancy_r": float(values.mean()),
        "profit_factor": float(profit_factor),
        "drawdown_r": float(max_drawdown),
        "avg_trades_day": float(
            len(values) / days
        ),
    }


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
        "expectancy_r": float(average_expectancy),
        "min_profit_factor": float(minimum_pf),
        "worst_drawdown_r": float(worst_drawdown),
        "avg_trades_day": float(average_frequency),
        "positive_periods": int(positive_periods),
        "periods_tested": int(len(metrics)),
    }


# ============================================================
# DISCOVER COMBINATIONS
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

    # --------------------------------------------------------
    # SESSION FILTER
    # --------------------------------------------------------

    session_value = str(session).strip()

    if session_value.lower() not in (
        "",
        "all",
        "none",
        "nan",
    ):

        session_name = session_value.lower()

        work = df[
            df["session"]
            .astype(str)
            .str.lower()
            == session_name
        ].copy()

    else:

        work = df.copy()

    print()
    print(
        f"Rows after session filter: "
        f"{len(work):,}"
    )

    if work.empty:
        raise RuntimeError(
            "No market data remains after "
            "the session filter."
        )

    # --------------------------------------------------------
    # PREPARE PERIOD DATA
    # --------------------------------------------------------

    period_data = []

    for name, start, end in periods:

        period_df = work[
            (work["timestamp"] >= start)
            &
            (work["timestamp"] <= end)
        ].copy()

        period_df = (
            period_df
            .reset_index(drop=True)
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

    # --------------------------------------------------------
    # COMBINATIONS
    # --------------------------------------------------------

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
            )

            if already_tested(
                connection,
                fingerprint,
            ):

                skipped += 1
                continue

            examined += 1

            metrics = []
            valid = True

            for (
                period_name,
                period_df,
            ) in period_data:

                if period_df.empty:
                    valid = False
                    break

                signal = np.ones(
                    len(period_df),
                    dtype=bool,
                )

                for feature in combo:

                    signal &= (
                        period_df[feature]
                        .to_numpy()
                    )

                result = backtest(
                    period_df,
                    signal,
                    direction,
                    rr,
                    max_bars,
                    max_open,
                )

                result["period"] = period_name

                metrics.append(result)

            # Register every tested strategy,
            # including failures.
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
                "strategy_fingerprint":
                    fingerprint,

                "direction":
                    direction,

                "session":
                    session,

                "conditions":
                    conditions,

                "condition_count":
                    condition_count,

                "rr":
                    float(rr),

                "score":
                    scored["score"],

                "trades":
                    scored["trades"],

                "net_r":
                    scored["net_r"],

                "expectancy_r":
                    scored["expectancy_r"],

                "min_profit_factor":
                    scored["min_profit_factor"],

                "worst_drawdown_r":
                    scored["worst_drawdown_r"],

                "avg_trades_day":
                    scored["avg_trades_day"],

                "positive_periods":
                    scored["positive_periods"],

                "periods_tested":
                    scored["periods_tested"],
            }

            for period in metrics:

                prefix = period["period"]

                row[f"{prefix}_trades"] = (
                    period["trades"]
                )

                row[f"{prefix}_net_r"] = (
                    period["net_r"]
                )

                row[f"{prefix}_expectancy_r"] = (
                    period["expectancy_r"]
                )

                row[f"{prefix}_profit_factor"] = (
                    period["profit_factor"]
                )

                row[f"{prefix}_drawdown_r"] = (
                    period["drawdown_r"]
                )

                row[f"{prefix}_win_rate"] = (
                    period["win_rate"]
                )

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
# SAVE RESULTS
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

    if not rows:

        pd.DataFrame(
            columns=[
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
        ).to_csv(
            output_path,
            index=False,
        )

        return pd.DataFrame()

    result = pd.DataFrame(rows)

    result = (
        result
        .drop_duplicates(
            [
                "direction",
                "session",
                "conditions",
                "rr",
            ]
        )
        .sort_values(
            [
                "score",
                "positive_periods",
                "trades",
                "net_r",
            ],
            ascending=False,
        )
        .reset_index(drop=True)
    )

    result.insert(
        0,
        "rank",
        range(1, len(result) + 1),
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

    # --------------------------------------------------------
    # PATHS
    # --------------------------------------------------------

    data_path = Path(args.data)
    registry_path = Path(args.db)
    output_path = Path(args.out)

    print()
    print("=" * 70)
    print("PATHS")
    print("=" * 70)

    print(
        f"Data:     {data_path}"
    )

    print(
        f"Registry: {registry_path}"
    )

    print(
        f"Output:   {output_path}"
    )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    df = load_data(data_path)

    df, available_features = prepare_features(df)

    if args.max_conditions > len(
        available_features
    ):

        args.max_conditions = len(
            available_features
        )

    # --------------------------------------------------------
    # REGISTRY
    # --------------------------------------------------------

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
        )

    finally:

        connection.close()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    result = save_results(
        rows,
        output_path,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TOP RESULTS
    # --------------------------------------------------------

    if not result.empty:

        print()
        print("=" * 70)
        print("TOP NEW DISCOVERY CANDIDATES")
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
            "No new candidates passed "
            "the discovery filters."
        )

    print()
    print("=" * 70)
    print("IMPORTANT")
    print("=" * 70)

    print(
        "You can run this script again."
    )

    print(
        "The SQLite registry will prevent "
        "already-tested strategies from "
        "being tested again."
    )

    print(
        "The next stage is to promote the "
        "strongest discovery candidates "
        "into the Top-100 pool."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()