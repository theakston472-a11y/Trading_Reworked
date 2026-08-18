from loader import load_data
from key_areas import find_key_areas, find_entry_levels


print("=" * 50)
print("FILTERED ENTRY ZONE TEST")
print("=" * 50)


df = load_data()


zones = find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3
)


print()
print("=" * 50)
print("TOP ENTRY LEVELS")
print("=" * 50)


for i, zone in enumerate(zones[:10], 1):

    print()
    print(f"ZONE {i}")
    print("-" * 30)

    print(f"Type: {zone['type']}")
    print(
        f"Range: {zone['low']:.5f} - {zone['high']:.5f}"
    )

    print(
        f"Strength: {zone['strength']:.1f}"
    )


    entries = find_entry_levels(
        zone,
        max_entries=3,
        min_distance=0.0005
    )


    print()
    print("ENTRY LEVELS:")


    for entry in entries:

        print(
            f"{entry['price']:.5f} | "
            f"Touches: {entry['touches']}"
        )


print()
print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)