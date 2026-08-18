import numpy as np
import pandas as pd


INSTITUTIONAL_FEATURE_VERSION = "2026-08-14-v5-smc-sequences"


# ============================================================
# HELPERS
# ============================================================


def _bool_series(df, name):
    if name not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)

    series = df[name]

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)

    if pd.api.types.is_numeric_dtype(series):
        return (
            pd.to_numeric(series, errors="coerce")
            .fillna(0)
            .astype(bool)
        )

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y", "on"})
    )


def _overlaps(low, high, zone_low, zone_high):
    return low <= zone_high and high >= zone_low


def _order_block_contexts(df, source_i, creation_i, direction):
    """
    Return (primary_label, contexts) for a validated order block.

    The source candle is the last opposing candle before the
    displacement/structure break.  Some reversal patterns (engulfing and
    morning/evening star) are only known on the displacement candle, so
    they are evaluated at ``creation_i`` rather than incorrectly forcing
    every subtype to exist on the source candle itself.
    """
    if (
        source_i is None
        or creation_i is None
        or source_i < 0
        or creation_i < 0
        or source_i >= len(df)
        or creation_i >= len(df)
    ):
        return "standard", set()

    source = df.iloc[source_i]
    creation = df.iloc[creation_i]
    contexts = set()

    context_start = max(0, source_i - 2)
    context_end = creation_i + 1
    window = df.iloc[context_start:context_end]

    if direction == "bullish":
        if (
            "liquidity_sweep_low" in window.columns
            and window["liquidity_sweep_low"].fillna(False).astype(bool).any()
        ):
            contexts.add("manipulation")

        if bool(source.get("bullish_pin_bar", False)):
            contexts.add("pin_bar")

        if bool(creation.get("bullish_engulfing", False)):
            contexts.add("engulfing")

        if bool(creation.get("morning_star", False)):
            contexts.add("star")

        if bool(source.get("indecision_candle", False)):
            contexts.add("indecision")

        if bool(source.get("bearish_marubozu", False)) or bool(
            creation.get("bullish_marubozu", False)
        ):
            contexts.add("marubozu")

    else:
        if (
            "liquidity_sweep_high" in window.columns
            and window["liquidity_sweep_high"].fillna(False).astype(bool).any()
        ):
            contexts.add("manipulation")

        if bool(source.get("bearish_pin_bar", False)):
            contexts.add("pin_bar")

        if bool(creation.get("bearish_engulfing", False)):
            contexts.add("engulfing")

        if bool(creation.get("evening_star", False)):
            contexts.add("star")

        if bool(source.get("indecision_candle", False)):
            contexts.add("indecision")

        if bool(source.get("bullish_marubozu", False)) or bool(
            creation.get("bearish_marubozu", False)
        ):
            contexts.add("marubozu")

    # Priority is only for the human-readable single type column.
    # The independent boolean subtype columns preserve every match.
    priority = [
        "manipulation",
        "star",
        "engulfing",
        "pin_bar",
        "indecision",
        "marubozu",
    ]

    primary = next(
        (name for name in priority if name in contexts),
        "standard",
    )

    return primary, contexts


def _find_last_opposite_candle(df, i, bullish_ob, lookback=5):
    """
    Return the most recent opposite-colour candle before a displacement
    / structure break. This matches the common 'last opposing candle
    before displacement' order-block definition more closely than only
    checking i-1.
    """
    start = max(0, i - lookback)

    for j in range(i - 1, start - 1, -1):
        o = float(df.iloc[j]["open"])
        c = float(df.iloc[j]["close"])

        if bullish_ob and c < o:
            return j

        if (not bullish_ob) and c > o:
            return j

    return None


# ============================================================
# INSTITUTIONAL FEATURES
# ============================================================


def add_institutional_features(df):
    """
    Add institutional / SMC-style features using only information known
    at the current candle.

    Core definitions used here:

    - Displacement: large directional body relative to ATR.
    - Bullish order block: last bearish candle before bullish
      displacement that breaks structure (BOS or CHOCH).
    - Bearish order block: last bullish candle before bearish
      displacement that breaks structure.
    - Order block retest: first later candle that trades back into a
      still-valid zone.
    - Order block invalidation: close through the far edge of the zone.
    - Breaker block: an invalidated order block, retained as a zone on
      the opposite side and detected again on its first retest.
    - Demand/supply: aliases of validated bullish/bearish order-block
      zones, preserved for compatibility with existing strategy files.

    Existing feature names are preserved. New columns are added for
    source indices, active zones, invalidation, breaker boundaries and
    order-block pattern/context classification.
    """

    df = df.copy()

    required = ["open", "high", "low", "close", "atr14"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    n = len(df)

    # ========================================================
    # BASIC MEASUREMENTS / DISPLACEMENT
    # ========================================================

    candle_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()

    body_ratio = np.where(
        candle_range > 0,
        body / candle_range,
        0.0,
    )

    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]

    atr = df["atr14"].replace(0, np.nan)

    range_vs_atr = np.where(
        atr > 0,
        candle_range / atr,
        0.0,
    )

    df["displacement_strength"] = range_vs_atr

    df["bullish_displacement"] = (
        bullish
        & (body_ratio >= 0.60)
        & (range_vs_atr >= 1.20)
    )

    df["bearish_displacement"] = (
        bearish
        & (body_ratio >= 0.60)
        & (range_vs_atr >= 1.20)
    )

    df["strong_bullish_displacement"] = (
        bullish
        & (body_ratio >= 0.70)
        & (range_vs_atr >= 1.50)
    )

    df["strong_bearish_displacement"] = (
        bearish
        & (body_ratio >= 0.70)
        & (range_vs_atr >= 1.50)
    )

    bullish_bos = _bool_series(df, "bullish_bos")
    bearish_bos = _bool_series(df, "bearish_bos")
    bullish_choch = _bool_series(df, "bullish_choch")
    bearish_choch = _bool_series(df, "bearish_choch")

    bullish_structure_break = bullish_bos | bullish_choch
    bearish_structure_break = bearish_bos | bearish_choch

    df["bullish_displacement_bos"] = (
        df["bullish_displacement"] & bullish_structure_break
    )

    df["bearish_displacement_bos"] = (
        df["bearish_displacement"] & bearish_structure_break
    )

    # ========================================================
    # OUTPUT ARRAYS
    # ========================================================

    bool_columns = [
        "bullish_order_block",
        "bearish_order_block",
        "bullish_order_block_retest",
        "bearish_order_block_retest",
        "bullish_order_block_invalidation",
        "bearish_order_block_invalidation",
        "bullish_order_block_active",
        "bearish_order_block_active",
        "bullish_order_block_liquidity",
        "bearish_order_block_liquidity",
        "bullish_demand_zone",
        "bearish_supply_zone",
        "demand_zone_retest",
        "supply_zone_retest",
        "bearish_breaker_block",
        "bullish_breaker_block",
        "bearish_breaker_retest",
        "bullish_breaker_retest",
        "bearish_breaker_active",
        "bullish_breaker_active",
        "bullish_order_block_manipulation",
        "bearish_order_block_manipulation",
        "bullish_order_block_pin_bar",
        "bearish_order_block_pin_bar",
        "bullish_order_block_engulfing",
        "bearish_order_block_engulfing",
        "bullish_order_block_indecision",
        "bearish_order_block_indecision",
        "bullish_order_block_marubozu",
        "bearish_order_block_marubozu",
        "bullish_order_block_star",
        "bearish_order_block_star",
    ]

    out_bool = {
        name: np.zeros(n, dtype=bool)
        for name in bool_columns
    }

    numeric_columns = [
        "bullish_order_block_high",
        "bullish_order_block_low",
        "bearish_order_block_high",
        "bearish_order_block_low",
        "bullish_order_block_source_index",
        "bearish_order_block_source_index",
        "active_bullish_order_block_high",
        "active_bullish_order_block_low",
        "active_bearish_order_block_high",
        "active_bearish_order_block_low",
        "demand_zone_high",
        "demand_zone_low",
        "supply_zone_high",
        "supply_zone_low",
        "bearish_breaker_high",
        "bearish_breaker_low",
        "bearish_breaker_source_index",
        "bullish_breaker_high",
        "bullish_breaker_low",
        "bullish_breaker_source_index",
        "active_bearish_breaker_high",
        "active_bearish_breaker_low",
        "active_bullish_breaker_high",
        "active_bullish_breaker_low",
    ]

    out_num = {
        name: np.full(n, np.nan)
        for name in numeric_columns
    }

    ob_type_bull = np.full(n, "", dtype=object)
    ob_type_bear = np.full(n, "", dtype=object)

    liquidity_low = _bool_series(df, "liquidity_sweep_low")
    liquidity_high = _bool_series(df, "liquidity_sweep_high")

    # Multiple zones can remain active. The most recent valid zone is
    # exposed through the active_* columns, while retests can come from
    # any still-valid zone.
    active_bull_obs = []
    active_bear_obs = []
    active_bear_breakers = []
    active_bull_breakers = []

    # ========================================================
    # MAIN STATE LOOP
    # ========================================================

    for i in range(n):
        low_i = float(df.iloc[i]["low"])
        high_i = float(df.iloc[i]["high"])
        close_i = float(df.iloc[i]["close"])

        # ----------------------------------------------------
        # 1) Existing bullish OBs: invalidation / first retest
        # ----------------------------------------------------

        kept = []
        retest_zone = None

        for zone in active_bull_obs:
            if i <= zone["created"]:
                kept.append(zone)
                continue

            if close_i < zone["low"]:
                out_bool["bullish_order_block_invalidation"][i] = True
                out_bool["bearish_breaker_block"][i] = True
                out_num["bearish_breaker_high"][i] = zone["high"]
                out_num["bearish_breaker_low"][i] = zone["low"]
                out_num["bearish_breaker_source_index"][i] = zone["source"]

                active_bear_breakers.append(
                    {
                        "high": zone["high"],
                        "low": zone["low"],
                        "created": i,
                        "source": zone["source"],
                        "retested": False,
                    }
                )
                continue

            if (
                not zone["retested"]
                and _overlaps(low_i, high_i, zone["low"], zone["high"])
            ):
                zone["retested"] = True
                retest_zone = zone
                out_bool["bullish_order_block_retest"][i] = True

            kept.append(zone)

        active_bull_obs = kept

        # ----------------------------------------------------
        # 2) Existing bearish OBs
        # ----------------------------------------------------

        kept = []
        bear_retest_zone = None

        for zone in active_bear_obs:
            if i <= zone["created"]:
                kept.append(zone)
                continue

            if close_i > zone["high"]:
                out_bool["bearish_order_block_invalidation"][i] = True
                out_bool["bullish_breaker_block"][i] = True
                out_num["bullish_breaker_high"][i] = zone["high"]
                out_num["bullish_breaker_low"][i] = zone["low"]
                out_num["bullish_breaker_source_index"][i] = zone["source"]

                active_bull_breakers.append(
                    {
                        "high": zone["high"],
                        "low": zone["low"],
                        "created": i,
                        "source": zone["source"],
                        "retested": False,
                    }
                )
                continue

            if (
                not zone["retested"]
                and _overlaps(low_i, high_i, zone["low"], zone["high"])
            ):
                zone["retested"] = True
                bear_retest_zone = zone
                out_bool["bearish_order_block_retest"][i] = True

            kept.append(zone)

        active_bear_obs = kept

        # ----------------------------------------------------
        # 3) Existing bearish breakers (failed bullish OB)
        # ----------------------------------------------------

        kept = []

        for zone in active_bear_breakers:
            if i <= zone["created"]:
                kept.append(zone)
                continue

            # A bearish breaker is no longer useful once price closes
            # cleanly back above its far edge.
            if close_i > zone["high"]:
                continue

            if (
                not zone["retested"]
                and _overlaps(low_i, high_i, zone["low"], zone["high"])
            ):
                zone["retested"] = True
                out_bool["bearish_breaker_retest"][i] = True

            kept.append(zone)

        active_bear_breakers = kept

        # ----------------------------------------------------
        # 4) Existing bullish breakers (failed bearish OB)
        # ----------------------------------------------------

        kept = []

        for zone in active_bull_breakers:
            if i <= zone["created"]:
                kept.append(zone)
                continue

            if close_i < zone["low"]:
                continue

            if (
                not zone["retested"]
                and _overlaps(low_i, high_i, zone["low"], zone["high"])
            ):
                zone["retested"] = True
                out_bool["bullish_breaker_retest"][i] = True

            kept.append(zone)

        active_bull_breakers = kept

        # ----------------------------------------------------
        # 5) Create NEW order blocks only when displacement also
        #    breaks structure. This removes the old behaviour where
        #    every opposite candle + large candle became an OB.
        # ----------------------------------------------------

        bullish_creation = bool(
            df.iloc[i]["bullish_displacement"]
        ) and bool(bullish_structure_break.iloc[i])

        bearish_creation = bool(
            df.iloc[i]["bearish_displacement"]
        ) and bool(bearish_structure_break.iloc[i])

        if bullish_creation:
            source_i = _find_last_opposite_candle(
                df,
                i,
                bullish_ob=True,
                lookback=5,
            )

            if source_i is not None:
                zone_high = float(df.iloc[source_i]["high"])
                zone_low = float(df.iloc[source_i]["low"])
                zone_type, zone_contexts = _order_block_contexts(
                    df, source_i, i, "bullish"
                )

                out_bool["bullish_order_block"][i] = True
                out_bool["bullish_demand_zone"][i] = True

                out_num["bullish_order_block_high"][i] = zone_high
                out_num["bullish_order_block_low"][i] = zone_low
                out_num["bullish_order_block_source_index"][i] = source_i

                out_num["demand_zone_high"][i] = zone_high
                out_num["demand_zone_low"][i] = zone_low

                ob_type_bull[i] = zone_type

                active_bull_obs.append(
                    {
                        "high": zone_high,
                        "low": zone_low,
                        "created": i,
                        "source": source_i,
                        "retested": False,
                        "type": zone_type,
                    }
                )

                for context in zone_contexts:
                    subtype_key = f"bullish_order_block_{context}"
                    if subtype_key in out_bool:
                        out_bool[subtype_key][i] = True

        if bearish_creation:
            source_i = _find_last_opposite_candle(
                df,
                i,
                bullish_ob=False,
                lookback=5,
            )

            if source_i is not None:
                zone_high = float(df.iloc[source_i]["high"])
                zone_low = float(df.iloc[source_i]["low"])
                zone_type, zone_contexts = _order_block_contexts(
                    df, source_i, i, "bearish"
                )

                out_bool["bearish_order_block"][i] = True
                out_bool["bearish_supply_zone"][i] = True

                out_num["bearish_order_block_high"][i] = zone_high
                out_num["bearish_order_block_low"][i] = zone_low
                out_num["bearish_order_block_source_index"][i] = source_i

                out_num["supply_zone_high"][i] = zone_high
                out_num["supply_zone_low"][i] = zone_low

                ob_type_bear[i] = zone_type

                active_bear_obs.append(
                    {
                        "high": zone_high,
                        "low": zone_low,
                        "created": i,
                        "source": source_i,
                        "retested": False,
                        "type": zone_type,
                    }
                )

                for context in zone_contexts:
                    subtype_key = f"bearish_order_block_{context}"
                    if subtype_key in out_bool:
                        out_bool[subtype_key][i] = True

        # ----------------------------------------------------
        # 6) Confluence on retest candle
        # ----------------------------------------------------

        if out_bool["bullish_order_block_retest"][i] and liquidity_low.iloc[i]:
            out_bool["bullish_order_block_liquidity"][i] = True

        if out_bool["bearish_order_block_retest"][i] and liquidity_high.iloc[i]:
            out_bool["bearish_order_block_liquidity"][i] = True

        out_bool["demand_zone_retest"][i] = out_bool[
            "bullish_order_block_retest"
        ][i]
        out_bool["supply_zone_retest"][i] = out_bool[
            "bearish_order_block_retest"
        ][i]

        # ----------------------------------------------------
        # 7) Expose most recent currently valid zones
        # ----------------------------------------------------

        if active_bull_obs:
            zone = active_bull_obs[-1]
            out_bool["bullish_order_block_active"][i] = True
            out_num["active_bullish_order_block_high"][i] = zone["high"]
            out_num["active_bullish_order_block_low"][i] = zone["low"]

        if active_bear_obs:
            zone = active_bear_obs[-1]
            out_bool["bearish_order_block_active"][i] = True
            out_num["active_bearish_order_block_high"][i] = zone["high"]
            out_num["active_bearish_order_block_low"][i] = zone["low"]

        if active_bear_breakers:
            zone = active_bear_breakers[-1]
            out_bool["bearish_breaker_active"][i] = True
            out_num["active_bearish_breaker_high"][i] = zone["high"]
            out_num["active_bearish_breaker_low"][i] = zone["low"]

        if active_bull_breakers:
            zone = active_bull_breakers[-1]
            out_bool["bullish_breaker_active"][i] = True
            out_num["active_bullish_breaker_high"][i] = zone["high"]
            out_num["active_bullish_breaker_low"][i] = zone["low"]

    # ========================================================
    # ASSIGN STATE ARRAYS
    # ========================================================

    for name, values in out_bool.items():
        df[name] = values

    for name, values in out_num.items():
        df[name] = values

    df["bullish_order_block_type"] = ob_type_bull
    df["bearish_order_block_type"] = ob_type_bear

    # Demand/supply active boundaries mirror active order blocks for
    # compatibility while preserving the stricter OB definition.
    df["active_demand_zone_high"] = df[
        "active_bullish_order_block_high"
    ]
    df["active_demand_zone_low"] = df[
        "active_bullish_order_block_low"
    ]
    df["active_supply_zone_high"] = df[
        "active_bearish_order_block_high"
    ]
    df["active_supply_zone_low"] = df[
        "active_bearish_order_block_low"
    ]

    # ========================================================
    # FIBONACCI CONFLUENCE
    # ========================================================

    fib_bullish = _bool_series(df, "fib_bullish")
    fib_bearish = _bool_series(df, "fib_bearish")

    near_fib_382 = _bool_series(df, "near_fib_382")
    near_fib_500 = _bool_series(df, "near_fib_500")
    near_fib_618 = _bool_series(df, "near_fib_618")

    fib_near = near_fib_382 | near_fib_500 | near_fib_618

    df["bullish_ob_fib_confluence"] = (
        df["bullish_order_block_retest"]
        & fib_bullish
        & fib_near
    )

    df["bearish_ob_fib_confluence"] = (
        df["bearish_order_block_retest"]
        & fib_bearish
        & fib_near
    )

    df["bullish_demand_liquidity"] = (
        df["demand_zone_retest"]
        & liquidity_low
    )

    df["bearish_supply_liquidity"] = (
        df["supply_zone_retest"]
        & liquidity_high
    )

    # ========================================================
    # MASTER FLAGS / COUNTS
    # ========================================================

    df["bullish_institutional_setup"] = (
        df["bullish_order_block"]
        | df["bullish_breaker_block"]
        | df["bullish_displacement"]
    )

    df["bearish_institutional_setup"] = (
        df["bearish_order_block"]
        | df["bearish_breaker_block"]
        | df["bearish_displacement"]
    )

    bullish_components = [
        df["bullish_order_block"],
        df["bullish_breaker_block"],
        df["bullish_displacement"],
    ]

    bearish_components = [
        df["bearish_order_block"],
        df["bearish_breaker_block"],
        df["bearish_displacement"],
    ]

    df["bullish_institutional_count"] = pd.concat(
        bullish_components,
        axis=1,
    ).sum(axis=1)

    df["bearish_institutional_count"] = pd.concat(
        bearish_components,
        axis=1,
    ).sum(axis=1)

    bullish_confluence_components = [
        df["bullish_order_block_retest"],
        df["bullish_order_block_liquidity"],
        df["bullish_ob_fib_confluence"],
        df["bullish_demand_liquidity"],
        df["bullish_breaker_retest"],
        df["bullish_displacement_bos"],
    ]

    bearish_confluence_components = [
        df["bearish_order_block_retest"],
        df["bearish_order_block_liquidity"],
        df["bearish_ob_fib_confluence"],
        df["bearish_supply_liquidity"],
        df["bearish_breaker_retest"],
        df["bearish_displacement_bos"],
    ]

    df["bullish_institutional_confluence_count"] = pd.concat(
        bullish_confluence_components,
        axis=1,
    ).sum(axis=1)

    df["bearish_institutional_confluence_count"] = pd.concat(
        bearish_confluence_components,
        axis=1,
    ).sum(axis=1)

    df = df.replace([np.inf, -np.inf], np.nan)

    return df


if __name__ == "__main__":
    print("=" * 70)
    print("INSTITUTIONAL FEATURE MODULE")
    print("=" * 70)
    print("Version:", INSTITUTIONAL_FEATURE_VERSION)
