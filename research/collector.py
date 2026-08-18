import pandas as pd

from research.features import build_features

from analysis.ema import add_emas



def attach_features(
    df,
    trades
):
    """
    Adds market features to trades.
    """



    df = build_features(df)



    # add EMA features

    df = add_emas(
        df
    )



    results = []



    for trade in trades:



        entry = trade["Entry"]



        matches = df[
            df["close"]
            .sub(entry)
            .abs()
            <
            0.00005
        ]



        if len(matches):

            candle = matches.iloc[0]



            trade["Day"] = (
                candle["day"]
            )



            trade["Session"] = (
                candle["session"]
            )



            trade["Hour"] = (
                candle["hour"]
            )



            trade["Body Strength"] = round(
                candle["body_strength"],
                2
            )



            # EMA position

            if candle["close"] > candle["ema_20"]:

                trade["EMA"] = "Above"

            else:

                trade["EMA"] = "Below"



            # trend

            if candle["ema_20"] > candle["ema_50"]:

                trade["Trend"] = "Bullish"

            else:

                trade["Trend"] = "Bearish"



            # ATR

            if "ATR" in candle:

                trade["ATR"] = round(
                    candle["ATR"],
                    5
                )



            # candle range

            trade["Range"] = round(
                candle["range"],
                5
            )



        results.append(
            trade
        )



    return results





def save_research(
    trades,
    filename="research/results.csv"
):


    df = pd.DataFrame(
        trades
    )


    df.to_csv(
        filename,
        index=False
    )


    print()

    print(
        "Research data saved:"
    )

    print(
        filename
    )