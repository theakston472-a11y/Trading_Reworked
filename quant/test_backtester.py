import pandas as pd

from quant.backtester import (
    backtest_strategy,
    session_breakdown,
    direction_breakdown
)


# ============================================================
# LOAD FEATURES
# ============================================================

FILE = "quant/feature_database.csv"


print("=" * 60)
print("QUANT BACKTEST TEST")
print("=" * 60)

print()

print(
    "Loading feature database..."
)

df = pd.read_csv(
    FILE
)

df["timestamp"] = pd.to_datetime(
    df["timestamp"]
)


print(
    f"Candles: {len(df)}"
)

print(
    f"Features: {len(df.columns)}"
)

print()


# ============================================================
# TEST STRATEGY
# ============================================================
#
# This is NOT our final strategy.
#
# We are simply testing that the backtester works.
#
# Example:
#
# Bullish liquidity sweep
# +
# Bullish EMA alignment
# +
# London session
#
# ============================================================

conditions = {

    "liquidity_sweep_low": True,

    "ema_bullish_alignment": True

}


# ============================================================
# BUY TEST
# ============================================================

print("=" * 60)

print(
    "BUY TEST"
)

print("=" * 60)

print()


result = backtest_strategy(

    df=df,

    conditions=conditions,

    direction="BUY",

    risk_reward=2.0,

    stop_mode="atr",

    stop_multiplier=1.0,

    max_bars=48

)


stats = result["stats"]

trades = result["trades"]


print(
    "Trades:",
    stats["trades"]
)

print(
    "Wins:",
    stats["wins"]
)

print(
    "Losses:",
    stats["losses"]
)

print(
    "Win rate:",
    stats["win_rate"],
    "%"
)

print(
    "Profit factor:",
    stats["profit_factor"]
)

print(
    "Net R:",
    stats["net_r"]
)

print(
    "Average R:",
    stats["average_r"]
)

print(
    "Expectancy:",
    stats["expectancy_r"]
)

print(
    "Max drawdown:",
    stats["max_drawdown_r"],
    "R"
)


# ============================================================
# SESSION BREAKDOWN
# ============================================================

print()

print("=" * 60)

print(
    "SESSION BREAKDOWN"
)

print("=" * 60)

print()


session_results = session_breakdown(
    trades
)


if not session_results.empty:

    print(
        session_results.to_string(
            index=False
        )
    )

else:

    print(
        "No trades to analyse."
    )


# ============================================================
# DIRECTION BREAKDOWN
# ============================================================

print()

print("=" * 60)

print(
    "DIRECTION BREAKDOWN"
)

print("=" * 60)

print()


direction_results = direction_breakdown(
    trades
)


if not direction_results.empty:

    print(
        direction_results.to_string(
            index=False
        )
    )

else:

    print(
        "No trades to analyse."
    )


# ============================================================
# SHOW TRADES
# ============================================================

print()

print("=" * 60)

print(
    "SAMPLE TRADES"
)

print("=" * 60)

print()


if not trades.empty:

    print(
        trades.head(20).to_string(
            index=False
        )
    )

else:

    print(
        "No trades generated."
    )


print()

print("=" * 60)

print(
    "BACKTEST TEST COMPLETE"
)

print("=" * 60)