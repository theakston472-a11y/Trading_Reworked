"""Deterministic checks for the public-SMC-guide feature expansion."""

from __future__ import annotations

import warnings
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quant.smc_guide_features import (
    _confirmed_pivots,
    _gap_state,
    _higher_timeframe,
    _implied_fvg_state,
    add_smc_guide_features,
)


def _base_frame(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(timestamps)
    wave = np.sin(np.arange(n) / 5.0) * 0.001
    close = 1.10 + wave
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "atr14": 0.001,
            "fib_swing_high": 1.11,
            "fib_swing_low": 1.09,
            "structural_trend": np.where(np.arange(n) % 2, "bullish", "bearish"),
        }
    )
    for name in (
        "bullish_fvg", "bearish_fvg", "bullish_bos", "bearish_bos",
        "bullish_choch", "bearish_choch", "liquidity_sweep_high",
        "liquidity_sweep_low", "bullish_displacement", "bearish_displacement",
        "bullish_order_block", "bearish_order_block",
        "bullish_order_block_retest", "bearish_order_block_retest",
        "bullish_breaker_retest", "bearish_breaker_retest",
        "bullish_fvg_retest", "bearish_fvg_retest",
    ):
        frame[name] = False
    for name in (
        "bullish_fvg_low", "bullish_fvg_high",
        "bearish_fvg_low", "bearish_fvg_high",
    ):
        frame[name] = np.nan
    return frame


def verify_pivot_confirmation() -> None:
    frame = pd.DataFrame(
        {
            "high": [1, 2, 3, 6, 3, 2, 1],
            "low": [0, 0, 0, 0, 0, 0, 0],
        }
    )
    pivots = _confirmed_pivots(frame, radius=2)
    assert not pivots["high_event"][3], "swing high leaked onto its source candle"
    assert pivots["high_event"][5], "swing high was not delayed until confirmation"
    assert pivots["high_source"][5] == 3


def verify_inverse_gap_sequence() -> None:
    frame = pd.DataFrame(
        {
            "open": [0.8, 0.9, 1.25, 1.05, 1.02],
            "high": [1.0, 1.0, 1.4, 1.10, 1.10],
            "low": [0.5, 0.7, 1.2, 0.85, 0.95],
            "close": [0.8, 0.9, 1.3, 0.90, 1.02],
            "bullish_fvg": [False, False, True, False, False],
            "bearish_fvg": [False] * 5,
            "bullish_fvg_low": [np.nan, np.nan, 1.0, np.nan, np.nan],
            "bullish_fvg_high": [np.nan, np.nan, 1.2, np.nan, np.nan],
            "bearish_fvg_low": [np.nan] * 5,
            "bearish_fvg_high": [np.nan] * 5,
        }
    )
    state = _gap_state(frame)
    assert not state["bearish_inverse_fvg"][:3].any()
    assert state["bearish_inverse_fvg"][3], "failed FVG did not become inverse FVG"
    assert state["bearish_inverse_fvg_retest"][4], "inverse FVG retest was not detected"


def verify_wick_implied_gaps() -> None:
    frame = pd.DataFrame(
        {
            "open": [1.0, 1.0],
            "high": [2.0, 2.0],
            "low": [0.0, 0.0],
            "close": [1.8, 0.2],
            "atr14": [1.0, 1.0],
            "bullish_fvg": [False, False],
            "bearish_fvg": [False, False],
        }
    )
    state = _implied_fvg_state(frame)
    assert bool(state["bullish_implied_fvg"].iloc[0])
    assert bool(state["bearish_implied_fvg"].iloc[1])
    assert state["bullish_implied_fvg_low"][0] == 0.0
    assert state["bearish_implied_fvg_high"][1] == 2.0


def verify_closed_higher_timeframe_only() -> None:
    timestamps = pd.date_range("2026-01-05 00:00", periods=5, freq="15min", tz="UTC")
    frame = _base_frame(timestamps)
    h1 = _higher_timeframe(frame, "1h", "h1")
    assert h1.loc[:3, "h1_bullish_trend"].isna().all(), "open H1 candle leaked into M15 rows"
    assert pd.notna(h1.loc[4, "h1_bullish_trend"]), "closed H1 candle was not exposed at 01:00"


def verify_integration_and_prefix_stability() -> None:
    timestamps = pd.date_range("2026-01-05 00:00", periods=192, freq="15min", tz="UTC")
    source = _base_frame(timestamps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)
        full = add_smc_guide_features(source)
        prefix = add_smc_guide_features(source.iloc[:144].copy())

    first_rows = full.groupby(full["timestamp"].dt.date).head(1).index
    assert full.loc[first_rows, "current_day_high"].isna().all()
    assert full.loc[first_rows, "current_day_low"].isna().all()

    stable_columns = [
        "swing_bullish_bos", "bullish_inverse_fvg", "bullish_implied_fvg",
        "bullish_bpr", "bullish_ote", "previous_week_high", "h1_bullish_trend",
        "new_york_silver_bullet_window",
    ]
    for column in stable_columns:
        pd.testing.assert_series_equal(
            prefix[column].reset_index(drop=True),
            full.loc[: len(prefix) - 1, column].reset_index(drop=True),
            check_names=False,
        )

    expected = {
        "bullish_bpr_retest", "bearish_bpr_retest",
        "h1_bullish_implied_fvg", "h1_bearish_implied_fvg",
        "h4_bullish_inverse_fvg", "h4_bearish_inverse_fvg",
        "previous_day_open", "previous_day_close",
        "previous_week_open", "previous_week_close",
        "previous_month_open", "previous_month_close",
        "bullish_silver_bullet_setup", "bearish_silver_bullet_setup",
    }
    missing = expected.difference(full.columns)
    assert not missing, f"missing expanded features: {sorted(missing)}"


def main() -> None:
    verify_pivot_confirmation()
    verify_inverse_gap_sequence()
    verify_wick_implied_gaps()
    verify_closed_higher_timeframe_only()
    verify_integration_and_prefix_stability()
    print("SMC guide feature verification: PASS")


if __name__ == "__main__":
    main()
