from loader import load_data
from key_areas import find_key_areas


print("=" * 50)
print("ZONE HIERARCHY TEST")
print("=" * 50)


# Load data
df = load_data()

print()
print("✓ Data loaded")


# Ensure lowercase columns
df.columns = [c.lower() for c in df.columns]


# Find zones
zones = find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3
)


print()
print("=" * 50)
print("MAJOR ZONES + ENTRY LEVELS")
print("=" * 50)


for i, zone in enumerate(zones[:10], start=1):

    print()
    print(f"ZONE {i}")
    print("-" * 30)

    print(f"Type: {zone['type']}")
    print(
        f"Range: "
        f"{zone['low']:.5f} - "
        f"{zone['high']:.5f}"
    )

    # Calculate midpoint
    mid = (zone['low'] + zone['high']) / 2

    print(f"Mid: {mid:.5f}")

    print(f"Touches: {zone['touches']}")
    print(f"Strength: {zone['strength']:.1f}")


    print()
    print("ENTRY LEVEL")
    print("-" * 20)

    print(
        f"{mid:.5f} | "
        f"Touches: {zone['touches']}"
    )


print()
print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)