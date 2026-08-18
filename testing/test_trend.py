from loader import load_data
from trend import get_trend

print("=" * 50)
print("TREND ENGINE TEST")
print("=" * 50)

df = load_data()

df.columns = [c.lower() for c in df.columns]

trend = get_trend(df)

print()

print("Direction :", trend["direction"])
print("Strength  :", trend["strength"], "%")

print()

print("Higher Highs :", trend["higher_highs"])
print("Higher Lows  :", trend["higher_lows"])

print()

print("Lower Highs :", trend["lower_highs"])
print("Lower Lows  :", trend["lower_lows"])