from pathlib import Path
import pandas as pd
import numpy as np

# =============================================================================
# TRUE RECENT-YEAR HISTORICAL RR ROBUSTNESS TEST
# =============================================================================

FEATURE_FILE = Path("quant/feature_database.csv")

OUTPUT_SUMMARY = Path("quant/recent_year_rr_summary.csv")
OUTPUT_TRADES = Path("quant/recent_year_rr_trade_results.csv")

START_DATE = pd.Timestamp("2025-01-01", tz="UTC")
END_DATE = pd.Timestamp("2026-08-31 23:59:59", tz="UTC")

# Test every 0.1R from 1R to 2R
RR_VALUES = [
    round(x, 1)
    for x in np.arange(1.0, 2.01, 0.1)
]

STRATEGY_NAME = (
    "SELL | New York | "
    "liquidity_sweep_high + bearish_candle + bearish_engulfing"
)

print("=" * 80)
print("TRUE RECENT-YEAR HISTORICAL RR ROBUSTNESS TEST")
print("=" * 80)

print()
print("Strategy:")
print(STRATEGY_NAME)

print()
print("Requested period:")
print(f"{START_DATE} -> {END_DATE}")

# =============================================================================
# LOAD FEATURE DATABASE
# =============================================================================

print()
print("Loading feature/candle database...")

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

df = pd.read_csv(FEATURE_FILE)

print(f"Candles loaded: {len(df):,}")

# =============================================================================
# TIMESTAMP
# =============================================================================

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce",
)

df = df.dropna(
    subset=["timestamp"]
).copy()

df = df.sort_values(
    "timestamp"
).reset_index(drop=True)

# =============================================================================
# FILTER PERIOD
# =============================================================================

period_df = df[
    (df["timestamp"] >= START_DATE)
    & (df["timestamp"] <= END_DATE)
].copy()

# VERY IMPORTANT:
# Reset index after filtering so iloc/index positions match correctly.
period_df = period_df.reset_index(drop=True)

print(
    f"Candles in requested period: "
    f"{len(period_df):,}"
)

if period_df.empty:
    raise RuntimeError(
        "No candles found in requested period."
    )

print(
    "Actual data range used:",
    period_df["timestamp"].iloc[0],
    "->",
    period_df["timestamp"].iloc[-1],
)

# =============================================================================
# SIGNAL DISCOVERY
# =============================================================================

print()
print("=" * 80)
print("SIGNAL DISCOVERY")
print("=" * 80)

signal_mask = (
    (period_df["session"] == "New York")
    & (period_df["liquidity_sweep_high"] == True)
    & (period_df["bearish_candle"] == True)
    & (period_df["bearish_engulfing"] == True)
)

signal_positions = np.flatnonzero(
    signal_mask.to_numpy()
)

print(
    f"Raw strategy signals found: "
    f"{len(signal_positions):,}"
)

# =============================================================================
# PREPARE ARRAYS
# =============================================================================

timestamps = period_df["timestamp"].to_numpy()
opens = period_df["open"].to_numpy()
highs = period_df["high"].to_numpy()
lows = period_df["low"].to_numpy()
closes = period_df["close"].to_numpy()

# =============================================================================
# BUILD CANDIDATES
# =============================================================================

candidates = []

for signal_idx in signal_positions:

    entry_price = float(
        closes[signal_idx]
    )

    stop_price = float(
        highs[signal_idx]
    )

    risk = stop_price - entry_price

    # SELL requires stop above entry.
    if risk <= 0:
        continue

    candidates.append(
        {
            "signal_idx": int(signal_idx),
            "entry_timestamp": timestamps[signal_idx],
            "entry_price": entry_price,
            "stop_price": stop_price,
            "risk": risk,
        }
    )

print(
    f"Valid candidate signals: "
    f"{len(candidates):,}"
)

if not candidates:
    raise RuntimeError(
        "No valid candidate signals found."
    )

# =============================================================================
# TRUE HISTORICAL RR TEST
# =============================================================================

all_results = []
all_trade_results = []

for rr in RR_VALUES:

    print()
    print(f"Testing {rr:.1f}R ...")

    trades = []

    # Index of first candle that may contain the next entry.
    next_available_idx = 0

    for candidate in candidates:

        signal_idx = candidate["signal_idx"]

        # One position at a time.
        if signal_idx < next_available_idx:
            continue

        entry_price = candidate["entry_price"]
        stop_price = candidate["stop_price"]
        risk = candidate["risk"]
        entry_timestamp = candidate["entry_timestamp"]

        # SELL target is below entry.
        target_price = (
            entry_price
            - (risk * rr)
        )

        exit_idx = None
        exit_reason = None
        exit_price = None

        # Start checking AFTER the signal candle.
        for j in range(
            signal_idx + 1,
            len(period_df)
        ):

            candle_high = float(
                highs[j]
            )

            candle_low = float(
                lows[j]
            )

            stop_hit = (
                candle_high >= stop_price
            )

            target_hit = (
                candle_low <= target_price
            )

            # Conservative intrabar assumption:
            # if both target and stop occur in
            # the same candle, stop wins.
            if stop_hit and target_hit:

                exit_idx = j
                exit_reason = "STOP"
                exit_price = stop_price

                break

            if stop_hit:

                exit_idx = j
                exit_reason = "STOP"
                exit_price = stop_price

                break

            if target_hit:

                exit_idx = j
                exit_reason = "TARGET"
                exit_price = target_price

                break

        # Trade remains open at end of dataset.
        # Do not count it as a completed trade.
        if exit_idx is None:
            continue

        if exit_reason == "TARGET":
            result_r = rr
        else:
            result_r = -1.0

        trades.append(
            {
                "rr": rr,
                "entry_timestamp": entry_timestamp,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "exit_timestamp": timestamps[exit_idx],
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "r": result_r,
            }
        )

        # Cannot take another trade until this
        # trade has exited.
        next_available_idx = exit_idx + 1

    # =========================================================================
    # STATISTICS
    # =========================================================================

    if not trades:

        print(
            "No completed trades."
        )

        continue

    trade_df = pd.DataFrame(
        trades
    )

    wins = int(
        (trade_df["r"] > 0).sum()
    )

    losses = int(
        (trade_df["r"] < 0).sum()
    )

    total_trades = len(
        trade_df
    )

    win_rate = (
        wins / total_trades
    )

    gross_profit = trade_df.loc[
        trade_df["r"] > 0,
        "r"
    ].sum()

    gross_loss = abs(
        trade_df.loc[
            trade_df["r"] < 0,
            "r"
        ].sum()
    )

    if gross_loss > 0:
        profit_factor = (
            gross_profit /
            gross_loss
        )
    else:
        profit_factor = float("inf")

    net_r = trade_df["r"].sum()

    expectancy = trade_df["r"].mean()

    cumulative_r = (
        trade_df["r"]
        .cumsum()
    )

    running_peak = (
        cumulative_r
        .cummax()
    )

    drawdown = (
        running_peak
        - cumulative_r
    )

    max_drawdown = drawdown.max()

    # =========================================================================
    # OUTPUT
    # =========================================================================

    print(
        f"Trades: {total_trades:4d} | "
        f"Wins: {wins:4d} | "
        f"Losses: {losses:4d} | "
        f"WR: {win_rate * 100:6.2f}% | "
        f"PF: {profit_factor:6.3f} | "
        f"Exp: {expectancy:7.4f}R | "
        f"Net R: {net_r:8.2f} | "
        f"DD: {max_drawdown:6.2f}R"
    )

    all_results.append(
        {
            "rr": rr,
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy_r": expectancy,
            "net_r": net_r,
            "max_drawdown_r": max_drawdown,
        }
    )

    trade_df["cumulative_r"] = (
        trade_df["r"].cumsum()
    )

    trade_df["drawdown_r"] = (
        trade_df["cumulative_r"].cummax()
        - trade_df["cumulative_r"]
    )

    all_trade_results.append(
        trade_df
    )

# =============================================================================
# FINAL RESULTS
# =============================================================================

if not all_results:

    raise RuntimeError(
        "No completed trade results were produced."
    )

results_df = pd.DataFrame(
    all_results
)

print()
print("=" * 80)
print("RESULTS")
print("=" * 80)

print()

print(
    results_df[
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
        ]
    ].to_string(
        index=False,
        float_format=lambda x:
            f"{x:.4f}",
    )
)

# =============================================================================
# SCORE
# =============================================================================

results_df[
    "expectancy_dd_score"
] = np.where(
    results_df["max_drawdown_r"] > 0,
    results_df["expectancy_r"]
    / results_df["max_drawdown_r"],
    np.nan,
)

# =============================================================================
# BEST EXPECTANCY
# =============================================================================

best_expectancy = results_df.loc[
    results_df["expectancy_r"].idxmax()
]

# =============================================================================
# BEST NET R
# =============================================================================

best_net_r = results_df.loc[
    results_df["net_r"].idxmax()
]

# =============================================================================
# BEST EXPECTANCY / DD
# =============================================================================

best_score = results_df.loc[
    results_df["expectancy_dd_score"].idxmax()
]

# =============================================================================
# PRINT BEST
# =============================================================================

print()
print("=" * 80)
print("BEST HISTORICAL RESULTS")
print("=" * 80)

print()
print("Highest historical expectancy:")
print(
    f"RR:                 "
    f"{best_expectancy['rr']:.1f}R"
)
print(
    f"Expectancy:         "
    f"{best_expectancy['expectancy_r']:.4f}R"
)
print(
    f"Win rate:           "
    f"{best_expectancy['win_rate'] * 100:.2f}%"
)
print(
    f"Profit factor:      "
    f"{best_expectancy['profit_factor']:.3f}"
)
print(
    f"Net R:              "
    f"{best_expectancy['net_r']:.2f}R"
)
print(
    f"Max DD:             "
    f"{best_expectancy['max_drawdown_r']:.2f}R"
)

print()
print("Highest historical net R:")
print(
    f"RR:                 "
    f"{best_net_r['rr']:.1f}R"
)
print(
    f"Net R:              "
    f"{best_net_r['net_r']:.2f}R"
)
print(
    f"Win rate:           "
    f"{best_net_r['win_rate'] * 100:.2f}%"
)
print(
    f"Profit factor:      "
    f"{best_net_r['profit_factor']:.3f}"
)
print(
    f"Max DD:             "
    f"{best_net_r['max_drawdown_r']:.2f}R"
)

print()
print("Best expectancy / drawdown:")
print(
    f"RR:                 "
    f"{best_score['rr']:.1f}R"
)
print(
    f"Score:              "
    f"{best_score['expectancy_dd_score']:.4f}"
)
print(
    f"Expectancy:         "
    f"{best_score['expectancy_r']:.4f}R"
)
print(
    f"Max DD:             "
    f"{best_score['max_drawdown_r']:.2f}R"
)

# =============================================================================
# SAVE
# =============================================================================

results_df.to_csv(
    OUTPUT_SUMMARY,
    index=False,
)

combined_trades = pd.concat(
    all_trade_results,
    ignore_index=True,
)

combined_trades.to_csv(
    OUTPUT_TRADES,
    index=False,
)

print()
print("Saved summary:")
print(OUTPUT_SUMMARY)

print()
print("Saved trade results:")
print(OUTPUT_TRADES)

print()
print("=" * 80)
print("RECENT-YEAR TEST COMPLETE")
print("=" * 80)