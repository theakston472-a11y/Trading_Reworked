from analysis.key_areas import (
    find_key_areas,
    find_entry_levels,
)

from analysis.rejection import (
    bullish_rejection,
    bearish_rejection,
    inside_zone,
    touching_entry,
)

from analysis.trend import get_trend

from analysis.ema import (
    add_emas,
    ema_direction,
    price_position,
)

from analysis.atr import (
    add_atr,
    get_atr,
)

from core.decision import evaluate_trade

from core.risk import (
    calculate_trade_levels,
    calculate_position_size,
)



def run_strategy(df):
    """
    Main strategy engine.
    Combines all analysis modules.
    """


    # -----------------------
    # PREPARE DATA
    # -----------------------

    df.columns = [
        c.lower()
        for c in df.columns
    ]


    df = add_emas(df)

    df = add_atr(df)



    current = df.iloc[-1]

    price = current["close"]



    # -----------------------
    # TREND
    # -----------------------

    trend_data = get_trend(df)

    trend = trend_data["direction"]



    # -----------------------
    # EMA
    # -----------------------

    ema = ema_direction(df)

    ema_position = price_position(df)



    # -----------------------
    # KEY ZONE
    # -----------------------

    zones = find_key_areas(
        df,
        tolerance=0.0005,
        minimum_rejections=3,
        max_zones=50,
    )


    active_zone = None
    entry_price = None



    for zone in zones:

        if inside_zone(price, zone):

            active_zone = zone


            entries = find_entry_levels(
                zone,
                max_entries=3
            )


            entry = touching_entry(
                price,
                entries
            )


            if entry:
                entry_price = entry["price"]


            break



    # -----------------------
    # REJECTION
    # -----------------------

    bullish = bullish_rejection(current)

    bearish = bearish_rejection(current)


    rejection = bullish or bearish



    # -----------------------
    # DECISION
    # -----------------------

    decision = evaluate_trade(

        zone=active_zone,

        entry=entry_price,

        rejection=rejection,

        trend=trend,

        ema=ema,

        price=price,

    )



    result = {

        "price": price,

        "trend": trend,

        "ema": ema,

        "ema_position": ema_position,

        "decision": decision,

        "trade": None,

    }



    # -----------------------
    # RISK ENGINE
    # -----------------------

    if decision["trade"]:

        atr = get_atr(df)


        trade = calculate_trade_levels(

            direction=decision["bias"],

            entry=entry_price,

            atr=atr

        )


        lots = calculate_position_size(

            balance=10000,

            risk_percent=1,

            stop_distance=abs(

                trade["stop"]
                -
                trade["entry"]

            )

        )


        trade["lots"] = lots


        result["trade"] = trade



    return result