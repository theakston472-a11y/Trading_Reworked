import pandas as pd


def bullish_rejection(candle, body_ratio=0.30):
    """
    Bullish rejection (hammer/pin bar)

    Returns:
        True / False
    """

    open_price = candle["open"]
    high = candle["high"]
    low = candle["low"]
    close = candle["close"]

    body = abs(close - open_price)

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    candle_range = high - low

    if candle_range == 0:
        return False

    small_body = body <= candle_range * body_ratio
    long_lower = lower_wick >= body * 2
    small_upper = upper_wick <= body

    return (
        close > open_price
        and small_body
        and long_lower
        and small_upper
    )


def bearish_rejection(candle, body_ratio=0.30):
    """
    Bearish rejection (shooting star)
    """

    open_price = candle["open"]
    high = candle["high"]
    low = candle["low"]
    close = candle["close"]

    body = abs(close - open_price)

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    candle_range = high - low

    if candle_range == 0:
        return False

    small_body = body <= candle_range * body_ratio
    long_upper = upper_wick >= body * 2
    small_lower = lower_wick <= body

    return (
        close < open_price
        and small_body
        and long_upper
        and small_lower
    )


def inside_zone(price, zone):
    return zone["low"] <= price <= zone["high"]


def touching_entry(price, entries, tolerance=0.00015):
    """
    Is current price close to an entry level?
    """

    for level in entries:

        if abs(price - level["price"]) <= tolerance:
            return level

    return None