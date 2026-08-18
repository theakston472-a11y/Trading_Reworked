def create_trade(
    direction,
    candle,
    risk_reward=2,
    stop_distance=0.00070
):
    """
    Creates a trade plan for backtesting.
    """


    entry = candle["close"]


    if direction == "BUY":

        stop = entry - stop_distance

        target = (
            entry +
            (stop_distance * risk_reward)
        )


    else:

        stop = entry + stop_distance

        target = (
            entry -
            (stop_distance * risk_reward)
        )


    return {

        "Direction": direction,

        "Entry": round(entry, 5),

        "Stop": round(stop, 5),

        "Target": round(target, 5),

    }





def check_trade_result(
    df,
    start_index,
    trade,
    max_candles=50
):
    """
    Checks whether stop or target was hit.
    """


    direction = trade["Direction"]


    entry = trade["Entry"]
    stop = trade["Stop"]
    target = trade["Target"]



    future = df.iloc[
        start_index + 1 :
        start_index + max_candles
    ]



    for _, candle in future.iterrows():


        high = candle["high"]
        low = candle["low"]



        if direction == "BUY":


            if low <= stop:

                return {
                    "Result": "LOSS",
                    "R": -1
                }


            if high >= target:

                return {
                    "Result": "WIN",
                    "R": 2
                }




        if direction == "SELL":


            if high >= stop:

                return {
                    "Result": "LOSS",
                    "R": -1
                }


            if low <= target:

                return {
                    "Result": "WIN",
                    "R": 2
                }




    return {

        "Result": "OPEN",

        "R": 0

    }