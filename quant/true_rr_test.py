import pandas as pd
import numpy as np
from pathlib import Path

AUDIT_FILE = Path("quant/trade_audit.csv")
FEATURE_FILE = Path("quant/feature_database.csv")

SUMMARY_FILE = Path("quant/true_rr_summary.csv")
TRADE_RESULTS_FILE = Path("quant/true_rr_trade_results.csv")

# Test 1.0R through 2.0R in 0.1R increments
RR_VALUES = [round(x, 1) for x in np.arange(1.0, 2.01, 0.1)]

DIRECTION = "SELL"
SESSION = "New York"

STRATEGY_NAME = (
    "liquidity_sweep_high + bearish_candle + bearish_engulfing"
)

print("=" * 80)
print("TRUE HISTORICAL RR TEST — 0.1R THROUGH 2.0R")
print("=" * 80)

print()
print("Strategy:")
print(f"{DIRECTION} | {SESSION}")
print(STRATEGY_NAME)

# -------------------------------------------------------------------------
# LOAD AUDIT
# -------------------------------------------------------------------------

print()
print("Loading trade audit...")

if not AUDIT_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {AUDIT_FILE}"
    )

audit = pd.read_csv(AUDIT_FILE)

print(f"Audited rows: {len(audit)}")

required_columns = [
    "entry_timestamp",
    "entry_price",
    "stop_price",
]

missing = [
    column
    for column in required_columns
    if column not in audit.columns
]

if missing:
    raise ValueError(
        f"Missing required audit columns: {missing}"
    )

audit["entry_timestamp"] = pd.to_datetime(
    audit["entry_timestamp"],
    utc=True,
    errors="coerce",
)

audit["entry_price"] = pd.to_numeric(
    audit["entry_price"],
    errors="coerce",
)

audit["stop_price"] = pd.to_numeric(
    audit["stop_price"],
    errors="coerce",
)

audit = audit.dropna(
    subset=[
        "entry_timestamp",
        "entry_price",
        "stop_price",
    ]
).copy()

audit = audit.sort_values(
    "entry_timestamp"
).reset_index(drop=True)

# -------------------------------------------------------------------------
# ONE POSITION AT A TIME
# -------------------------------------------------------------------------

print()
print("Applying one-position-at-a-time constraint...")

selected = []

last_exit = None

for _, trade in audit.iterrows():

    entry_time = trade["entry_timestamp"]

    exit_time = None

    if "exit_timestamp" in audit.columns:

        candidate = pd.to_datetime(
            trade["exit_timestamp"],
            utc=True,
            errors="coerce",
        )

        if pd.notna(candidate):
            exit_time = candidate

    if last_exit is None:
        selected.append(trade)

        if exit_time is not None:
            last_exit = exit_time

        continue

    if entry_time >= last_exit:

        selected.append(trade)

        if exit_time is not None:
            last_exit = exit_time

audit = pd.DataFrame(
    selected
).reset_index(drop=True)

print(
    f"Trades after constraint: {len(audit)}"
)

if len(audit) == 0:
    raise ValueError(
        "No trades remain after one-position constraint."
    )

# -------------------------------------------------------------------------
# LOAD FEATURE DATABASE
# -------------------------------------------------------------------------

print()
print("Loading feature/candle database...")

if not FEATURE_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {FEATURE_FILE}"
    )

df = pd.read_csv(FEATURE_FILE)

print(
    f"Candles loaded: {len(df):,}"
)

# -------------------------------------------------------------------------
# FIND TIMESTAMP
# -------------------------------------------------------------------------

timestamp_candidates = [
    "timestamp",
    "datetime",
    "time",
    "date",
]

timestamp_column = None

for column in timestamp_candidates:

    if column in df.columns:
        timestamp_column = column
        break

if timestamp_column is None:
    raise ValueError(
        "Could not find timestamp column in feature database."
    )

df[timestamp_column] = pd.to_datetime(
    df[timestamp_column],
    utc=True,
    errors="coerce",
)

df = df.dropna(
    subset=[timestamp_column]
).copy()

df = df.sort_values(
    timestamp_column
).reset_index(drop=True)

# -------------------------------------------------------------------------
# FIND HIGH / LOW
# -------------------------------------------------------------------------

def find_column(candidates):

    for candidate in candidates:

        if candidate in df.columns:
            return candidate

    return None


HIGH_COL = find_column(
    ["high", "High", "HIGH"]
)

LOW_COL = find_column(
    ["low", "Low", "LOW"]
)

if HIGH_COL is None:
    raise ValueError(
        "Could not find HIGH column."
    )

if LOW_COL is None:
    raise ValueError(
        "Could not find LOW column."
    )

df[HIGH_COL] = pd.to_numeric(
    df[HIGH_COL],
    errors="coerce",
)

df[LOW_COL] = pd.to_numeric(
    df[LOW_COL],
    errors="coerce",
)

df = df.dropna(
    subset=[
        HIGH_COL,
        LOW_COL,
    ]
).copy()

# -------------------------------------------------------------------------
# TRUE HISTORICAL RR TEST
# -------------------------------------------------------------------------

def test_rr(rr):

    results = []

    for trade_index, (_, trade) in enumerate(
        audit.iterrows()
    ):

        entry_time = trade["entry_timestamp"]

        entry_price = float(
            trade["entry_price"]
        )

        stop_price = float(
            trade["stop_price"]
        )

        # SELL strategy:
        # risk = stop above entry
        risk = stop_price - entry_price

        if risk <= 0:
            continue

        target_price = (
            entry_price - risk * rr
        )

        candles = df[
            df[timestamp_column] >= entry_time
        ]

        # Do not allow this trade to consume
        # candles after the next audited signal.
        if trade_index + 1 < len(audit):

            next_entry = audit.iloc[
                trade_index + 1
            ]["entry_timestamp"]

            candles = candles[
                candles[timestamp_column]
                < next_entry
            ]

        outcome = None
        exit_time = None
        exit_price = None

        for _, candle in candles.iterrows():

            candle_high = float(
                candle[HIGH_COL]
            )

            candle_low = float(
                candle[LOW_COL]
            )

            candle_time = candle[
                timestamp_column
            ]

            hit_stop = (
                candle_high >= stop_price
            )

            hit_target = (
                candle_low <= target_price
            )

            # Conservative assumption:
            # if both levels occur within
            # the same candle, count STOP first.
            if hit_stop and hit_target:

                outcome = "STOP"
                exit_time = candle_time
                exit_price = stop_price

                break

            if hit_stop:

                outcome = "STOP"
                exit_time = candle_time
                exit_price = stop_price

                break

            if hit_target:

                outcome = "TARGET"
                exit_time = candle_time
                exit_price = target_price

                break

        if outcome is None:
            continue

        if outcome == "TARGET":
            r_result = rr
        else:
            r_result = -1.0

        results.append(
            {
                "rr": rr,
                "trade_number": trade_index + 1,
                "entry_timestamp": entry_time,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "exit_timestamp": exit_time,
                "exit_price": exit_price,
                "exit_reason": outcome,
                "r": r_result,
            }
        )

    return pd.DataFrame(results)


# -------------------------------------------------------------------------
# STATISTICS
# -------------------------------------------------------------------------

def calculate_stats(results):

    if len(results) == 0:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "net_r": 0.0,
            "max_drawdown_r": 0.0,
        }

    wins = int(
        (results["r"] > 0).sum()
    )

    losses = int(
        (results["r"] < 0).sum()
    )

    trades = len(results)

    win_rate = (
        wins / trades * 100
    )

    gross_profit = results.loc[
        results["r"] > 0,
        "r",
    ].sum()

    gross_loss = abs(
        results.loc[
            results["r"] < 0,
            "r",
        ].sum()
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit /
            gross_loss
        )

    else:

        profit_factor = float("inf")

    net_r = results["r"].sum()

    expectancy = (
        net_r / trades
    )

    cumulative = results[
        "r"
    ].cumsum()

    running_max = cumulative.cummax()

    drawdown = (
        running_max - cumulative
    )

    max_drawdown = drawdown.max()

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy_r": expectancy,
        "net_r": net_r,
        "max_drawdown_r": max_drawdown,
    }


# -------------------------------------------------------------------------
# RUN ALL RR VALUES
# -------------------------------------------------------------------------

summary_rows = []

trade_result_frames = []

print()
print("=" * 80)
print("TESTING RR VALUES")
print("=" * 80)

for rr in RR_VALUES:

    print()
    print(
        f"Testing {rr:.1f}R ..."
    )

    results = test_rr(rr)

    stats = calculate_stats(
        results
    )

    if stats["max_drawdown_r"] > 0:

        score = (
            stats["expectancy_r"] /
            stats["max_drawdown_r"]
        )

    else:

        score = 0.0

    print(
        f"Trades: {stats['trades']:4d} | "
        f"Wins: {stats['wins']:4d} | "
        f"Losses: {stats['losses']:4d} | "
        f"WR: {stats['win_rate']:6.2f}% | "
        f"PF: {stats['profit_factor']:6.3f} | "
        f"Exp: {stats['expectancy_r']:7.4f}R | "
        f"Net R: {stats['net_r']:8.2f} | "
        f"DD: {stats['max_drawdown_r']:6.2f}R"
    )

    summary_rows.append(
        {
            "rr": rr,
            **stats,
            "score": score,
        }
    )

    if len(results) > 0:

        trade_result_frames.append(
            results
        )

summary = pd.DataFrame(
    summary_rows
)

if trade_result_frames:

    trade_results = pd.concat(
        trade_result_frames,
        ignore_index=True,
    )

else:

    trade_results = pd.DataFrame()

# -------------------------------------------------------------------------
# SAVE
# -------------------------------------------------------------------------

summary.to_csv(
    SUMMARY_FILE,
    index=False,
)

trade_results.to_csv(
    TRADE_RESULTS_FILE,
    index=False,
)

# -------------------------------------------------------------------------
# RESULTS TABLE
# -------------------------------------------------------------------------

print()
print("=" * 80)
print("RR COMPARISON")
print("=" * 80)

print()

print(
    summary[
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

# -------------------------------------------------------------------------
# BEST RR VALUES
# -------------------------------------------------------------------------

best_expectancy = summary.loc[
    summary["expectancy_r"].idxmax()
]

best_net_r = summary.loc[
    summary["net_r"].idxmax()
]

best_score = summary.loc[
    summary["score"].idxmax()
]

print()
print("=" * 80)
print("BEST RR RESULTS")
print("=" * 80)

print()
print(
    "Highest historical expectancy:"
)

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
    f"{best_expectancy['win_rate']:.2f}%"
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
print(
    "Highest historical net R:"
)

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
    f"{best_net_r['win_rate']:.2f}%"
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
print(
    "Best expectancy / drawdown score:"
)

print(
    f"RR:                 "
    f"{best_score['rr']:.1f}R"
)

print(
    f"Score:              "
    f"{best_score['score']:.4f}"
)

print(
    f"Expectancy:         "
    f"{best_score['expectancy_r']:.4f}R"
)

print(
    f"Max DD:             "
    f"{best_score['max_drawdown_r']:.2f}R"
)

print()
print("=" * 80)
print("FILES SAVED")
print("=" * 80)

print()
print(SUMMARY_FILE)
print(TRADE_RESULTS_FILE)

print()
print("=" * 80)
print("TRUE HISTORICAL RR TEST COMPLETE")
print("=" * 80)