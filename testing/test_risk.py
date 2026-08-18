from core.loader import load_data

from analysis.atr import (
    add_atr,
    get_atr,
)

from core.risk import (
    calculate_trade_levels,
    calculate_position_size,
)



print("=" * 50)
print("RISK ENGINE TEST")
print("=" * 50)


df = load_data()

df.columns = [
    c.lower()
    for c in df.columns
]


df = add_atr(df)


current = df.iloc[-1]


price = current["close"]

atr = get_atr(df)



print()

print("CURRENT MARKET")
print("----------------")

print(
    f"Price : {price:.5f}"
)

print(
    f"ATR   : {atr:.5f}"
)



trade = calculate_trade_levels(
    direction="SELL",
    entry=price,
    atr=atr
)



print()

print("TRADE LEVELS")
print("----------------")

print(
    f"Entry  : {trade['entry']}"
)

print(
    f"Stop   : {trade['stop']}"
)

print(
    f"Target : {trade['target']}"
)



lots = calculate_position_size(
    balance=10000,
    risk_percent=1,
    stop_distance=abs(
        trade["stop"] -
        trade["entry"]
    )
)



print()

print("POSITION SIZE")
print("----------------")

print(
    f"Lots : {lots}"
)



print()
print("TEST COMPLETE")