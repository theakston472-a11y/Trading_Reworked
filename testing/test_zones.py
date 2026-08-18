from loader import load_data
from key_areas import find_key_areas


print("=" * 50)
print("ZONE MERGING TEST")
print("=" * 50)


df = load_data()

df.columns = [c.lower() for c in df.columns]


areas = find_key_areas(
    df,
    tolerance=0.0010,
    minimum_rejections=50,
    max_results=50
)


print()
print("=" * 50)
print("RAW AREAS")
print("=" * 50)


for area in areas:
    print(
        f"{area['price']:.5f} | "
        f"Strength: {area['count']}"
    )


print()
print("=" * 50)
print("MERGED ZONES")
print("=" * 50)


zones = []


for area in areas:

    added = False

    for zone in zones:

        if abs(area["price"] - zone["mid"]) <= 0.0030:

            zone["prices"].append(area["price"])
            zone["strength"] += area["count"]

            zone["mid"] = sum(zone["prices"]) / len(zone["prices"])

            added = True
            break


    if not added:

        zones.append(
            {
                "prices":[area["price"]],
                "strength":area["count"],
                "mid":area["price"]
            }
        )


zones.sort(
    key=lambda x:x["strength"],
    reverse=True
)


for i, zone in enumerate(zones[:10],1):

    print()
    print(
        f"Zone {i}"
    )

    print(
        f"Range: "
        f"{min(zone['prices']):.5f} - "
        f"{max(zone['prices']):.5f}"
    )

    print(
        f"Strength: {zone['strength']}"
    )