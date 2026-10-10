"""Independent, look-ahead-safe features inspired by public SMC concepts.

The referenced MQL5 guide documents concepts, not the proprietary source code
or exact algorithms of its commercial indicator.  The definitions below are
therefore explicit project-native implementations that can be tested and
versioned.  Existing feature names and behaviour are left untouched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


SMC_GUIDE_FEATURE_VERSION = "2026-10-10-v10-smc-guide-expansion"


def _bool(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df:
        return pd.Series(False, index=df.index, dtype=bool)
    series = df[name]
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "on"})


def _overlap(low: float, high: float, zone_low: float, zone_high: float) -> bool:
    return low <= zone_high and high >= zone_low


def _implied_fvg_state(df: pd.DataFrame) -> dict[str, pd.Series | np.ndarray]:
    """Detect wick-rejection imbalances using only the just-closed candle."""
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    body_low = df[["open", "close"]].min(axis=1)
    body_high = df[["open", "close"]].max(axis=1)
    lower_wick_ratio = (body_low - df["low"]) / candle_range
    upper_wick_ratio = (df["high"] - body_high) / candle_range
    close_location = (df["close"] - df["low"]) / candle_range
    atr = df.get("atr14")
    if atr is None:
        previous_close = df["close"].shift(1)
        true_range = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - previous_close).abs(),
                (df["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(14, min_periods=1).mean()
    meaningful_range = candle_range >= pd.Series(atr, index=df.index).fillna(candle_range) * 0.75
    bullish = (
        ~_bool(df, "bullish_fvg")
        & meaningful_range
        & (lower_wick_ratio >= 0.35)
        & (close_location >= 0.65)
    ).fillna(False)
    bearish = (
        ~_bool(df, "bearish_fvg")
        & meaningful_range
        & (upper_wick_ratio >= 0.35)
        & (close_location <= 0.35)
    ).fillna(False)
    return {
        "bullish_implied_fvg": bullish,
        "bearish_implied_fvg": bearish,
        "bullish_implied_fvg_low": np.where(bullish, df["low"], np.nan),
        "bullish_implied_fvg_high": np.where(bullish, body_low, np.nan),
        "bearish_implied_fvg_low": np.where(bearish, body_high, np.nan),
        "bearish_implied_fvg_high": np.where(bearish, df["high"], np.nan),
    }


def _confirmed_pivots(df: pd.DataFrame, radius: int = 5) -> dict[str, np.ndarray]:
    """Return pivots only on the candle where the right-side bars have closed."""
    n = len(df)
    high_event = np.zeros(n, dtype=bool)
    low_event = np.zeros(n, dtype=bool)
    high_price = np.full(n, np.nan)
    low_price = np.full(n, np.nan)
    high_source = np.full(n, np.nan)
    low_source = np.full(n, np.nan)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    for pivot in range(radius, n - radius):
        confirmation = pivot + radius
        high_window = highs[pivot - radius : pivot + radius + 1]
        low_window = lows[pivot - radius : pivot + radius + 1]
        if highs[pivot] == np.max(high_window) and int(np.sum(high_window == highs[pivot])) == 1:
            high_event[confirmation] = True
            high_price[confirmation] = highs[pivot]
            high_source[confirmation] = pivot
        if lows[pivot] == np.min(low_window) and int(np.sum(low_window == lows[pivot])) == 1:
            low_event[confirmation] = True
            low_price[confirmation] = lows[pivot]
            low_source[confirmation] = pivot
    return {
        "high_event": high_event,
        "low_event": low_event,
        "high_price": high_price,
        "low_price": low_price,
        "high_source": high_source,
        "low_source": low_source,
    }


def _structure_from_pivots(df: pd.DataFrame, pivots: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    n = len(df)
    bull_bos = np.zeros(n, dtype=bool)
    bear_bos = np.zeros(n, dtype=bool)
    bull_choch = np.zeros(n, dtype=bool)
    bear_choch = np.zeros(n, dtype=bool)
    trend = np.full(n, "neutral", dtype=object)
    closes = df["close"].to_numpy(dtype=float)
    last_high = np.nan
    last_low = np.nan
    high_broken = False
    low_broken = False
    state = "neutral"
    for i in range(n):
        if pivots["high_event"][i]:
            last_high = pivots["high_price"][i]
            high_broken = False
        if pivots["low_event"][i]:
            last_low = pivots["low_price"][i]
            low_broken = False
        if np.isfinite(last_high) and not high_broken and closes[i] > last_high:
            if state == "bearish":
                bull_choch[i] = True
            else:
                bull_bos[i] = True
            state = "bullish"
            high_broken = True
        if np.isfinite(last_low) and not low_broken and closes[i] < last_low:
            if state == "bullish":
                bear_choch[i] = True
            else:
                bear_bos[i] = True
            state = "bearish"
            low_broken = True
        trend[i] = state
    return {
        "bullish_bos": bull_bos,
        "bearish_bos": bear_bos,
        "bullish_choch": bull_choch,
        "bearish_choch": bear_choch,
        "trend": trend,
    }


def _gap_state(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Track FVG invalidations, inverse FVGs and overlapping BPR zones."""
    n = len(df)
    names = [
        "bullish_inverse_fvg", "bearish_inverse_fvg",
        "bullish_inverse_fvg_retest", "bearish_inverse_fvg_retest",
        "bullish_bpr", "bearish_bpr", "balanced_price_range",
    ]
    out = {name: np.zeros(n, dtype=bool) for name in names}
    numeric = [
        "bullish_inverse_fvg_low", "bullish_inverse_fvg_high",
        "bearish_inverse_fvg_low", "bearish_inverse_fvg_high",
        "bpr_low", "bpr_high", "active_bullish_fvg_low_v10",
        "active_bullish_fvg_high_v10", "active_bearish_fvg_low_v10",
        "active_bearish_fvg_high_v10",
    ]
    out.update({name: np.full(n, np.nan) for name in numeric})
    bull_gaps: list[dict] = []
    bear_gaps: list[dict] = []
    bull_inverse: list[dict] = []
    bear_inverse: list[dict] = []
    for i in range(n):
        low = float(df.loc[i, "low"])
        high = float(df.loc[i, "high"])
        close = float(df.loc[i, "close"])

        kept = []
        for zone in bull_gaps:
            if i - zone["created"] > 500:
                continue
            if close < zone["low"]:
                out["bearish_inverse_fvg"][i] = True
                out["bearish_inverse_fvg_low"][i] = zone["low"]
                out["bearish_inverse_fvg_high"][i] = zone["high"]
                bear_inverse.append({**zone, "created": i, "retested": False})
            else:
                kept.append(zone)
        bull_gaps = kept

        kept = []
        for zone in bear_gaps:
            if i - zone["created"] > 500:
                continue
            if close > zone["high"]:
                out["bullish_inverse_fvg"][i] = True
                out["bullish_inverse_fvg_low"][i] = zone["low"]
                out["bullish_inverse_fvg_high"][i] = zone["high"]
                bull_inverse.append({**zone, "created": i, "retested": False})
            else:
                kept.append(zone)
        bear_gaps = kept

        kept = []
        for zone in bull_inverse:
            if i - zone["created"] > 250 or close < zone["low"]:
                continue
            if i > zone["created"] and not zone["retested"] and _overlap(low, high, zone["low"], zone["high"]):
                out["bullish_inverse_fvg_retest"][i] = True
                zone["retested"] = True
            kept.append(zone)
        bull_inverse = kept

        kept = []
        for zone in bear_inverse:
            if i - zone["created"] > 250 or close > zone["high"]:
                continue
            if i > zone["created"] and not zone["retested"] and _overlap(low, high, zone["low"], zone["high"]):
                out["bearish_inverse_fvg_retest"][i] = True
                zone["retested"] = True
            kept.append(zone)
        bear_inverse = kept

        if bool(df.loc[i, "bullish_fvg"]):
            zone = {"low": float(df.loc[i, "bullish_fvg_low"]), "high": float(df.loc[i, "bullish_fvg_high"]), "created": i}
            overlaps = [z for z in bear_gaps if _overlap(zone["low"], zone["high"], z["low"], z["high"])]
            if overlaps:
                other = overlaps[-1]
                out["bullish_bpr"][i] = out["balanced_price_range"][i] = True
                out["bpr_low"][i] = max(zone["low"], other["low"])
                out["bpr_high"][i] = min(zone["high"], other["high"])
            bull_gaps.append(zone)

        if bool(df.loc[i, "bearish_fvg"]):
            zone = {"low": float(df.loc[i, "bearish_fvg_low"]), "high": float(df.loc[i, "bearish_fvg_high"]), "created": i}
            overlaps = [z for z in bull_gaps if _overlap(zone["low"], zone["high"], z["low"], z["high"])]
            if overlaps:
                other = overlaps[-1]
                out["bearish_bpr"][i] = out["balanced_price_range"][i] = True
                out["bpr_low"][i] = max(zone["low"], other["low"])
                out["bpr_high"][i] = min(zone["high"], other["high"])
            bear_gaps.append(zone)

        if bull_gaps:
            out["active_bullish_fvg_low_v10"][i] = bull_gaps[-1]["low"]
            out["active_bullish_fvg_high_v10"][i] = bull_gaps[-1]["high"]
        if bear_gaps:
            out["active_bearish_fvg_low_v10"][i] = bear_gaps[-1]["low"]
            out["active_bearish_fvg_high_v10"][i] = bear_gaps[-1]["high"]
    return out


def _zone_retests(df: pd.DataFrame, event: pd.Series, lows: pd.Series, highs: pd.Series, prefix: str) -> dict[str, np.ndarray]:
    n = len(df)
    retest = np.zeros(n, dtype=bool)
    filled = np.zeros(n, dtype=bool)
    active_low = np.full(n, np.nan)
    active_high = np.full(n, np.nan)
    zones: list[dict] = []
    bullish = prefix.startswith("bullish")
    for i in range(n):
        bar_low = float(df.loc[i, "low"])
        bar_high = float(df.loc[i, "high"])
        kept = []
        for zone in zones:
            if i - zone["created"] > 250:
                continue
            if i > zone["created"] and not zone["retested"] and _overlap(bar_low, bar_high, zone["low"], zone["high"]):
                retest[i] = True
                zone["retested"] = True
            fully_filled = bar_low <= zone["low"] if bullish else bar_high >= zone["high"]
            if i > zone["created"] and fully_filled:
                filled[i] = True
                continue
            kept.append(zone)
        zones = kept
        if bool(event.iloc[i]) and np.isfinite(lows.iloc[i]) and np.isfinite(highs.iloc[i]):
            zones.append({"low": float(lows.iloc[i]), "high": float(highs.iloc[i]), "created": i, "retested": False})
        if zones:
            active_low[i] = zones[-1]["low"]
            active_high[i] = zones[-1]["high"]
    return {
        f"{prefix}_retest": retest,
        f"{prefix}_filled": filled,
        f"active_{prefix}_low": active_low,
        f"active_{prefix}_high": active_high,
    }


def _swing_order_blocks(df: pd.DataFrame) -> dict[str, np.ndarray]:
    n = len(df)
    fields = [
        "bullish_swing_order_block", "bearish_swing_order_block",
        "bullish_swing_order_block_retest", "bearish_swing_order_block_retest",
        "bullish_swing_breaker", "bearish_swing_breaker",
        "bullish_swing_breaker_retest", "bearish_swing_breaker_retest",
    ]
    out = {name: np.zeros(n, dtype=bool) for name in fields}
    for name in [
        "bullish_swing_order_block_low", "bullish_swing_order_block_high",
        "bearish_swing_order_block_low", "bearish_swing_order_block_high",
    ]:
        out[name] = np.full(n, np.nan)
    bull_zones: list[dict] = []
    bear_zones: list[dict] = []
    bull_breakers: list[dict] = []
    bear_breakers: list[dict] = []
    bull_break = _bool(df, "swing_bullish_bos") | _bool(df, "swing_bullish_choch")
    bear_break = _bool(df, "swing_bearish_bos") | _bool(df, "swing_bearish_choch")
    bull_displacement = _bool(df, "bullish_displacement")
    bear_displacement = _bool(df, "bearish_displacement")

    def source_before(i: int, bullish: bool) -> int | None:
        for j in range(i - 1, max(-1, i - 7), -1):
            if bullish and float(df.loc[j, "close"]) < float(df.loc[j, "open"]):
                return j
            if not bullish and float(df.loc[j, "close"]) > float(df.loc[j, "open"]):
                return j
        return None

    for i in range(n):
        low, high, close = float(df.loc[i, "low"]), float(df.loc[i, "high"]), float(df.loc[i, "close"])
        kept = []
        for z in bull_zones:
            if close < z["low"]:
                out["bearish_swing_breaker"][i] = True
                bear_breakers.append({**z, "created": i, "retested": False})
            else:
                if i > z["created"] and not z["retested"] and _overlap(low, high, z["low"], z["high"]):
                    out["bullish_swing_order_block_retest"][i] = True
                    z["retested"] = True
                kept.append(z)
        bull_zones = kept
        kept = []
        for z in bear_zones:
            if close > z["high"]:
                out["bullish_swing_breaker"][i] = True
                bull_breakers.append({**z, "created": i, "retested": False})
            else:
                if i > z["created"] and not z["retested"] and _overlap(low, high, z["low"], z["high"]):
                    out["bearish_swing_order_block_retest"][i] = True
                    z["retested"] = True
                kept.append(z)
        bear_zones = kept
        kept = []
        for z in bull_breakers:
            if close < z["low"]:
                continue
            if i > z["created"] and not z["retested"] and _overlap(low, high, z["low"], z["high"]):
                out["bullish_swing_breaker_retest"][i] = True
                z["retested"] = True
            kept.append(z)
        bull_breakers = kept
        kept = []
        for z in bear_breakers:
            if close > z["high"]:
                continue
            if i > z["created"] and not z["retested"] and _overlap(low, high, z["low"], z["high"]):
                out["bearish_swing_breaker_retest"][i] = True
                z["retested"] = True
            kept.append(z)
        bear_breakers = kept
        if bull_break.iloc[i] and bull_displacement.iloc[i]:
            source = source_before(i, True)
            if source is not None:
                zone = {"low": float(df.loc[source, "low"]), "high": float(df.loc[source, "high"]), "created": i, "retested": False}
                bull_zones.append(zone)
                out["bullish_swing_order_block"][i] = True
                out["bullish_swing_order_block_low"][i], out["bullish_swing_order_block_high"][i] = zone["low"], zone["high"]
        if bear_break.iloc[i] and bear_displacement.iloc[i]:
            source = source_before(i, False)
            if source is not None:
                zone = {"low": float(df.loc[source, "low"]), "high": float(df.loc[source, "high"]), "created": i, "retested": False}
                bear_zones.append(zone)
                out["bearish_swing_order_block"][i] = True
                out["bearish_swing_order_block_low"][i], out["bearish_swing_order_block_high"][i] = zone["low"], zone["high"]
    return out


def _higher_timeframe(df: pd.DataFrame, rule: str, prefix: str) -> pd.DataFrame:
    indexed = df.set_index("timestamp")[["open", "high", "low", "close"]]
    bars = indexed.resample(rule, label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna().reset_index()
    bars["ema20"] = bars["close"].ewm(span=20, adjust=False).mean()
    bars["ema50"] = bars["close"].ewm(span=50, adjust=False).mean()
    bars["bullish_trend"] = (bars["close"] > bars["ema20"]) & (bars["ema20"] > bars["ema50"])
    bars["bearish_trend"] = (bars["close"] < bars["ema20"]) & (bars["ema20"] < bars["ema50"])
    bars["bullish_fvg"] = bars["low"] > bars["high"].shift(2)
    bars["bearish_fvg"] = bars["high"] < bars["low"].shift(2)
    bars["bullish_fvg_low"] = np.where(bars["bullish_fvg"], bars["high"].shift(2), np.nan)
    bars["bullish_fvg_high"] = np.where(bars["bullish_fvg"], bars["low"], np.nan)
    bars["bearish_fvg_low"] = np.where(bars["bearish_fvg"], bars["high"], np.nan)
    bars["bearish_fvg_high"] = np.where(bars["bearish_fvg"], bars["low"].shift(2), np.nan)
    for name, values in _implied_fvg_state(bars).items():
        bars[name] = values
    gaps = _gap_state(bars)
    for name, values in gaps.items():
        bars[name] = values
    keep = [
        "timestamp", "bullish_trend", "bearish_trend", "bullish_fvg", "bearish_fvg",
        "bullish_implied_fvg", "bearish_implied_fvg",
        "bullish_inverse_fvg", "bearish_inverse_fvg", "bullish_bpr", "bearish_bpr",
        "active_bullish_fvg_low_v10", "active_bullish_fvg_high_v10",
        "active_bearish_fvg_low_v10", "active_bearish_fvg_high_v10",
    ]
    bars = bars[keep].rename(columns={name: f"{prefix}_{name}" for name in keep if name != "timestamp"})
    return pd.merge_asof(
        df[["timestamp"]].sort_values("timestamp"),
        bars.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    ).drop(columns="timestamp")


def add_smc_guide_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    required = {"timestamp", "open", "high", "low", "close", "atr14", "bullish_fvg", "bearish_fvg"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError("Missing SMC guide inputs: " + ", ".join(missing))

    # Internal/swing market structure and strong/weak liquidity.
    df["internal_bullish_bos"] = _bool(df, "bullish_bos")
    df["internal_bearish_bos"] = _bool(df, "bearish_bos")
    df["internal_bullish_choch"] = _bool(df, "bullish_choch")
    df["internal_bearish_choch"] = _bool(df, "bearish_choch")
    df["internal_trend"] = df.get("structural_trend", "neutral")
    pivots = _confirmed_pivots(df, radius=5)
    structure = _structure_from_pivots(df, pivots)
    df["swing_high_v10"], df["swing_low_v10"] = pivots["high_event"], pivots["low_event"]
    df["swing_high_price_v10"], df["swing_low_price_v10"] = pivots["high_price"], pivots["low_price"]
    df["swing_high_source_index_v10"], df["swing_low_source_index_v10"] = pivots["high_source"], pivots["low_source"]
    for name, values in structure.items():
        df[f"swing_{name}"] = values
    df["internal_swing_bullish_alignment"] = (df["internal_trend"] == "bullish") & (df["swing_trend"] == "bullish")
    df["internal_swing_bearish_alignment"] = (df["internal_trend"] == "bearish") & (df["swing_trend"] == "bearish")
    df["weak_high"] = df["swing_high_v10"] & (df["swing_trend"] == "bullish")
    df["strong_high"] = df["swing_high_v10"] & (df["swing_trend"] == "bearish")
    df["strong_low"] = df["swing_low_v10"] & (df["swing_trend"] == "bullish")
    df["weak_low"] = df["swing_low_v10"] & (df["swing_trend"] == "bearish")
    df["buy_side_liquidity_level"] = pd.Series(pivots["high_price"]).ffill().shift(1)
    df["sell_side_liquidity_level"] = pd.Series(pivots["low_price"]).ffill().shift(1)
    tolerance = df["atr14"].fillna(0) * 0.15
    df["near_buy_side_liquidity"] = (df["high"] - df["buy_side_liquidity_level"]).abs() <= tolerance
    df["near_sell_side_liquidity"] = (df["low"] - df["sell_side_liquidity_level"]).abs() <= tolerance
    df["buy_side_liquidity_sweep"] = _bool(df, "liquidity_sweep_high")
    df["sell_side_liquidity_sweep"] = _bool(df, "liquidity_sweep_low")

    # Explicit internal aliases plus separately confirmed swing OBs/breakers.
    for side in ("bullish", "bearish"):
        df[f"{side}_internal_order_block"] = _bool(df, f"{side}_order_block")
        df[f"{side}_internal_order_block_retest"] = _bool(df, f"{side}_order_block_retest")
        df[f"{side}_internal_breaker_retest"] = _bool(df, f"{side}_breaker_retest")
    for name, values in _swing_order_blocks(df).items():
        df[name] = values

    # Inverse FVGs and balanced price ranges.
    for name, values in _gap_state(df).items():
        df[name] = values
    for name, values in _zone_retests(
        df, df["bullish_bpr"], df["bpr_low"], df["bpr_high"], "bullish_bpr"
    ).items():
        df[name] = values
    for name, values in _zone_retests(
        df, df["bearish_bpr"], df["bpr_low"], df["bpr_high"], "bearish_bpr"
    ).items():
        df[name] = values

    # Implied FVG: an imbalance inferred from a large rejection wick rather
    # than a classic three-candle gap.  The wick itself is the active zone.
    for name, values in _implied_fvg_state(df).items():
        df[name] = values
    for name, values in _zone_retests(
        df, df["bullish_implied_fvg"], df["bullish_implied_fvg_low"], df["bullish_implied_fvg_high"], "bullish_implied_fvg"
    ).items():
        df[name] = values
    for name, values in _zone_retests(
        df, df["bearish_implied_fvg"], df["bearish_implied_fvg_low"], df["bearish_implied_fvg_high"], "bearish_implied_fvg"
    ).items():
        df[name] = values

    # Liquidity voids: sustained displacement with little candle overlap.
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    body_ratio = (df["close"] - df["open"]).abs() / candle_range
    bull = (df["close"] > df["open"]) & (body_ratio >= 0.60)
    bear = (df["close"] < df["open"]) & (body_ratio >= 0.60)
    bull_overlap = (df["high"].shift(1) - df["low"]).clip(lower=0) / candle_range
    bear_overlap = (df["high"] - df["low"].shift(1)).clip(lower=0) / candle_range
    three_bar_move = (df["close"] - df["open"].shift(2)).abs()
    df["bullish_liquidity_void"] = bull & bull.shift(1).fillna(False) & bull.shift(2).fillna(False) & (bull_overlap <= 0.35) & (three_bar_move >= df["atr14"] * 2)
    df["bearish_liquidity_void"] = bear & bear.shift(1).fillna(False) & bear.shift(2).fillna(False) & (bear_overlap <= 0.35) & (three_bar_move >= df["atr14"] * 2)
    recent_bull_break = (_bool(df, "bullish_bos") | _bool(df, "bullish_choch")).rolling(3, min_periods=1).max().astype(bool)
    recent_bear_break = (_bool(df, "bearish_bos") | _bool(df, "bearish_choch")).rolling(3, min_periods=1).max().astype(bool)
    df["bullish_liquidity_void_bms"] = df["bullish_liquidity_void"] & recent_bull_break
    df["bearish_liquidity_void_bms"] = df["bearish_liquidity_void"] & recent_bear_break

    # Opening gaps and first mitigation/fill.
    gap_threshold = df["atr14"].shift(1).fillna(0) * 0.15
    time_gap = df["timestamp"].diff() > pd.Timedelta(minutes=30)
    day_change = df["timestamp"].dt.date != df["timestamp"].shift(1).dt.date
    eligible_open = time_gap | day_change
    gap = df["open"] - df["close"].shift(1)
    df["bullish_opening_gap"] = eligible_open & (gap > gap_threshold)
    df["bearish_opening_gap"] = eligible_open & (-gap > gap_threshold)
    df["bullish_opening_gap_low"] = np.where(df["bullish_opening_gap"], df["close"].shift(1), np.nan)
    df["bullish_opening_gap_high"] = np.where(df["bullish_opening_gap"], df["open"], np.nan)
    df["bearish_opening_gap_low"] = np.where(df["bearish_opening_gap"], df["open"], np.nan)
    df["bearish_opening_gap_high"] = np.where(df["bearish_opening_gap"], df["close"].shift(1), np.nan)
    for name, values in _zone_retests(df, df["bullish_opening_gap"], df["bullish_opening_gap_low"], df["bullish_opening_gap_high"], "bullish_opening_gap").items():
        df[name] = values
    for name, values in _zone_retests(df, df["bearish_opening_gap"], df["bearish_opening_gap_low"], df["bearish_opening_gap_high"], "bearish_opening_gap").items():
        df[name] = values

    # Premium, discount, equilibrium and OTE (62%-79%) of confirmed range.
    range_high = df[["fib_swing_high", "fib_swing_low"]].max(axis=1)
    range_low = df[["fib_swing_high", "fib_swing_low"]].min(axis=1)
    dealing_range = range_high - range_low
    df["dealing_range_high"], df["dealing_range_low"] = range_high, range_low
    df["dealing_range_equilibrium"] = (range_high + range_low) / 2
    df["premium_zone"] = df["close"] > df["dealing_range_equilibrium"]
    df["discount_zone"] = df["close"] < df["dealing_range_equilibrium"]
    df["equilibrium_zone"] = (df["close"] - df["dealing_range_equilibrium"]).abs() <= tolerance
    df["bullish_ote_low"] = range_high - dealing_range * 0.79
    df["bullish_ote_high"] = range_high - dealing_range * 0.62
    df["bullish_ote_mid"] = range_high - dealing_range * 0.705
    df["bearish_ote_low"] = range_low + dealing_range * 0.62
    df["bearish_ote_high"] = range_low + dealing_range * 0.79
    df["bearish_ote_mid"] = range_low + dealing_range * 0.705
    df["bullish_ote"] = (df["internal_trend"] == "bullish") & (df["low"] <= df["bullish_ote_high"]) & (df["high"] >= df["bullish_ote_low"])
    df["bearish_ote"] = (df["internal_trend"] == "bearish") & (df["low"] <= df["bearish_ote_high"]) & (df["high"] >= df["bearish_ote_low"])

    # Current-day and previous day/week/month OHLC, without future leakage.
    day_key = df["timestamp"].dt.date
    daily = df.assign(_key=day_key).groupby("_key").agg(
        _open=("open", "first"), _high=("high", "max"), _low=("low", "min"), _close=("close", "last")
    )
    df["current_day_open"] = df.groupby(day_key)["open"].transform("first")
    df["current_day_high"] = df.groupby(day_key)["high"].transform(lambda values: values.cummax().shift(1))
    df["current_day_low"] = df.groupby(day_key)["low"].transform(lambda values: values.cummin().shift(1))
    df["current_day_close"] = df["close"]
    df["previous_day_open"] = day_key.map(daily["_open"].shift(1))
    df["previous_day_close"] = day_key.map(daily["_close"].shift(1))
    week_key = (df["timestamp"].dt.normalize() - pd.to_timedelta(df["timestamp"].dt.dayofweek, unit="D")).dt.date
    month_key = df["timestamp"].dt.tz_localize(None).dt.to_period("M")
    weekly = df.assign(_key=week_key).groupby("_key").agg(
        _open=("open", "first"), _high=("high", "max"), _low=("low", "min"), _close=("close", "last")
    )
    monthly = df.assign(_key=month_key).groupby("_key").agg(
        _open=("open", "first"), _high=("high", "max"), _low=("low", "min"), _close=("close", "last")
    )
    df["previous_week_open"] = week_key.map(weekly["_open"].shift(1))
    df["previous_week_high"] = week_key.map(weekly["_high"].shift(1))
    df["previous_week_low"] = week_key.map(weekly["_low"].shift(1))
    df["previous_week_close"] = week_key.map(weekly["_close"].shift(1))
    df["previous_month_open"] = month_key.map(monthly["_open"].shift(1))
    df["previous_month_high"] = month_key.map(monthly["_high"].shift(1))
    df["previous_month_low"] = month_key.map(monthly["_low"].shift(1))
    df["previous_month_close"] = month_key.map(monthly["_close"].shift(1))
    df["current_day_high_sweep"] = (df["high"] > df["current_day_high"]) & (df["close"] < df["current_day_high"])
    df["current_day_low_sweep"] = (df["low"] < df["current_day_low"]) & (df["close"] > df["current_day_low"])
    for period in ("week", "month"):
        df[f"previous_{period}_high_sweep"] = (df["high"] > df[f"previous_{period}_high"]) & (df["close"] < df[f"previous_{period}_high"])
        df[f"previous_{period}_low_sweep"] = (df["low"] < df[f"previous_{period}_low"]) & (df["close"] > df[f"previous_{period}_low"])

    # Standard sessions, kill zones, overlap and DST-aware New York Silver Bullet.
    utc_hour = df["timestamp"].dt.hour
    london_time = df["timestamp"].dt.tz_convert("Europe/London")
    new_york_time = df["timestamp"].dt.tz_convert("America/New_York")
    berlin_time = df["timestamp"].dt.tz_convert("Europe/Berlin")
    sydney_time = df["timestamp"].dt.tz_convert("Australia/Sydney")
    df["sydney_session"] = sydney_time.dt.hour.between(8, 16, inclusive="left")
    df["tokyo_session"] = utc_hour.between(0, 8, inclusive="left")
    df["frankfurt_session"] = berlin_time.dt.hour.between(7, 9, inclusive="left")
    df["london_session_v10"] = london_time.dt.hour.between(8, 16, inclusive="left")
    df["new_york_session_v10"] = new_york_time.dt.hour.between(8, 17, inclusive="left")
    df["london_kill_zone"] = london_time.dt.hour.between(7, 10, inclusive="left")
    df["new_york_kill_zone"] = new_york_time.dt.hour.between(8, 11, inclusive="left")
    df["london_new_york_overlap"] = df["london_session_v10"] & df["new_york_session_v10"]
    df["new_york_silver_bullet_window"] = new_york_time.dt.hour.eq(10)

    # Confirmed higher-timeframe trend/FVG/IFVG/BPR state.
    for column, values in _higher_timeframe(df, "1h", "h1").items():
        df[column] = values
    for column, values in _higher_timeframe(df, "4h", "h4").items():
        df[column] = values

    # Directional confluence and complete timed setup candidates.
    bull_imbalance = _bool(df, "bullish_fvg_retest") | df["bullish_inverse_fvg_retest"] | df["bullish_implied_fvg_retest"] | df["bullish_bpr"]
    bear_imbalance = _bool(df, "bearish_fvg_retest") | df["bearish_inverse_fvg_retest"] | df["bearish_implied_fvg_retest"] | df["bearish_bpr"]
    bull_block = df["bullish_internal_order_block_retest"] | df["bullish_swing_order_block_retest"] | df["bullish_swing_breaker_retest"]
    bear_block = df["bearish_internal_order_block_retest"] | df["bearish_swing_order_block_retest"] | df["bearish_swing_breaker_retest"]
    bull_components = pd.concat([
        df["internal_swing_bullish_alignment"], df["sell_side_liquidity_sweep"], bull_imbalance,
        bull_block, df["discount_zone"] | df["bullish_ote"], df["h1_bullish_trend"].fillna(False).astype(bool),
    ], axis=1)
    bear_components = pd.concat([
        df["internal_swing_bearish_alignment"], df["buy_side_liquidity_sweep"], bear_imbalance,
        bear_block, df["premium_zone"] | df["bearish_ote"], df["h1_bearish_trend"].fillna(False).astype(bool),
    ], axis=1)
    df["bullish_smc_confluence_count"] = bull_components.astype(bool).sum(axis=1)
    df["bearish_smc_confluence_count"] = bear_components.astype(bool).sum(axis=1)
    df["bullish_smc_confluence"] = df["bullish_smc_confluence_count"] >= 3
    df["bearish_smc_confluence"] = df["bearish_smc_confluence_count"] >= 3
    recent_sell_sweep = df["sell_side_liquidity_sweep"].rolling(8, min_periods=1).max().astype(bool)
    recent_buy_sweep = df["buy_side_liquidity_sweep"].rolling(8, min_periods=1).max().astype(bool)
    df["bullish_silver_bullet_setup"] = df["new_york_silver_bullet_window"] & recent_sell_sweep & (bull_imbalance | bull_block) & df["bullish_smc_confluence"]
    df["bearish_silver_bullet_setup"] = df["new_york_silver_bullet_window"] & recent_buy_sweep & (bear_imbalance | bear_block) & df["bearish_smc_confluence"]
    df["bullish_kill_zone_setup"] = (df["london_kill_zone"] | df["new_york_kill_zone"]) & df["bullish_smc_confluence"]
    df["bearish_kill_zone_setup"] = (df["london_kill_zone"] | df["new_york_kill_zone"]) & df["bearish_smc_confluence"]

    return df
