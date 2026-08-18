def calculate_trade_levels(
    direction,
    entry,
    atr,
    risk_reward=2
):
    """
    Creates stop and target levels.
    """


    stop_distance = atr * 2


    if direction == "BUY":

        stop = entry - stop_distance

        target = (
            entry +
            (stop_distance * risk_reward)
        )


    elif direction == "SELL":

        stop = entry + stop_distance

        target = (
            entry -
            (stop_distance * risk_reward)
        )


    else:

        return None



    return {

        "direction": direction,

        "entry": round(entry,5),

        "stop": round(stop,5),

        "target": round(target,5),

        "risk_reward": risk_reward

    }



def calculate_position_size(
    balance,
    risk_percent,
    stop_distance,
    pip_value=10
):
    """
    Calculates lot size.
    """


    risk_amount = (
        balance *
        (risk_percent / 100)
    )


    pips = stop_distance * 10000


    lot_size = (
        risk_amount /
        (pips * pip_value)
    )


    return round(lot_size,2)