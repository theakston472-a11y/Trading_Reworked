from __future__ import annotations

import html
import json
import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

FEATURE_FILE = ROOT / "quant" / "feature_database.csv"
TOP_FILE = ROOT / "results" / "strategy_lab_top_final.csv"
DB_FILE = ROOT / "results" / "strategy_lab.sqlite"

OUTPUT_DIR = ROOT / "results" / "visual_validation"
CHART_DIR = OUTPUT_DIR / "charts"

TOP_N = 20

# Number of examples per strategy
WIN_EXAMPLES = 2
LOSS_EXAMPLES = 2

# Candles shown before/after the trade
BARS_BEFORE = 32
BARS_AFTER = 18


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def find_timestamp_index(
    df,
    value,
):
    """
    Locate a stored trade timestamp in the full feature dataframe.
    Stored entry_i/exit_i values are period-relative and must not be
    used directly against the full feature database.
    """

    try:
        timestamp = pd.to_datetime(
            value,
            utc=True,
            errors="coerce",
        )

        if pd.isna(timestamp):
            return None

        differences = (
            df["timestamp"]
            - timestamp
        ).abs()

        if differences.empty:
            return None

        index = int(
            differences.idxmin()
        )

        if differences.loc[
            index
        ] > pd.Timedelta(
            minutes=20
        ):
            return None

        return index

    except Exception:
        return None


def condition_list(condition_string):
    return [
        x.strip()
        for x in str(condition_string).split("+")
        if x.strip()
    ]


# ============================================================
# STRATEGY EXPLANATIONS
# ============================================================

CONDITION_EXPLANATIONS = {
    "bullish_candle":
        "A bullish candle was present.",

    "bearish_candle":
        "A bearish candle was present.",

    "strong_bullish_candle":
        "A strong bullish candle was present.",

    "strong_bearish_candle":
        "A strong bearish candle was present.",

    "bullish_bos":
        "Price had a bullish break of structure (BOS).",

    "bearish_bos":
        "Price had a bearish break of structure (BOS).",

    "bullish_choch":
        "Price showed a bullish change of character (CHOCH).",

    "bearish_choch":
        "Price showed a bearish change of character (CHOCH).",

    "liquidity_sweep_high":
        "Price swept a previous high, indicating a possible liquidity grab.",

    "liquidity_sweep_low":
        "Price swept a previous low, indicating a possible liquidity grab.",

    "equal_high":
        "An equal-high structure was present.",

    "equal_low":
        "An equal-low structure was present.",

    "near_fib_382":
        "Price was near the Fibonacci 38.2% level.",

    "near_fib_500":
        "Price was near the Fibonacci 50.0% level.",

    "near_fib_618":
        "Price was near the Fibonacci 61.8% level.",

    "fib_382_rejection":
        "Price rejected the Fibonacci 38.2% level.",

    "fib_500_rejection":
        "Price rejected the Fibonacci 50.0% level.",

    "fib_618_rejection":
        "Price rejected the Fibonacci 61.8% level.",

    "bullish_fib_382_rejection":
        "Price produced a bullish rejection from Fibonacci 38.2%.",

    "bullish_fib_500_rejection":
        "Price produced a bullish rejection from Fibonacci 50.0%.",

    "bullish_fib_618_rejection":
        "Price produced a bullish rejection from Fibonacci 61.8%.",

    "bearish_fib_382_rejection":
        "Price produced a bearish rejection from Fibonacci 38.2%.",

    "bearish_fib_500_rejection":
        "Price produced a bearish rejection from Fibonacci 50.0%.",

    "bearish_fib_618_rejection":
        "Price produced a bearish rejection from Fibonacci 61.8%.",

    "bullish_engulfing":
        "A bullish engulfing candle was present.",

    "bearish_engulfing":
        "A bearish engulfing candle was present.",

    "bullish_pin_bar":
        "A bullish pin bar was present.",

    "bearish_pin_bar":
        "A bearish pin bar was present.",

    "inside_bar":
        "An inside-bar pattern was present.",

    "outside_bar":
        "An outside-bar pattern was present.",

    "above_ema20":
        "Price was above the 20-period EMA.",

    "above_ema50":
        "Price was above the 50-period EMA.",

    "above_ema100":
        "Price was above the 100-period EMA.",

    "above_ema200":
        "Price was above the 200-period EMA.",

    "ema_bullish_alignment":
        "The EMAs were in bullish alignment.",

    "ema_bearish_alignment":
        "The EMAs were in bearish alignment.",

    "bullish_order_block":
        "A bullish order block was present.",

    "bearish_order_block":
        "A bearish order block was present.",

    "bullish_order_block_retest":
        "Price was retesting a bullish order block.",

    "bearish_order_block_retest":
        "Price was retesting a bearish order block.",

    "bullish_demand_zone":
        "Price was inside a bullish demand zone.",

    "bearish_supply_zone":
        "Price was inside a bearish supply zone.",

    "demand_zone_retest":
        "Price was retesting a demand zone.",

    "supply_zone_retest":
        "Price was retesting a supply zone.",

    "bearish_breaker_block":
        "A bearish breaker-block structure was present.",

    "bullish_breaker_block":
        "A bullish breaker-block structure was present.",

    "bearish_breaker_retest":
        "Price was retesting a bearish breaker block.",

    "bullish_breaker_retest":
        "Price was retesting a bullish breaker block.",

    "bullish_ob_fib_confluence":
        "A bullish order-block and Fibonacci confluence was present.",

    "bearish_ob_fib_confluence":
        "A bearish order-block and Fibonacci confluence was present.",

    "bullish_demand_liquidity":
        "Bullish demand and liquidity conditions aligned.",

    "bearish_supply_liquidity":
        "Bearish supply and liquidity conditions aligned.",

    "bullish_institutional_setup":
        "A bullish institutional-style setup was detected.",

    "bearish_institutional_setup":
        "A bearish institutional-style setup was detected.",
}


def explain_strategy(conditions, direction, session):
    parts = []

    for condition in condition_list(conditions):
        explanation = CONDITION_EXPLANATIONS.get(
            condition,
            condition.replace("_", " ").capitalize() + "."
        )
        parts.append(explanation)

    direction_text = (
        "The strategy looks for BUY opportunities."
        if str(direction).upper() == "BUY"
        else "The strategy looks for SELL opportunities."
    )

    session_text = f"It only looks for setups during the {session} session."

    return [
        direction_text,
        session_text,
        *parts,
    ]


# ============================================================
# LOAD DATA
# ============================================================

def load_feature_data():
    print("Loading feature database...")

    df = pd.read_csv(FEATURE_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "ema20",
        "ema50",
        "ema100",
        "ema200",
        "fib_382",
        "fib_500",
        "fib_618",
        "fib_tolerance",
        "fib_swing_high",
        "fib_swing_low",
        "fib_swing_high_index",
        "fib_swing_low_index",
        "bullish_order_block_high",
        "bullish_order_block_low",
        "bearish_order_block_high",
        "bearish_order_block_low",
        "demand_zone_high",
        "demand_zone_low",
        "supply_zone_high",
        "supply_zone_low",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    print(f"Feature rows: {len(df):,}")

    return df


def load_top_strategies():
    print("Loading Top Final results...")

    df = pd.read_csv(TOP_FILE)

    required = [
        "rank",
        "direction",
        "session",
        "conditions",
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "robust_score",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise SystemExit(
            "Top-final file is missing columns: "
            + ", ".join(missing)
        )

    # Sort using the existing Strategy Lab ranking.
    df = df.sort_values(
        "robust_score",
        ascending=False,
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # REMOVE DUPLICATE STRATEGY FAMILIES
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "direction",
            "session",
            "conditions",
        ],
        keep="first",
    ).reset_index(drop=True)

    df["visual_rank"] = range(1, len(df) + 1)

    df = df.head(TOP_N).copy()

    print(f"Unique strategy families selected: {len(df)}")

    return df


# ============================================================
# DATABASE
# ============================================================

def load_trade_details(strategy):
    con = sqlite3.connect(DB_FILE)

    query = """
        SELECT
            direction,
            session,
            conditions,
            rr,
            period,
            trades,
            result_json
        FROM results
        WHERE period = 'ALL'
          AND direction = ?
          AND session = ?
          AND conditions = ?
        ORDER BY ABS(rr - ?) ASC, created_at DESC
        LIMIT 1
    """

    try:
        row = con.execute(
            query,
            (
                str(strategy["direction"]),
                str(strategy["session"]),
                str(strategy["conditions"]),
                float(strategy["rr"]),
            ),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        con.close()
        raise SystemExit(
            "Could not read the Strategy Lab database.\n"
            f"SQLite error: {exc}"
        )

    con.close()

    if row is None:
        return []

    result_json = row[-1]

    if not result_json:
        return []

    try:
        trades = json.loads(result_json)
    except Exception:
        return []

    if not isinstance(trades, list):
        return []

    return trades


# ============================================================
# CANDLESTICK DRAWING
# ============================================================

def draw_candles(ax, data):
    """TradingView-style monochrome candles on a dark chart."""
    width = 0.66

    for i, candle in data.reset_index(drop=True).iterrows():
        o = safe_float(candle["open"], np.nan)
        h = safe_float(candle["high"], np.nan)
        l = safe_float(candle["low"], np.nan)
        c = safe_float(candle["close"], np.nan)

        if not all(math.isfinite(x) for x in [o, h, l, c]):
            continue

        bullish = c >= o

        wick_color = "#D8D8D8"
        body_face = "#F4F4F4" if bullish else "#3A3A3A"
        body_edge = "#F4F4F4" if bullish else "#C7C7C7"

        ax.plot(
            [i, i],
            [l, h],
            color=wick_color,
            linewidth=1.0,
            solid_capstyle="round",
            zorder=3,
        )

        body_low = min(o, c)
        body_height = abs(c - o)
        if body_height <= 0:
            body_height = max((h - l) * 0.015, 1e-8)

        ax.add_patch(
            Rectangle(
                (i - width / 2, body_low),
                width,
                body_height,
                facecolor=body_face,
                edgecolor=body_edge,
                linewidth=0.9,
                zorder=4,
            )
        )


# ============================================================
# FIXED FIBONACCI FOR THE TRADE
# ============================================================

def draw_fixed_trade_fib(
    ax,
    signal_row,
    chart_start,
    signal_position,
    exit_position,
    conditions,
    data_len,
):
    """
    Draw the Fib that existed on the setup candle as fixed horizontal
    levels. Do not plot the later, continuously updating Fib series.
    """
    conditions = set(condition_list(conditions))

    fib_related = any(
        ("fib" in condition.lower())
        or ("382" in condition)
        or ("500" in condition)
        or ("618" in condition)
        for condition in conditions
    )

    if not fib_related:
        return

    f382 = safe_float(signal_row.get("fib_382"), np.nan)
    f500 = safe_float(signal_row.get("fib_500"), np.nan)
    f618 = safe_float(signal_row.get("fib_618"), np.nan)
    swing_high = safe_float(signal_row.get("fib_swing_high"), np.nan)
    swing_low = safe_float(signal_row.get("fib_swing_low"), np.nan)

    if not all(
        math.isfinite(x)
        for x in [f382, f500, f618, swing_high, swing_low]
    ):
        return

    fib_range = swing_high - swing_low
    if fib_range <= 0:
        return

    # In the feature engine bullish retracements have 38.2 above 61.8;
    # bearish retracements have 38.2 below 61.8.
    bullish_context = f382 > f618

    if bullish_context:
        levels = {
            "0.236": swing_high - fib_range * 0.236,
            "0.382": f382,
            "0.500": f500,
            "0.618": f618,
            "0.700": swing_high - fib_range * 0.700,
        }
    else:
        levels = {
            "0.236": swing_low + fib_range * 0.236,
            "0.382": f382,
            "0.500": f500,
            "0.618": f618,
            "0.700": swing_low + fib_range * 0.700,
        }

    high_index = safe_float(signal_row.get("fib_swing_high_index"), np.nan)
    low_index = safe_float(signal_row.get("fib_swing_low_index"), np.nan)

    if math.isfinite(high_index):
        high_x = int(round(high_index)) - chart_start
    else:
        high_x = max(0, signal_position - 10)

    if math.isfinite(low_index):
        low_x = int(round(low_index)) - chart_start
    else:
        low_x = max(0, signal_position - 10)

    anchor_left = max(0, min(high_x, low_x))
    x0 = min(anchor_left, max(0, signal_position - 8))
    x1 = min(
        data_len - 1,
        max(exit_position + 4, signal_position + 10),
    )

    zone_bottom = min(levels.values())
    zone_top = max(levels.values())

    ax.add_patch(
        Rectangle(
            (x0, zone_bottom),
            max(x1 - x0, 1),
            max(zone_top - zone_bottom, 1e-8),
            facecolor="#00CFE8",
            edgecolor="#00CFE8",
            linewidth=0.7,
            alpha=0.13,
            zorder=1,
        )
    )

    for label, level in levels.items():
        ax.hlines(
            level,
            x0,
            x1,
            colors="#00D7F2",
            linewidth=1.15,
            zorder=2,
        )
        ax.text(
            x1 + 0.25,
            level,
            f"{label} ({level:.5f})",
            color="#00D7F2",
            fontsize=9,
            va="center",
            ha="left",
            zorder=8,
        )

    # Draw the actual swing-to-swing anchor when it is visible.
    if -2 <= high_x <= data_len + 1 and -2 <= low_x <= data_len + 1:
        ax.plot(
            [low_x, high_x],
            [swing_low, swing_high],
            color="#B8B8B8",
            linestyle=(0, (5, 5)),
            linewidth=1.25,
            alpha=0.85,
            zorder=2,
        )
        ax.scatter(
            [low_x, high_x],
            [swing_low, swing_high],
            s=24,
            color="#00D7F2",
            zorder=7,
        )


# ============================================================
# RELEVANT INDICATORS
# ============================================================

def draw_relevant_indicators(
    ax,
    data,
    conditions,
    signal_row=None,
    chart_start=0,
    signal_position=None,
    exit_position=None,
):
    conditions = set(condition_list(conditions))

    # EMA
    ema_columns = []
    for ema in ["ema20", "ema50", "ema100", "ema200"]:
        if f"above_{ema}" in conditions:
            ema_columns.append(ema)

    if "ema_bullish_alignment" in conditions:
        ema_columns.extend(["ema20", "ema50", "ema100", "ema200"])
    if "ema_bearish_alignment" in conditions:
        ema_columns.extend(["ema20", "ema50", "ema100", "ema200"])

    ema_colors = {
        "ema20": "#F5B041",
        "ema50": "#9B59B6",
        "ema100": "#5DADE2",
        "ema200": "#AAB7B8",
    }

    for col in dict.fromkeys(ema_columns):
        if col in data.columns:
            values = pd.to_numeric(data[col], errors="coerce")
            if values.notna().any():
                ax.plot(
                    range(len(data)),
                    values,
                    linewidth=1.0,
                    color=ema_colors.get(col, "#AAAAAA"),
                    alpha=0.9,
                    label=col.upper(),
                    zorder=2,
                )

    # Fixed trade Fib - deliberately NOT the moving dataframe series.
    if (
        signal_row is not None
        and signal_position is not None
        and exit_position is not None
    ):
        draw_fixed_trade_fib(
            ax=ax,
            signal_row=signal_row,
            chart_start=chart_start,
            signal_position=signal_position,
            exit_position=exit_position,
            conditions=conditions,
            data_len=len(data),
        )

    # Order blocks
    if (
        "bullish_order_block" in conditions
        or "bullish_order_block_retest" in conditions
        or "bullish_ob_fib_confluence" in conditions
    ):
        if (
            "bullish_order_block_high" in data.columns
            and "bullish_order_block_low" in data.columns
        ):
            high = pd.to_numeric(data["bullish_order_block_high"], errors="coerce")
            low = pd.to_numeric(data["bullish_order_block_low"], errors="coerce")
            if high.notna().any() and low.notna().any():
                ax.fill_between(
                    range(len(data)),
                    low,
                    high,
                    color="#00A86B",
                    alpha=0.10,
                    label="Bullish OB",
                    zorder=0,
                )

    if (
        "bearish_order_block" in conditions
        or "bearish_order_block_retest" in conditions
        or "bearish_ob_fib_confluence" in conditions
    ):
        if (
            "bearish_order_block_high" in data.columns
            and "bearish_order_block_low" in data.columns
        ):
            high = pd.to_numeric(data["bearish_order_block_high"], errors="coerce")
            low = pd.to_numeric(data["bearish_order_block_low"], errors="coerce")
            if high.notna().any() and low.notna().any():
                ax.fill_between(
                    range(len(data)),
                    low,
                    high,
                    color="#C0392B",
                    alpha=0.10,
                    label="Bearish OB",
                    zorder=0,
                )

    # Supply / demand
    if (
        "bullish_demand_zone" in conditions
        or "demand_zone_retest" in conditions
        or "bullish_demand_liquidity" in conditions
    ):
        if (
            "demand_zone_high" in data.columns
            and "demand_zone_low" in data.columns
        ):
            ax.fill_between(
                range(len(data)),
                pd.to_numeric(data["demand_zone_low"], errors="coerce"),
                pd.to_numeric(data["demand_zone_high"], errors="coerce"),
                color="#00A86B",
                alpha=0.08,
                label="Demand",
                zorder=0,
            )

    if (
        "bearish_supply_zone" in conditions
        or "supply_zone_retest" in conditions
        or "bearish_supply_liquidity" in conditions
    ):
        if (
            "supply_zone_high" in data.columns
            and "supply_zone_low" in data.columns
        ):
            ax.fill_between(
                range(len(data)),
                pd.to_numeric(data["supply_zone_low"], errors="coerce"),
                pd.to_numeric(data["supply_zone_high"], errors="coerce"),
                color="#C0392B",
                alpha=0.08,
                label="Supply",
                zorder=0,
            )


# ============================================================
# SAVE INDIVIDUAL TRADE CHART
# ============================================================

def save_trade_chart(
    feature_df,
    strategy,
    trade,
    strategy_number,
    trade_number,
    outcome_type,
):
    entry_i = find_timestamp_index(feature_df, trade.get("entry_time"))
    exit_i = find_timestamp_index(feature_df, trade.get("exit_time"))
    signal_i = find_timestamp_index(feature_df, trade.get("signal_time"))

    if entry_i is None:
        return None
    if exit_i is None:
        exit_i = min(len(feature_df) - 1, entry_i + 12)
    if signal_i is None:
        signal_i = max(0, entry_i - 1)

    start = max(0, min(signal_i, entry_i) - BARS_BEFORE)
    end = min(len(feature_df) - 1, exit_i + BARS_AFTER)
    data = feature_df.iloc[start:end + 1].copy()

    if data.empty:
        return None

    signal_position = signal_i - start
    entry_position = entry_i - start
    exit_position = exit_i - start
    signal_row = feature_df.iloc[signal_i]

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    draw_candles(ax, data)
    draw_relevant_indicators(
        ax,
        data,
        strategy["conditions"],
        signal_row=signal_row,
        chart_start=start,
        signal_position=signal_position,
        exit_position=exit_position,
    )

    direction = str(strategy["direction"]).upper()
    session = str(strategy["session"])
    rr_value = float(strategy["rr"])

    entry = safe_float(trade["entry"])
    sl = safe_float(trade["sl"])
    tp = safe_float(trade["tp"])
    result_r = safe_float(trade.get("outcome_r"))
    reason = str(trade.get("reason", "UNKNOWN")).upper()

    # TradingView-style position/risk-reward box.
    rr_box_end = min(
        len(data) - 1,
        max(exit_position, entry_position + 6),
    )
    rr_box_width = max(rr_box_end - entry_position, 1)

    profit_low = min(entry, tp)
    profit_high = max(entry, tp)
    risk_low = min(entry, sl)
    risk_high = max(entry, sl)

    ax.add_patch(
        Rectangle(
            (entry_position, profit_low),
            rr_box_width,
            max(profit_high - profit_low, 1e-8),
            facecolor="#008A6E",
            edgecolor="#14B89A",
            linewidth=1.0,
            alpha=0.28,
            zorder=1,
        )
    )
    ax.add_patch(
        Rectangle(
            (entry_position, risk_low),
            rr_box_width,
            max(risk_high - risk_low, 1e-8),
            facecolor="#7E1F2A",
            edgecolor="#E74C5B",
            linewidth=1.0,
            alpha=0.30,
            zorder=1,
        )
    )

    ax.hlines(
        entry,
        entry_position,
        rr_box_end,
        colors="#F2F2F2",
        linewidth=1.3,
        zorder=6,
    )
    ax.hlines(
        sl,
        entry_position,
        rr_box_end,
        colors="#FF4D5A",
        linewidth=1.1,
        zorder=6,
    )
    ax.hlines(
        tp,
        entry_position,
        rr_box_end,
        colors="#13C6A3",
        linewidth=1.1,
        zorder=6,
    )

    label_x = rr_box_end + 0.3
    ax.text(
        label_x,
        sl,
        f"SL  {sl:.5f}",
        color="#FFFFFF",
        fontsize=9,
        va="center",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#E83E4D", edgecolor="none"),
        zorder=10,
    )
    ax.text(
        label_x,
        entry,
        f"ENTRY  {entry:.5f}",
        color="#FFFFFF",
        fontsize=9,
        va="center",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#737373", edgecolor="none"),
        zorder=10,
    )
    ax.text(
        label_x,
        tp,
        f"TP  {tp:.5f}",
        color="#FFFFFF",
        fontsize=9,
        va="center",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#00A88A", edgecolor="none"),
        zorder=10,
    )

    # Highlight the setup candle.
    if 0 <= signal_position < len(data):
        signal_low = safe_float(feature_df.iloc[signal_i]["low"])
        signal_high = safe_float(feature_df.iloc[signal_i]["high"])
        ax.add_patch(
            Rectangle(
                (signal_position - 0.42, signal_low),
                0.84,
                max(signal_high - signal_low, 1e-8),
                fill=False,
                edgecolor="#00D7F2",
                linewidth=1.4,
                zorder=7,
            )
        )
        ax.text(
            signal_position,
            signal_high,
            "SETUP",
            color="#00D7F2",
            fontsize=8,
            fontweight="bold",
            ha="center",
            va="bottom",
            zorder=9,
        )

    ax.scatter(
        [entry_position],
        [entry],
        s=55,
        marker="o",
        facecolor="#FFFFFF",
        edgecolor="#111111",
        linewidth=0.8,
        zorder=9,
    )

    exit_price = safe_float(trade.get("exit_price"), np.nan)
    if not math.isfinite(exit_price):
        exit_price = safe_float(feature_df.iloc[exit_i]["close"])

    if reason == "TP":
        exit_text = "TP HIT"
    elif reason == "SL":
        exit_text = "SL HIT"
    else:
        exit_text = reason

    exit_color = "#18C79C" if result_r >= 0 else "#FF4D5A"
    ax.scatter(
        [exit_position],
        [exit_price],
        s=90,
        marker="X",
        color=exit_color,
        zorder=10,
    )
    ax.annotate(
        f"{exit_text}  {result_r:+.2f}R",
        xy=(exit_position, exit_price),
        xytext=(8, 8 if result_r >= 0 else -12),
        textcoords="offset points",
        color=exit_color,
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="bottom" if result_r >= 0 else "top",
        zorder=10,
    )

    title = (
        f"Strategy #{strategy_number} | "
        f"{direction} | {session} | "
        f"RR {rr_value:.1f} | "
        f"{outcome_type.upper()} | "
        f"{result_r:+.2f}R"
    )
    ax.set_title(
        title,
        fontsize=16,
        fontweight="bold",
        color="#F2F2F2",
        pad=12,
    )

    tick_positions = np.linspace(
        0,
        len(data) - 1,
        min(9, len(data)),
        dtype=int,
    )
    tick_labels = [
        data.iloc[pos]["timestamp"].strftime("%d %b\n%H:%M")
        for pos in tick_positions
    ]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=0)

    ax.set_ylabel("Price", color="#D8D8D8")
    ax.set_xlabel("15-minute candles", color="#D8D8D8")
    ax.tick_params(axis="both", colors="#D8D8D8")
    for spine in ax.spines.values():
        spine.set_color("#393939")

    ax.grid(color="#2A2A2A", alpha=0.55, linewidth=0.7)
    ax.set_axisbelow(True)

    visible_low = min(
        safe_float(data["low"].min()),
        entry,
        sl,
        tp,
        exit_price,
    )
    visible_high = max(
        safe_float(data["high"].max()),
        entry,
        sl,
        tp,
        exit_price,
    )
    y_range = max(visible_high - visible_low, 1e-6)
    ax.set_ylim(visible_low - y_range * 0.10, visible_high + y_range * 0.12)
    ax.set_xlim(-1, len(data) + 7)

    condition_text = "SETUP: " + str(strategy["conditions"])
    ax.text(
        0.012,
        0.975,
        condition_text,
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=9,
        color="#FFFFFF",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="#176B87",
            edgecolor="#00D7F2",
            alpha=0.92,
        ),
        zorder=20,
    )

    win = result_r >= 0
    ax.text(
        0.985,
        0.975,
        f"{'WIN' if win else 'LOSS'}  {result_r:+.2f}R",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=11,
        fontweight="bold",
        color="#FFFFFF",
        bbox=dict(
            boxstyle="round,pad=0.38",
            facecolor="#008A6E" if win else "#C03949",
            edgecolor="none",
            alpha=0.96,
        ),
        zorder=20,
    )

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(
            loc="lower left",
            fontsize=8,
            facecolor="#111111",
            edgecolor="#444444",
            labelcolor="#EAEAEA",
            framealpha=0.9,
        )

    fig.tight_layout()

    strategy_dir = CHART_DIR / f"strategy_{strategy_number:02d}"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{outcome_type}_{trade_number:02d}.png"
    output_path = strategy_dir / filename

    fig.savefig(
        output_path,
        dpi=170,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    return output_path


# ============================================================
# HTML
# ============================================================

def html_metric(label, value):
    return f"""
    <div class="metric">
        <div class="metric-label">{html.escape(str(label))}</div>
        <div class="metric-value">{html.escape(str(value))}</div>
    </div>
    """


def build_html(strategy_cards):
    cards = []

    for card in strategy_cards:
        strategy = card["strategy"]

        explanations = "".join(
            f"<li>{html.escape(x)}</li>"
            for x in card["explanations"]
        )

        chart_html = ""

        for chart in card["charts"]:
            relative = chart.relative_to(
                OUTPUT_DIR
            ).as_posix()

            label = chart.stem.replace(
                "_",
                " ",
            ).title()

            chart_html += f"""
            <div class="chart">
                <h3>{html.escape(label)}</h3>
                <img src="{html.escape(relative)}">
            </div>
            """

        cards.append(
            f"""
            <section class="strategy-card">

                <div class="strategy-header">

                    <div>
                        <div class="rank">
                            #{int(strategy["visual_rank"])}
                        </div>

                        <h2>
                            {html.escape(str(strategy["direction"]))}
                            —
                            {html.escape(str(strategy["session"]))}
                        </h2>

                        <div class="conditions">
                            {html.escape(str(strategy["conditions"]))}
                        </div>
                    </div>

                    <div class="score">
                        <span>ROBUST SCORE</span>
                        <strong>
                            {safe_float(strategy["robust_score"]):.2f}
                        </strong>
                    </div>

                </div>

                <div class="metrics">

                    {html_metric("RR", f'{safe_float(strategy["rr"]):.1f}')}

                    {html_metric("Trades", int(strategy["trades"]))}

                    {html_metric("Net R", f'{safe_float(strategy["net_r"]):+.2f}R')}

                    {html_metric("Profit Factor", f'{safe_float(strategy["profit_factor"]):.2f}')}

                    {html_metric("Max DD", f'{safe_float(strategy["max_drawdown_r"]):.2f}R')}

                    {html_metric("Expectancy", f'{safe_float(strategy.get("expectancy_r", 0)):+.3f}R')}

                    {html_metric("Win Rate", f'{safe_float(strategy.get("win_rate", 0)):.1f}%')}

                </div>

                <div class="explanation">

                    <h3>How this strategy works</h3>

                    <ul>
                        {explanations}
                    </ul>

                </div>

                <div class="charts">

                    <h3>Actual historical trades</h3>

                    {chart_html}

                </div>

            </section>
            """
        )

    return f"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<title>Strategy Lab — Visual Validation</title>

<style>

body {{
    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background:
        #111827;

    color:
        #e5e7eb;

    margin:
        0;

    padding:
        30px;
}}

.container {{
    max-width:
        1500px;

    margin:
        auto;
}}

h1 {{
    font-size:
        34px;

    margin-bottom:
        5px;
}}

.subtitle {{
    color:
        #9ca3af;

    margin-bottom:
        35px;
}}

.strategy-card {{
    background:
        #1f2937;

    border:
        1px solid #374151;

    border-radius:
        14px;

    padding:
        24px;

    margin-bottom:
        35px;

    box-shadow:
        0 8px 25px rgba(0,0,0,0.25);
}}

.strategy-header {{
    display:
        flex;

    justify-content:
        space-between;

    align-items:
        flex-start;

    gap:
        25px;
}}

.rank {{
    font-size:
        14px;

    color:
        #9ca3af;
}}

h2 {{
    margin:
        5px 0 8px;

    font-size:
        26px;
}}

h3 {{
    margin-top:
        25px;
}}

.conditions {{
    color:
        #93c5fd;

    font-family:
        Consolas,
        monospace;

    font-size:
        14px;
}}

.score {{
    text-align:
        right;
}}

.score span {{
    display:
        block;

    color:
        #9ca3af;

    font-size:
        11px;
}}

.score strong {{
    font-size:
        30px;
}}

.metrics {{
    display:
        grid;

    grid-template-columns:
        repeat(7, 1fr);

    gap:
        10px;

    margin-top:
        25px;
}}

.metric {{
    background:
        #111827;

    border-radius:
        9px;

    padding:
        12px;

    text-align:
        center;
}}

.metric-label {{
    color:
        #9ca3af;

    font-size:
        11px;

    margin-bottom:
        5px;
}}

.metric-value {{
    font-size:
        18px;

    font-weight:
        bold;
}}

.explanation {{
    background:
        #111827;

    border-radius:
        10px;

    padding:
        15px 20px;

    margin-top:
        25px;
}}

.explanation li {{
    margin-bottom:
        7px;

    line-height:
        1.45;
}}

.chart {{
    margin-top:
        25px;

    background:
        #111827;

    border-radius:
        10px;

    padding:
        15px;
}}

.chart img {{
    width:
        100%;

    height:
        auto;

    border-radius:
        7px;

    display:
        block;
}}

@media (max-width: 1000px) {{

    .metrics {{
        grid-template-columns:
            repeat(3, 1fr);
    }}

}}

@media (max-width: 600px) {{

    body {{
        padding:
            10px;
    }}

    .strategy-header {{
        flex-direction:
            column;
    }}

    .score {{
        text-align:
            left;
    }}

    .metrics {{
        grid-template-columns:
            repeat(2, 1fr);
    }}

}}

</style>

</head>

<body>

<div class="container">

<h1>Strategy Lab — Visual Validation</h1>

<div class="subtitle">
Top {TOP_N} unique strategy families with actual historical
trade examples from the Strategy Lab backtest.
</div>

{''.join(cards)}

</div>

</body>

</html>
"""


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("STRATEGY LAB VISUAL VALIDATION")
    print("=" * 70)
    print()

    if not FEATURE_FILE.exists():
        raise SystemExit(
            f"Feature database not found:\n{FEATURE_FILE}"
        )

    if not TOP_FILE.exists():
        raise SystemExit(
            f"Top-final file not found:\n{TOP_FILE}"
        )

    if not DB_FILE.exists():
        raise SystemExit(
            f"Strategy Lab database not found:\n{DB_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    CHART_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    feature_df = load_feature_data()

    strategies = load_top_strategies()

    cards = []

    for _, strategy in strategies.iterrows():

        number = int(
            strategy["visual_rank"]
        )

        print()
        print(
            f"[{number:02d}/{len(strategies):02d}] "
            f"{strategy['direction']} "
            f"{strategy['session']} | "
            f"{strategy['conditions']}"
        )

        trades = load_trade_details(
            strategy
        )

        if not trades:
            print(
                "  WARNING: No stored trade details found."
            )

            cards.append(
                {
                    "strategy": strategy,
                    "explanations": explain_strategy(
                        strategy["conditions"],
                        strategy["direction"],
                        strategy["session"],
                    ),
                    "charts": [],
                }
            )

            continue

        # ----------------------------------------------------
        # Sort actual trades by outcome.
        # ----------------------------------------------------

        wins = [
            t for t in trades
            if safe_float(t.get("outcome_r")) > 0
        ]

        losses = [
            t for t in trades
            if safe_float(t.get("outcome_r")) < 0
        ]

        # Strongest examples first.
        wins = sorted(
            wins,
            key=lambda x: safe_float(
                x.get("outcome_r")
            ),
            reverse=True,
        )

        losses = sorted(
            losses,
            key=lambda x: safe_float(
                x.get("outcome_r")
            ),
        )

        selected = []

        for trade in wins[:WIN_EXAMPLES]:
            selected.append(
                ("win", trade)
            )

        for trade in losses[:LOSS_EXAMPLES]:
            selected.append(
                ("loss", trade)
            )

        charts = []

        for trade_number, (
            outcome_type,
            trade,
        ) in enumerate(
            selected,
            start=1,
        ):

            chart = save_trade_chart(
                feature_df,
                strategy,
                trade,
                number,
                trade_number,
                outcome_type,
            )

            if chart:
                charts.append(chart)

        cards.append(
            {
                "strategy": strategy,
                "explanations": explain_strategy(
                    strategy["conditions"],
                    strategy["direction"],
                    strategy["session"],
                ),
                "charts": charts,
            }
        )

        print(
            f"  Stored trades: {len(trades):,}"
        )

        print(
            f"  Wins available: {len(wins):,}"
        )

        print(
            f"  Losses available: {len(losses):,}"
        )

        print(
            f"  Charts created: {len(charts)}"
        )

    # --------------------------------------------------------
    # HTML REPORT
    # --------------------------------------------------------

    report = build_html(
        cards
    )

    html_file = (
        OUTPUT_DIR
        / "strategy_report.html"
    )

    html_file.write_text(
        report,
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("VISUAL VALIDATION COMPLETE")
    print("=" * 70)
    print()
    print(
        f"Report:\n  {html_file}"
    )
    print()
    print(
        f"Charts:\n  {CHART_DIR}"
    )
    print()
    print(
        "Open the HTML report in your browser."
    )
    print()


if __name__ == "__main__":
    main()