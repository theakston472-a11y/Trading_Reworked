import pandas as pd
import numpy as np


def add_swing_points(df, lookback=3):

    df = df.copy()

    df["swing_high"] = False
    df["swing_low"] = False

    for i in range(
        lookback,
        len(df) - lookback
    ):

        current_high = df.loc[i, "high"]
        current_low = df.loc[i, "low"]

        previous_highs = df.loc[
            i - lookback:i - 1,
            "high"
        ]

        next_highs = df.loc[
            i + 1:i + lookback,
            "high"
        ]

        previous_lows = df.loc[
            i - lookback:i - 1,
            "low"
        ]

        next_lows = df.loc[
            i + 1:i + lookback,
            "low"
        ]

        if (
            current_high > previous_highs.max()
            and
            current_high > next_highs.max()
        ):
            df.loc[i, "swing_high"] = True

        if (
            current_low < previous_lows.min()
            and
            current_low < next_lows.min()
        ):
            df.loc[i, "swing_low"] = True

    return df


def add_market_structure(df):

    df = df.copy()

    df["higher_high"] = False
    df["lower_high"] = False
    df["higher_low"] = False
    df["lower_low"] = False

    last_swing_high = None
    last_swing_low = None

    for i in range(len(df)):

        if df.loc[i, "swing_high"]:

            current_high = df.loc[i, "high"]

            if last_swing_high is not None:

                if current_high > last_swing_high:

                    df.loc[
                        i,
                        "higher_high"
                    ] = True

                elif current_high < last_swing_high:

                    df.loc[
                        i,
                        "lower_high"
                    ] = True

            last_swing_high = current_high

        if df.loc[i, "swing_low"]:

            current_low = df.loc[i, "low"]

            if last_swing_low is not None:

                if current_low > last_swing_low:

                    df.loc[
                        i,
                        "higher_low"
                    ] = True

                elif current_low < last_swing_low:

                    df.loc[
                        i,
                        "lower_low"
                    ] = True

            last_swing_low = current_low

    return df


def add_bos_features(df):

    df = df.copy()

    df["bullish_bos"] = False
    df["bearish_bos"] = False

    last_swing_high = np.nan
    last_swing_low = np.nan

    previous_bullish_bos = False
    previous_bearish_bos = False

    for i in range(len(df)):

        close = df.loc[i, "close"]

        if df.loc[i, "swing_high"]:

            last_swing_high = df.loc[
                i,
                "high"
            ]

        if df.loc[i, "swing_low"]:

            last_swing_low = df.loc[
                i,
                "low"
            ]

        bullish_bos = (
            not pd.isna(last_swing_high)
            and
            close > last_swing_high
        )

        bearish_bos = (
            not pd.isna(last_swing_low)
            and
            close < last_swing_low
        )

        if bullish_bos and not previous_bullish_bos:

            df.loc[
                i,
                "bullish_bos"
            ] = True

        if bearish_bos and not previous_bearish_bos:

            df.loc[
                i,
                "bearish_bos"
            ] = True

        previous_bullish_bos = bullish_bos
        previous_bearish_bos = bearish_bos

    return df


def add_choch_features(df):

    df = df.copy()

    df["bullish_choch"] = False
    df["bearish_choch"] = False

    structure = "Neutral"

    for i in range(len(df)):

        if df.loc[i, "higher_high"]:

            if structure == "Bearish":

                df.loc[
                    i,
                    "bullish_choch"
                ] = True

            structure = "Bullish"

        elif df.loc[i, "lower_low"]:

            if structure == "Bullish":

                df.loc[
                    i,
                    "bearish_choch"
                ] = True

            structure = "Bearish"

    return df


def add_equal_high_low_features(
    df,
    tolerance=0.0002
):

    df = df.copy()

    df["equal_high"] = False
    df["equal_low"] = False

    recent_high = None
    recent_low = None

    for i in range(len(df)):

        current_high = df.loc[
            i,
            "high"
        ]

        current_low = df.loc[
            i,
            "low"
        ]

        if recent_high is not None:

            if abs(
                current_high - recent_high
            ) <= tolerance:

                df.loc[
                    i,
                    "equal_high"
                ] = True

        if recent_low is not None:

            if abs(
                current_low - recent_low
            ) <= tolerance:

                df.loc[
                    i,
                    "equal_low"
                ] = True

        if df.loc[i, "swing_high"]:

            recent_high = current_high

        if df.loc[i, "swing_low"]:

            recent_low = current_low

    return df


def add_liquidity_sweeps(df):

    df = df.copy()

    df["liquidity_sweep_high"] = False
    df["liquidity_sweep_low"] = False

    previous_swing_high = None
    previous_swing_low = None

    for i in range(len(df)):

        high = df.loc[i, "high"]
        low = df.loc[i, "low"]
        close = df.loc[i, "close"]

        if previous_swing_high is not None:

            if (
                high > previous_swing_high
                and
                close < previous_swing_high
            ):

                df.loc[
                    i,
                    "liquidity_sweep_high"
                ] = True

        if previous_swing_low is not None:

            if (
                low < previous_swing_low
                and
                close > previous_swing_low
            ):

                df.loc[
                    i,
                    "liquidity_sweep_low"
                ] = True

        if df.loc[i, "swing_high"]:

            previous_swing_high = high

        if df.loc[i, "swing_low"]:

            previous_swing_low = low

    return df


def add_market_structure_features(df):

    print(
        "Adding swing points..."
    )

    df = add_swing_points(df)

    print(
        "Adding market structure..."
    )

    df = add_market_structure(df)

    print(
        "Adding BOS..."
    )

    df = add_bos_features(df)

    print(
        "Adding CHOCH..."
    )

    df = add_choch_features(df)

    print(
        "Adding equal highs/lows..."
    )

    df = add_equal_high_low_features(df)

    print(
        "Adding liquidity sweeps..."
    )

    df = add_liquidity_sweeps(df)

    return df