"""MT5-backed multi-symbol paper bot for the funded shortlist.

Paper-only: this program reads MT5 prices but never sends broker orders.
It maintains a local ledger and enforces the agreed Alpha Pro controls.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import textwrap
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from paper_bot_email import notify_event, send_daily_summary, send_email

warnings.filterwarnings("ignore", category=DeprecationWarning)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "results" / "alpha_mt5_paper"
DEFAULT_MT5_TERMINAL = Path(
    os.environ.get("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
)
STAGES = {
    "PHASE_1": {"risk": 0.01, "target": 11030.0},
    "PHASE_2": {"risk": 0.01, "target": 10520.0},
    "QUALIFIED": {"risk": 0.005, "target": None},
}
PHASE_START_BALANCE = 10000.0
MAGIC = 260818
DEFAULT_PIP_SIZE = 0.0001
LIVE_BAR_MAX_AGE_MINUTES = 35
EVENT_JOURNAL = None
CHART_DIR = None
FEATURE_CACHES = {}
EMAIL_STATE_DIR = None
JOURNAL_FIELDS = [
    "time", "kind", "processing_mode", "bar_time", "strategy", "reason",
    "entry_mode", "entry", "sl", "tp", "price", "stop_pips",
    "target_pips", "estimated_lot", "risk_dollars", "result_r", "pnl",
    "balance", "day", "message", "pending_entry", "chart_path",
]


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="GBPUSD", help="Fallback symbol for an older shortlist without a symbol column")
    p.add_argument("--terminal-path", type=Path, default=DEFAULT_MT5_TERMINAL)
    p.add_argument("--shortlist", type=Path, default=ROOT / "results" / "funded_strategy_shortlist.csv")
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--reset-balance", type=float)
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--status", action="store_true", help="Print saved paper-account status without connecting to MT5")
    p.add_argument("--no-charts", action="store_true", help="Disable automatic PNG charts when trades close")
    p.add_argument("--self-test", action="store_true")
    return p.parse_args()


def pip_size_for(symbol):
    return 0.01 if str(symbol).upper().endswith("JPY") else DEFAULT_PIP_SIZE


def normalized_symbol(value):
    return "".join(character for character in str(value).upper() if character.isalnum())


def resolve_symbol(mt5, requested):
    requested = str(requested).strip()
    if mt5.symbol_info(requested) is not None:
        return requested
    wanted = normalized_symbol(requested)
    exact = []
    prefixed = []
    for item in mt5.symbols_get() or []:
        name = str(getattr(item, "name", ""))
        normalized = normalized_symbol(name)
        if normalized == wanted:
            exact.append(name)
        elif normalized.startswith(wanted):
            prefixed.append(name)
    matches = exact or prefixed
    if not matches:
        raise RuntimeError(f"MT5 does not provide a symbol matching {requested!r}")
    return sorted(matches, key=lambda name: (len(name), name))[0]


def pip_value_per_lot(mt5, symbol, price, pip_size=None):
    """Return account-currency value of one pip for one lot."""
    pip_size = float(pip_size or pip_size_for(symbol))
    try:
        value = mt5.order_calc_profit(
            mt5.ORDER_TYPE_BUY, str(symbol), 1.0, float(price), float(price) + pip_size
        )
        if value is not None and math.isfinite(float(value)) and abs(float(value)) > 0:
            return abs(float(value))
    except Exception:
        pass
    return 10.0


def atomic_json(value, path):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def initial_state():
    return {
        "stage": "PHASE_1", "balance": PHASE_START_BALANCE,
        "day_start_balance": PHASE_START_BALANCE,
        "account_start_balance": PHASE_START_BALANCE,
        "personal_daily_limit": 0.03,
        "broker_day": None, "last_bar_time": None, "trading_days": [],
        "last_bar_times": {}, "last_prices": {},
        "positions": [], "pending": [], "events": [], "locked": False,
        "lock_reason": None, "last_daily_email_date": None, "phase_history": [],
    }


def load_state(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else initial_state()
    defaults = initial_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
    if not isinstance(state.get("last_bar_times"), dict):
        state["last_bar_times"] = {}
    if state.get("last_bar_time") and "GBPUSD" not in state["last_bar_times"]:
        state["last_bar_times"]["GBPUSD"] = state["last_bar_time"]
    if not isinstance(state.get("last_prices"), dict):
        state["last_prices"] = {}
    for collection in ("positions", "pending"):
        for item in state.get(collection, []):
            item.setdefault("symbol", "GBPUSD")
            item.setdefault("pip_size", pip_size_for(item["symbol"]))
            item.setdefault("pip_value_per_lot", 10.0)
            label = str(item.get("strategy", ""))
            if label.count("|") == 3:
                item["strategy"] = f"{item['symbol']}|{label}"
    return state, path


def event(state, kind, **details):
    record = {"time": datetime.now(timezone.utc).isoformat(), "kind": kind, **details}
    state["events"].append(record)
    state["events"] = state["events"][-1000:]
    if EVENT_JOURNAL is not None:
        EVENT_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        new_file = not EVENT_JOURNAL.exists()
        with EVENT_JOURNAL.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=JOURNAL_FIELDS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(record)
    print(json.dumps(record, default=str), flush=True)
    if EMAIL_STATE_DIR is not None:
        try:
            notify_event(kind, details, state, EMAIL_STATE_DIR)
        except Exception as exc:
            print(f"WARNING: event email failed: {exc}", file=sys.stderr, flush=True)


def bar_processing_mode(timestamp):
    age = pd.Timestamp.now(tz="UTC") - pd.Timestamp(timestamp)
    return "LIVE" if age <= pd.Timedelta(minutes=LIVE_BAR_MAX_AGE_MINUTES) else "CATCH_UP"


def iso_time(value):
    return pd.Timestamp(value).isoformat()


def add_minutes(value, minutes):
    return (pd.Timestamp(value) + pd.Timedelta(minutes=minutes)).isoformat()


def broker_day(timestamp):
    return (pd.Timestamp(timestamp) + pd.Timedelta(hours=3)).date().isoformat()


def equity(state, prices):
    if not isinstance(prices, dict):
        prices = {str(pos.get("symbol", "GBPUSD")): float(prices) for pos in state["positions"]}
    floating = 0.0
    for pos in state["positions"]:
        symbol = str(pos.get("symbol", "GBPUSD"))
        price = float(prices.get(symbol, pos.get("last_price", pos["entry"])))
        move = price - pos["entry"]
        if pos["direction"] == "SELL":
            move = -move
        floating += move / pos["risk_distance"] * pos["risk_dollars"]
    return state["balance"] + floating


def risk_allowed(state, prices):
    if state["locked"] or len(state["positions"]) >= 2:
        return False, "locked or two positions already open"
    loss = state["day_start_balance"] - equity(state, prices)
    planned = state["balance"] * STAGES[state["stage"]]["risk"]
    daily_limit = float(state.get("personal_daily_limit", 0.03))
    if loss + planned > state["day_start_balance"] * daily_limit + 1e-9:
        return False, f"{daily_limit * 100:g}% personal daily risk limit"
    return True, "ok"


def bool_value(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def matches(row, strategy):
    if str(row["session"]).strip().lower() != str(strategy["session"]).strip().lower():
        return False
    for condition in str(strategy["conditions"]).split("+"):
        if condition not in row or not bool_value(row[condition]):
            return False
    fib_col = "fib_bullish" if strategy["direction"] == "BUY" else "fib_bearish"
    return bool_value(row.get(fib_col, False))


def fib_level(row, conditions):
    ratios = [r for r in (382, 500, 618) if f"fib_{r}" in str(conditions)]
    if not ratios:
        return None
    value = row.get(f"fib_{max(ratios)}")
    return float(value) if pd.notna(value) else None


def refresh_day(state, timestamp, processing_mode=None):
    day = broker_day(timestamp)
    if state["broker_day"] != day:
        state["broker_day"] = day
        state["day_start_balance"] = state["balance"]
        if state.get("lock_reason") == "DAILY_LIMIT":
            state["locked"] = False
            state["lock_reason"] = None
        event(state, "BROKER_DAY_RESET", day=day, balance=state["balance"],
              bar_time=iso_time(timestamp), processing_mode=processing_mode)


def save_trade_chart(pos, exit_time, exit_price, reason):
    """Save a compact audit chart. A chart failure must never stop trading."""
    frame = FEATURE_CACHES.get(str(pos.get("symbol", "GBPUSD")))
    if CHART_DIR is None or frame is None:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        signal_time = pd.Timestamp(pos.get("signal_bar_time", pos["entry_bar_time"]))
        end_time = pd.Timestamp(exit_time)
        before = signal_time - pd.Timedelta(hours=5)
        after = end_time + pd.Timedelta(hours=1)
        chart = frame[(frame["timestamp"] >= before) & (frame["timestamp"] <= after)].copy()
        if chart.empty:
            return None
        chart = chart.reset_index(drop=True)
        fig, ax = plt.subplots(figsize=(14, 7), facecolor="#10151d")
        ax.set_facecolor("#10151d")
        for i, row in chart.iterrows():
            colour = "#22c55e" if row.close >= row.open else "#ef4444"
            ax.vlines(i, row.low, row.high, color=colour, linewidth=1)
            bottom = min(row.open, row.close)
            height = max(abs(row.close - row.open), float(pos.get("pip_size", DEFAULT_PIP_SIZE)) * 0.05)
            ax.add_patch(Rectangle((i - 0.32, bottom), 0.64, height,
                                   facecolor=colour, edgecolor=colour, linewidth=0.7))

        # Plot only the EMA filters that belong to this strategy so the
        # chart explains the signal without becoming cluttered.
        for ema_number in (20, 100, 200):
            ema_column = f"ema{ema_number}"
            if f"ema{ema_number}" in pos["strategy"].lower() and ema_column in chart.columns:
                ax.plot(chart.index, chart[ema_column], color="#f59e0b", linewidth=1.8,
                        label=f"EMA {ema_number}", zorder=2)

        signal_row = frame[frame["timestamp"] == signal_time]
        fib_ratio = next((ratio for ratio in (382, 500, 618)
                          if f"fib_{ratio}" in pos["strategy"]), None)
        if not signal_row.empty:
            signal_data = signal_row.iloc[0]
            swing_low = signal_data.get("fib_swing_low")
            swing_high = signal_data.get("fib_swing_high")
            if pd.notna(swing_low):
                ax.axhline(float(swing_low), color="#94a3b8", linewidth=1.0,
                           linestyle=":", label=f"Confirmed swing low {float(swing_low):.5f}")
            if pd.notna(swing_high):
                ax.axhline(float(swing_high), color="#cbd5e1", linewidth=1.0,
                           linestyle=":", label=f"Confirmed swing high {float(swing_high):.5f}")

        entry_label = f"Entry {pos['entry']:.5f}"
        entry_colour = "#60a5fa"
        if fib_ratio is not None:
            entry_label = f"Entry / Fib {fib_ratio / 10:.1f}%  {pos['entry']:.5f}"
            entry_colour = "#facc15"
        ax.axhline(pos["entry"], color=entry_colour, linewidth=2.0,
                   linestyle="--", label=entry_label)
        ax.axhline(pos["sl"], color="#ef4444", linestyle="--", label=f"SL {pos['sl']:.5f}")
        ax.axhline(pos["tp"], color="#22c55e", linestyle="--", label=f"TP {pos['tp']:.5f}")

        def chart_index(timestamp):
            matches = chart.index[chart["timestamp"] == pd.Timestamp(timestamp)]
            return int(matches[0]) if len(matches) else None

        signal_x = chart_index(signal_time)
        entry_x = chart_index(pos["entry_bar_time"])
        exit_x = chart_index(exit_time)
        if signal_x is not None:
            ax.axvline(signal_x, color="#a78bfa", alpha=0.85, linewidth=1.4,
                       linestyle="-.", label=f"Signal {signal_time.strftime('%H:%M')} UTC")
        if entry_x is not None:
            ax.scatter(entry_x, pos["entry"], marker="^", s=120, color="#facc15",
                       edgecolor="black", linewidth=0.8, zorder=6, label="Entry filled")
        if exit_x is not None:
            ax.scatter(exit_x, exit_price, marker="X", s=120, color="#22c55e" if reason == "TP" else "#ef4444",
                       edgecolor="white", linewidth=0.8, zorder=6, label=f"Exit {reason}")
        time_labels = [pd.Timestamp(x).strftime("%d %b\n%H:%M") for x in chart["timestamp"]]
        tick_step = max(1, len(chart) // 10)
        ticks = list(range(0, len(chart), tick_step))
        ax.set_xticks(ticks, [time_labels[i] for i in ticks])
        ax.tick_params(colors="#d1d5db")
        for spine in ax.spines.values():
            spine.set_color("#475569")
        title = f"{pos.get('symbol', 'GBPUSD')} | {pos['strategy']} | {reason} | {pos.get('processing_mode', 'UNKNOWN')}"
        ax.set_title(title, color="white", fontsize=11)
        ax.legend(facecolor="#17202b", labelcolor="white", loc="best")
        ax.grid(alpha=0.15)
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in pos["strategy"])[:90]
        filename = f"{pd.Timestamp(exit_time).strftime('%Y%m%d_%H%M')}_{safe}_{reason}.png"
        path = CHART_DIR / filename
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        return str(path)
    except Exception as exc:
        print(f"WARNING: trade chart could not be saved: {exc}", file=sys.stderr)
        return None


def save_signal_chart(order, signal_time):
    """Save a live pending-entry chart for attachment to the signal email."""
    frame = FEATURE_CACHES.get(str(order.get("symbol", "GBPUSD")))
    if CHART_DIR is None or frame is None:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        signal_time = pd.Timestamp(signal_time)
        chart = frame[frame["timestamp"] <= signal_time].tail(88).copy()
        if chart.empty:
            return None
        chart = chart.reset_index(drop=True)
        signal_row = frame[frame["timestamp"] == signal_time]
        if signal_row.empty:
            return None
        signal_data = signal_row.iloc[0]
        signal_x = len(chart) - 1
        expiry_time = pd.Timestamp(order["expires_bar_time"])
        wait_bars = max(1, int(math.ceil((expiry_time - signal_time) / pd.Timedelta(minutes=15))))
        right_x = signal_x + wait_bars + 1

        fig, ax = plt.subplots(figsize=(15, 8.5), facecolor="#090d12")
        ax.set_facecolor("#090d12")
        for i, row in chart.iterrows():
            colour = "#22c55e" if row.close >= row.open else "#ef4444"
            ax.vlines(i, row.low, row.high, color=colour, linewidth=1.0, zorder=2)
            bottom = min(row.open, row.close)
            height = max(abs(row.close - row.open), float(order.get("pip_size", DEFAULT_PIP_SIZE)) * 0.05)
            ax.add_patch(Rectangle((i - 0.32, bottom), 0.64, height,
                                   facecolor=colour, edgecolor=colour,
                                   linewidth=0.7, zorder=3))

        strategy_text = str(order["strategy"])
        label_parts = strategy_text.split("|")
        conditions = label_parts[-2] if len(label_parts) >= 3 else strategy_text
        for ema_number, colour in ((20, "#38bdf8"), (100, "#f59e0b"), (200, "#c084fc")):
            ema_column = f"ema{ema_number}"
            if f"ema{ema_number}" in conditions.lower() and ema_column in chart.columns:
                ax.plot(chart.index, chart[ema_column], color=colour, linewidth=1.7,
                        label=f"EMA {ema_number}", zorder=4)

        fib_ratio = next((ratio for ratio in (382, 500, 618)
                          if f"fib_{ratio}" in conditions), None)
        swing_low = signal_data.get("fib_swing_low")
        swing_high = signal_data.get("fib_swing_high")
        if pd.notna(swing_low):
            ax.axhline(float(swing_low), color="#64748b", linewidth=1.0,
                       linestyle=":", alpha=0.75,
                       label=f"Confirmed swing low {float(swing_low):.5f}")
        if pd.notna(swing_high):
            ax.axhline(float(swing_high), color="#94a3b8", linewidth=1.0,
                       linestyle=":", alpha=0.75,
                       label=f"Confirmed swing high {float(swing_high):.5f}")

        current_price = float(signal_data["close"])
        ax.axhline(current_price, color="#e2e8f0", linewidth=0.9,
                   linestyle=":", alpha=0.45, label=f"Signal close {current_price:.5f}")
        ax.axvspan(signal_x - 0.5, signal_x + 0.5, color="#a78bfa", alpha=0.22,
                   label="Setup candle")

        entry = order.get("entry")
        sl = order.get("sl")
        tp = order.get("tp")
        if entry is not None:
            entry = float(entry)
            entry_label = f"ENTRY TO HIT {entry:.5f}"
            if fib_ratio is not None:
                entry_label += f" / Fib {fib_ratio / 10:.1f}%"
            ax.axhline(entry, color="#facc15", linewidth=1.8, linestyle=":",
                       alpha=0.8, label=entry_label)
            if sl is not None and tp is not None:
                sl, tp = float(sl), float(tp)
                width = max(1, right_x - signal_x)
                ax.add_patch(Rectangle((signal_x, min(entry, tp)), width,
                                       abs(tp - entry), facecolor="#22c55e",
                                       edgecolor="none", alpha=0.11, zorder=0))
                ax.add_patch(Rectangle((signal_x, min(entry, sl)), width,
                                       abs(sl - entry), facecolor="#ef4444",
                                       edgecolor="none", alpha=0.13, zorder=0))
                ax.axhline(sl, color="#ef4444", linewidth=1.2, linestyle=":",
                           alpha=0.65, label=f"SL {sl:.5f}")
                ax.axhline(tp, color="#22c55e", linewidth=1.2, linestyle=":",
                           alpha=0.65, label=f"TP {tp:.5f} ({order['rr']:g}R)")
                distance_pips = abs(current_price - entry) / float(order.get("pip_size", DEFAULT_PIP_SIZE))
                ax.annotate(f"Waiting: {distance_pips:.1f} pips to entry",
                            xy=(signal_x, entry), xytext=(max(0, signal_x - 22), entry),
                            color="#fde68a", fontsize=10,
                            arrowprops={"arrowstyle": "->", "color": "#facc15", "alpha": 0.65})
        else:
            ax.axvspan(signal_x + 0.5, signal_x + 1.5, color="#facc15", alpha=0.12,
                       label="Entry will be next M15 candle open")

        time_labels = [pd.Timestamp(x).strftime("%d %b\n%H:%M") for x in chart["timestamp"]]
        tick_step = max(1, len(chart) // 10)
        ticks = list(range(0, len(chart), tick_step))
        ax.set_xticks(ticks, [time_labels[i] for i in ticks])
        ax.set_xlim(-1, right_x)
        ax.tick_params(colors="#d1d5db")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.grid(alpha=0.12, linestyle=":")
        session_name = label_parts[-3] if len(label_parts) >= 4 else "Unknown session"
        chart_status = str(order.get("chart_status", "PENDING"))
        ax.set_title(
            f"{order.get('symbol', 'GBPUSD')} | {chart_status} {order['direction']} | {session_name} | {order['rr']:g}R target | "
            f"setup {signal_time.strftime('%d %b %H:%M')} UTC",
            color="white", fontsize=11,
        )
        friendly_conditions = conditions.replace("_", " ").replace("+", "  +  ")
        conditions_footer = textwrap.fill(
            f"CONDITIONS MET: {friendly_conditions}", width=150
        )
        footer = (
            f"{conditions_footer}\n"
            f"Entry mode: {order['entry_mode']}  |  Expires: {expiry_time.strftime('%d %b %H:%M')} UTC  |  "
            "Yellow dotted line = price required before the paper trade opens"
        )
        fig.text(0.015, 0.02, footer, color="#cbd5e1", fontsize=9, va="bottom")
        ax.legend(facecolor="#111827", edgecolor="#334155", labelcolor="white",
                  loc="best", fontsize=8)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.91, bottom=0.17)
        signal_directory = CHART_DIR / "signals"
        signal_directory.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in strategy_text)[:90]
        filename = f"{signal_time.strftime('%Y%m%d_%H%M')}_{safe}_PENDING.png"
        path = signal_directory / filename
        fig.savefig(path, dpi=145, facecolor=fig.get_facecolor())
        plt.close(fig)
        return str(path)
    except Exception as exc:
        print(f"WARNING: signal chart could not be saved: {exc}", file=sys.stderr)
        return None


def close_position(state, pos, price, timestamp, reason):
    move = price - pos["entry"]
    if pos["direction"] == "SELL":
        move = -move
    result_r = move / pos["risk_distance"]
    pnl = result_r * pos["risk_dollars"]
    state["balance"] += pnl
    state["positions"].remove(pos)
    day = broker_day(timestamp)
    if day not in state["trading_days"]:
        state["trading_days"].append(day)
    chart_path = save_trade_chart(pos, timestamp, price, reason)
    event(state, "CLOSE", symbol=pos.get("symbol", "GBPUSD"), strategy=pos["strategy"], reason=reason, price=price,
          result_r=result_r, pnl=pnl, balance=state["balance"],
          bar_time=iso_time(timestamp), processing_mode=pos.get("processing_mode", "UNKNOWN"),
          chart_path=chart_path, message=f"chart={chart_path}" if chart_path else None)


def advance_completed_phase(state, timestamp, target):
    """Record a pass and immediately start the next paper-account phase."""
    completed_stage = str(state["stage"])
    next_stage = "PHASE_2" if completed_stage == "PHASE_1" else "QUALIFIED"
    actual_balance = float(state["balance"])
    overshoot = max(0.0, actual_balance - float(target))
    cancelled_pending = len(state["pending"])
    state["pending"].clear()
    record = {
        "stage": completed_stage,
        "next_stage": next_stage,
        "passed_at": iso_time(timestamp),
        "target": float(target),
        "credited_balance": float(target),
        "actual_close_balance": actual_balance,
        "overshoot": overshoot,
        "cancelled_pending": cancelled_pending,
    }
    state.setdefault("phase_history", []).append(record)
    state["phase_history"] = state["phase_history"][-100:]
    event(
        state,
        "PHASE_PASSED",
        stage=completed_stage,
        next_stage=next_stage,
        target=float(target),
        balance=actual_balance,
        overshoot=overshoot,
        bar_time=iso_time(timestamp),
        processing_mode=bar_processing_mode(timestamp),
        message=(
            f"{completed_stage} passed at the ${target:,.2f} safety threshold; "
            f"{next_stage} starts immediately at ${PHASE_START_BALANCE:,.2f}. "
            f"Cancelled pending entries: {cancelled_pending}."
        ),
    )
    state["stage"] = next_stage
    state["balance"] = PHASE_START_BALANCE
    state["day_start_balance"] = PHASE_START_BALANCE
    state["account_start_balance"] = PHASE_START_BALANCE
    state["locked"] = False
    state["lock_reason"] = None
    state["broker_day"] = broker_day(timestamp)
    event(
        state,
        "PHASE_STARTED",
        stage=next_stage,
        balance=state["balance"],
        bar_time=iso_time(timestamp),
        processing_mode=bar_processing_mode(timestamp),
        message=f"{next_stage} is active immediately.",
    )


def manage_positions(state, bar, symbol):
    for pos in list(state["positions"]):
        if str(pos.get("symbol", "GBPUSD")) != str(symbol):
            continue
        pos["last_price"] = float(bar.close)
        if pos["direction"] == "BUY":
            stop_hit, target_hit = bar.low <= pos["sl"], bar.high >= pos["tp"]
        else:
            stop_hit, target_hit = bar.high >= pos["sl"], bar.low <= pos["tp"]
        if stop_hit:
            close_position(state, pos, pos["sl"], bar.timestamp, "SL")
        elif target_hit:
            close_position(state, pos, pos["tp"], bar.timestamp, "TP")
        elif pd.Timestamp(bar.timestamp) >= pd.Timestamp(pos["entry_bar_time"]) + pd.Timedelta(minutes=15 * 47):
            close_position(state, pos, float(bar.close), bar.timestamp, "TIME")


def enforce_controls(state, prices, timestamp):
    stage = STAGES[state["stage"]]
    current_equity = equity(state, prices)

    def close_all(reason):
        for pos in list(state["positions"]):
            symbol = str(pos.get("symbol", "GBPUSD"))
            price = float(prices.get(symbol, pos.get("last_price", pos["entry"])))
            close_position(state, pos, price, timestamp, reason)

    if stage["target"] is not None and current_equity >= stage["target"]:
        close_all("PHASE_PROFIT_LOCK")
        advance_completed_phase(state, timestamp, stage["target"])
        return True
    daily_limit = float(state.get("personal_daily_limit", 0.03))
    if state["day_start_balance"] - current_equity >= state["day_start_balance"] * daily_limit:
        close_all("PERSONAL_DAILY_STOP")
        state["locked"] = True
        state["lock_reason"] = "DAILY_LIMIT"
        event(state, "DAILY_LOCK", balance=state["balance"], bar_time=iso_time(timestamp),
              processing_mode=bar_processing_mode(timestamp))
    hard_floor = float(state.get("account_start_balance", 10000.0)) * 0.90
    if current_equity <= hard_floor and not state["locked"]:
        close_all("HARD_MAX_LOSS")
        state["locked"] = True
        state["lock_reason"] = "HARD_MAX_LOSS"
        event(state, "HARD_MAX_LOSS_LOCK", balance=state["balance"],
              bar_time=iso_time(timestamp), processing_mode=bar_processing_mode(timestamp))
    return False


def process_pending(state, bar, symbol, mt5=None, broker_symbol=None):
    for order in list(state["pending"]):
        if str(order.get("symbol", "GBPUSD")) != str(symbol):
            continue
        order.setdefault("symbol", str(symbol))
        bar_time = pd.Timestamp(bar.timestamp)
        signal_time = pd.Timestamp(order["signal_bar_time"])
        expiry_time = pd.Timestamp(order["expires_bar_time"])
        if bar_time > expiry_time:
            state["pending"].remove(order)
            event(state, "PENDING_EXPIRED", strategy=order["strategy"],
                  pending_entry=order.get("entry"), chart_path=order.get("signal_chart_path"),
                  bar_time=iso_time(bar.timestamp), processing_mode=order["processing_mode"])
            continue
        if order.get("entry_mode") == "next_open":
            if bar_time != signal_time + pd.Timedelta(minutes=15):
                continue
            order["entry"] = float(bar.open)
            if order["direction"] == "BUY":
                order["sl"] = order["entry"] - order["risk_distance"]
                order["tp"] = order["entry"] + order["risk_distance"] * order["rr"]
            else:
                order["sl"] = order["entry"] + order["risk_distance"]
                order["tp"] = order["entry"] - order["risk_distance"] * order["rr"]
        elif bar_time <= signal_time or not (bar.low <= order["entry"] <= bar.high):
            continue
        prices = dict(state.get("last_prices", {}))
        prices[str(symbol)] = float(order["entry"])
        allowed, reason = risk_allowed(state, prices)
        state["pending"].remove(order)
        if not allowed:
            event(state, "ENTRY_BLOCKED", symbol=symbol, strategy=order["strategy"], reason=reason,
                  bar_time=iso_time(bar.timestamp), processing_mode=order["processing_mode"])
            continue
        risk_dollars = state["balance"] * STAGES[state["stage"]]["risk"]
        pip_size = float(order.get("pip_size", pip_size_for(symbol)))
        pip_value = float(order.get("pip_value_per_lot", 10.0))
        if mt5 is not None and broker_symbol is not None:
            pip_value = pip_value_per_lot(mt5, broker_symbol, order["entry"], pip_size)
        stop_pips = order["risk_distance"] / pip_size
        target_pips = stop_pips * order["rr"]
        estimated_lot = risk_dollars / (stop_pips * pip_value) if stop_pips > 0 and pip_value > 0 else 0.0
        order.update({
            "risk_dollars": risk_dollars,
            "entry_bar_time": iso_time(bar.timestamp),
            "last_price": float(order["entry"]),
            "pip_size": pip_size,
            "pip_value_per_lot": pip_value,
        })
        state["positions"].append(order)
        event(state, "OPEN", symbol=symbol, strategy=order["strategy"], entry=order["entry"], sl=order["sl"],
              tp=order["tp"], risk_dollars=risk_dollars, stop_pips=stop_pips,
              target_pips=target_pips, estimated_lot=estimated_lot,
              chart_path=order.get("signal_chart_path"),
              bar_time=iso_time(bar.timestamp), processing_mode=order["processing_mode"])


def find_signals(state, bar, strategies, symbol):
    for _, strategy in strategies.iterrows():
        if not matches(bar._asdict(), strategy):
            continue
        level = fib_level(bar._asdict(), strategy["conditions"])
        label = f"{symbol}|{strategy['direction']}|{strategy['session']}|{strategy['conditions']}|RR{strategy['rr']:g}"
        if any(x["strategy"] == label for x in state["pending"] + state["positions"]):
            continue
        distance = max(float(bar.atr14), abs(float(bar.high) - float(bar.low)))
        direction = str(strategy["direction"]).upper()
        rr = float(strategy["rr"])
        entry_mode = "fib_touch" if level is not None else "next_open"
        sl = (level - distance if direction == "BUY" else level + distance) if level is not None else None
        tp = (level + distance * rr if direction == "BUY" else level - distance * rr) if level is not None else None
        wait_value = strategy.get("entry_wait_bars", 6)
        wait_bars = 6 if pd.isna(wait_value) else int(wait_value)
        mode = bar_processing_mode(bar.timestamp)
        expiry_bars = wait_bars if entry_mode == "fib_touch" else 1
        pending_order = {
            "symbol": symbol, "strategy": label, "direction": direction,
            "entry": level, "sl": sl, "tp": tp,
            "entry_mode": entry_mode, "rr": rr,
            "risk_distance": distance, "signal_bar_time": iso_time(bar.timestamp),
            "expires_bar_time": add_minutes(bar.timestamp, 15 * expiry_bars),
            "processing_mode": mode, "pip_size": pip_size_for(symbol),
        }
        if mode == "LIVE":
            pending_order["signal_chart_path"] = save_signal_chart(pending_order, bar.timestamp)
        state["pending"].append(pending_order)
        event(state, "SIGNAL", symbol=symbol, strategy=label, entry_mode=entry_mode, pending_entry=level,
              sl=sl, tp=tp, chart_path=pending_order.get("signal_chart_path"),
              bar_time=iso_time(bar.timestamp), processing_mode=mode,
              message=f"expires={add_minutes(bar.timestamp, 15 * expiry_bars)}")


def connect_mt5(terminal_path=None):
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package missing. Install with: python -m pip install MetaTrader5") from exc
    if terminal_path and Path(terminal_path).is_file():
        initialized = mt5.initialize(path=str(terminal_path))
    else:
        initialized = mt5.initialize()
    if not initialized:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    return mt5


def current_tick_prices(mt5, symbol_map, fallback_prices):
    """Return fresh midpoint marks so the phase target is checked every loop."""
    prices = dict(fallback_prices or {})
    for symbol, broker_symbol in symbol_map.items():
        try:
            tick = mt5.symbol_info_tick(broker_symbol)
        except Exception:
            tick = None
        if tick is None:
            continue
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        if bid > 0 and ask > 0:
            prices[str(symbol)] = (bid + ask) / 2.0
        elif bid > 0 or ask > 0:
            prices[str(symbol)] = bid or ask
    return prices


def get_features(mt5, broker_symbol, state_dir, symbol=None):
    symbol = str(symbol or broker_symbol)
    rates = mt5.copy_rates_from_pos(broker_symbol, mt5.TIMEFRAME_M15, 0, 12000)
    if rates is None or len(rates) < 500:
        raise RuntimeError(f"Not enough MT5 bars for {symbol} ({broker_symbol}): {mt5.last_error()}")
    raw = pd.DataFrame(rates)
    raw["timestamp"] = pd.to_datetime(raw["time"], unit="s", utc=True)
    # Some MT5 broker terminals expose candle epochs shifted to broker-local
    # time. During an open market, detect a whole-hour future offset and
    # normalize it back to UTC before session classification.
    latest = raw["timestamp"].max()
    drift_hours = (latest - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600.0
    rounded_drift = int(round(drift_hours))
    if 1 <= abs(rounded_drift) <= 14 and abs(drift_hours - rounded_drift) <= 0.35:
        raw["timestamp"] = raw["timestamp"] - pd.Timedelta(hours=rounded_drift)
        print(f"Normalized MT5 candle timestamps by {-rounded_drift:+d}h to UTC", flush=True)
    raw_path = state_dir / f"mt5_bars_{symbol}.csv"
    raw[["timestamp", "open", "high", "low", "close"]].to_csv(raw_path, index=False)
    if symbol == "GBPUSD":
        raw[["timestamp", "open", "high", "low", "close"]].to_csv(state_dir / "mt5_bars.csv", index=False)
    sys.path.insert(0, str(ROOT))
    from quant.feature_engine import build_features
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=DeprecationWarning)
        features = build_features(str(raw_path))
    features["timestamp"] = pd.to_datetime(features["timestamp"], utc=True)
    return features.iloc[:-1].reset_index(drop=True)  # exclude still-forming candle


def write_health(state_dir, state, latest_bars):
    now = pd.Timestamp.now(tz="UTC")
    bars = {str(symbol): pd.Timestamp(value) for symbol, value in latest_bars.items()}
    oldest = min(bars.values())
    health = {
        "checked_at": now.isoformat(),
        "last_closed_bar": oldest.isoformat(),
        "last_closed_bars": {symbol: value.isoformat() for symbol, value in bars.items()},
        "bar_lag_minutes": round(max((now - value).total_seconds() / 60.0 for value in bars.values()), 2),
        "stage": state["stage"],
        "phase_target": STAGES[state["stage"]]["target"],
        "completed_phases": len(state.get("phase_history", [])),
        "balance": state["balance"],
        "open_positions": len(state["positions"]),
        "pending_entries": len(state["pending"]),
        "locked": state["locked"],
        "paper_only": True,
    }
    atomic_json(health, state_dir / "health.json")


def maybe_send_daily_email(state, state_dir, latest_bar):
    london_now = datetime.now(ZoneInfo("Europe/London"))
    today = london_now.date().isoformat()
    if london_now.hour < 18 or state.get("last_daily_email_date") == today:
        return False
    if send_daily_summary(state, state_dir, latest_bar):
        state["last_daily_email_date"] = today
        return True
    return False


def print_saved_status(state, state_dir):
    closes = [x for x in state.get("events", []) if x.get("kind") == "CLOSE"]
    live = [x for x in closes if x.get("processing_mode") == "LIVE"]
    catch_up = [x for x in closes if x.get("processing_mode") == "CATCH_UP"]
    legacy = len(closes) - len(live) - len(catch_up)
    print("ALPHA MT5 PAPER STATUS")
    print("======================")
    print(f"Stage: {state['stage']}")
    print(f"Paper balance: ${state['balance']:,.2f}")
    print(f"Last processed candle: {state.get('last_bar_time')}")
    for symbol, timestamp in sorted(state.get("last_bar_times", {}).items()):
        print(f"  {symbol}: {timestamp}")
    print(f"Open positions: {len(state['positions'])}")
    print(f"Pending entries: {len(state['pending'])}")
    print(f"Closed trades: {len(closes)} (live {len(live)}, catch-up {len(catch_up)}, legacy {legacy})")
    print(f"Locked: {state['locked']}")
    print(f"Journal: {state_dir / 'trade_journal.csv'}")
    print(f"Charts: {state_dir / 'charts'}")


def cycle(args, state, state_path, mt5, strategies, symbol_map):
    events_to_process = []
    latest_bars = {}
    live_prices = current_tick_prices(mt5, symbol_map, state.get("last_prices", {}))
    state["last_prices"].update(live_prices)
    if enforce_controls(state, live_prices, pd.Timestamp.now(tz="UTC")):
        atomic_json(state, state_path)
        saved_bars = {
            symbol: timestamp
            for symbol, timestamp in state.get("last_bar_times", {}).items()
            if symbol in symbol_map and timestamp
        }
        if saved_bars:
            write_health(args.state_dir, state, saved_bars)
    symbol_order = {symbol: index for index, symbol in enumerate(symbol_map)}
    for symbol, broker_symbol in symbol_map.items():
        features = get_features(mt5, broker_symbol, args.state_dir, symbol)
        features["sequence"] = range(len(features))
        FEATURE_CACHES[symbol] = features
        latest = pd.Timestamp(features.iloc[-1]["timestamp"])
        latest_bars[symbol] = latest
        last_bar = state["last_bar_times"].get(symbol)
        if not last_bar:
            state["last_bar_times"][symbol] = latest.isoformat()
            state["last_prices"][symbol] = float(features.iloc[-1]["close"])
            event(state, "INITIALIZED", symbol=symbol, last_closed_bar=latest.isoformat())
            continue
        if symbol not in state["last_prices"]:
            known = features[features["timestamp"] <= pd.Timestamp(last_bar)]
            state["last_prices"][symbol] = float(
                known.iloc[-1]["close"] if not known.empty else features.iloc[-1]["close"]
            )
        unseen = features[features["timestamp"] > pd.Timestamp(last_bar)]
        if unseen.empty:
            state["last_prices"][symbol] = float(features.iloc[-1]["close"])
        for bar in unseen.itertuples(index=False):
            events_to_process.append((pd.Timestamp(bar.timestamp), symbol_order[symbol], symbol, broker_symbol, bar))

    ordered_events = sorted(events_to_process, key=lambda item: (item[0], item[1]))
    transition_timestamp = None
    for index, (timestamp, _, symbol, broker_symbol, bar) in enumerate(ordered_events):
        state["last_prices"][symbol] = float(bar.close)
        refresh_day(state, bar.timestamp, bar_processing_mode(bar.timestamp))
        manage_positions(state, bar, symbol)
        if enforce_controls(state, state["last_prices"], bar.timestamp):
            transition_timestamp = timestamp
        if transition_timestamp != timestamp and not state["locked"]:
            process_pending(state, bar, symbol, mt5, broker_symbol)
            symbol_strategies = strategies[strategies["symbol"] == symbol]
            find_signals(state, bar, symbol_strategies, symbol)
        state["last_bar_times"][symbol] = bar.timestamp.isoformat()
        next_timestamp = ordered_events[index + 1][0] if index + 1 < len(ordered_events) else None
        if next_timestamp != timestamp:
            if enforce_controls(state, state["last_prices"], bar.timestamp):
                transition_timestamp = timestamp

    if "GBPUSD" in state["last_bar_times"]:
        state["last_bar_time"] = state["last_bar_times"]["GBPUSD"]
    elif state["last_bar_times"]:
        state["last_bar_time"] = max(state["last_bar_times"].values())
    atomic_json(state, state_path)
    write_health(args.state_dir, state, latest_bars)
    newest_bar = max(latest_bars.values())
    if maybe_send_daily_email(state, args.state_dir, newest_bar):
        atomic_json(state, state_path)
    print(f"status symbols={','.join(symbol_map)} stage={state['stage']} balance={state['balance']:.2f} equity={equity(state, state['last_prices']):.2f} open={len(state['positions'])} pending={len(state['pending'])} days={len(state['trading_days'])} locked={state['locked']}", flush=True)


def wait_with_live_controls(args, state, state_path, mt5, symbol_map):
    """Check account controls every five seconds between full strategy scans."""
    deadline = time.monotonic() + max(int(args.interval), 5)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(5.0, remaining))
        before = (
            state["stage"], float(state["balance"]), len(state["positions"]),
            len(state["pending"]), bool(state["locked"]), state.get("lock_reason"),
            len(state.get("events", [])),
        )
        live_prices = current_tick_prices(mt5, symbol_map, state.get("last_prices", {}))
        state["last_prices"].update(live_prices)
        enforce_controls(state, live_prices, pd.Timestamp.now(tz="UTC"))
        after = (
            state["stage"], float(state["balance"]), len(state["positions"]),
            len(state["pending"]), bool(state["locked"]), state.get("lock_reason"),
            len(state.get("events", [])),
        )
        if after != before:
            atomic_json(state, state_path)
            latest_bars = {
                symbol: timestamp
                for symbol, timestamp in state.get("last_bar_times", {}).items()
                if symbol in symbol_map and timestamp
            }
            if latest_bars:
                write_health(args.state_dir, state, latest_bars)
            print(
                f"live-control stage={state['stage']} balance={state['balance']:.2f} "
                f"equity={equity(state, live_prices):.2f} open={len(state['positions'])} "
                f"pending={len(state['pending'])} locked={state['locked']}",
                flush=True,
            )


def self_test():
    from types import SimpleNamespace
    from tempfile import TemporaryDirectory
    s = initial_state()
    s["broker_day"] = "2026-01-01"
    assert risk_allowed(s, 1.25)[0]
    s["positions"] = [{"entry": 1.25, "direction": "BUY", "risk_distance": .001, "risk_dollars": 100}]
    assert risk_allowed(s, 1.25)[0]
    s["positions"].append({"entry": 1.25, "direction": "BUY", "risk_distance": .001, "risk_dollars": 100})
    assert not risk_allowed(s, 1.25)[0]
    s["stage"] = "QUALIFIED"
    assert math.isclose(STAGES[s["stage"]]["risk"], .005)
    passed = initial_state()
    passed["balance"] = 11100.0
    passed["day_start_balance"] = 10000.0
    passed["locked"] = True
    passed["lock_reason"] = "PHASE_TARGET"
    passed["pending"] = [{"strategy": "OLD_PHASE_PENDING"}]
    changed = enforce_controls(passed, {}, pd.Timestamp("2026-01-05T09:00:00Z"))
    assert changed
    assert passed["stage"] == "PHASE_2"
    assert math.isclose(passed["balance"], PHASE_START_BALANCE)
    assert not passed["locked"] and not passed["pending"]
    assert passed["phase_history"][-1]["target"] == 11030.0
    assert passed["phase_history"][-1]["actual_close_balance"] == 11100.0
    floating_pass = initial_state()
    floating_pass["balance"] = 10950.0
    floating_pass["positions"] = [{
        "symbol": "GBPUSD", "strategy": "GBPUSD|TARGET_TEST", "direction": "BUY",
        "entry": 1.0, "sl": 0.99, "tp": 1.10, "risk_distance": 0.01,
        "risk_dollars": 100.0, "entry_bar_time": "2026-01-05T08:00:00+00:00",
        "processing_mode": "LIVE",
    }]
    assert enforce_controls(
        floating_pass, {"GBPUSD": 1.008}, pd.Timestamp("2026-01-05T09:00:00Z")
    )
    assert floating_pass["stage"] == "PHASE_2" and not floating_pass["positions"]
    assert math.isclose(floating_pass["phase_history"][-1]["actual_close_balance"], 11030.0)
    phase_two = initial_state()
    phase_two["stage"] = "PHASE_2"
    phase_two["balance"] = 10520.0
    assert enforce_controls(phase_two, {}, pd.Timestamp("2026-01-06T09:00:00Z"))
    assert phase_two["stage"] == "QUALIFIED"
    assert math.isclose(phase_two["balance"], PHASE_START_BALANCE)
    s = initial_state()
    signal_time = pd.Timestamp("2026-01-05T09:00:00Z")
    s["pending"] = [{
        "strategy": "TEST", "direction": "BUY", "entry": None, "sl": None, "tp": None,
        "entry_mode": "next_open", "rr": 4.0, "risk_distance": .001,
        "signal_bar_time": signal_time.isoformat(),
        "expires_bar_time": (signal_time + pd.Timedelta(minutes=15)).isoformat(),
        "processing_mode": "LIVE",
    }]
    next_bar = SimpleNamespace(timestamp=signal_time + pd.Timedelta(minutes=15),
                               open=1.25, high=1.251, low=1.249, close=1.25)
    process_pending(s, next_bar, "GBPUSD")
    assert len(s["positions"]) == 1 and not s["pending"]
    assert s["positions"][0]["symbol"] == "GBPUSD"
    multi = initial_state()
    multi["positions"] = [
        {"symbol": "GBPUSD", "strategy": "GBPUSD|TEST", "direction": "BUY", "entry": 1.25,
         "sl": 1.24, "tp": 1.26, "risk_distance": 0.01, "risk_dollars": 100.0,
         "entry_bar_time": signal_time.isoformat(), "processing_mode": "LIVE"},
        {"symbol": "GBPJPY", "strategy": "GBPJPY|TEST", "direction": "BUY", "entry": 150.0,
         "sl": 149.0, "tp": 151.0, "risk_distance": 1.0, "risk_dollars": 100.0,
         "entry_bar_time": signal_time.isoformat(), "processing_mode": "LIVE"},
    ]
    gbp_bar = SimpleNamespace(timestamp=signal_time + pd.Timedelta(minutes=30),
                              open=1.25, high=1.261, low=1.249, close=1.26)
    manage_positions(multi, gbp_bar, "GBPUSD")
    assert len(multi["positions"]) == 1 and multi["positions"][0]["symbol"] == "GBPJPY"
    assert math.isclose(equity(multi, {"GBPJPY": 150.5}), 10150.0)
    s["positions"] = []
    s["locked"], s["lock_reason"], s["broker_day"] = True, "DAILY_LIMIT", "2026-01-05"
    refresh_day(s, pd.Timestamp("2026-01-06T01:00:00Z"), "LIVE")
    assert not s["locked"] and s["lock_reason"] is None
    original_get_features = globals()["get_features"]
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        test_state = initial_state()
        test_state["last_daily_email_date"] = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        frames = {}
        for index, symbol in enumerate(("GBPUSD", "GBPJPY", "AUDUSD")):
            frames[symbol] = pd.DataFrame(
                [{"timestamp": pd.Timestamp("2026-01-05T09:00:00Z"), "open": 1 + index,
                  "high": 1.1 + index, "low": 0.9 + index, "close": 1.0 + index}]
            )

        def fake_features(_mt5, _broker_symbol, _state_dir, symbol=None):
            return frames[str(symbol)].copy()

        try:
            globals()["get_features"] = fake_features
            args = SimpleNamespace(state_dir=folder)
            empty_strategies = pd.DataFrame(columns=["symbol", "direction", "session", "conditions", "rr"])
            symbol_map = {symbol: symbol for symbol in frames}
            cycle(args, test_state, folder / "state.json", object(), empty_strategies, symbol_map)
            assert set(test_state["last_bar_times"]) == set(frames)
            assert set(test_state["last_prices"]) == set(frames)
            assert json.loads((folder / "health.json").read_text(encoding="utf-8"))["open_positions"] == 0
        finally:
            globals()["get_features"] = original_get_features
    print("SELF-TEST PASSED: risk, automatic phase transition, timestamp entries, daily reset, and state controls")


def main():
    global EVENT_JOURNAL, CHART_DIR, EMAIL_STATE_DIR
    args = cli()
    if args.self_test:
        self_test(); return 0
    state, state_path = load_state(args.state_dir)
    EVENT_JOURNAL = args.state_dir / "trade_journal.csv"
    CHART_DIR = None if args.no_charts else args.state_dir / "charts"
    EMAIL_STATE_DIR = args.state_dir
    if args.status:
        print_saved_status(state, args.state_dir)
        return 0
    if args.stage:
        state = initial_state()
        state["stage"] = args.stage
        state["balance"] = args.reset_balance or 10000.0
        state["day_start_balance"] = state["balance"]
        state["account_start_balance"] = state["balance"]
        atomic_json(state, state_path)
        print(f"stage set to {args.stage}; paper balance reset to {state['balance']:.2f}")
        return 0
    strategies = pd.read_csv(args.shortlist)
    if "symbol" not in strategies.columns:
        strategies.insert(0, "symbol", args.symbol)
    strategies["symbol"] = strategies["symbol"].astype(str).str.strip().str.upper()
    required = {"symbol", "direction", "session", "conditions", "rr"}
    missing = sorted(required.difference(strategies.columns))
    if missing:
        raise RuntimeError(f"Shortlist is missing required columns: {', '.join(missing)}")
    if "robust_score" in strategies.columns:
        strategies = strategies.sort_values("robust_score", ascending=False, kind="stable").reset_index(drop=True)
    mt5 = connect_mt5(args.terminal_path)
    try:
        symbol_map = {}
        for symbol in strategies["symbol"].drop_duplicates():
            broker_symbol = resolve_symbol(mt5, symbol)
            if not mt5.symbol_select(broker_symbol, True):
                raise RuntimeError(f"MT5 could not select {broker_symbol}: {mt5.last_error()}")
            symbol_map[symbol] = broker_symbol
        event(state, "BOT_STARTED", balance=state["balance"],
              message=f"MT5 connected; paper-only monitoring is active for {', '.join(symbol_map)}")
        atomic_json(state, state_path)
        while True:
            cycle(args, state, state_path, mt5, strategies, symbol_map)
            if args.once:
                break
            wait_with_live_controls(args, state, state_path, mt5, symbol_map)
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            from sentry_setup import init_sentry
            if init_sentry():
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
        except Exception:
            pass
        try:
            send_email(
                "Paper Bot - STOPPED WITH ERROR",
                f"The paper bot stopped.\n\nError: {exc}\nTime UTC: {datetime.now(timezone.utc).isoformat()}",
                EMAIL_STATE_DIR or DEFAULT_STATE,
            )
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
