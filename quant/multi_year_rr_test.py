from pathlib import Path
import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

FEATURE_FILE = Path("quant/feature_database.csv")

SUMMARY_FILE = Path("quant/multi_year_rr_summary.csv")
YEARLY_FILE = Path("quant/multi_year_rr_yearly.csv")
TRADE_FILE = Path("quant/multi_year_rr_trade_results.csv")

START_DATE = pd.Timestamp("2023-01-01 00:00:00+00:00")
END_DATE = pd.Timestamp("2026-08-31 23:59:59+00:00")

RR_VALUES = [round(x, 1) for x in np.arange(1.0, 2.01, 0.1)]

DIRECTION = "SELL"
SESSION = "New York"

REQUIRED_FEATURES = [
    "liquidity_sweep_high",
    "bearish_candle",
    "bearish_engulfing",
]


# =============================================================================
# HELPERS
# =============================================================================

def as_bool(series):
    """
    Convert common CSV boolean representations into real booleans.
    """
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y", "t"])
    )


def max_drawdown(r_values):
    """
    Calculate maximum drawdown in R.
    """
    if not r_values:
        return 0.0

    equity = np.cumsum(r_values)
    peaks = np.maximum.accumulate(np.insert(equity, 0, 0.0))[1:]
    drawdowns = peaks - equity

    return float(np.max(drawdowns))


def profit_factor(r_values):
    """
    Gross profit / gross loss.
    """
    wins = sum(r for r in r_values if r > 0)
    losses = abs(sum(r for r in r_values if r < 0))

    if losses == 0:
        if wins > 0:
            return float("inf")
        return 0.0

    return wins / losses


def print_result(rr, result):
    print(
        f"Trades: {result['trades']:4d} | "
        f"Wins: {result['wins']:4d} | "
        f"Losses: {result['losses']:4d} | "
        f"WR: {result['win_rate']:6.2f}% | "
        f"PF: {result['profit_factor']:6.3f} | "
        f"Exp: {result['expectancy_r']:7.4f}R | "
        f"Net R: {result['net_r']:8.2f} | "
        f"DD: {result['max_drawdown_r']:6.2f}R"
    )


# =============================================================================
# LOAD DATA
# =============================================================================

print()
print("=" * 80)
print("TRUE MULTI-YEAR HISTORICAL RR ROBUSTNESS TEST")
print("=" * 80)
print()

print("Strategy:")
print("SELL | New York")
print("liquidity_sweep_high + bearish_candle + bearish_engulfing")
print()

print("Requested period:")
print(f"{START_DATE} -> {END_DATE}")
print()

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

print("Loading feature/candle database...")

df = pd.read_csv(FEATURE_FILE)

print(f"Candles loaded: {len(df):,}")

# -------------------------------------------------------------------------
# Timestamp
# -------------------------------------------------------------------------

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce",
)

df = df.dropna(subset=["timestamp"])

# -------------------------------------------------------------------------
# Check required columns
# -------------------------------------------------------------------------

required_columns = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "session",
] + REQUIRED_FEATURES

missing = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing:
    raise ValueError(
        "Missing required columns:\n"
        + "\n".join(missing)
    )

# -------------------------------------------------------------------------
# Convert OHLC to numeric
# -------------------------------------------------------------------------

for column in ["open", "high", "low", "close"]:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )

df = df.dropna(
    subset=["open", "high", "low", "close"]
)

df = df.sort_values("timestamp").reset_index(drop=True)

# -------------------------------------------------------------------------
# Filter requested historical period
# -------------------------------------------------------------------------

period_mask = (
    (df["timestamp"] >= START_DATE)
    & (df["timestamp"] <= END_DATE)
)

df_period = df.loc[period_mask].copy()

print(
    f"Candles in requested period: "
    f"{len(df_period):,}"
)

if df_period.empty:
    raise RuntimeError(
        "No candles found in requested period."
    )

print(
    f"Actual data range used: "
    f"{df_period['timestamp'].min()} -> "
    f"{df_period['timestamp'].max()}"
)

# =============================================================================
# NORMALISE FEATURE COLUMNS
# =============================================================================

for column in REQUIRED_FEATURES:
    df_period[column] = as_bool(df_period[column])

df_period["session"] = (
    df_period["session"]
    .astype(str)
    .str.strip()
)

# =============================================================================
# FIND ALL SIGNALS
# =============================================================================

signal_mask = (
    (df_period["session"] == SESSION)
    & df_period["liquidity_sweep_high"]
    & df_period["bearish_candle"]
    & df_period["bearish_engulfing"]
)

signal_rows = df_period.loc[signal_mask].copy()

print()
print("=" * 80)
print("SIGNAL DISCOVERY")
print("=" * 80)

print(
    f"Raw strategy signals found: "
    f"{len(signal_rows):,}"
)

if signal_rows.empty:
    raise RuntimeError(
        "No matching strategy signals were found."
    )

# =============================================================================
# ONE POSITION AT A TIME
# =============================================================================
#
# We create candidate signals first.
#
# The position is considered active from the signal candle's close/entry
# until either stop or target is reached.
#
# If another signal occurs while a position is active, it is ignored.
#
# Entry = signal candle close.
#
# Stop = signal candle high.
#
# Risk = stop - entry.
#
# This matches the SELL structure used by the existing trade audit.
# =============================================================================

candidate_signals = []

for _, row in signal_rows.iterrows():

    entry_index = row.name
    entry_price = float(row["close"])
    stop_price = float(row["high"])

    risk = stop_price - entry_price

    if risk <= 0:
        continue

    candidate_signals.append(
        {
            "signal_index": entry_index,
            "entry_timestamp": row["timestamp"],
            "entry_price": entry_price,
            "stop_price": stop_price,
            "risk": risk,
        }
    )

print(
    f"Valid candidate signals: "
    f"{len(candidate_signals):,}"
)

# =============================================================================
# BUILD ONE-POSITION TRADE PATH
# =============================================================================

accepted_signals = []

next_available_index = -1

for signal in candidate_signals:

    signal_index = signal["signal_index"]

    if signal_index < next_available_index:
        continue

    entry_price = signal["entry_price"]
    stop_price = signal["stop_price"]
    risk = signal["risk"]

    # Find the first candle after entry.
    future = df.loc[
        df.index > signal_index
    ]

    exit_index = None
    exit_timestamp = None
    exit_price = None

    # We need the actual path for every RR later.
    #
    # To make the one-position constraint independent of RR, we use
    # the original 1R stop/target path to establish the signal sequence.
    #
    # The final RR calculations are then performed separately.
    target_price = entry_price - risk

    for future_index, future_row in future.iterrows():

        candle_high = float(future_row["high"])
        candle_low = float(future_row["low"])

        stop_hit = candle_high >= stop_price
        target_hit = candle_low <= target_price

        if stop_hit and target_hit:
            # Conservative assumption:
            # if both are touched inside the same candle,
            # assume the stop happened first.
            exit_index = future_index
            exit_timestamp = future_row["timestamp"]
            exit_price = stop_price
            break

        if stop_hit:
            exit_index = future_index
            exit_timestamp = future_row["timestamp"]
            exit_price = stop_price
            break

        if target_hit:
            exit_index = future_index
            exit_timestamp = future_row["timestamp"]
            exit_price = target_price
            break

    if exit_index is None:
        continue

    accepted_signals.append(
        {
            **signal,
            "exit_index_1r": exit_index,
            "exit_timestamp_1r": exit_timestamp,
            "exit_price_1r": exit_price,
        }
    )

    # Next signal must occur after this trade closes.
    next_available_index = exit_index + 1


print(
    f"Signals after one-position constraint: "
    f"{len(accepted_signals):,}"
)

if not accepted_signals:
    raise RuntimeError(
        "No trades survived the one-position constraint."
    )

# =============================================================================
# TRUE RR ENGINE
# =============================================================================
#
# For each accepted signal:
#
# SELL:
#
# Entry = close
# Stop  = high
# Risk  = stop - entry
#
# Target(RR) = entry - risk * RR
#
# We then scan subsequent candles.
#
# If both stop and target are touched in the same candle, we assume
# the stop happened first. This is deliberately conservative.
# =============================================================================

def run_rr_test(rr):

    trades = []

    for trade_number, signal in enumerate(
        accepted_signals,
        start=1,
    ):

        entry_index = signal["signal_index"]
        entry_timestamp = signal["entry_timestamp"]
        entry_price = signal["entry_price"]
        stop_price = signal["stop_price"]
        risk = signal["risk"]

        target_price = entry_price - (risk * rr)

        exit_index = None
        exit_timestamp = None
        exit_price = None
        exit_reason = None

        future = df.loc[
            df.index > entry_index
        ]

        for future_index, future_row in future.iterrows():

            candle_high = float(future_row["high"])
            candle_low = float(future_row["low"])

            stop_hit = candle_high >= stop_price
            target_hit = candle_low <= target_price

            if stop_hit and target_hit:
                exit_index = future_index
                exit_timestamp = future_row["timestamp"]
                exit_price = stop_price
                exit_reason = "STOP"
                break

            if stop_hit:
                exit_index = future_index
                exit_timestamp = future_row["timestamp"]
                exit_price = stop_price
                exit_reason = "STOP"
                break

            if target_hit:
                exit_index = future_index
                exit_timestamp = future_row["timestamp"]
                exit_price = target_price
                exit_reason = "TARGET"
                break

        # No exit available inside database.
        if exit_index is None:
            continue

        if exit_reason == "TARGET":
            r_value = rr
        else:
            r_value = -1.0

        trades.append(
            {
                "rr": rr,
                "trade_number": trade_number,
                "entry_timestamp": entry_timestamp,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "exit_timestamp": exit_timestamp,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "r": r_value,
                "year": entry_timestamp.year,
            }
        )

    if not trades:
        return None, []

    r_values = [
        trade["r"]
        for trade in trades
    ]

    wins = sum(
        1
        for r in r_values
        if r > 0
    )

    losses = sum(
        1
        for r in r_values
        if r < 0
    )

    total_trades = len(r_values)

    net_r = sum(r_values)

    expectancy = (
        net_r / total_trades
        if total_trades
        else 0.0
    )

    win_rate = (
        wins / total_trades * 100
        if total_trades
        else 0.0
    )

    pf = profit_factor(r_values)

    dd = max_drawdown(r_values)

    result = {
        "rr": rr,
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": pf,
        "expectancy_r": expectancy,
        "net_r": net_r,
        "max_drawdown_r": dd,
    }

    return result, trades


# =============================================================================
# RUN ALL RR VALUES
# =============================================================================

all_results = []
all_trade_results = []

print()
print("=" * 80)
print("TRUE HISTORICAL RR TEST")
print("=" * 80)
print()

for rr in RR_VALUES:

    print(f"Testing {rr:.1f}R ...")

    result, trades = run_rr_test(rr)

    if result is None:
        print("No completed trades.")
        continue

    print_result(
        rr,
        result,
    )

    all_results.append(result)

    all_trade_results.extend(trades)


# =============================================================================
# SUMMARY DATAFRAME
# =============================================================================

summary_df = pd.DataFrame(all_results)

if summary_df.empty:
    raise RuntimeError(
        "No RR results were generated."
    )

# Score:
#
# expectancy / drawdown
#
# Higher is better.
summary_df["score"] = np.where(
    summary_df["max_drawdown_r"] > 0,
    summary_df["expectancy_r"]
    / summary_df["max_drawdown_r"],
    0.0,
)

# =============================================================================
# YEARLY RESULTS
# =============================================================================

yearly_rows = []

trade_df = pd.DataFrame(all_trade_results)

for year in sorted(
    trade_df["year"].unique()
):

    for rr in RR_VALUES:

        year_trades = trade_df[
            (trade_df["year"] == year)
            & (trade_df["rr"] == rr)
        ].copy()

        if year_trades.empty:
            continue

        r_values = (
            year_trades["r"]
            .astype(float)
            .tolist()
        )

        wins = sum(
            r > 0
            for r in r_values
        )

        losses = sum(
            r < 0
            for r in r_values
        )

        trades = len(r_values)

        net_r = sum(r_values)

        expectancy = (
            net_r / trades
            if trades
            else 0.0
        )

        win_rate = (
            wins / trades * 100
            if trades
            else 0.0
        )

        yearly_rows.append(
            {
                "year": year,
                "rr": rr,
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "profit_factor": profit_factor(
                    r_values
                ),
                "expectancy_r": expectancy,
                "net_r": net_r,
                "max_drawdown_r": max_drawdown(
                    r_values
                ),
            }
        )

yearly_df = pd.DataFrame(yearly_rows)


# =============================================================================
# PRINT RESULTS
# =============================================================================

print()
print("=" * 80)
print("COMBINED RR RESULTS")
print("=" * 80)
print()

print(
    summary_df[
        [
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
    ].to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)

# =============================================================================
# BEST RESULTS
# =============================================================================

best_expectancy = summary_df.loc[
    summary_df["expectancy_r"].idxmax()
]

best_net_r = summary_df.loc[
    summary_df["net_r"].idxmax()
]

best_score = summary_df.loc[
    summary_df["score"].idxmax()
]

print()
print("=" * 80)
print("BEST HISTORICAL RESULTS")
print("=" * 80)

print()
print(
    f"Highest expectancy: "
    f"{best_expectancy['rr']:.1f}R"
)

print(
    f"Expectancy: "
    f"{best_expectancy['expectancy_r']:.4f}R"
)

print(
    f"Win rate: "
    f"{best_expectancy['win_rate']:.2f}%"
)

print(
    f"Profit factor: "
    f"{best_expectancy['profit_factor']:.3f}"
)

print(
    f"Net R: "
    f"{best_expectancy['net_r']:.2f}R"
)

print(
    f"Max DD: "
    f"{best_expectancy['max_drawdown_r']:.2f}R"
)

print()
print(
    f"Highest net R: "
    f"{best_net_r['rr']:.1f}R"
)

print(
    f"Net R: "
    f"{best_net_r['net_r']:.2f}R"
)

print()
print(
    f"Best expectancy/DD: "
    f"{best_score['rr']:.1f}R"
)

print(
    f"Score: "
    f"{best_score['score']:.4f}"
)

# =============================================================================
# YEARLY TABLE
# =============================================================================

print()
print("=" * 80)
print("YEAR-BY-YEAR RESULTS")
print("=" * 80)
print()

if not yearly_df.empty:

    print(
        yearly_df.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

else:

    print(
        "No yearly results available."
    )


# =============================================================================
# SAVE FILES
# =============================================================================

summary_df.to_csv(
    SUMMARY_FILE,
    index=False,
)

yearly_df.to_csv(
    YEARLY_FILE,
    index=False,
)

trade_df.to_csv(
    TRADE_FILE,
    index=False,
)

print()
print("=" * 80)
print("FILES SAVED")
print("=" * 80)

print()
print(SUMMARY_FILE)
print(YEARLY_FILE)
print(TRADE_FILE)

print()
print("=" * 80)
print("TRUE MULTI-YEAR TEST COMPLETE")
print("=" * 80)
print()