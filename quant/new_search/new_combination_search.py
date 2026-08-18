from pathlib import Path
from itertools import combinations
import numpy as np
import pandas as pd

FEATURE_FILE = Path("quant/feature_database.csv")
SAVED_FILE = Path("quant/saved_strategies.json")
OUTPUT_DIR = Path("quant/new_search")

SUMMARY_FILE = OUTPUT_DIR / "new_combination_results.csv"
TOP_FILE = OUTPUT_DIR / "new_combination_top100.csv"

START_DATE = "2025-01-01 00:00:00+00:00"
END_DATE = "2026-08-31 23:59:59+00:00"

DIRECTION = "SELL"
SESSION = "New York"

MIN_TRADES = 30
MAX_CONDITIONS = 4
TOP_N = 100

RR_VALUES = [round(x, 1) for x in np.arange(1.0, 2.01, 0.1)]

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

BASE_STRATEGY = {
    "liquidity_sweep_high",
    "bearish_candle",
    "bearish_engulfing",
}


def bool_series(s):
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)

    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0).astype(float) != 0

    return (
        s.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y"])
    )


def max_drawdown(values):
    if len(values) == 0:
        return 0.0

    equity = np.cumsum(values)
    peak = np.maximum.accumulate(
        np.insert(equity, 0, 0.0)
    )[1:]

    drawdown = peak - equity

    return float(drawdown.max())


def evaluate(signal, rr):
    """
    Historical SELL backtest.

    Entry:
        close of signal candle

    Stop:
        max(signal candle high - entry, ATR14)

    Target:
        entry - stop_distance * RR

    Important:
        Only one position may be open at a time.
        After a trade completes, later signals are considered.
    """

    indices = np.flatnonzero(signal)

    results = []

    next_available_index = -1

    for idx in indices:

        # One-position-at-a-time constraint.
        if idx <= next_available_index:
            continue

        if idx >= len(df) - 1:
            continue

        entry = float(df.iloc[idx]["close"])
        signal_high = float(df.iloc[idx]["high"])

        atr = df.iloc[idx].get("atr14", np.nan)

        if pd.isna(atr):
            atr = 0.0

        atr = float(atr)

        distance = max(
            signal_high - entry,
            atr
        )

        if distance <= 0:
            continue

        stop = entry + distance
        target = entry - distance * rr

        outcome = None
        exit_idx = None

        end_idx = min(
            len(df) - 1,
            idx + 2000
        )

        for j in range(idx + 1, end_idx + 1):

            candle_high = float(df.iloc[j]["high"])
            candle_low = float(df.iloc[j]["low"])

            hit_stop = candle_high >= stop
            hit_target = candle_low <= target

            # Conservative assumption:
            # if both are touched inside one candle,
            # stop is assumed to have occurred first.
            if hit_stop and hit_target:
                outcome = -1.0
                exit_idx = j
                break

            if hit_stop:
                outcome = -1.0
                exit_idx = j
                break

            if hit_target:
                outcome = rr
                exit_idx = j
                break

        if outcome is None:
            continue

        results.append(outcome)

        # No new position until this trade has completed.
        next_available_index = exit_idx

    if not results:
        return None

    values = np.asarray(
        results,
        dtype=float
    )

    wins = int(
        np.sum(values > 0)
    )

    losses = int(
        np.sum(values < 0)
    )

    trades = len(values)

    net_r = float(
        values.sum()
    )

    expectancy = float(
        values.mean()
    )

    gross_profit = float(
        values[values > 0].sum()
    ) if wins else 0.0

    gross_loss = abs(
        float(
            values[values < 0].sum()
        )
    ) if losses else 0.0

    if gross_loss:
        profit_factor = (
            gross_profit /
            gross_loss
        )
    elif gross_profit:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    win_rate = (
        wins /
        trades *
        100.0
    )

    dd = max_drawdown(values)

    score = (
        expectancy /
        max(dd, 1.0)
    )

    return {
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


print("=" * 80)
print("NEW STRATEGY COMBINATION DISCOVERY")
print("=" * 80)
print()

print(f"Direction: {DIRECTION}")
print(f"Session:   {SESSION}")
print(
    f"Period:    {START_DATE} -> {END_DATE}"
)
print()

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

print("Loading feature database...")

df = pd.read_csv(
    FEATURE_FILE
)

print(
    f"Candles loaded: {len(df):,}"
)

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce"
)

start = pd.Timestamp(
    START_DATE
)

end = pd.Timestamp(
    END_DATE
)

df = df[
    (df["timestamp"] >= start)
    &
    (df["timestamp"] <= end)
].copy()

df = df.sort_values(
    "timestamp"
).reset_index(
    drop=True
)

print(
    f"Candles in period: {len(df):,}"
)

if "session" in df.columns:

    df = df[
        df["session"]
        .astype(str)
        .str.lower()
        == SESSION.lower()
    ].copy()

    df = df.reset_index(
        drop=True
    )

print(
    f"New York candles: {len(df):,}"
)

# ---------------------------------------------------------------------
# CREATE MISSING EMA POLARITY FEATURES
# ---------------------------------------------------------------------

for ema in [
    "20",
    "50",
    "100",
    "200",
]:

    above = f"above_ema{ema}"
    below = f"below_ema{ema}"

    if (
        above in df.columns
        and below not in df.columns
    ):
        df[below] = (
            ~bool_series(df[above])
        )

# ---------------------------------------------------------------------
# CHECK FEATURES
# ---------------------------------------------------------------------

missing = [
    feature
    for feature in FEATURES
    if feature not in df.columns
]

if missing:

    print()
    print(
        "Missing feature columns:"
    )

    for feature in missing:
        print(
            f"  {feature}"
        )

    raise RuntimeError(
        "Required feature columns are missing."
    )

for feature in FEATURES:
    df[feature] = bool_series(
        df[feature]
    )

print()
print("=" * 80)
print("SEARCHING NEW COMBINATIONS")
print("=" * 80)
print()

results = []

for size in range(
    1,
    MAX_CONDITIONS + 1
):

    print(
        f"Testing {size}-condition combinations..."
    )

    qualifying = 0
    tested = 0

    for combo in combinations(
        FEATURES,
        size
    ):

        # Never rediscover the exact
        # saved strategy.
        if set(combo) == BASE_STRATEGY:
            continue

        signal = np.ones(
            len(df),
            dtype=bool
        )

        for feature in combo:

            signal &= (
                df[feature]
                .to_numpy(
                    dtype=bool
                )
            )

        candidate_count = int(
            signal.sum()
        )

        if candidate_count < MIN_TRADES:
            continue

        qualifying += 1

        for rr in RR_VALUES:

            metrics = evaluate(
                signal,
                rr
            )

            if metrics is None:
                continue

            if (
                metrics["trades"]
                < MIN_TRADES
            ):
                continue

            tested += 1

            results.append({
                "direction": DIRECTION,
                "session": SESSION,
                "conditions":
                    " + ".join(combo),
                "condition_count": size,
                "rr": rr,
                "trades":
                    metrics["trades"],
                "wins":
                    metrics["wins"],
                "losses":
                    metrics["losses"],
                "win_rate":
                    metrics["win_rate"],
                "profit_factor":
                    metrics["profit_factor"],
                "expectancy_r":
                    metrics["expectancy_r"],
                "net_r":
                    metrics["net_r"],
                "max_drawdown_r":
                    metrics["max_drawdown_r"],
                "score":
                    metrics["score"],
            })

    print(
        f"  Qualifying combinations: "
        f"{qualifying:,}"
    )

    print(
        f"  Tested RR combinations: "
        f"{tested:,}"
    )

    print()

# ---------------------------------------------------------------------
# SAVE RESULTS
# ---------------------------------------------------------------------

if not results:

    raise RuntimeError(
        "No qualifying combinations were found."
    )

results_df = pd.DataFrame(
    results
)

results_df = results_df.sort_values(
    [
        "score",
        "expectancy_r",
        "net_r",
    ],
    ascending=False
).reset_index(
    drop=True
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

results_df.to_csv(
    SUMMARY_FILE,
    index=False
)

results_df.head(
    TOP_N
).to_csv(
    TOP_FILE,
    index=False
)

# ---------------------------------------------------------------------
# DISPLAY RESULTS
# ---------------------------------------------------------------------

print()
print("=" * 80)
print("TOP 20 NEW STRATEGY COMBINATIONS")
print("=" * 80)
print()

display_columns = [
    "conditions",
    "rr",
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
    results_df.head(20)[
        display_columns
    ].to_string(
        index=False,
        float_format=lambda x:
            f"{x:.4f}"
    )
)

best = results_df.iloc[0]

print()
print("=" * 80)
print("BEST NEW COMBINATION")
print("=" * 80)
print()

print(
    f"Conditions:    "
    f"{best['conditions']}"
)

print(
    f"RR:            "
    f"{best['rr']:.1f}R"
)

print(
    f"Trades:        "
    f"{int(best['trades'])}"
)

print(
    f"Wins:          "
    f"{int(best['wins'])}"
)

print(
    f"Losses:        "
    f"{int(best['losses'])}"
)

print(
    f"Win rate:      "
    f"{best['win_rate']:.2f}%"
)

print(
    f"Profit factor: "
    f"{best['profit_factor']:.3f}"
)

print(
    f"Expectancy:    "
    f"{best['expectancy_r']:.4f}R"
)

print(
    f"Net R:         "
    f"{best['net_r']:.2f}R"
)

print(
    f"Max DD:        "
    f"{best['max_drawdown_r']:.2f}R"
)

print(
    f"Score:         "
    f"{best['score']:.6f}"
)

print()
print("=" * 80)
print("FILES SAVED")
print("=" * 80)
print()

print(
    f"All results: "
    f"{SUMMARY_FILE}"
)

print(
    f"Top 100:     "
    f"{TOP_FILE}"
)

print()
print("SEARCH COMPLETE")
