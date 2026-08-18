import pandas as pd
import numpy as np


# ============================================================
# CANDLE PATTERNS
# ============================================================

def add_candle_pattern_features(df):

    df = df.copy()

    previous_open = df["open"].shift(1)
    previous_close = df["close"].shift(1)

    previous_high = df["high"].shift(1)
    previous_low = df["low"].shift(1)

    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]

    previous_bullish = (
        previous_close > previous_open
    )

    previous_bearish = (
        previous_close < previous_open
    )

    # --------------------------------------------------------
    # Engulfing
    # --------------------------------------------------------

    df["bullish_engulfing"] = (
        bullish
        &
        previous_bearish
        &
        (df["open"] <= previous_close)
        &
        (df["close"] >= previous_open)
    )

    df["bearish_engulfing"] = (
        bearish
        &
        previous_bullish
        &
        (df["open"] >= previous_close)
        &
        (df["close"] <= previous_open)
    )

    # --------------------------------------------------------
    # Candle measurements
    # --------------------------------------------------------

    candle_range = (
        df["high"] - df["low"]
    )

    body = (
        df["close"] - df["open"]
    ).abs()

    upper_wick = (
        df["high"]
        -
        df[["open", "close"]].max(axis=1)
    )

    lower_wick = (
        df[["open", "close"]].min(axis=1)
        -
        df["low"]
    )

    body_ratio = np.where(
        candle_range > 0,
        body / candle_range,
        0
    )

    # --------------------------------------------------------
    # Pin bars
    # --------------------------------------------------------

    df["bullish_pin_bar"] = (
        (lower_wick >= body * 2)
        &
        (lower_wick > upper_wick)
    )

    df["bearish_pin_bar"] = (
        (upper_wick >= body * 2)
        &
        (upper_wick > lower_wick)
    )

    # --------------------------------------------------------
    # Inside / outside bars
    # --------------------------------------------------------

    df["inside_bar"] = (
        (df["high"] < previous_high)
        &
        (df["low"] > previous_low)
    )

    df["outside_bar"] = (
        (df["high"] > previous_high)
        &
        (df["low"] < previous_low)
    )

    # --------------------------------------------------------
    # Strong candles
    # --------------------------------------------------------

    df["strong_bullish_candle"] = (
        bullish
        &
        (body_ratio >= 0.70)
    )

    df["strong_bearish_candle"] = (
        bearish
        &
        (body_ratio >= 0.70)
    )

    # --------------------------------------------------------
    # Doji
    # --------------------------------------------------------

    df["doji"] = (
        body_ratio <= 0.10
    )

    return df


# ============================================================
# FAIR VALUE GAP
# ============================================================

def add_fvg_features(df):

    df = df.copy()

    df["bullish_fvg"] = False
    df["bearish_fvg"] = False

    df["fvg_size"] = 0.0

    two_back_high = (
        df["high"].shift(2)
    )

    two_back_low = (
        df["low"].shift(2)
    )

    bullish_gap = (
        df["low"] > two_back_high
    )

    bearish_gap = (
        df["high"] < two_back_low
    )

    df.loc[
        bullish_gap,
        "bullish_fvg"
    ] = True

    df.loc[
        bearish_gap,
        "bearish_fvg"
    ] = True

    df.loc[
        bullish_gap,
        "fvg_size"
    ] = (
        df.loc[bullish_gap, "low"]
        -
        two_back_high[bullish_gap]
    )

    df.loc[
        bearish_gap,
        "fvg_size"
    ] = (
        two_back_low[bearish_gap]
        -
        df.loc[bearish_gap, "high"]
    )

    return df


# ============================================================
# SESSION LEVELS
# ============================================================

def add_session_features(df):

    df = df.copy()

    df["session_high"] = np.nan
    df["session_low"] = np.nan

    current_session = None

    session_high = None
    session_low = None

    for i in range(len(df)):

        session = df.loc[
            i,
            "session"
        ]

        high = df.loc[
            i,
            "high"
        ]

        low = df.loc[
            i,
            "low"
        ]

        if session != current_session:

            current_session = session

            session_high = high
            session_low = low

        else:

            session_high = max(
                session_high,
                high
            )

            session_low = min(
                session_low,
                low
            )

        df.loc[
            i,
            "session_high"
        ] = session_high

        df.loc[
            i,
            "session_low"
        ] = session_low

    df["previous_session_high"] = (
        df["session_high"].shift(1)
    )

    df["previous_session_low"] = (
        df["session_low"].shift(1)
    )

    return df


# ============================================================
# DAILY LEVELS
# ============================================================

def add_previous_day_features(df):

    df = df.copy()

    df["date"] = (
        df["timestamp"].dt.date
    )

    daily_high = (
        df.groupby("date")["high"]
        .transform("max")
    )

    daily_low = (
        df.groupby("date")["low"]
        .transform("min")
    )

    df["daily_high"] = daily_high
    df["daily_low"] = daily_low

    previous_high_by_day = (
        df.groupby("date")["high"]
        .max()
        .shift(1)
    )

    previous_low_by_day = (
        df.groupby("date")["low"]
        .min()
        .shift(1)
    )

    df["previous_day_high"] = (
        df["date"].map(
            previous_high_by_day
        )
    )

    df["previous_day_low"] = (
        df["date"].map(
            previous_low_by_day
        )
    )

    return df


# ============================================================
# PREVIOUS DAY SWEEPS
# ============================================================

def add_previous_day_sweep_features(df):

    df = df.copy()

    df["previous_day_high_sweep"] = False
    df["previous_day_low_sweep"] = False

    high_level = (
        df["previous_day_high"]
    )

    low_level = (
        df["previous_day_low"]
    )

    df["previous_day_high_sweep"] = (
        (df["high"] > high_level)
        &
        (df["close"] < high_level)
    )

    df["previous_day_low_sweep"] = (
        (df["low"] < low_level)
        &
        (df["close"] > low_level)
    )

    return df


# ============================================================
# FIBONACCI FEATURES
# ============================================================

def add_fibonacci_features(
    df,
    lookback=50
):

    df = df.copy()

    # --------------------------------------------------------
    # Create columns
    # --------------------------------------------------------

    df["fib_range"] = np.nan

    df["fib_236"] = np.nan
    df["fib_382"] = np.nan
    df["fib_500"] = np.nan
    df["fib_618"] = np.nan
    df["fib_786"] = np.nan

    df["fib_position"] = np.nan

    df["near_fib_236"] = False
    df["near_fib_382"] = False
    df["near_fib_500"] = False
    df["near_fib_618"] = False
    df["near_fib_786"] = False

    # --------------------------------------------------------
    # Rolling swing range
    # --------------------------------------------------------

    rolling_high = (
        df["high"]
        .rolling(lookback)
        .max()
    )

    rolling_low = (
        df["low"]
        .rolling(lookback)
        .min()
    )

    price_range = (
        rolling_high
        -
        rolling_low
    )

    df["fib_range"] = price_range

    # --------------------------------------------------------
    # Retracement levels
    # --------------------------------------------------------

    df["fib_236"] = (
        rolling_high
        -
        price_range * 0.236
    )

    df["fib_382"] = (
        rolling_high
        -
        price_range * 0.382
    )

    df["fib_500"] = (
        rolling_high
        -
        price_range * 0.500
    )

    df["fib_618"] = (
        rolling_high
        -
        price_range * 0.618
    )

    df["fib_786"] = (
        rolling_high
        -
        price_range * 0.786
    )

    # --------------------------------------------------------
    # Current price position inside the range
    #
    # 0.0 = range low
    # 1.0 = range high
    # --------------------------------------------------------

    df["fib_position"] = np.where(
        price_range > 0,
        (
            df["close"]
            -
            rolling_low
        )
        /
        price_range,
        np.nan
    )

    # --------------------------------------------------------
    # Dynamic tolerance
    #
    # Instead of requiring price to be almost exactly
    # on a Fibonacci level, we use a percentage of the
    # current swing range.
    # --------------------------------------------------------

    tolerance = (
        price_range * 0.02
    )

    # --------------------------------------------------------
    # Near Fibonacci levels
    # --------------------------------------------------------

    df["near_fib_236"] = (
        (
            df["close"]
            -
            df["fib_236"]
        ).abs()
        <= tolerance
    )

    df["near_fib_382"] = (
        (
            df["close"]
            -
            df["fib_382"]
        ).abs()
        <= tolerance
    )

    df["near_fib_500"] = (
        (
            df["close"]
            -
            df["fib_500"]
        ).abs()
        <= tolerance
    )

    df["near_fib_618"] = (
        (
            df["close"]
            -
            df["fib_618"]
        ).abs()
        <= tolerance
    )

    df["near_fib_786"] = (
        (
            df["close"]
            -
            df["fib_786"]
        ).abs()
        <= tolerance
    )

    return df


# ============================================================
# MASTER PRICE ACTION FUNCTION
# ============================================================

def add_price_action_features(df):

    print(
        "Adding candle patterns..."
    )

    df = add_candle_pattern_features(
        df
    )

    print(
        "Adding Fair Value Gaps..."
    )

    df = add_fvg_features(
        df
    )

    print(
        "Adding session levels..."
    )

    df = add_session_features(
        df
    )

    print(
        "Adding previous day levels..."
    )

    df = add_previous_day_features(
        df
    )

    print(
        "Adding previous day sweeps..."
    )

    df = add_previous_day_sweep_features(
        df
    )

    print(
        "Adding Fibonacci levels..."
    )

    df = add_fibonacci_features(
        df
    )

    # --------------------------------------------------------
    # Remove temporary date column
    # --------------------------------------------------------

    if "date" in df.columns:

        df.drop(
            columns=["date"],
            inplace=True
        )

    return df