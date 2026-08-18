import numpy as np


def get_trend(df, lookback=80):
    """
    Determine market trend using swing structure.

    Returns:
        {
            "direction": "bullish" / "bearish" / "sideways",
            "strength": float,
            "higher_highs": int,
            "higher_lows": int,
            "lower_highs": int,
            "lower_lows": int
        }
    """

    highs = df["high"].tail(lookback).values
    lows = df["low"].tail(lookback).values

    swing_highs = []
    swing_lows = []

    for i in range(2, len(highs) - 2):

        if (
            highs[i] > highs[i-1]
            and highs[i] > highs[i-2]
            and highs[i] > highs[i+1]
            and highs[i] > highs[i+2]
        ):
            swing_highs.append(highs[i])

        if (
            lows[i] < lows[i-1]
            and lows[i] < lows[i-2]
            and lows[i] < lows[i+1]
            and lows[i] < lows[i+2]
        ):
            swing_lows.append(lows[i])

    higher_highs = 0
    lower_highs = 0

    for i in range(1, len(swing_highs)):
        if swing_highs[i] > swing_highs[i-1]:
            higher_highs += 1
        else:
            lower_highs += 1

    higher_lows = 0
    lower_lows = 0

    for i in range(1, len(swing_lows)):
        if swing_lows[i] > swing_lows[i-1]:
            higher_lows += 1
        else:
            lower_lows += 1

    bullish = higher_highs + higher_lows
    bearish = lower_highs + lower_lows

    total = bullish + bearish

    if total == 0:
        strength = 0

    else:
        strength = round(max(bullish, bearish) / total * 100, 1)

    if bullish > bearish:
        direction = "bullish"

    elif bearish > bullish:
        direction = "bearish"

    else:
        direction = "sideways"

    return {

        "direction": direction,
        "strength": strength,

        "higher_highs": higher_highs,
        "higher_lows": higher_lows,

        "lower_highs": lower_highs,
        "lower_lows": lower_lows,
    }