from loader import load_data
from key_areas import find_key_areas, find_entry_levels


print("=" * 50)
print("LIVE ZONE PROXIMITY TEST")
print("=" * 50)


# Load data

df = load_data()


# Make sure columns are clean

df.columns = [
    str(col).lower()
    for col in df.columns
]


# Current market price

current_price = float(
    df["close"].iloc[-1]
)


print()
print(f"CURRENT PRICE: {current_price:.5f}")


# Find zones

zones = find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3,
    max_zones=50
)


# Store distances

zone_distance = []


for zone in zones:

    distance = abs(
        zone["mid"]
        -
        current_price
    )


    zone_distance.append({

        "zone": zone,

        "distance": distance

    })


# Sort nearest first

zone_distance.sort(
    key=lambda x:
    x["distance"]
)



print()
print("=" * 50)
print("NEAREST SUPPORT / RESISTANCE")
print("=" * 50)



support_count = 0
resistance_count = 0



for item in zone_distance:


    zone = item["zone"]


    if (
        zone["type"] == "support"
        and support_count < 3
    ):

        print()

        print("SUPPORT")

        print("-" * 30)

        print(
            f"Range: "
            f"{zone['low']:.5f}"
            f" - "
            f"{zone['high']:.5f}"
        )

        print(
            f"Mid: "
            f"{zone['mid']:.5f}"
        )

        print(
            f"Distance: "
            f"{item['distance']:.5f}"
        )

        print(
            f"Strength: "
            f"{zone['strength']:.0f}"
        )


        print()

        print("Entry levels:")


        entries = find_entry_levels(
            zone,
            max_entries=3
        )


        for entry in entries:

            print(
                f"  {entry['price']:.5f}"
                f" | Touches: "
                f"{entry['touches']}"
            )


        support_count += 1



    if (
        zone["type"] == "resistance"
        and resistance_count < 3
    ):

        print()

        print("RESISTANCE")

        print("-" * 30)

        print(
            f"Range: "
            f"{zone['low']:.5f}"
            f" - "
            f"{zone['high']:.5f}"
        )

        print(
            f"Mid: "
            f"{zone['mid']:.5f}"
        )

        print(
            f"Distance: "
            f"{item['distance']:.5f}"
        )

        print(
            f"Strength: "
            f"{zone['strength']:.0f}"
        )


        print()

        print("Entry levels:")


        entries = find_entry_levels(
            zone,
            max_entries=3
        )


        for entry in entries:

            print(
                f"  {entry['price']:.5f}"
                f" | Touches: "
                f"{entry['touches']}"
            )


        resistance_count += 1



    if (
        support_count >= 3
        and resistance_count >= 3
    ):

        break



print()
print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)