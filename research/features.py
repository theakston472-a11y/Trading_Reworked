import pandas as pd


def add_time_features(df):
    """
    Adds date, day and forex session information.
    """

    df = df.copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    elif "time" in df.columns:
        df["date"] = pd.to_datetime(df["time"])

    else:
        df["date"] = pd.to_datetime(df.index)


    df["day"] = (
        df["date"]
        .dt.day_name()
    )


    df["hour"] = (
        df["date"]
        .dt.hour
    )


    df["session"] = (
        df["hour"]
        .apply(get_session)
    )


    return df



def get_session(hour):
    """
    Forex session classifier.
    """

    if 0 <= hour < 7:
        return "Asia"


    if 7 <= hour < 12:
        return "London"


    if 12 <= hour < 17:
        return "New York"


    return "Other"





def add_candle_features(df):
    """
    Adds candle behaviour measurements.
    """

    df = df.copy()


    df["body"] = (
        abs(
            df["close"]
            -
            df["open"]
        )
    )


    df["range"] = (
        df["high"]
        -
        df["low"]
    )


    df["body_strength"] = (
        df["body"]
        /
        df["range"]
        .replace(0, 0.00001)
    )


    df["bullish"] = (
        df["close"]
        >
        df["open"]
    )


    return df





def build_features(df):
    """
    Creates research-ready dataframe.
    """

    df = df.copy()


    # standardise columns

    df.columns = [
        c.lower()
        for c in df.columns
    ]


    df = add_time_features(df)


    df = add_candle_features(df)


    return df