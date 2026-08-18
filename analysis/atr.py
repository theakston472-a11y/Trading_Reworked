import pandas as pd


def add_atr(df, period=14):
    """
    Adds ATR to dataframe.
    """

    df = df.copy()

    high_low = df["high"] - df["low"]

    high_close = (
        abs(df["high"] - df["close"].shift())
    )

    low_close = (
        abs(df["low"] - df["close"].shift())
    )


    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(axis=1)


    df["atr"] = (
        true_range
        .rolling(period)
        .mean()
    )


    return df



def get_atr(df):

    return df.iloc[-1]["atr"]