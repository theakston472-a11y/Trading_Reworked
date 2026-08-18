from __future__ import annotations

from pathlib import Path
import importlib.util

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FEATURE_FILE = ROOT / "quant" / "feature_database.csv"
LAB_FILE = ROOT / "scripts" / "strategy_lab.py"

EXPECTED_LAB_VERSION = "2026-08-14-v5-smc-sequences"


def as_bool(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)

    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0).astype(bool)

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y", "on"})
    )


def load_lab():
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_verify",
        LAB_FILE,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    print("=" * 70)
    print("TRADING REPAIR VERIFICATION — SMC V5")
    print("=" * 70)

    lab = load_lab()
    lab_version = getattr(lab, "BACKTEST_ENGINE_VERSION", "MISSING")

    print("Strategy Lab engine:", lab_version)

    if lab_version != EXPECTED_LAB_VERSION:
        print("FAIL: strategy_lab.py is not the V5 SMC version.")
        raise SystemExit(1)

    if not FEATURE_FILE.exists():
        print("Feature database is missing:")
        print(FEATURE_FILE)
        print("Build it with: python -m quant.build_features")
        raise SystemExit(2)

    print()
    print("Loading feature database...")
    df = pd.read_csv(FEATURE_FILE)
    print(f"Rows: {len(df):,}")

    required = [
        # Base / corrected swings
        "timestamp", "open", "high", "low", "close", "session", "atr14",
        "swing_high", "swing_low",
        "swing_high_price", "swing_low_price",
        "swing_high_source_index", "swing_low_source_index",
        # Structure
        "bullish_bos", "bearish_bos", "bullish_choch", "bearish_choch",
        "structural_trend",
        "bullish_structure_break_level", "bearish_structure_break_level",
        # Liquidity
        "liquidity_sweep_high", "liquidity_sweep_low",
        "liquidity_sweep_high_level", "liquidity_sweep_low_level",
        "liquidity_sweep_high_wick_ratio", "liquidity_sweep_low_wick_ratio",
        "equal_high_liquidity_sweep", "equal_low_liquidity_sweep",
        # FVG zones
        "bullish_fvg", "bearish_fvg",
        "bullish_fvg_low", "bullish_fvg_high",
        "bearish_fvg_low", "bearish_fvg_high",
        "bullish_fvg_retest", "bearish_fvg_retest",
        "bullish_fvg_displacement", "bearish_fvg_displacement",
        # Ordered SMC sequence
        "bullish_liquidity_structure_shift",
        "bearish_liquidity_structure_shift",
        "bullish_liquidity_fvg_setup",
        "bearish_liquidity_fvg_setup",
        "bullish_smc_reversal_setup",
        "bearish_smc_reversal_setup",
        "bullish_smc_fvg_retest",
        "bearish_smc_fvg_retest",
        "bullish_smc_sweep_index", "bearish_smc_sweep_index",
        "bullish_smc_sweep_level", "bearish_smc_sweep_level",
        "bullish_smc_target_high", "bearish_smc_target_low",
        # Fib
        "fib_swing_high", "fib_swing_low",
        "fib_swing_high_index", "fib_swing_low_index",
        "fib_382", "fib_500", "fib_618", "fib_tolerance",
        # OB / breaker
        "bullish_order_block", "bearish_order_block",
        "bullish_order_block_source_index", "bearish_order_block_source_index",
        "bullish_order_block_retest", "bearish_order_block_retest",
        "bullish_order_block_invalidation", "bearish_order_block_invalidation",
        "bullish_breaker_block", "bearish_breaker_block",
        "bullish_breaker_high", "bullish_breaker_low",
        "bullish_breaker_source_index",
        "bearish_breaker_high", "bearish_breaker_low",
        "bearish_breaker_source_index",
        "bullish_breaker_retest", "bearish_breaker_retest",
        "bullish_order_block_manipulation",
        "bearish_order_block_manipulation",
        "bullish_order_block_pin_bar", "bearish_order_block_pin_bar",
        "bullish_order_block_engulfing", "bearish_order_block_engulfing",
        "bullish_order_block_indecision", "bearish_order_block_indecision",
        "bullish_order_block_marubozu", "bearish_order_block_marubozu",
        "bullish_order_block_star", "bearish_order_block_star",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        print()
        print("Feature DB is not rebuilt with the V5 SMC engine.")
        print("Missing columns:")
        for c in missing:
            print("  -", c)
        print()
        print("Run: python -m quant.build_features")
        raise SystemExit(3)

    numeric = [
        "open", "high", "low", "close", "atr14",
        "swing_high_price", "swing_low_price",
        "swing_high_source_index", "swing_low_source_index",
        "liquidity_sweep_high_level", "liquidity_sweep_low_level",
        "liquidity_sweep_high_wick_ratio", "liquidity_sweep_low_wick_ratio",
        "bullish_fvg_low", "bullish_fvg_high",
        "bearish_fvg_low", "bearish_fvg_high",
        "bullish_order_block_source_index", "bearish_order_block_source_index",
        "bullish_breaker_source_index", "bearish_breaker_source_index",
        "bullish_smc_sweep_index", "bearish_smc_sweep_index",
        "bullish_smc_sweep_level", "bearish_smc_sweep_level",
        "bullish_smc_target_high", "bearish_smc_target_low",
    ]

    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ========================================================
    # TRUE SWING MAPPING
    # ========================================================

    high_bad = 0
    low_bad = 0

    high_rows = df.index[as_bool(df["swing_high"])][:200]
    low_rows = df.index[as_bool(df["swing_low"])][:200]

    for confirmation_i in high_rows:
        source = df.loc[confirmation_i, "swing_high_source_index"]
        price = df.loc[confirmation_i, "swing_high_price"]

        if not np.isfinite(source) or not np.isfinite(price):
            high_bad += 1
            continue

        source_i = int(source)

        if (
            source_i != confirmation_i - 2
            or source_i < 0
            or source_i >= len(df)
            or not np.isclose(price, df.loc[source_i, "high"], rtol=0, atol=1e-12)
        ):
            high_bad += 1

    for confirmation_i in low_rows:
        source = df.loc[confirmation_i, "swing_low_source_index"]
        price = df.loc[confirmation_i, "swing_low_price"]

        if not np.isfinite(source) or not np.isfinite(price):
            low_bad += 1
            continue

        source_i = int(source)

        if (
            source_i != confirmation_i - 2
            or source_i < 0
            or source_i >= len(df)
            or not np.isclose(price, df.loc[source_i, "low"], rtol=0, atol=1e-12)
        ):
            low_bad += 1

    print()
    print(f"Checked swing highs: {len(high_rows)} | bad mappings: {high_bad}")
    print(f"Checked swing lows:  {len(low_rows)} | bad mappings: {low_bad}")

    if high_bad or low_bad:
        print("FAIL: true swing mapping")
        raise SystemExit(4)

    # ========================================================
    # LIQUIDITY SWEEP DEFINITIONS
    # ========================================================

    high_sweeps = df.index[as_bool(df["liquidity_sweep_high"])][:500]
    low_sweeps = df.index[as_bool(df["liquidity_sweep_low"])][:500]

    high_sweep_bad = 0
    low_sweep_bad = 0

    for i in high_sweeps:
        level = df.loc[i, "liquidity_sweep_high_level"]
        wick_ratio = df.loc[i, "liquidity_sweep_high_wick_ratio"]
        if (
            not np.isfinite(level)
            or df.loc[i, "high"] <= level
            or df.loc[i, "close"] >= level
            or wick_ratio < 0.35 - 1e-12
        ):
            high_sweep_bad += 1

    for i in low_sweeps:
        level = df.loc[i, "liquidity_sweep_low_level"]
        wick_ratio = df.loc[i, "liquidity_sweep_low_wick_ratio"]
        if (
            not np.isfinite(level)
            or df.loc[i, "low"] >= level
            or df.loc[i, "close"] <= level
            or wick_ratio < 0.35 - 1e-12
        ):
            low_sweep_bad += 1

    print(
        f"Liquidity high sweeps checked: {len(high_sweeps)} "
        f"| bad: {high_sweep_bad}"
    )
    print(
        f"Liquidity low sweeps checked:  {len(low_sweeps)} "
        f"| bad: {low_sweep_bad}"
    )

    if high_sweep_bad or low_sweep_bad:
        print("FAIL: liquidity sweep definition")
        raise SystemExit(5)

    # ========================================================
    # FVG DEFINITION
    # ========================================================

    bull_fvgs = df.index[as_bool(df["bullish_fvg"])][:500]
    bear_fvgs = df.index[as_bool(df["bearish_fvg"])][:500]

    bull_fvg_bad = 0
    bear_fvg_bad = 0

    for i in bull_fvgs:
        if i < 2:
            bull_fvg_bad += 1
            continue
        expected_low = df.loc[i - 2, "high"]
        expected_high = df.loc[i, "low"]
        if (
            not (expected_high > expected_low)
            or not np.isclose(df.loc[i, "bullish_fvg_low"], expected_low, atol=1e-12)
            or not np.isclose(df.loc[i, "bullish_fvg_high"], expected_high, atol=1e-12)
        ):
            bull_fvg_bad += 1

    for i in bear_fvgs:
        if i < 2:
            bear_fvg_bad += 1
            continue
        expected_low = df.loc[i, "high"]
        expected_high = df.loc[i - 2, "low"]
        if (
            not (expected_high > expected_low)
            or not np.isclose(df.loc[i, "bearish_fvg_low"], expected_low, atol=1e-12)
            or not np.isclose(df.loc[i, "bearish_fvg_high"], expected_high, atol=1e-12)
        ):
            bear_fvg_bad += 1

    print(f"Bullish FVGs checked: {len(bull_fvgs)} | bad: {bull_fvg_bad}")
    print(f"Bearish FVGs checked: {len(bear_fvgs)} | bad: {bear_fvg_bad}")

    if bull_fvg_bad or bear_fvg_bad:
        print("FAIL: FVG definition")
        raise SystemExit(6)

    # ========================================================
    # ORDERED SMC SWEEP -> STRUCTURE -> FVG CHECK
    # ========================================================

    bull_setups = df.index[as_bool(df["bullish_smc_reversal_setup"])][:300]
    bear_setups = df.index[as_bool(df["bearish_smc_reversal_setup"])][:300]

    bull_sequence_bad = 0
    bear_sequence_bad = 0

    for i in bull_setups:
        sweep_i = df.loc[i, "bullish_smc_sweep_index"]
        if not np.isfinite(sweep_i):
            bull_sequence_bad += 1
            continue
        sweep_i = int(sweep_i)
        if (
            sweep_i > i
            or i - sweep_i > 8
            or not bool(as_bool(df.loc[[sweep_i], "liquidity_sweep_low"]).iloc[0])
            or not bool(as_bool(df.loc[[i], "bullish_fvg_displacement"]).iloc[0])
        ):
            bull_sequence_bad += 1
            continue
        break_window = (
            as_bool(df.loc[sweep_i:i, "bullish_bos"])
            | as_bool(df.loc[sweep_i:i, "bullish_choch"])
        )
        if not bool(break_window.any()):
            bull_sequence_bad += 1

    for i in bear_setups:
        sweep_i = df.loc[i, "bearish_smc_sweep_index"]
        if not np.isfinite(sweep_i):
            bear_sequence_bad += 1
            continue
        sweep_i = int(sweep_i)
        if (
            sweep_i > i
            or i - sweep_i > 8
            or not bool(as_bool(df.loc[[sweep_i], "liquidity_sweep_high"]).iloc[0])
            or not bool(as_bool(df.loc[[i], "bearish_fvg_displacement"]).iloc[0])
        ):
            bear_sequence_bad += 1
            continue
        break_window = (
            as_bool(df.loc[sweep_i:i, "bearish_bos"])
            | as_bool(df.loc[sweep_i:i, "bearish_choch"])
        )
        if not bool(break_window.any()):
            bear_sequence_bad += 1

    print(
        f"Bullish sweep/structure/FVG setups checked: {len(bull_setups)} "
        f"| bad: {bull_sequence_bad}"
    )
    print(
        f"Bearish sweep/structure/FVG setups checked: {len(bear_setups)} "
        f"| bad: {bear_sequence_bad}"
    )

    if bull_sequence_bad or bear_sequence_bad:
        print("FAIL: ordered SMC sequence definition")
        raise SystemExit(7)

    # ========================================================
    # ORDER BLOCK SOURCE / STRUCTURE CHECK
    # ========================================================

    bull_obs = df.index[as_bool(df["bullish_order_block"])][:300]
    bear_obs = df.index[as_bool(df["bearish_order_block"])][:300]

    bull_ob_bad = 0
    bear_ob_bad = 0

    for i in bull_obs:
        source = df.loc[i, "bullish_order_block_source_index"]
        if not np.isfinite(source):
            bull_ob_bad += 1
            continue
        source_i = int(source)
        if (
            source_i >= i
            or i - source_i > 5
            or df.loc[source_i, "close"] >= df.loc[source_i, "open"]
            or not bool(
                as_bool(df.loc[[i], "bullish_bos"]).iloc[0]
                or as_bool(df.loc[[i], "bullish_choch"]).iloc[0]
            )
        ):
            bull_ob_bad += 1

    for i in bear_obs:
        source = df.loc[i, "bearish_order_block_source_index"]
        if not np.isfinite(source):
            bear_ob_bad += 1
            continue
        source_i = int(source)
        if (
            source_i >= i
            or i - source_i > 5
            or df.loc[source_i, "close"] <= df.loc[source_i, "open"]
            or not bool(
                as_bool(df.loc[[i], "bearish_bos"]).iloc[0]
                or as_bool(df.loc[[i], "bearish_choch"]).iloc[0]
            )
        ):
            bear_ob_bad += 1

    print(f"Bullish order blocks checked: {len(bull_obs)} | bad: {bull_ob_bad}")
    print(f"Bearish order blocks checked: {len(bear_obs)} | bad: {bear_ob_bad}")

    if bull_ob_bad or bear_ob_bad:
        print("FAIL: order-block source / structure definition")
        raise SystemExit(7)

    # ========================================================
    # SESSION / POSITION INDEX ALIGNMENT
    # ========================================================

    test = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2025-01-01", periods=5, freq="15min", tz="UTC"
            ),
            "open": [1.0] * 5,
            "high": [1.1] * 5,
            "low": [0.9] * 5,
            "close": [1.0] * 5,
            "atr14": [0.1] * 5,
            "session": ["Asia", "London", "New York", "London", "New York"],
            "test_condition": ["False", "False", "False", "False", "True"],
        }
    )

    indices = lab.signal_indices(test, "BUY", "New York", "test_condition")

    if indices.tolist() != [4]:
        print("FAIL: session/index alignment returned", indices.tolist())
        raise SystemExit(8)

    print()
    print("Session/index alignment: PASS")
    print("True swing-price mapping: PASS")
    print("Liquidity sweep definition: PASS")
    print("Fair value gap definition: PASS")
    print("Ordered sweep -> structure -> FVG sequence: PASS")
    print("Order block / breaker framework: PASS")
    print("Feature DB: V5 SMC definitions")
    print()
    print("SMC V5 VERIFICATION PASSED")


if __name__ == "__main__":
    main()
