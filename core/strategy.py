import pandas as pd



def find_key_area(
    df,
    lookback=100,
    tolerance=0.0005,
    minimum_rejections=5
):
    """
    Finds stronger support/resistance areas.
    Requires more touches.
    """


    df = df.tail(lookback)


    prices = []


    for _, row in df.iterrows():

        prices.append(row["high"])
        prices.append(row["low"])



    zones = []

    checked = set()



    for price in prices:


        rounded = round(price, 4)


        if rounded in checked:

            continue


        checked.add(rounded)



        touches = sum(
            abs(price - p) <= tolerance
            for p in prices
        )



        if touches >= minimum_rejections:


            zones.append(
                {
                    "price": round(price,5),
                    "touches": touches
                }
            )


    return zones





def strong_rejection(
    candle,
    direction
):
    """
    Checks candle quality.
    """

    body = abs(
        candle["close"]
        -
        candle["open"]
    )


    total_range = (
        candle["high"]
        -
        candle["low"]
    )


    if total_range == 0:

        return False



    strength = body / total_range



    # Require a meaningful candle body

    if strength < 0.55:

        return False



    if direction == "BUY":


        if candle["close"] > candle["open"]:

            return True



    if direction == "SELL":


        if candle["close"] < candle["open"]:

            return True



    return False





def check_rejection(
    candle,
    key_area,
    direction
):

    area = key_area["price"]



    # BUY rejection

    if direction == "BUY":


        if candle["low"] <= area:


            if strong_rejection(
                candle,
                "BUY"
            ):

                return True




    # SELL rejection

    if direction == "SELL":


        if candle["high"] >= area:


            if strong_rejection(
                candle,
                "SELL"
            ):

                return True



    return False