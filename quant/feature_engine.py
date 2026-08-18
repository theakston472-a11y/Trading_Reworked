import pandas as pd
import numpy as np
from quant.institutional_features import add_institutional_features

FEATURE_ENGINE_VERSION = "2026-08-16-v8-bos-fib-sequence"


def build_features(input_file):

    print("Loading market data...")

    df = pd.read_csv(input_file)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    # =========================================================
    # TIME FEATURES
    # =========================================================

    print("Adding time features...")

    df["hour"] = df["timestamp"].dt.hour
    df["minute"] = df["timestamp"].dt.minute
    df["day_of_week"] = df["timestamp"].dt.dayofweek

    def get_session(hour):

        if 0 <= hour < 8:
            return "Asia"

        elif 8 <= hour < 13:
            return "London"

        elif 13 <= hour < 21:
            return "New York"

        else:
            return "other"

    df["session"] = df["hour"].apply(
        get_session
    )

    # =========================================================
    # PRICE FEATURES
    # =========================================================

    print("Adding price features...")

    df["range"] = (
        df["high"] - df["low"]
    )

    df["body"] = (
        df["close"] - df["open"]
    ).abs()

    df["body_strength"] = np.where(
        df["range"] > 0,
        df["body"] / df["range"],
        0
    )

    df["bullish_candle"] = (
        df["close"] > df["open"]
    )

    df["bearish_candle"] = (
        df["close"] < df["open"]
    )

    df["upper_wick"] = (
        df["high"]
        -
        df[["open", "close"]].max(axis=1)
    )

    df["lower_wick"] = (
        df[["open", "close"]].min(axis=1)
        -
        df["low"]
    )

    # =========================================================
    # EMA
    # =========================================================

    print("Adding EMA features...")

    for period in [20, 50, 100, 200]:

        df[f"ema{period}"] = (
            df["close"]
            .ewm(
                span=period,
                adjust=False
            )
            .mean()
        )

        df[f"above_ema{period}"] = (
            df["close"] > df[f"ema{period}"]
        )

    df["ema_bullish_alignment"] = (
        (df["ema20"] > df["ema50"])
        &
        (df["ema50"] > df["ema100"])
        &
        (df["ema100"] > df["ema200"])
    )

    df["ema_bearish_alignment"] = (
        (df["ema20"] < df["ema50"])
        &
        (df["ema50"] < df["ema100"])
        &
        (df["ema100"] < df["ema200"])
    )

    df["trend"] = np.where(
        df["ema_bullish_alignment"],
        "bullish",
        np.where(
            df["ema_bearish_alignment"],
            "bearish",
            "neutral"
        )
    )

    # =========================================================
    # ATR
    # =========================================================

    print("Adding ATR features...")

    previous_close = df["close"].shift(1)

    tr1 = (
        df["high"] - df["low"]
    )

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

    df["true_range"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr14"] = (
        df["true_range"]
        .rolling(14)
        .mean()
    )

    df["range_vs_atr"] = np.where(
        df["atr14"] > 0,
        df["range"] / df["atr14"],
        0
    )

    df["large_range"] = (
        df["range_vs_atr"] >= 1.5
    )

    df["small_range"] = (
        df["range_vs_atr"] <= 0.5
    )

    # =========================================================
    # SWING POINTS
    # =========================================================

    print("Adding swing points...")

    # IMPORTANT:
    #
    # A 5-candle pivot is only confirmed after two candles to
    # the right have closed.  The BOOLEAN marker therefore
    # belongs on the confirmation candle, but the PRICE and
    # SOURCE INDEX must still point back to the original pivot.
    #
    # The older engine shifted only the boolean and then read
    # high/low from the confirmation candle.  That made market
    # structure and Fibonacci anchors use the wrong prices.
    #
    # These columns keep both pieces of information:
    #   swing_high / swing_low          -> confirmation event
    #   swing_high_price / swing_low_price -> true pivot price
    #   swing_*_source_index            -> true pivot candle
    #
    # This remains look-ahead safe because none of these values
    # appears until two candles after the pivot occurred.

    raw_swing_high = (
        (df["high"] > df["high"].shift(1))
        &
        (df["high"] > df["high"].shift(2))
        &
        (df["high"] > df["high"].shift(-1))
        &
        (df["high"] > df["high"].shift(-2))
    )

    raw_swing_low = (
        (df["low"] < df["low"].shift(1))
        &
        (df["low"] < df["low"].shift(2))
        &
        (df["low"] < df["low"].shift(-1))
        &
        (df["low"] < df["low"].shift(-2))
    )

    raw_index = pd.Series(
        np.arange(len(df), dtype=float),
        index=df.index,
    )

    confirmed_high_price = (
        df["high"]
        .where(raw_swing_high)
        .shift(2)
    )

    confirmed_low_price = (
        df["low"]
        .where(raw_swing_low)
        .shift(2)
    )

    confirmed_high_source = (
        raw_index
        .where(raw_swing_high)
        .shift(2)
    )

    confirmed_low_source = (
        raw_index
        .where(raw_swing_low)
        .shift(2)
    )

    df["swing_high"] = (
        confirmed_high_price
        .notna()
        .astype(bool)
    )

    df["swing_low"] = (
        confirmed_low_price
        .notna()
        .astype(bool)
    )

    df["swing_high_price"] = confirmed_high_price
    df["swing_low_price"] = confirmed_low_price

    df["swing_high_source_index"] = confirmed_high_source
    df["swing_low_source_index"] = confirmed_low_source


    # =========================================================
    # MARKET STRUCTURE
    # =========================================================

    print("Adding market structure...")

    last_swing_high = np.nan
    previous_swing_high = np.nan

    last_swing_low = np.nan
    previous_swing_low = np.nan

    higher_high = []
    lower_high = []
    higher_low = []
    lower_low = []

    for i in range(len(df)):

        if df.loc[i, "swing_high"]:

            previous_swing_high = last_swing_high
            last_swing_high = df.loc[i, "swing_high_price"]

        if df.loc[i, "swing_low"]:

            previous_swing_low = last_swing_low
            last_swing_low = df.loc[i, "swing_low_price"]

        if (
            not np.isnan(previous_swing_high)
            and df.loc[i, "swing_high"]
        ):
            higher_high.append(last_swing_high > previous_swing_high)
            lower_high.append(last_swing_high < previous_swing_high)
        else:
            higher_high.append(False)
            lower_high.append(False)

        if (
            not np.isnan(previous_swing_low)
            and df.loc[i, "swing_low"]
        ):
            higher_low.append(last_swing_low > previous_swing_low)
            lower_low.append(last_swing_low < previous_swing_low)
        else:
            higher_low.append(False)
            lower_low.append(False)

    df["higher_high"] = higher_high
    df["lower_high"] = lower_high
    df["higher_low"] = higher_low
    df["lower_low"] = lower_low

    # =========================================================
    # BOS / CHOCH — STRUCTURE EVENTS, NOT PERSISTENT STATES
    # =========================================================
    #
    # A break is evaluated against the latest CONFIRMED swing.
    # Each swing level can only generate one break event.
    #
    # BOS:
    #   continuation / first directional structure break.
    #
    # CHOCH:
    #   first break in the opposite direction to the current
    #   structure state.
    #
    # This is deliberately independent of EMA trend so market
    # structure means market structure.
    # =========================================================

    print("Adding BOS...")
    print("Adding CHOCH...")

    bullish_bos = np.zeros(len(df), dtype=bool)
    bearish_bos = np.zeros(len(df), dtype=bool)
    bullish_choch = np.zeros(len(df), dtype=bool)
    bearish_choch = np.zeros(len(df), dtype=bool)

    bullish_break_level = np.full(len(df), np.nan)
    bearish_break_level = np.full(len(df), np.nan)

    structural_trend = np.empty(len(df), dtype=object)

    active_high = np.nan
    active_low = np.nan

    high_level_broken = True
    low_level_broken = True

    structure_state = "neutral"

    for i in range(len(df)):

        if bool(df.loc[i, "swing_high"]):
            value = df.loc[i, "swing_high_price"]

            if pd.notna(value):
                active_high = float(value)
                high_level_broken = False

        if bool(df.loc[i, "swing_low"]):
            value = df.loc[i, "swing_low_price"]

            if pd.notna(value):
                active_low = float(value)
                low_level_broken = False

        close_i = float(df.loc[i, "close"])

        broke_high = (
            pd.notna(active_high)
            and not high_level_broken
            and close_i > active_high
        )

        broke_low = (
            pd.notna(active_low)
            and not low_level_broken
            and close_i < active_low
        )

        # In the rare case one very large candle closes beyond
        # both tracked levels, use the larger normalized break.
        if broke_high and broke_low:
            atr_i = df.loc[i, "atr14"]

            if pd.isna(atr_i) or atr_i <= 0:
                atr_i = max(
                    abs(active_high - active_low),
                    1e-12,
                )

            high_extension = (close_i - active_high) / atr_i
            low_extension = (active_low - close_i) / atr_i

            if high_extension >= low_extension:
                broke_low = False
            else:
                broke_high = False

        if broke_high:
            bullish_break_level[i] = active_high
            high_level_broken = True

            if structure_state == "bearish":
                bullish_choch[i] = True
            else:
                bullish_bos[i] = True

            structure_state = "bullish"

        elif broke_low:
            bearish_break_level[i] = active_low
            low_level_broken = True

            if structure_state == "bullish":
                bearish_choch[i] = True
            else:
                bearish_bos[i] = True

            structure_state = "bearish"

        structural_trend[i] = structure_state

    df["bullish_bos"] = bullish_bos
    df["bearish_bos"] = bearish_bos
    df["bullish_choch"] = bullish_choch
    df["bearish_choch"] = bearish_choch

    df["bullish_structure_break_level"] = bullish_break_level
    df["bearish_structure_break_level"] = bearish_break_level
    df["structural_trend"] = structural_trend

    # =========================================================
    # EQUAL HIGHS / LOWS — SWING-TO-SWING LIQUIDITY POOLS
    # =========================================================

    print("Adding equal highs/lows...")

    tolerance = df["atr14"] * 0.10

    previous_confirmed_high = (
        df["swing_high_price"]
        .ffill()
        .shift(1)
    )

    previous_confirmed_low = (
        df["swing_low_price"]
        .ffill()
        .shift(1)
    )

    df["equal_high"] = (
        df["swing_high"]
        &
        previous_confirmed_high.notna()
        &
        (
            (
                df["swing_high_price"]
                -
                previous_confirmed_high
            ).abs()
            <= tolerance
        )
    )

    df["equal_low"] = (
        df["swing_low"]
        &
        previous_confirmed_low.notna()
        &
        (
            (
                df["swing_low_price"]
                -
                previous_confirmed_low
            ).abs()
            <= tolerance
        )
    )

    df["equal_high_level"] = np.where(
        df["equal_high"],
        (
            df["swing_high_price"]
            + previous_confirmed_high
        ) / 2.0,
        np.nan,
    )

    df["equal_low_level"] = np.where(
        df["equal_low"],
        (
            df["swing_low_price"]
            + previous_confirmed_low
        ) / 2.0,
        np.nan,
    )

    # =========================================================
    # LIQUIDITY SWEEPS
    # =========================================================
    #
    # High sweep:
    #   - takes a confirmed swing high
    #   - leaves a meaningful upper wick
    #   - closes back below the swept level
    #
    # Low sweep:
    #   - takes a confirmed swing low
    #   - leaves a meaningful lower wick
    #   - closes back above the swept level
    #
    # A 35% wick/range requirement prevents ordinary marginal
    # breaks from being labelled as stop-hunts.
    # =========================================================

    print("Adding liquidity sweeps...")

    recent_high = (
        df["swing_high_price"]
        .ffill()
        .shift(1)
    )

    recent_low = (
        df["swing_low_price"]
        .ffill()
        .shift(1)
    )

    safe_range = df["range"].replace(0, np.nan)

    upper_wick_ratio = (
        df["upper_wick"] / safe_range
    ).fillna(0.0)

    lower_wick_ratio = (
        df["lower_wick"] / safe_range
    ).fillna(0.0)

    minimum_penetration = (
        df["atr14"]
        .fillna(0.0)
        * 0.02
    )

    df["liquidity_sweep_high_level"] = recent_high
    df["liquidity_sweep_low_level"] = recent_low

    df["liquidity_sweep_high_wick_ratio"] = upper_wick_ratio
    df["liquidity_sweep_low_wick_ratio"] = lower_wick_ratio

    df["liquidity_sweep_high"] = (
        recent_high.notna()
        &
        (
            df["high"]
            >
            recent_high + minimum_penetration
        )
        &
        (df["close"] < recent_high)
        &
        (upper_wick_ratio >= 0.35)
    )

    df["liquidity_sweep_low"] = (
        recent_low.notna()
        &
        (
            df["low"]
            <
            recent_low - minimum_penetration
        )
        &
        (df["close"] > recent_low)
        &
        (lower_wick_ratio >= 0.35)
    )

    # Stronger subset: the latest swing itself formed part of an
    # equal-high / equal-low liquidity pool.

    latest_high_was_equal = (
        df["equal_high"]
        .where(df["swing_high"])
        .ffill()
        .shift(1)
        .fillna(False)
        .astype(bool)
    )

    latest_low_was_equal = (
        df["equal_low"]
        .where(df["swing_low"])
        .ffill()
        .shift(1)
        .fillna(False)
        .astype(bool)
    )

    df["equal_high_liquidity_sweep"] = (
        df["liquidity_sweep_high"]
        &
        latest_high_was_equal
    )

    df["equal_low_liquidity_sweep"] = (
        df["liquidity_sweep_low"]
        &
        latest_low_was_equal
    )

    # =========================================================
    # CANDLE PATTERNS
    # =========================================================

    print("Adding candle patterns...")

    previous_open = (
        df["open"].shift(1)
    )

    previous_close = (
        df["close"].shift(1)
    )

    df["bullish_engulfing"] = (
        (df["close"] > df["open"])
        &
        (previous_close < previous_open)
        &
        (df["open"] <= previous_close)
        &
        (df["close"] >= previous_open)
    )

    df["bearish_engulfing"] = (
        (df["close"] < df["open"])
        &
        (previous_close > previous_open)
        &
        (df["open"] >= previous_close)
        &
        (df["close"] <= previous_open)
    )

    df["bullish_pin_bar"] = (
        (df["lower_wick"] >= df["body"] * 2)
        &
        (df["upper_wick"] <= df["body"])
    )

    df["bearish_pin_bar"] = (
        (df["upper_wick"] >= df["body"] * 2)
        &
        (df["lower_wick"] <= df["body"])
    )

    df["inside_bar"] = (
        (df["high"] < df["high"].shift(1))
        &
        (df["low"] > df["low"].shift(1))
    )

    df["outside_bar"] = (
        (df["high"] > df["high"].shift(1))
        &
        (df["low"] < df["low"].shift(1))
    )

    df["strong_bullish_candle"] = (
        df["bullish_candle"]
        &
        (df["body_strength"] >= 0.70)
    )

    df["strong_bearish_candle"] = (
        df["bearish_candle"]
        &
        (df["body_strength"] >= 0.70)
    )

    df["doji"] = (
        df["body_strength"] <= 0.10
    )



    # ---------------------------------------------------------
    # Extra candle / reversal context used by order-block
    # classification. These are additional features; the
    # existing candle-pattern columns remain unchanged.
    # ---------------------------------------------------------

    safe_range_for_patterns = df["range"].replace(0, np.nan)

    df["indecision_candle"] = (
        df["body_strength"] <= 0.30
    )

    df["bullish_marubozu"] = (
        df["bullish_candle"]
        &
        (df["body_strength"] >= 0.85)
        &
        (df["upper_wick"] <= safe_range_for_patterns * 0.08)
        &
        (df["lower_wick"] <= safe_range_for_patterns * 0.08)
    )

    df["bearish_marubozu"] = (
        df["bearish_candle"]
        &
        (df["body_strength"] >= 0.85)
        &
        (df["upper_wick"] <= safe_range_for_patterns * 0.08)
        &
        (df["lower_wick"] <= safe_range_for_patterns * 0.08)
    )

    first_body_mid = (
        df["open"].shift(2)
        + df["close"].shift(2)
    ) / 2.0

    df["morning_star"] = (
        df["bearish_candle"].shift(2).fillna(False)
        &
        (df["body_strength"].shift(1) <= 0.35)
        &
        df["bullish_candle"]
        &
        (df["close"] > first_body_mid)
    )

    df["evening_star"] = (
        df["bullish_candle"].shift(2).fillna(False)
        &
        (df["body_strength"].shift(1) <= 0.35)
        &
        df["bearish_candle"]
        &
        (df["close"] < first_body_mid)
    )

    df["bullish_manipulation_candle"] = (
        df["liquidity_sweep_low"]
        &
        df["bullish_candle"]
    )

    df["bearish_manipulation_candle"] = (
        df["liquidity_sweep_high"]
        &
        df["bearish_candle"]
    )

    # =========================================================
    # FAIR VALUE GAPS
    # =========================================================
    #
    # Standard three-candle imbalance:
    #
    # Bullish:
    #   candle 3 low > candle 1 high
    #
    # Bearish:
    #   candle 3 high < candle 1 low
    #
    # The original boolean feature names are preserved.  Zone
    # boundaries, size and first mitigation/fill events are also
    # stored so charts and future strategy rules can use the
    # actual rectangle rather than a single boolean.
    # =========================================================

    print("Adding Fair Value Gaps...")

    two_back_high = df["high"].shift(2)
    two_back_low = df["low"].shift(2)

    df["bullish_fvg"] = (
        df["low"] > two_back_high
    )

    df["bearish_fvg"] = (
        df["high"] < two_back_low
    )

    df["bullish_fvg_low"] = np.where(
        df["bullish_fvg"],
        two_back_high,
        np.nan,
    )

    df["bullish_fvg_high"] = np.where(
        df["bullish_fvg"],
        df["low"],
        np.nan,
    )

    df["bearish_fvg_low"] = np.where(
        df["bearish_fvg"],
        df["high"],
        np.nan,
    )

    df["bearish_fvg_high"] = np.where(
        df["bearish_fvg"],
        two_back_low,
        np.nan,
    )

    df["bullish_fvg_size"] = np.where(
        df["bullish_fvg"],
        df["low"] - two_back_high,
        0.0,
    )

    df["bearish_fvg_size"] = np.where(
        df["bearish_fvg"],
        two_back_low - df["high"],
        0.0,
    )

    safe_atr = df["atr14"].replace(0, np.nan)

    df["bullish_fvg_size_atr"] = (
        df["bullish_fvg_size"] / safe_atr
    ).fillna(0.0)

    df["bearish_fvg_size_atr"] = (
        df["bearish_fvg_size"] / safe_atr
    ).fillna(0.0)

    # Track the latest unfilled FVG in each direction.
    bullish_fvg_retest = np.zeros(len(df), dtype=bool)
    bearish_fvg_retest = np.zeros(len(df), dtype=bool)
    bullish_fvg_filled = np.zeros(len(df), dtype=bool)
    bearish_fvg_filled = np.zeros(len(df), dtype=bool)

    active_bull_low = np.full(len(df), np.nan)
    active_bull_high = np.full(len(df), np.nan)
    active_bear_low = np.full(len(df), np.nan)
    active_bear_high = np.full(len(df), np.nan)

    bull_zone = None
    bear_zone = None

    for i in range(len(df)):

        # Existing bullish zone: mitigation starts when price
        # returns into the rectangle; fully filled when price
        # reaches the lower boundary.
        if bull_zone is not None and i > bull_zone["created"]:
            if float(df.loc[i, "low"]) <= bull_zone["high"]:
                if not bull_zone["retested"]:
                    bullish_fvg_retest[i] = True
                    bull_zone["retested"] = True

            if float(df.loc[i, "low"]) <= bull_zone["low"]:
                bullish_fvg_filled[i] = True
                bull_zone = None

        # Existing bearish zone.
        if bear_zone is not None and i > bear_zone["created"]:
            if float(df.loc[i, "high"]) >= bear_zone["low"]:
                if not bear_zone["retested"]:
                    bearish_fvg_retest[i] = True
                    bear_zone["retested"] = True

            if float(df.loc[i, "high"]) >= bear_zone["high"]:
                bearish_fvg_filled[i] = True
                bear_zone = None

        # A newly created gap becomes active after this candle.
        if bool(df.loc[i, "bullish_fvg"]):
            bull_zone = {
                "low": float(df.loc[i, "bullish_fvg_low"]),
                "high": float(df.loc[i, "bullish_fvg_high"]),
                "created": i,
                "retested": False,
            }

        if bool(df.loc[i, "bearish_fvg"]):
            bear_zone = {
                "low": float(df.loc[i, "bearish_fvg_low"]),
                "high": float(df.loc[i, "bearish_fvg_high"]),
                "created": i,
                "retested": False,
            }

        if bull_zone is not None:
            active_bull_low[i] = bull_zone["low"]
            active_bull_high[i] = bull_zone["high"]

        if bear_zone is not None:
            active_bear_low[i] = bear_zone["low"]
            active_bear_high[i] = bear_zone["high"]

    df["bullish_fvg_retest"] = bullish_fvg_retest
    df["bearish_fvg_retest"] = bearish_fvg_retest
    df["bullish_fvg_filled"] = bullish_fvg_filled
    df["bearish_fvg_filled"] = bearish_fvg_filled

    df["active_bullish_fvg_low"] = active_bull_low
    df["active_bullish_fvg_high"] = active_bull_high
    df["active_bearish_fvg_low"] = active_bear_low
    df["active_bearish_fvg_high"] = active_bear_high

    # =========================================================
    # SESSION LEVELS
    # =========================================================

    print("Adding session levels...")

    df["session_date"] = (
        df["timestamp"].dt.date
    )

    # IMPORTANT:
    #
    # These are running session highs/lows rather than the
    # final high/low of the completed session.
    #
    # This prevents future candles in the same session from
    # leaking into earlier rows.

    session_group = (
        df.groupby(
            ["session_date", "session"]
        )
    )

    df["session_high"] = (
        session_group["high"]
        .cummax()
        .shift(1)
    )

    df["session_low"] = (
        session_group["low"]
        .cummin()
        .shift(1)
    )

    # =========================================================
    # PREVIOUS DAY LEVELS
    # =========================================================

    print("Adding previous day levels...")

    df["date"] = (
        df["timestamp"].dt.date
    )

    daily_high = (
        df.groupby("date")["high"]
        .max()
    )

    daily_low = (
        df.groupby("date")["low"]
        .min()
    )

    previous_day_high = (
        daily_high.shift(1)
    )

    previous_day_low = (
        daily_low.shift(1)
    )

    df["previous_day_high"] = (
        df["date"].map(
            previous_day_high
        )
    )

    df["previous_day_low"] = (
        df["date"].map(
            previous_day_low
        )
    )

    # =========================================================
    # PREVIOUS DAY SWEEPS
    # =========================================================

    print("Adding previous day sweeps...")

    df["previous_day_high_sweep"] = (
        (df["high"] > df["previous_day_high"])
        &
        (df["close"] < df["previous_day_high"])
    )

    df["previous_day_low_sweep"] = (
        (df["low"] < df["previous_day_low"])
        &
        (df["close"] > df["previous_day_low"])
    )

    # =========================================================
    # FIBONACCI
    # =========================================================

    print("Adding Fibonacci levels...")

    # ---------------------------------------------------------
    # Confirmed swing points
    # ---------------------------------------------------------
    #
    # The swing features above have already been shifted forward
    # by two candles. Therefore these values represent swings
    # that are known at the current candle.
    #
    # We additionally shift the values by one candle so the
    # current row cannot simultaneously create and use the
    # swing point.
    # ---------------------------------------------------------

    confirmed_swing_high = (
        df["swing_high_price"]
        .ffill()
        .shift(1)
    )

    confirmed_swing_low = (
        df["swing_low_price"]
        .ffill()
        .shift(1)
    )

    # ---------------------------------------------------------
    # Track the TRUE pivot candle for the latest confirmed swing
    # ---------------------------------------------------------

    last_high_index = (
        df["swing_high_source_index"]
        .ffill()
        .shift(1)
    )

    last_low_index = (
        df["swing_low_source_index"]
        .ffill()
        .shift(1)
    )

    # Expose the exact anchors used by every Fib calculation.
    # These make validation charts deterministic instead of
    # having to guess which visible swing created the levels.
    df["fib_swing_high"] = confirmed_swing_high
    df["fib_swing_low"] = confirmed_swing_low
    df["fib_swing_high_index"] = last_high_index
    df["fib_swing_low_index"] = last_low_index

    # ---------------------------------------------------------
    # Direction of the current swing
    # ---------------------------------------------------------

    df["fib_bullish"] = (
        last_high_index > last_low_index
    )

    df["fib_bearish"] = (
        last_low_index > last_high_index
    )

    fib_range = (
        confirmed_swing_high
        -
        confirmed_swing_low
    )

    valid_fib_range = (
        fib_range > 0
    )

    # ---------------------------------------------------------
    # Bullish retracement
    # ---------------------------------------------------------

    bull_fib_382 = (
        confirmed_swing_high
        -
        fib_range * 0.382
    )

    bull_fib_500 = (
        confirmed_swing_high
        -
        fib_range * 0.500
    )

    bull_fib_618 = (
        confirmed_swing_high
        -
        fib_range * 0.618
    )

    # ---------------------------------------------------------
    # Bearish retracement
    # ---------------------------------------------------------

    bear_fib_382 = (
        confirmed_swing_low
        +
        fib_range * 0.382
    )

    bear_fib_500 = (
        confirmed_swing_low
        +
        fib_range * 0.500
    )

    bear_fib_618 = (
        confirmed_swing_low
        +
        fib_range * 0.618
    )

    # ---------------------------------------------------------
    # Select directional Fib levels
    # ---------------------------------------------------------

    df["fib_382"] = np.where(
        df["fib_bullish"],
        bull_fib_382,
        np.where(
            df["fib_bearish"],
            bear_fib_382,
            np.nan
        )
    )

    df["fib_500"] = np.where(
        df["fib_bullish"],
        bull_fib_500,
        np.where(
            df["fib_bearish"],
            bear_fib_500,
            np.nan
        )
    )

    df["fib_618"] = np.where(
        df["fib_bullish"],
        bull_fib_618,
        np.where(
            df["fib_bearish"],
            bear_fib_618,
            np.nan
        )
    )

    # ---------------------------------------------------------
    # Fib proximity
    # ---------------------------------------------------------

    fib_tolerance = (
        df["atr14"] * 0.20
    )

    df["fib_tolerance"] = fib_tolerance

    df["near_fib_382"] = (
        valid_fib_range
        &
        (
            (
                df["close"]
                -
                df["fib_382"]
            ).abs()
            <= fib_tolerance
        )
    )

    df["near_fib_500"] = (
        valid_fib_range
        &
        (
            (
                df["close"]
                -
                df["fib_500"]
            ).abs()
            <= fib_tolerance
        )
    )

    df["near_fib_618"] = (
        valid_fib_range
        &
        (
            (
                df["close"]
                -
                df["fib_618"]
            ).abs()
            <= fib_tolerance
        )
    )

    # ---------------------------------------------------------
    # Fib rejection
    # ---------------------------------------------------------

    df["fib_382_rejection"] = (
        (
            df["fib_bullish"]
            &
            (
                df["low"]
                <=
                df["fib_382"] + fib_tolerance
            )
            &
            (
                df["close"]
                >
                df["fib_382"]
            )
        )
        |
        (
            df["fib_bearish"]
            &
            (
                df["high"]
                >=
                df["fib_382"] - fib_tolerance
            )
            &
            (
                df["close"]
                <
                df["fib_382"]
            )
        )
    )

    df["fib_500_rejection"] = (
        (
            df["fib_bullish"]
            &
            (
                df["low"]
                <=
                df["fib_500"] + fib_tolerance
            )
            &
            (
                df["close"]
                >
                df["fib_500"]
            )
        )
        |
        (
            df["fib_bearish"]
            &
            (
                df["high"]
                >=
                df["fib_500"] - fib_tolerance
            )
            &
            (
                df["close"]
                <
                df["fib_500"]
            )
        )
    )

    df["fib_618_rejection"] = (
        (
            df["fib_bullish"]
            &
            (
                df["low"]
                <=
                df["fib_618"] + fib_tolerance
            )
            &
            (
                df["close"]
                >
                df["fib_618"]
            )
        )
        |
        (
            df["fib_bearish"]
            &
            (
                df["high"]
                >=
                df["fib_618"] - fib_tolerance
            )
            &
            (
                df["close"]
                <
                df["fib_618"]
            )
        )
    )

    # ---------------------------------------------------------
    # Direction-specific Fib rejection
    # ---------------------------------------------------------

    df["bullish_fib_382_rejection"] = (
        df["fib_bullish"]
        &
        df["fib_382_rejection"]
    )

    df["bullish_fib_500_rejection"] = (
        df["fib_bullish"]
        &
        df["fib_500_rejection"]
    )

    df["bullish_fib_618_rejection"] = (
        df["fib_bullish"]
        &
        df["fib_618_rejection"]
    )

    df["bearish_fib_382_rejection"] = (
        df["fib_bearish"]
        &
        df["fib_382_rejection"]
    )

    df["bearish_fib_500_rejection"] = (
        df["fib_bearish"]
        &
        df["fib_500_rejection"]
    )

    df["bearish_fib_618_rejection"] = (
        df["fib_bearish"]
        &
        df["fib_618_rejection"]
    )

    # ---------------------------------------------------------
    # Fib + BOS context
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Fib + BOS SEQUENCE context
    #
    # BUY:
    #   swing LOW -> bullish BOS during leg -> swing HIGH
    #   -> later Fib retracement
    #
    # SELL:
    #   swing HIGH -> bearish BOS during leg -> swing LOW
    #   -> later Fib retracement
    #
    # This intentionally does NOT require BOS and Fib
    # retracement to occur on the same candle.
    # ---------------------------------------------------------

    current_bar_index = pd.Series(
        np.arange(len(df), dtype=float),
        index=df.index,
    )

    bullish_bos_bar = pd.Series(
        np.where(
            df["bullish_bos"].fillna(False),
            current_bar_index,
            np.nan,
        ),
        index=df.index,
    )

    bearish_bos_bar = pd.Series(
        np.where(
            df["bearish_bos"].fillna(False),
            current_bar_index,
            np.nan,
        ),
        index=df.index,
    )

    last_bullish_bos_index = (
        bullish_bos_bar
        .ffill()
    )

    last_bearish_bos_index = (
        bearish_bos_bar
        .ffill()
    )

    # Bullish BOS must belong to the LOW -> HIGH leg
    bullish_bos_in_fib_leg = (
        df["fib_bullish"]
        &
        last_bullish_bos_index.notna()
        &
        df["fib_swing_low_index"].notna()
        &
        df["fib_swing_high_index"].notna()
        &
        (
            last_bullish_bos_index
            >=
            df["fib_swing_low_index"]
        )
        &
        (
            last_bullish_bos_index
            <=
            df["fib_swing_high_index"]
        )
        &
        (
            current_bar_index
            >
            df["fib_swing_high_index"]
        )
    )

    # Bearish BOS must belong to the HIGH -> LOW leg
    bearish_bos_in_fib_leg = (
        df["fib_bearish"]
        &
        last_bearish_bos_index.notna()
        &
        df["fib_swing_high_index"].notna()
        &
        df["fib_swing_low_index"].notna()
        &
        (
            last_bearish_bos_index
            >=
            df["fib_swing_high_index"]
        )
        &
        (
            last_bearish_bos_index
            <=
            df["fib_swing_low_index"]
        )
        &
        (
            current_bar_index
            >
            df["fib_swing_low_index"]
        )
    )

    # ---------------------------------------------------------
    # Direction-specific BOS -> Fib retracement
    # ---------------------------------------------------------

    df["bullish_bos_fib_382"] = (
        bullish_bos_in_fib_leg
        &
        df["near_fib_382"]
    )

    df["bullish_bos_fib_500"] = (
        bullish_bos_in_fib_leg
        &
        df["near_fib_500"]
    )

    df["bullish_bos_fib_618"] = (
        bullish_bos_in_fib_leg
        &
        df["near_fib_618"]
    )

    df["bearish_bos_fib_382"] = (
        bearish_bos_in_fib_leg
        &
        df["near_fib_382"]
    )

    df["bearish_bos_fib_500"] = (
        bearish_bos_in_fib_leg
        &
        df["near_fib_500"]
    )

    df["bearish_bos_fib_618"] = (
        bearish_bos_in_fib_leg
        &
        df["near_fib_618"]
    )

    # Generic BOS/Fib context
    df["fib_382_bos_context"] = (
        df["bullish_bos_fib_382"]
        |
        df["bearish_bos_fib_382"]
    )

    df["fib_500_bos_context"] = (
        df["bullish_bos_fib_500"]
        |
        df["bearish_bos_fib_500"]
    )

    df["fib_618_bos_context"] = (
        df["bullish_bos_fib_618"]
        |
        df["bearish_bos_fib_618"]
    )

    # ---------------------------------------------------------
    # Fib + liquidity sweep
    # ---------------------------------------------------------

    df["fib_382_liquidity_context"] = (
        df["near_fib_382"]
        &
        (
            df["liquidity_sweep_high"]
            |
            df["liquidity_sweep_low"]
        )
    )

    df["fib_500_liquidity_context"] = (
        df["near_fib_500"]
        &
        (
            df["liquidity_sweep_high"]
            |
            df["liquidity_sweep_low"]
        )
    )

    df["fib_618_liquidity_context"] = (
        df["near_fib_618"]
        &
        (
            df["liquidity_sweep_high"]
            |
            df["liquidity_sweep_low"]
        )
    )

    # Direction-specific liquidity + Fib

    df["bullish_fib_liquidity"] = (
        df["fib_bullish"]
        &
        (
            df["liquidity_sweep_low"]
            |
            df["previous_day_low_sweep"]
        )
        &
        (
            df["near_fib_382"]
            |
            df["near_fib_500"]
            |
            df["near_fib_618"]
        )
    )

    df["bearish_fib_liquidity"] = (
        df["fib_bearish"]
        &
        (
            df["liquidity_sweep_high"]
            |
            df["previous_day_high_sweep"]
        )
        &
        (
            df["near_fib_382"]
            |
            df["near_fib_500"]
            |
            df["near_fib_618"]
        )
    )

    # =========================================================
    # CLEAN
    # =========================================================

    df = df.replace(
        [np.inf, -np.inf],
        np.nan
    )

    # =========================================================
    # INSTITUTIONAL FEATURES
    # =========================================================

    print("Adding institutional features...")
    df = add_institutional_features(df)

    # =========================================================
    # SMC SEQUENCE FEATURES
    # =========================================================
    #
    # These model the sequence shown in the reference examples:
    #
    #   identify confirmed swing liquidity
    #       -> sweep the swing / equal highs or lows
    #       -> structure shifts away from the sweep
    #       -> directional FVG forms
    #       -> optional later FVG retest
    #       -> opposing confirmed swing is the visible target
    #
    # The sequence is intentionally event ordered and uses only
    # information that was available by each candle close.
    # =========================================================

    print("Adding SMC sweep/FVG sequence features...")

    bull_disp = df["bullish_displacement"].fillna(False).astype(bool)
    bear_disp = df["bearish_displacement"].fillna(False).astype(bool)

    # The displacement candle in a three-candle FVG is the middle
    # candle (i - 1), not the third candle where the gap becomes
    # confirmed.  Keep raw FVGs and expose this stronger subset.
    df["bullish_fvg_displacement"] = (
        df["bullish_fvg"].fillna(False).astype(bool)
        & bull_disp.shift(1).fillna(False).astype(bool)
    )

    df["bearish_fvg_displacement"] = (
        df["bearish_fvg"].fillna(False).astype(bool)
        & bear_disp.shift(1).fillna(False).astype(bool)
    )

    n = len(df)
    sequence_window = 8

    bull_shift = np.zeros(n, dtype=bool)
    bear_shift = np.zeros(n, dtype=bool)
    bull_fvg_setup = np.zeros(n, dtype=bool)
    bear_fvg_setup = np.zeros(n, dtype=bool)
    bull_full_setup = np.zeros(n, dtype=bool)
    bear_full_setup = np.zeros(n, dtype=bool)
    bull_fvg_retest_setup = np.zeros(n, dtype=bool)
    bear_fvg_retest_setup = np.zeros(n, dtype=bool)

    bull_sweep_index = np.full(n, np.nan)
    bear_sweep_index = np.full(n, np.nan)
    bull_sweep_level = np.full(n, np.nan)
    bear_sweep_level = np.full(n, np.nan)
    bull_target_high = np.full(n, np.nan)
    bear_target_low = np.full(n, np.nan)
    bull_setup_fvg_low = np.full(n, np.nan)
    bull_setup_fvg_high = np.full(n, np.nan)
    bear_setup_fvg_low = np.full(n, np.nan)
    bear_setup_fvg_high = np.full(n, np.nan)

    latest_high_before = df["swing_high_price"].ffill().shift(1)
    latest_low_before = df["swing_low_price"].ffill().shift(1)

    last_low_sweep = None
    last_high_sweep = None
    low_sweep_shift_seen = False
    high_sweep_shift_seen = False
    active_bull_setup_fvg = None
    active_bear_setup_fvg = None

    for i in range(n):
        # Retest active sequence FVGs before replacing them with a
        # newly formed zone on this candle.
        if active_bull_setup_fvg is not None and i > active_bull_setup_fvg["created"]:
            if (
                float(df.loc[i, "low"]) <= active_bull_setup_fvg["high"]
                and float(df.loc[i, "high"]) >= active_bull_setup_fvg["low"]
            ):
                bull_fvg_retest_setup[i] = True
                bull_sweep_index[i] = active_bull_setup_fvg["sweep_index"]
                bull_sweep_level[i] = active_bull_setup_fvg["sweep_level"]
                bull_target_high[i] = active_bull_setup_fvg["target"]
                bull_setup_fvg_low[i] = active_bull_setup_fvg["low"]
                bull_setup_fvg_high[i] = active_bull_setup_fvg["high"]
                active_bull_setup_fvg = None

        if active_bear_setup_fvg is not None and i > active_bear_setup_fvg["created"]:
            if (
                float(df.loc[i, "low"]) <= active_bear_setup_fvg["high"]
                and float(df.loc[i, "high"]) >= active_bear_setup_fvg["low"]
            ):
                bear_fvg_retest_setup[i] = True
                bear_sweep_index[i] = active_bear_setup_fvg["sweep_index"]
                bear_sweep_level[i] = active_bear_setup_fvg["sweep_level"]
                bear_target_low[i] = active_bear_setup_fvg["target"]
                bear_setup_fvg_low[i] = active_bear_setup_fvg["low"]
                bear_setup_fvg_high[i] = active_bear_setup_fvg["high"]
                active_bear_setup_fvg = None

        if bool(df.loc[i, "liquidity_sweep_low"]):
            last_low_sweep = {
                "index": i,
                "level": float(df.loc[i, "liquidity_sweep_low_level"]),
                "target": (
                    float(latest_high_before.iloc[i])
                    if pd.notna(latest_high_before.iloc[i])
                    else np.nan
                ),
            }
            low_sweep_shift_seen = False

        if bool(df.loc[i, "liquidity_sweep_high"]):
            last_high_sweep = {
                "index": i,
                "level": float(df.loc[i, "liquidity_sweep_high_level"]),
                "target": (
                    float(latest_low_before.iloc[i])
                    if pd.notna(latest_low_before.iloc[i])
                    else np.nan
                ),
            }
            high_sweep_shift_seen = False

        # Expire stale sweep state.
        if (
            last_low_sweep is not None
            and i - last_low_sweep["index"] > sequence_window
        ):
            last_low_sweep = None
            low_sweep_shift_seen = False

        if (
            last_high_sweep is not None
            and i - last_high_sweep["index"] > sequence_window
        ):
            last_high_sweep = None
            high_sweep_shift_seen = False

        bullish_break = bool(df.loc[i, "bullish_bos"]) or bool(
            df.loc[i, "bullish_choch"]
        )
        bearish_break = bool(df.loc[i, "bearish_bos"]) or bool(
            df.loc[i, "bearish_choch"]
        )

        if last_low_sweep is not None and bullish_break:
            bull_shift[i] = True
            low_sweep_shift_seen = True

        if last_high_sweep is not None and bearish_break:
            bear_shift[i] = True
            high_sweep_shift_seen = True

        if last_low_sweep is not None and bool(df.loc[i, "bullish_fvg_displacement"]):
            bull_fvg_setup[i] = True
            bull_full_setup[i] = low_sweep_shift_seen
            bull_sweep_index[i] = last_low_sweep["index"]
            bull_sweep_level[i] = last_low_sweep["level"]
            bull_target_high[i] = last_low_sweep["target"]
            bull_setup_fvg_low[i] = float(df.loc[i, "bullish_fvg_low"])
            bull_setup_fvg_high[i] = float(df.loc[i, "bullish_fvg_high"])
            active_bull_setup_fvg = {
                "low": bull_setup_fvg_low[i],
                "high": bull_setup_fvg_high[i],
                "created": i,
                "sweep_index": last_low_sweep["index"],
                "sweep_level": last_low_sweep["level"],
                "target": last_low_sweep["target"],
            }

        if last_high_sweep is not None and bool(df.loc[i, "bearish_fvg_displacement"]):
            bear_fvg_setup[i] = True
            bear_full_setup[i] = high_sweep_shift_seen
            bear_sweep_index[i] = last_high_sweep["index"]
            bear_sweep_level[i] = last_high_sweep["level"]
            bear_target_low[i] = last_high_sweep["target"]
            bear_setup_fvg_low[i] = float(df.loc[i, "bearish_fvg_low"])
            bear_setup_fvg_high[i] = float(df.loc[i, "bearish_fvg_high"])
            active_bear_setup_fvg = {
                "low": bear_setup_fvg_low[i],
                "high": bear_setup_fvg_high[i],
                "created": i,
                "sweep_index": last_high_sweep["index"],
                "sweep_level": last_high_sweep["level"],
                "target": last_high_sweep["target"],
            }

    df["bullish_liquidity_structure_shift"] = bull_shift
    df["bearish_liquidity_structure_shift"] = bear_shift
    df["bullish_liquidity_fvg_setup"] = bull_fvg_setup
    df["bearish_liquidity_fvg_setup"] = bear_fvg_setup
    df["bullish_smc_reversal_setup"] = bull_full_setup
    df["bearish_smc_reversal_setup"] = bear_full_setup
    df["bullish_smc_fvg_retest"] = bull_fvg_retest_setup
    df["bearish_smc_fvg_retest"] = bear_fvg_retest_setup

    df["bullish_smc_sweep_index"] = bull_sweep_index
    df["bearish_smc_sweep_index"] = bear_sweep_index
    df["bullish_smc_sweep_level"] = bull_sweep_level
    df["bearish_smc_sweep_level"] = bear_sweep_level
    df["bullish_smc_target_high"] = bull_target_high
    df["bearish_smc_target_low"] = bear_target_low
    df["bullish_smc_fvg_low"] = bull_setup_fvg_low
    df["bullish_smc_fvg_high"] = bull_setup_fvg_high
    df["bearish_smc_fvg_low"] = bear_setup_fvg_low
    df["bearish_smc_fvg_high"] = bear_setup_fvg_high

    return df


