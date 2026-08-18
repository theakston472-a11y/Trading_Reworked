from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent

FEATURE_FILE = BASE / "feature_database.csv"
OUTPUT_FILE = BASE / "trade_audit.csv"

TEST_START = pd.Timestamp("2026-07-01", tz="UTC")
TEST_END = pd.Timestamp("2026-08-08", tz="UTC")

DIRECTION = "SELL"
SESSION = "New York"

CONDITIONS = [
    "liquidity_sweep_high",
    "bearish_candle",
    "bearish_engulfing",
]

MIN_R = 1.0


def calculate_trade_result(df, signal_index, direction):
    """
    Reconstruct a simple 1R trade from the signal candle.

    Entry:
        close of signal candle

    Risk:
        signal candle range

    Target:
        1R

    Stop:
        1R

    The trade is evaluated candle-by-candle after the signal.
    """

    pos = signal_index

    if pos >= len(df) - 1:
        return None

    signal = df.iloc[pos]

    entry = float(signal["close"])

    candle_range = float(signal["high"]) - float(signal["low"])

    if not np.isfinite(candle_range) or candle_range <= 0:
        return None

    if direction == "SELL":
        stop = entry + candle_range
        target = entry - candle_range

    else:
        stop = entry - candle_range
        target = entry + candle_range

    for j in range(pos + 1, len(df)):
        candle = df.iloc[j]

        high = float(candle["high"])
        low = float(candle["low"])

        timestamp = candle["timestamp"]

        if direction == "SELL":

            stop_hit = high >= stop
            target_hit = low <= target

            if stop_hit and target_hit:
                # Conservative assumption when both occur
                # inside the same candle.
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": stop,
                    "r": -1.0,
                    "exit_reason": "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST",
                }

            if stop_hit:
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": stop,
                    "r": -1.0,
                    "exit_reason": "STOP",
                }

            if target_hit:
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": target,
                    "r": 1.0,
                    "exit_reason": "TARGET",
                }

        else:

            stop_hit = low <= stop
            target_hit = high >= target

            if stop_hit and target_hit:
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": stop,
                    "r": -1.0,
                    "exit_reason": "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST",
                }

            if stop_hit:
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": stop,
                    "r": -1.0,
                    "exit_reason": "STOP",
                }

            if target_hit:
                return {
                    "exit_timestamp": timestamp,
                    "exit_price": target,
                    "r": 1.0,
                    "exit_reason": "TARGET",
                }

    return {
        "exit_timestamp": df.iloc[-1]["timestamp"],
        "exit_price": float(df.iloc[-1]["close"]),
        "r": (
            (entry - float(df.iloc[-1]["close"])) / candle_range
            if direction == "SELL"
            else (float(df.iloc[-1]["close"]) - entry) / candle_range
        ),
        "exit_reason": "END_OF_TEST",
    }


def main():

    print()
    print("=" * 80)
    print("TRADE-LEVEL AUDIT")
    print("=" * 80)
    print()

    print("Strategy:")
    print(f"{DIRECTION} | {SESSION}")
    print(" + ".join(CONDITIONS))
    print()

    print("Loading feature database...")

    df = pd.read_csv(FEATURE_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    df = df.dropna(subset=["timestamp"]).copy()

    df = df.sort_values("timestamp").reset_index(drop=True)

    print(f"Candles loaded: {len(df)}")

    print()
    print(
        f"Audit period: "
        f"{TEST_START} -> {TEST_END}"
    )

    df = df[
        (df["timestamp"] >= TEST_START)
        & (df["timestamp"] < TEST_END)
    ].copy()

    df = df.reset_index(drop=True)

    print(f"Audit candles: {len(df)}")
    print()

    if df.empty:
        raise RuntimeError("No candles found.")

    required = [
        "session",
        "close",
        "high",
        "low",
    ] + CONDITIONS

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing columns: {missing}"
        )

    print("Finding signals...")

    session_mask = (
        df["session"].astype(str) == SESSION
    )

    condition_mask = pd.Series(
        True,
        index=df.index,
    )

    for condition in CONDITIONS:

        values = df[condition]

        if values.dtype == bool:
            condition_mask &= values.fillna(False)

        else:
            condition_mask &= (
                values
                .fillna(0)
                .astype(float)
                .ne(0)
            )

    signals = df[
        session_mask & condition_mask
    ].copy()

    print(f"Signals found: {len(signals)}")
    print()

    trades = []

    for signal_index in signals.index:

        signal = df.loc[signal_index]

        result = calculate_trade_result(
            df,
            signal_index,
            DIRECTION,
        )

        if result is None:
            continue

        entry = float(signal["close"])

        candle_range = (
            float(signal["high"])
            - float(signal["low"])
        )

        if DIRECTION == "SELL":
            stop = entry + candle_range
            target = entry - candle_range
        else:
            stop = entry - candle_range
            target = entry + candle_range

        trades.append(
            {
                "trade_number": len(trades) + 1,
                "entry_timestamp": signal["timestamp"],
                "direction": DIRECTION,
                "session": SESSION,
                "entry_price": entry,
                "stop_price": stop,
                "target_price": target,
                "risk_distance": candle_range,
                "exit_timestamp": result["exit_timestamp"],
                "exit_price": result["exit_price"],
                "r": result["r"],
                "exit_reason": result["exit_reason"],
            }
        )

    if not trades:
        print("No trades generated.")
        return

    out = pd.DataFrame(trades)

    out["cumulative_r"] = out["r"].cumsum()

    equity = out["cumulative_r"]

    running_peak = equity.cummax()

    out["drawdown_r"] = (
        running_peak - equity
    )

    out.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    wins = out[out["r"] > 0]
    losses = out[out["r"] < 0]

    total_trades = len(out)

    win_rate = (
        len(wins)
        / total_trades
        * 100
    )

    gross_profit = (
        wins["r"].sum()
        if len(wins)
        else 0
    )

    gross_loss = abs(
        losses["r"].sum()
    ) if len(losses) else 0

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.inf
    )

    net_r = out["r"].sum()

    expectancy = out["r"].mean()

    max_dd = out["drawdown_r"].max()

    print("=" * 80)
    print("AUDIT RESULTS")
    print("=" * 80)
    print()

    print(f"Trades:          {total_trades}")
    print(f"Win rate:        {win_rate:.2f}%")
    print(f"Profit factor:   {profit_factor:.3f}")
    print(f"Net R:           {net_r:.2f}")
    print(f"Expectancy:      {expectancy:.4f} R")
    print(f"Max drawdown:    {max_dd:.2f} R")
    print()

    print("=" * 80)
    print("TRADE-BY-TRADE RESULTS")
    print("=" * 80)
    print()

    display_columns = [
        "trade_number",
        "entry_timestamp",
        "entry_price",
        "stop_price",
        "target_price",
        "exit_timestamp",
        "exit_price",
        "r",
        "exit_reason",
        "cumulative_r",
        "drawdown_r",
    ]

    print(
        out[display_columns]
        .to_string(index=False)
    )

    print()
    print("=" * 80)
    print("EXIT SUMMARY")
    print("=" * 80)
    print()

    print(
        out["exit_reason"]
        .value_counts()
        .to_string()
    )

    print()
    print(f"Saved audit to:")
    print(OUTPUT_FILE)
    print()

    print("=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()