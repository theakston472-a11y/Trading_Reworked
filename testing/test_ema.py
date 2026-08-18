from core.loader import load_data

from analysis.ema import (
    add_emas,
    ema_direction,
    price_position,
)


print("=" * 50)
print("EMA ENGINE TEST")
print("=" * 50)


# Load data
df = load_data()


# Clean columns
df.columns = [c.lower() for c in df.columns]


print()
print("✓ Data loaded")


# Add EMA calculations
df = add_emas(df)


current = df.iloc[-1]


price = current["close"]

ema20 = current["ema_20"]
ema50 = current["ema_50"]


print()
print("=" * 50)
print("EMA VALUES")
print("=" * 50)

print(f"Current Price : {price:.5f}")
print()
print(f"EMA 20        : {ema20:.5f}")
print(f"EMA 50        : {ema50:.5f}")


direction = ema_direction(df)
position = price_position(df)


print()
print("=" * 50)
print("EMA SIGNAL")
print("=" * 50)

print(f"EMA Direction : {direction}")
print(f"Price Position: {position}")


print()
print("=" * 50)
print("EMA DISTANCE")
print("=" * 50)


print(
    f"Price vs EMA20 : {price - ema20:.5f}"
)

print(
    f"Price vs EMA50 : {price - ema50:.5f}"
)


print()
print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)