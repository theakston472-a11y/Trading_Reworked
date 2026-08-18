import numpy as np


def find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3,
    max_zones=20
):
    """
    Finds support/resistance zones
    with internal entry levels.
    """


    # -----------------------------------
    # Normalise columns
    # -----------------------------------

    df = df.copy()

    df.columns = [
        str(col).lower()
        for col in df.columns
    ]


    required = [
        "high",
        "low",
        "close"
    ]


    for col in required:

        if col not in df.columns:

            raise Exception(
                f"Missing column {col}. Found: {df.columns.tolist()}"
            )


    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values



    # -----------------------------------
    # Collect rejection points
    # -----------------------------------

    levels = []


    for i in range(len(df)):

        high = highs[i]
        low = lows[i]
        close = closes[i]


        # Resistance rejection

        if high > close:

            levels.append({

                "price": high,

                "type": "resistance"

            })


        # Support rejection

        if low < close:

            levels.append({

                "price": low,

                "type": "support"

            })



    # -----------------------------------
    # Cluster similar prices
    # -----------------------------------

    clusters = []


    for item in levels:


        found = False


        for cluster in clusters:


            if abs(
                item["price"]
                -
                cluster["price"]
            ) <= tolerance:


                cluster["prices"].append(
                    item["price"]
                )


                cluster["touches"] += 1


                if item["type"] == "support":

                    cluster["support"] += 1

                else:

                    cluster["resistance"] += 1


                found = True

                break



        if not found:


            clusters.append({

                "price":
                    item["price"],

                "prices":
                    [
                        item["price"]
                    ],

                "touches":
                    1,

                "support":
                    1
                    if item["type"] == "support"
                    else 0,

                "resistance":
                    1
                    if item["type"] == "resistance"
                    else 0

            })



    # -----------------------------------
    # Build zones
    # -----------------------------------

    zones = []


    for cluster in clusters:


        if cluster["touches"] < minimum_rejections:

            continue



        mid = np.mean(
            cluster["prices"]
        )


        zone_type = (

            "support"

            if cluster["support"]
            >
            cluster["resistance"]

            else

            "resistance"

        )


        zones.append({

            "low":
                min(cluster["prices"]),

            "high":
                max(cluster["prices"]),

            "mid":
                mid,

            "touches":
                cluster["touches"],

            "strength":
                float(cluster["touches"]),

            "type":
                zone_type,

            "levels":
                []

        })



    # -----------------------------------
    # Rank zones
    # -----------------------------------

    zones = sorted(

        zones,

        key=lambda x:
        x["strength"],

        reverse=True

    )


    zones = zones[:max_zones]



    # -----------------------------------
    # Find internal entry levels
    # -----------------------------------

    for zone in zones:


        entries = {}



        for i in range(len(df)):


            for price in [
                highs[i],
                lows[i]
            ]:


                if (

                    zone["low"]

                    <=

                    price

                    <=

                    zone["high"]

                ):


                    price = round(
                        float(price),
                        5
                    )


                    if price not in entries:

                        entries[price] = 1

                    else:

                        entries[price] += 1



        zone["levels"] = []


        for price, touches in entries.items():


            zone["levels"].append({

                "price":
                    price,

                "touches":
                    touches

            })



        zone["levels"] = sorted(

            zone["levels"],

            key=lambda x:
            x["touches"],

            reverse=True

        )



    return zones





def find_entry_levels(
    zone,
    max_entries=3,
    min_distance=0.0005
):
    """
    Returns the strongest entry
    levels inside a zone.
    """


    selected = []


    for level in zone.get(
        "levels",
        []
    ):


        too_close = False


        for chosen in selected:


            if abs(

                level["price"]

                -

                chosen["price"]

            ) < min_distance:


                too_close = True

                break



        if too_close:

            continue



        selected.append(level)



        if len(selected) >= max_entries:

            break



    return selected





def print_key_areas(zones):


    print()

    print("=" * 50)

    print(
        "KEY AREAS FOUND"
    )

    print("=" * 50)



    for number, zone in enumerate(
        zones,
        1
    ):


        print()

        print(
            f"ZONE {number}"
        )

        print("-" * 30)


        print(
            f"Type: {zone['type']}"
        )


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
            f"Touches: "
            f"{zone['touches']}"
        )


        print(
            f"Strength: "
            f"{zone['strength']:.1f}"
        )