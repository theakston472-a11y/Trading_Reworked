"""MT5-backed GBPUSD paper bot for the funded shortlist.

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
    "PHASE_1": {"risk": 0.01, "target": 11020.0},
    "PHASE_2": {"risk": 0.01, "target": 10520.0},
    "QUALIFIED": {"risk": 0.005, "target": None},
}
MAGIC = 260818
PIP_SIZE = 0.0001
LIVE_BAR_MAX_AGE_MINUTES = 35
EVENT_JOURNAL = None
CHART_DIR = None
FEATURE_CACHE = None
EMAIL_STATE_DIR = None
JOURNAL_FIELDS = [
    "time", "kind", "processing_mode", "bar_time", "strategy", "reason",
    "entry_mode", "entry", "sl", "tp", "price", "stop_pips",
    "target_pips", "estimated_lot", "risk_dollars", "result_r", "pnl",
    "balance", "day", "message", "pending_entry", "chart_path",
]


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="GBPUSD")
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


def atomic_json(value, path):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def initial_state():
    return {
        "stage": "PHASE_1", "balance": 10000.0, "day_start_balance": 10000.0,
        "account_start_balance": 10000.0,
        "personal_daily_limit": 0.03,
        "broker_day": None, "last_bar_time": None, "trading_days": [],
        "positions": [], "pending": [], "events": [], "locked": False,
        "lock_reason": None, "last_daily_email_date": None,
    }


def load_state(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else initial_state()
    defaults = initial_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
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


def equity(state, price):
    floating = 0.0
    for pos in state["positions"]:
        move = price - pos["entry"]
        if pos["direction"] == "SELL":
            move = -move
        floating += move / pos["risk_distance"] * pos["risk_dollars"]
    return state["balance"] + floating


def risk_allowed(state, price):
    if state["locked"] or len(state["positions"]) >= 2:
        return False, "locked or two positions already open"
    loss = state["day_start_balance"] - equity(state, price)
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
    if CHART_DIR is None or FEATURE_CACHE is None:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        frame = FEATURE_CACHE
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
            height = max(abs(row.close - row.open), PIP_SIZE * 0.05)
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
        title = f"{pos['strategy']} | {reason} | {pos.get('processing_mode', 'UNKNOWN')}"
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
    if CHART_DIR is None or FEATURE_CACHE is None:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        frame = FEATURE_CACHE
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
            height = max(abs(row.close - row.open), PIP_SIZE * 0.05)
            ax.add_patch(Rectangle((i - 0.32, bottom), 0.64, height,
                                   facecolor=colour, edgecolor=colour,
                                   linewidth=0.7, zorder=3))

        strategy_text = str(order["strategy"])
        conditions = strategy_text.split("|")[2] if strategy_text.count("|") >= 2 else strategy_text
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
                distance_pips = abs(current_price - entry) / PIP_SIZE
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
        label_parts = strategy_text.split("|")
        session_name = label_parts[1] if len(label_parts) > 1 else "Unknown session"
        chart_status = str(order.get("chart_status", "PENDING"))
        ax.set_title(
            f"{chart_status} {order['direction']} | {session_name} | {order['rr']:g}R target | "
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
    event(state, "CLOSE", strategy=pos["strategy"], reason=reason, price=price,
          result_r=result_r, pnl=pnl, balance=state["balance"],
          bar_time=iso_time(timestamp), processing_mode=pos.get("processing_mode", "UNKNOWN"),
          chart_path=chart_path, message=f"chart={chart_path}" if chart_path else None)


def manage_positions(state, bar):
    for pos in list(state["positions"]):
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


def enforce_controls(state, price, timestamp):
    stage = STAGES[state["stage"]]
    current_equity = equity(state, price)
    if stage["target"] is not None and current_equity >= stage["target"]:
        for pos in list(state["positions"]):
            close_position(state, pos, price, timestamp, "PHASE_PROFIT_LOCK")
        state["locked"] = True
        state["lock_reason"] = "PHASE_TARGET"
        event(state, "PHASE_LOCKED", stage=state["stage"], balance=state["balance"])
    daily_limit = float(state.get("personal_daily_limit", 0.03))
    if state["day_start_balance"] - current_equity >= state["day_start_balance"] * daily_limit:
        for pos in list(state["positions"]):
            close_position(state, pos, price, timestamp, "PERSONAL_DAILY_STOP")
        state["locked"] = True
        state["lock_reason"] = "DAILY_LIMIT"
        event(state, "DAILY_LOCK", balance=state["balance"], bar_time=iso_time(timestamp),
              processing_mode=bar_processing_mode(timestamp))
    hard_floor = float(state.get("account_start_balance", 10000.0)) * 0.90
    if current_equity <= hard_floor and not state["locked"]:
        for pos in list(state["positions"]):
            close_position(state, pos, price, timestamp, "HARD_MAX_LOSS")
        state["locked"] = True
        state["lock_reason"] = "HARD_MAX_LOSS"
        event(state, "HARD_MAX_LOSS_LOCK", balance=state["balance"],
              bar_time=iso_time(timestamp), processing_mode=bar_processing_mode(timestamp))


def process_pending(state, bar):
    for order in list(state["pending"]):
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
        allowed, reason = risk_allowed(state, order["entry"])
        state["pending"].remove(order)
        if not allowed:
            event(state, "ENTRY_BLOCKED", strategy=order["strategy"], reason=reason,
                  bar_time=iso_time(bar.timestamp), processing_mode=order["processing_mode"])
            continue
        risk_dollars = state["balance"] * STAGES[state["stage"]]["risk"]
        stop_pips = order["risk_distance"] / PIP_SIZE
        target_pips = stop_pips * order["rr"]
        estimated_lot = risk_dollars / (stop_pips * 10.0) if stop_pips > 0 else 0.0
        order.update({"risk_dollars": risk_dollars, "entry_bar_time": iso_time(bar.timestamp)})
        state["positions"].append(order)
        event(state, "OPEN", strategy=order["strategy"], entry=order["entry"], sl=order["sl"],
              tp=order["tp"], risk_dollars=risk_dollars, stop_pips=stop_pips,
              target_pips=target_pips, estimated_lot=estimated_lot,
              chart_path=order.get("signal_chart_path"),
              bar_time=iso_time(bar.timestamp), processing_mode=order["processing_mode"])


def find_signals(state, bar, strategies):
    for _, strategy in strategies.iterrows():
        if not matches(bar._asdict(), strategy):
            continue
        level = fib_level(bar._asdict(), strategy["conditions"])
        label = f"{strategy['direction']}|{strategy['session']}|{strategy['conditions']}|RR{strategy['rr']:g}"
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
            "strategy": label, "direction": direction, "entry": level, "sl": sl, "tp": tp,
            "entry_mode": entry_mode, "rr": rr,
            "risk_distance": distance, "signal_bar_time": iso_time(bar.timestamp),
            "expires_bar_time": add_minutes(bar.timestamp, 15 * expiry_bars),
            "processing_mode": mode,
        }
        if mode == "LIVE":
            pending_order["signal_chart_path"] = save_signal_chart(pending_order, bar.timestamp)
        state["pending"].append(pending_order)
        event(state, "SIGNAL", strategy=label, entry_mode=entry_mode, pending_entry=level,
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


def get_features(mt5, symbol, state_dir):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 12000)
    if rates is None or len(rates) < 500:
        raise RuntimeError(f"Not enough MT5 bars for {symbol}: {mt5.last_error()}")
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
    raw_path = state_dir / "mt5_bars.csv"
    raw[["timestamp", "open", "high", "low", "close"]].to_csv(raw_path, index=False)
    sys.path.insert(0, str(ROOT))
    from quant.feature_engine import build_features
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=DeprecationWarning)
        features = build_features(str(raw_path))
    features["timestamp"] = pd.to_datetime(features["timestamp"], utc=True)
    return features.iloc[:-1].reset_index(drop=True)  # exclude still-forming candle


def write_health(state_dir, state, latest_bar):
    now = pd.Timestamp.now(tz="UTC")
    latest = pd.Timestamp(latest_bar)
    health = {
        "checked_at": now.isoformat(),
        "last_closed_bar": latest.isoformat(),
        "bar_lag_minutes": round((now - latest).total_seconds() / 60.0, 2),
        "stage": state["stage"],
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
    print(f"Open positions: {len(state['positions'])}")
    print(f"Pending entries: {len(state['pending'])}")
    print(f"Closed trades: {len(closes)} (live {len(live)}, catch-up {len(catch_up)}, legacy {legacy})")
    print(f"Locked: {state['locked']}")
    print(f"Journal: {state_dir / 'trade_journal.csv'}")
    print(f"Charts: {state_dir / 'charts'}")


def cycle(args, state, state_path, mt5, strategies):
    global FEATURE_CACHE
    features = get_features(mt5, args.symbol, args.state_dir)
    FEATURE_CACHE = features
    features["sequence"] = range(len(features))
    if state["last_bar_time"] is None:
        state["last_bar_time"] = features.iloc[-1]["timestamp"].isoformat()
        event(state, "INITIALIZED", last_closed_bar=state["last_bar_time"])
        atomic_json(state, state_path)
        return
    unseen = features[features["timestamp"] > pd.Timestamp(state["last_bar_time"])]
    for bar in unseen.itertuples(index=False):
        refresh_day(state, bar.timestamp, bar_processing_mode(bar.timestamp))
        manage_positions(state, bar)
        process_pending(state, bar)
        find_signals(state, bar, strategies)
        enforce_controls(state, float(bar.close), bar.timestamp)
        state["last_bar_time"] = bar.timestamp.isoformat()
    atomic_json(state, state_path)
    write_health(args.state_dir, state, features.iloc[-1]["timestamp"])
    if maybe_send_daily_email(state, args.state_dir, features.iloc[-1]["timestamp"]):
        atomic_json(state, state_path)
    print(f"status stage={state['stage']} balance={state['balance']:.2f} equity={equity(state, float(features.iloc[-1]['close'])):.2f} open={len(state['positions'])} pending={len(state['pending'])} days={len(state['trading_days'])} locked={state['locked']}", flush=True)


def self_test():
    from types import SimpleNamespace
    s = initial_state()
    s["broker_day"] = "2026-01-01"
    assert risk_allowed(s, 1.25)[0]
    s["positions"] = [{"entry": 1.25, "direction": "BUY", "risk_distance": .001, "risk_dollars": 100}]
    assert risk_allowed(s, 1.25)[0]
    s["positions"].append({"entry": 1.25, "direction": "BUY", "risk_distance": .001, "risk_dollars": 100})
    assert not risk_allowed(s, 1.25)[0]
    s["stage"] = "QUALIFIED"
    assert math.isclose(STAGES[s["stage"]]["risk"], .005)
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
    process_pending(s, next_bar)
    assert len(s["positions"]) == 1 and not s["pending"]
    s["positions"] = []
    s["locked"], s["lock_reason"], s["broker_day"] = True, "DAILY_LIMIT", "2026-01-05"
    refresh_day(s, pd.Timestamp("2026-01-06T01:00:00Z"), "LIVE")
    assert not s["locked"] and s["lock_reason"] is None
    print("SELF-TEST PASSED: risk, timestamp entries, daily reset, and state controls")


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
    mt5 = connect_mt5(args.terminal_path)
    try:
        event(state, "BOT_STARTED", balance=state["balance"],
              message="MT5 connected; paper-only monitoring is active")
        atomic_json(state, state_path)
        while True:
            cycle(args, state, state_path, mt5, strategies)
            if args.once:
                break
            time.sleep(max(args.interval, 5))
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
