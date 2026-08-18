from loader import load_data
from key_areas import find_key_areas, find_entry_levels
from rejection import (
    bullish_rejection,
    bearish_rejection,
    inside_zone,
    touching_entry,
)
from confidence import calculate_confidence

print("=" * 50)
print("LIVE REJECTION TEST")
print("=" * 50)

df = load_data()

df.columns = [c.lower() for c in df.columns]

zones = find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3,
    max_zones=50,
)

current = df.iloc[-1]
price = current["close"]

print()
print(f"Current Price: {price:.5f}")
print()

for zone in zones:

    if not inside_zone(price, zone):
        continue

    print("=" * 40)
    print("PRICE INSIDE KEY ZONE")
    print("=" * 40)

    print(f"Type      : {zone['type']}")
    print(f"Range     : {zone['low']:.5f} - {zone['high']:.5f}")
    print(f"Strength  : {zone['strength']:.0f}")

    entries = find_entry_levels(zone, max_entries=3)

    entry = touching_entry(price, entries)

    print()

    if entry:
        print(
            f"✓ Near entry level {entry['price']:.5f}"
            f" ({entry['touches']} touches)"
        )
    else:
        print("• Not near an entry level")

    print()

    near_entry = entry is not None

    bull = bullish_rejection(current)
    bear = bearish_rejection(current)

    rejection = bull or bear

    if bull:
        print("✓ Bullish rejection")

    elif bear:
        print("✓ Bearish rejection")

    else:
        print("• No rejection candle")

    confidence = calculate_confidence(
        in_zone=True,
        near_entry=near_entry,
        rejection=rejection,
        trend=False,
        impulse=False,
    )

    print()
    print("=" * 40)
    print("CONFIDENCE")
    print("=" * 40)

    print(f"Score    : {confidence['score']}/100")
    print(f"Decision : {confidence['decision']}")