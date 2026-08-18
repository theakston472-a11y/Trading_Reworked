import pandas as pd


# ==========================================
# EMA CALCULATIONS
# ==========================================

def add_ema(df, period):
    """
    Add EMA to dataframe
    """

    df = df.copy()

    df[f"ema_{period}"] = (
        df["close"]
        .ewm(
            span=period,
            adjust=False
        )
        .mean()
    )

    return df



def add_emas(df):
    """
    Add strategy EMAs
    """

    df = add_ema(df, 20)
    df = add_ema(df, 50)

    return df



# ==========================================
# EMA DIRECTION
# ==========================================

def ema_direction(df):
    """
    EMA trend direction
    """

    last = df.iloc[-1]

    ema20 = last["ema_20"]
    ema50 = last["ema_50"]


    if ema20 > ema50:
        return "bullish"


    elif ema20 < ema50:
        return "bearish"


    else:
        return "neutral"



# ==========================================
# PRICE POSITION
# ==========================================

def price_position(df):
    """
    Price relative to EMA20
    """

    last = df.iloc[-1]

    price = last["close"]
    ema20 = last["ema_20"]


    if price > ema20:
        return "above"


    elif price < ema20:
        return "below"


    else:
        return "on"



# ==========================================
# EMA DISTANCE
# ==========================================

def ema_distance(df):

    last = df.iloc[-1]

    price = last["close"]

    ema20 = last["ema_20"]
    ema50 = last["ema_50"]


    return {

        "price_vs_ema20":
            price - ema20,


        "price_vs_ema50":
            price - ema50

    }



# ==========================================
# EMA STRENGTH
# ==========================================

def ema_strength(df):

    """
    Measures separation between EMA20 and EMA50
    """

    last = df.iloc[-1]

    ema20 = last["ema_20"]
    ema50 = last["ema_50"]


    distance = abs(
        ema20 - ema50
    )


    # convert to percentage style

    strength = (
        distance /
        last["close"]
    ) * 10000


    return round(
        strength,
        2
    )



# ==========================================
# EMA AGREEMENT
# ==========================================

def ema_agrees(
        trend_direction,
        ema_direction_value
):

    return (
        trend_direction
        ==
        ema_direction_value
    )



# ==========================================
# EMA SIGNAL
# ==========================================

def ema_signal(df):

    direction = ema_direction(df)

    position = price_position(df)


    if (
        direction == "bullish"
        and position == "above"
    ):

        return "BUY"


    elif (
        direction == "bearish"
        and position == "below"
    ):

        return "SELL"


    else:

        return "WAIT"