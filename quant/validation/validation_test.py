from pathlib import Path
import numpy as np
import pandas as pd

# ============================================================================
# OUT-OF-SAMPLE VALIDATION TEST
# ============================================================================
#
# These strategies were selected using 2025-2026 data.
# This script validates them WITHOUT changing their rules or RR.
#
# VALIDATION PERIOD:
#   2023-01-01 -> 2024-12-31
#
# STRATEGY 1:
#   SELL
#   bearish_fib_618_rejection + bearish_bos_fib_382
#   RR = 1.1
#
# STRATEGY 2:
#   BUY
#   bullish_fib_500_rejection + small_range + below_ema200
#   RR = 1.9
#
# IMPORTANT:
#   No optimisation is performed here.
#   No RR search is performed here.
#   No feature search is performed here.
# ============================================================================

FEATURE_FILE = Path("quant/feature_database.csv")
OUTPUT_DIR = Path("quant/validation")

SUMMARY_FILE = OUTPUT_DIR / "validation_summary.csv"
TRADE_FILE = OUTPUT_DIR / "validation_trade_results.csv"

START_DATE = "2023-01-01 00:00:00+00:00"
END_DATE = "2024-12-31 23:59:59+00:00"

SESSION = "New York"

# Maximum number of candles allowed for a trade to remain open.
MAX_HOLD_CANDLES = 2000

# ---------------------------------------------------------------------------
# LOCKED STRATEGIES
# ---------------------------------------------------------------------------

STRATEGIES = [
    {
        "name": "SELL_FIB618_REJECTION_BOS_FIB382",
        "direction": "SELL",
        "conditions": [
            "bearish_fib_618_rejection",
            "bearish_bos_fib_382",
        ],
        "rr": 1.1,
    },
    {
        "name": "BUY_FIB500_REJECTION_SMALL_RANGE_BELOW_EMA200",
        "direction": "BUY",
        "conditions": [
            "bullish_fib_500_rejection",
            "small_range",
            "below_ema200",
        ],
        "rr": 1.9,
    },
]


# ============================================================================
# HELPERS
# ============================================================================

def bool_series(series):
    """
    Convert feature columns safely to boolean.
    """
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float) != 0

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y"])
    )


def max_drawdown(values):
    """
    Calculate maximum peak-to-trough drawdown in R.
    """
    if len(values) == 0:
        return 0.0

    equity = np.cumsum(values)

    peaks = np.maximum.accumulate(
        np.insert(equity, 0, 0.0)
    )[1:]

    drawdowns = peaks - equity

    return float(drawdowns.max())


def build_signal(df, conditions):
    """
    Build the exact AND condition signal.
    """
    signal = np.ones(
        len(df),
        dtype=bool
    )

    for condition in conditions:
        signal &= df[condition].to_numpy(dtype=bool)

    return signal


def evaluate_strategy(df, signal, direction, rr):
    """
    Evaluate a fixed strategy using one-position-at-a-time.

    Entry:
        signal candle close

    SELL:
        stop = entry + max(candle_high - entry, ATR14)
        target = entry - distance * RR

    BUY:
        stop = entry - max(entry - candle_low, ATR14)
        target = entry + distance * RR

    Same candle stop + target:
        STOP is assumed to hit first (conservative).

    A position remains open until:
        - stop
        - target
        - MAX_HOLD_CANDLES
        - end of available data

    Open positions at the end are NOT counted as completed trades.
    """

    candidate_indices = np.flatnonzero(signal)

    results = []

    next_available_index = 0

    for idx in candidate_indices:

        # One-position-at-a-time constraint.
        if idx < next_available_index:
            continue

        if idx >= len(df) - 1:
            continue

        row = df.iloc[idx]

        entry = float(row["close"])
        high0 = float(row["high"])
        low0 = float(row["low"])

        atr = row.get("atr14", np.nan)

        if pd.isna(atr):
            atr = 0.0

        atr = float(atr)

        if direction == "SELL":

            distance = max(
                high0 - entry,
                atr
            )

            if distance <= 0:
                continue

            stop = entry + distance
            target = entry - distance * rr

        elif direction == "BUY":

            distance = max(
                entry - low0,
                atr
            )

            if distance <= 0:
                continue

            stop = entry - distance
            target = entry + distance * rr

        else:
            raise ValueError(
                f"Unknown direction: {direction}"
            )

        outcome = None
        exit_idx = None
        exit_reason = None

        end_idx = min(
            len(df) - 1,
            idx + MAX_HOLD_CANDLES
        )

        for j in range(idx + 1, end_idx + 1):

            candle_high = float(df.iloc[j]["high"])
            candle_low = float(df.iloc[j]["low"])

            if direction == "SELL":

                hit_stop = candle_high >= stop
                hit_target = candle_low <= target

                # Conservative assumption when both are hit
                # inside the same candle.
                if hit_stop and hit_target:
                    outcome = -1.0
                    exit_reason = "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST"
                    exit_idx = j
                    break

                if hit_stop:
                    outcome = -1.0
                    exit_reason = "STOP"
                    exit_idx = j
                    break

                if hit_target:
                    outcome = rr
                    exit_reason = "TARGET"
                    exit_idx = j
                    break

            else:

                hit_stop = candle_low <= stop
                hit_target = candle_high >= target

                # Conservative assumption when both are hit
                # inside the same candle.
                if hit_stop and hit_target:
                    outcome = -1.0
                    exit_reason = "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST"
                    exit_idx = j
                    break

                if hit_stop:
                    outcome = -1.0
                    exit_reason = "STOP"
                    exit_idx = j
                    break

                if hit_target:
                    outcome = rr
                    exit_reason = "TARGET"
                    exit_idx = j
                    break

        # Do not count unfinished positions.
        if outcome is None:
            continue

        results.append(
            {
                "signal_index": idx,
                "signal_timestamp": df.iloc[idx]["timestamp"],
                "entry": entry,
                "stop": stop,
                "target": target,
                "exit_index": exit_idx,
                "exit_timestamp": df.iloc[exit_idx]["timestamp"],
                "exit_reason": exit_reason,
                "outcome_r": outcome,
            }
        )

        # Lock the next available position until this trade exits.
        next_available_index = exit_idx + 1

    if not results:
        return None

    trades_df = pd.DataFrame(results)

    values = trades_df["outcome_r"].to_numpy(
        dtype=float
    )

    wins = int(np.sum(values > 0))
    losses = int(np.sum(values < 0))
    trades = len(values)

    net_r = float(values.sum())
    expectancy = float(values.mean())

    gross_profit = float(
        values[values > 0].sum()
    ) if wins else 0.0

    gross_loss = abs(
        float(values[values < 0].sum())
    ) if losses else 0.0

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    win_rate = (
        wins / trades * 100.0
    )

    dd = max_drawdown(values)

    score = expectancy / max(dd, 1.0)

    metrics = {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy_r": expectancy,
        "net_r": net_r,
        "max_drawdown_r": dd,
        "score": score,
    }

    return metrics, trades_df


# ============================================================================
# LOAD DATA
# ============================================================================

print("=" * 80)
print("OUT-OF-SAMPLE STRATEGY VALIDATION")
print("=" * 80)
print()

print("Validation period:")
print(f"{START_DATE} -> {END_DATE}")
print()

print("IMPORTANT:")
print("Rules and RR are LOCKED.")
print("No optimisation is being performed.")
print()

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

print("Loading feature database...")

df = pd.read_csv(FEATURE_FILE)

print(f"Candles loaded: {len(df):,}")

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce"
)

df = df.dropna(
    subset=["timestamp"]
)

start = pd.Timestamp(START_DATE)
end = pd.Timestamp(END_DATE)

df = df[
    (df["timestamp"] >= start)
    & (df["timestamp"] <= end)
].copy()

df = df.sort_values(
    "timestamp"
).reset_index(drop=True)

print(
    f"Candles in validation period: {len(df):,}"
)

if len(df) == 0:
    raise RuntimeError(
        "No candles found in validation period."
    )

print(
    "Actual data range used: "
    f"{df['timestamp'].min()} -> "
    f"{df['timestamp'].max()}"
)

# ============================================================================
# SESSION FILTER
# ============================================================================

if "session" not in df.columns:
    raise RuntimeError(
        "Missing required column: session"
    )

df = df[
    df["session"]
    .astype(str)
    .str.lower()
    == SESSION.lower()
].copy()

df = df.reset_index(drop=True)

print(
    f"{SESSION} candles: {len(df):,}"
)

# ============================================================================
# CHECK REQUIRED FEATURES
# ============================================================================

required_features = sorted(
    {
        condition
        for strategy in STRATEGIES
        for condition in strategy["conditions"]
    }
)

missing = [
    feature
    for feature in required_features
    if feature not in df.columns
]

if missing:
    print()
    print("MISSING FEATURE COLUMNS:")

    for feature in missing:
        print(f"  {feature}")

    raise RuntimeError(
        "Required validation features are missing."
    )

for feature in required_features:
    df[feature] = bool_series(
        df[feature]
    )

# ============================================================================
# RUN VALIDATION
# ============================================================================

summary_rows = []
all_trade_rows = []

print()
print("=" * 80)
print("RUNNING LOCKED VALIDATION TESTS")
print("=" * 80)
print()

for strategy in STRATEGIES:

    name = strategy["name"]
    direction = strategy["direction"]
    conditions = strategy["conditions"]
    rr = strategy["rr"]

    print("-" * 80)
    print(f"Strategy:   {name}")
    print(f"Direction:  {direction}")
    print(f"Conditions: {' + '.join(conditions)}")
    print(f"RR:         {rr:.1f}R")
    print("-" * 80)

    signal = build_signal(
        df,
        conditions
    )

    raw_signals = int(
        signal.sum()
    )

    print(
        f"Raw signals: {raw_signals}"
    )

    evaluation = evaluate_strategy(
        df=df,
        signal=signal,
        direction=direction,
        rr=rr,
    )

    if evaluation is None:

        print(
            "No completed trades."
        )
        print()

        summary_rows.append(
            {
                "strategy": name,
                "direction": direction,
                "conditions": " + ".join(conditions),
                "rr": rr,
                "raw_signals": raw_signals,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy_r": 0.0,
                "net_r": 0.0,
                "max_drawdown_r": 0.0,
                "score": 0.0,
            }
        )

        continue

    metrics, trades_df = evaluation

    trades_df.insert(
        0,
        "strategy",
        name
    )

    trades_df.insert(
        1,
        "direction",
        direction
    )

    trades_df.insert(
        2,
        "conditions",
        " + ".join(conditions)
    )

    trades_df.insert(
        3,
        "rr",
        rr
    )

    all_trade_rows.append(
        trades_df
    )

    summary_rows.append(
        {
            "strategy": name,
            "direction": direction,
            "conditions": " + ".join(conditions),
            "rr": rr,
            "raw_signals": raw_signals,
            "trades": metrics["trades"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"],
            "expectancy_r": metrics["expectancy_r"],
            "net_r": metrics["net_r"],
            "max_drawdown_r": metrics["max_drawdown_r"],
            "score": metrics["score"],
        }
    )

    print()
    print(
        f"Completed trades: {metrics['trades']}"
    )
    print(
        f"Wins:             {metrics['wins']}"
    )
    print(
        f"Losses:           {metrics['losses']}"
    )
    print(
        f"Win rate:         {metrics['win_rate']:.2f}%"
    )
    print(
        f"Profit factor:    {metrics['profit_factor']:.3f}"
    )
    print(
        f"Expectancy:       {metrics['expectancy_r']:.4f}R"
    )
    print(
        f"Net R:            {metrics['net_r']:.2f}R"
    )
    print(
        f"Max DD:            {metrics['max_drawdown_r']:.2f}R"
    )
    print(
        f"Score:             {metrics['score']:.6f}"
    )
    print()

# ============================================================================
# SAVE RESULTS
# ============================================================================

if not summary_rows:
    raise RuntimeError(
        "No validation results were produced."
    )

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

summary_df = pd.DataFrame(
    summary_rows
)

summary_df.to_csv(
    SUMMARY_FILE,
    index=False
)

if all_trade_rows:
    trade_df = pd.concat(
        all_trade_rows,
        ignore_index=True
    )
else:
    trade_df = pd.DataFrame()

trade_df.to_csv(
    TRADE_FILE,
    index=False
)

# ============================================================================
# FINAL COMPARISON
# ============================================================================

print()
print("=" * 80)
print("VALIDATION RESULTS")
print("=" * 80)
print()

display_cols = [
    "strategy",
    "direction",
    "rr",
    "raw_signals",
    "trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "expectancy_r",
    "net_r",
    "max_drawdown_r",
    "score",
]

print(
    summary_df[
        display_cols
    ].to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    )
)

# ============================================================================
# VERDICT
# ============================================================================

print()
print("=" * 80)
print("VALIDATION INTERPRETATION")
print("=" * 80)
print()

for _, row in summary_df.iterrows():

    print(
        f"{row['direction']} | "
        f"{row['conditions']}"
    )

    if row["trades"] == 0:
        print(
            "  RESULT: NO COMPLETED TRADES"
        )

    elif row["expectancy_r"] > 0:
        print(
            "  RESULT: POSITIVE VALIDATION EXPECTANCY"
        )

        print(
            f"  Net R: {row['net_r']:.2f}R | "
            f"PF: {row['profit_factor']:.3f} | "
            f"DD: {row['max_drawdown_r']:.2f}R"
        )

    else:
        print(
            "  RESULT: NEGATIVE VALIDATION EXPECTANCY"
        )

        print(
            f"  Net R: {row['net_r']:.2f}R | "
            f"PF: {row['profit_factor']:.3f} | "
            f"DD: {row['max_drawdown_r']:.2f}R"
        )

    print()

print("=" * 80)
print("FILES SAVED")
print("=" * 80)
print()

print(
    f"Summary:       {SUMMARY_FILE}"
)

print(
    f"Trade results: {TRADE_FILE}"
)

print()
print("VALIDATION COMPLETE")
