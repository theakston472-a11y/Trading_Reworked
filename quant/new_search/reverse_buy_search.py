from pathlib import Path
import numpy as np
import pandas as pd

FEATURE_FILE = Path("quant/feature_database.csv")
SELL_TOP_FILE = Path("quant/new_search/new_combination_top100.csv")
OUTPUT_DIR = Path("quant/new_search")

RESULTS_FILE = OUTPUT_DIR / "reverse_buy_results.csv"
TOP_FILE = OUTPUT_DIR / "reverse_buy_top20.csv"

START_DATE = "2025-01-01 00:00:00+00:00"
END_DATE = "2026-08-31 23:59:59+00:00"

SESSION = "New York"

MIN_TRADES = 30
TOP_SELL_CANDIDATES = 20

RR_VALUES = [round(x, 1) for x in np.arange(1.0, 2.01, 0.1)]

# ---------------------------------------------------------------------------
# SELL -> BUY FEATURE MIRROR
# ---------------------------------------------------------------------------

MIRROR = {
    "liquidity_sweep_high": "liquidity_sweep_low",
    "previous_day_high_sweep": "previous_day_low_sweep",

    "bearish_candle": "bullish_candle",
    "bearish_engulfing": "bullish_engulfing",
    "bearish_pin_bar": "bullish_pin_bar",
    "strong_bearish_candle": "strong_bullish_candle",

    "bearish_bos": "bullish_bos",
    "bearish_choch": "bullish_choch",

    "lower_high": "higher_high",
    "lower_low": "higher_low",

    "bearish_fvg": "bullish_fvg",

    "bearish_fib_liquidity": "bullish_fib_liquidity",

    "bearish_fib_382_rejection": "bullish_fib_382_rejection",
    "bearish_fib_500_rejection": "bullish_fib_500_rejection",
    "bearish_fib_618_rejection": "bullish_fib_618_rejection",

    "bearish_bos_fib_382": "bullish_bos_fib_382",
    "bearish_bos_fib_500": "bullish_bos_fib_500",
    "bearish_bos_fib_618": "bullish_bos_fib_618",

    "near_fib_382": "near_fib_382",
    "near_fib_500": "near_fib_500",
    "near_fib_618": "near_fib_618",

    "small_range": "small_range",
    "large_range": "large_range",

    "above_ema20": "below_ema20",
    "above_ema50": "below_ema50",
    "above_ema100": "below_ema100",
    "above_ema200": "below_ema200",
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

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
    equity = np.cumsum(values)

    if len(equity) == 0:
        return 0.0

    peak = np.maximum.accumulate(
        np.insert(equity, 0, 0.0)
    )[1:]

    drawdown = peak - equity

    return float(drawdown.max())


def evaluate(signal, rr):
    indices = np.flatnonzero(signal)

    results = []

    in_trade_until = -1

    for idx in indices:

        # One-position-at-a-time constraint.
        if idx <= in_trade_until:
            continue

        if idx >= len(df) - 1:
            continue

        entry = float(df.iloc[idx]["close"])
        low0 = float(df.iloc[idx]["low"])

        atr = df.iloc[idx].get("atr14", np.nan)

        if pd.isna(atr):
            atr = 0.0

        atr = float(atr)

        # BUY:
        # Stop below entry.
        distance = max(entry - low0, atr)

        if distance <= 0:
            continue

        stop = entry - distance
        target = entry + distance * rr

        outcome = None
        exit_idx = None

        end_idx = min(len(df) - 1, idx + 2000)

        for j in range(idx + 1, end_idx + 1):

            candle_high = float(df.iloc[j]["high"])
            candle_low = float(df.iloc[j]["low"])

            hit_stop = candle_low <= stop
            hit_target = candle_high >= target

            # Conservative assumption:
            # If both are touched inside the same candle,
            # assume the stop was hit first.
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

        if outcome is not None:
            results.append(outcome)
            in_trade_until = exit_idx

    if not results:
        return None

    values = np.array(results, dtype=float)

    wins = int(np.sum(values > 0))
    losses = int(np.sum(values < 0))
    trades = len(values)

    net_r = float(values.sum())
    expectancy = float(values.mean())

    gross_profit = (
        float(values[values > 0].sum())
        if wins
        else 0.0
    )

    gross_loss = (
        abs(float(values[values < 0].sum()))
        if losses
        else 0.0
    )

    if gross_loss:
        profit_factor = gross_profit / gross_loss
    elif gross_profit:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    win_rate = wins / trades * 100.0

    dd = max_drawdown(values)

    score = expectancy / max(dd, 1.0)

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


# ---------------------------------------------------------------------------
# START
# ---------------------------------------------------------------------------

print("=" * 80)
print("REVERSE BUY STRATEGY TEST")
print("=" * 80)
print()

print("SELL candidates -> BUY mirror")
print(f"Session: {SESSION}")
print(f"Period:  {START_DATE} -> {END_DATE}")
print()

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

if not SELL_TOP_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {SELL_TOP_FILE}"
    )

print("Loading feature database...")

df = pd.read_csv(FEATURE_FILE)

print(f"Candles loaded: {len(df):,}")

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce",
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

print(f"Candles in period: {len(df):,}")

if "session" in df.columns:
    df = df[
        df["session"].astype(str).str.lower()
        == SESSION.lower()
    ].copy()

df = df.reset_index(drop=True)

print(f"New York candles: {len(df):,}")
print()

# ---------------------------------------------------------------------------
# CREATE MISSING EMA POLARITY FEATURES
# ---------------------------------------------------------------------------

for ema in ["20", "50", "100", "200"]:

    above = f"above_ema{ema}"
    below = f"below_ema{ema}"

    if above in df.columns and below not in df.columns:
        df[below] = ~bool_series(df[above])

    if below in df.columns and above not in df.columns:
        df[above] = ~bool_series(df[below])

# ---------------------------------------------------------------------------
# LOAD SELL RESULTS
# ---------------------------------------------------------------------------

print("Loading strongest SELL candidates...")

sell_df = pd.read_csv(SELL_TOP_FILE)

if "conditions" not in sell_df.columns:
    raise RuntimeError(
        "SELL results do not contain a 'conditions' column."
    )

# Prefer the strongest distinct condition sets.
distinct_conditions = []

for conditions in sell_df["conditions"].astype(str):

    if conditions not in distinct_conditions:
        distinct_conditions.append(conditions)

    if len(distinct_conditions) >= TOP_SELL_CANDIDATES:
        break

print(
    f"Distinct SELL candidates selected: "
    f"{len(distinct_conditions)}"
)

print()

# ---------------------------------------------------------------------------
# MIRROR FEATURES
# ---------------------------------------------------------------------------

buy_candidates = []

for sell_conditions in distinct_conditions:

    sell_features = [
        x.strip()
        for x in sell_conditions.split("+")
    ]

    buy_features = []

    valid = True

    for feature in sell_features:

        feature = feature.strip()

        if feature not in MIRROR:
            print(
                f"Skipping unsupported feature: {feature}"
            )
            valid = False
            break

        mirrored = MIRROR[feature]

        if mirrored not in buy_features:
            buy_features.append(mirrored)

    if not valid:
        continue

    if not buy_features:
        continue

    buy_conditions = " + ".join(buy_features)

    if buy_conditions not in [
        x["conditions"]
        for x in buy_candidates
    ]:
        buy_candidates.append({
            "sell_conditions": sell_conditions,
            "conditions": buy_conditions,
        })

print("BUY mirror candidates:")

for i, candidate in enumerate(
    buy_candidates,
    start=1,
):
    print(
        f"{i:2d}. "
        f"{candidate['conditions']}"
    )

print()

# ---------------------------------------------------------------------------
# CHECK FEATURES
# ---------------------------------------------------------------------------

required_features = set()

for candidate in buy_candidates:

    for feature in candidate["conditions"].split("+"):
        required_features.add(feature.strip())

missing = [
    feature
    for feature in sorted(required_features)
    if feature not in df.columns
]

if missing:

    print("Missing BUY feature columns:")

    for feature in missing:
        print(f"  {feature}")

    raise RuntimeError(
        "Required BUY mirror feature columns are missing."
    )

for feature in required_features:
    df[feature] = bool_series(df[feature])

# ---------------------------------------------------------------------------
# TEST BUY CANDIDATES
# ---------------------------------------------------------------------------

results = []

print("=" * 80)
print("TESTING BUY MIRRORS")
print("=" * 80)
print()

for candidate_number, candidate in enumerate(
    buy_candidates,
    start=1,
):

    conditions = candidate["conditions"]

    features = [
        x.strip()
        for x in conditions.split("+")
    ]

    signal = np.ones(
        len(df),
        dtype=bool,
    )

    for feature in features:
        signal &= df[feature].to_numpy(
            dtype=bool
        )

    candidate_count = int(signal.sum())

    print(
        f"[{candidate_number}/{len(buy_candidates)}] "
        f"{conditions}"
    )

    print(
        f"  Candidate signals: "
        f"{candidate_count}"
    )

    if candidate_count < MIN_TRADES:
        print(
            f"  Skipped: fewer than "
            f"{MIN_TRADES} signals."
        )
        print()
        continue

    for rr in RR_VALUES:

        metrics = evaluate(
            signal,
            rr,
        )

        if metrics is None:
            continue

        if metrics["trades"] < MIN_TRADES:
            continue

        results.append({
            "direction": "BUY",
            "session": SESSION,
            "sell_conditions": candidate[
                "sell_conditions"
            ],
            "conditions": conditions,
            "rr": rr,
            "trades": metrics["trades"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics[
                "profit_factor"
            ],
            "expectancy_r": metrics[
                "expectancy_r"
            ],
            "net_r": metrics["net_r"],
            "max_drawdown_r": metrics[
                "max_drawdown_r"
            ],
            "score": metrics["score"],
        })

    print()

# ---------------------------------------------------------------------------
# SAVE
# ---------------------------------------------------------------------------

if not results:
    raise RuntimeError(
        "No qualifying BUY mirror results were produced."
    )

results_df = pd.DataFrame(results)

results_df = results_df.sort_values(
    [
        "score",
        "expectancy_r",
        "net_r",
    ],
    ascending=False,
).reset_index(drop=True)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

results_df.to_csv(
    RESULTS_FILE,
    index=False,
)

results_df.head(20).to_csv(
    TOP_FILE,
    index=False,
)

# ---------------------------------------------------------------------------
# DISPLAY
# ---------------------------------------------------------------------------

print()
print("=" * 80)
print("TOP BUY MIRROR RESULTS")
print("=" * 80)
print()

display_cols = [
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
    results_df.head(20)[display_cols].to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)

best = results_df.iloc[0]

print()
print("=" * 80)
print("BEST BUY MIRROR")
print("=" * 80)
print()

print(
    f"Conditions:    {best['conditions']}"
)
print(
    f"Original SELL: {best['sell_conditions']}"
)
print(
    f"RR:            {best['rr']:.1f}R"
)
print(
    f"Trades:        {int(best['trades'])}"
)
print(
    f"Wins:          {int(best['wins'])}"
)
print(
    f"Losses:        {int(best['losses'])}"
)
print(
    f"Win rate:      {best['win_rate']:.2f}%"
)
print(
    f"Profit factor: {best['profit_factor']:.3f}"
)
print(
    f"Expectancy:    {best['expectancy_r']:.4f}R"
)
print(
    f"Net R:         {best['net_r']:.2f}R"
)
print(
    f"Max DD:        {best['max_drawdown_r']:.2f}R"
)
print(
    f"Score:         {best['score']:.6f}"
)

print()
print("=" * 80)
print("FILES SAVED")
print("=" * 80)
print()

print(f"All BUY results: {RESULTS_FILE}")
print(f"Top 20 BUY:      {TOP_FILE}")

print()
print("BUY MIRROR TEST COMPLETE")
