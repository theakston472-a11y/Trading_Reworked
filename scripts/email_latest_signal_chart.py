"""Rebuild and email the latest live paper-bot signal chart for a UK date."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = ROOT / "results" / "alpha_mt5_paper"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import alpha_mt5_paper_bot as bot
from paper_bot_email import send_email


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--date", help="UK date in YYYY-MM-DD form; defaults to today")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def event_time(event):
    value = event.get("bar_time") or event.get("time")
    return pd.Timestamp(value) if value else None


def parse_strategy(label):
    parts = str(label).split("|")
    if len(parts) < 4 or not parts[-1].upper().startswith("RR"):
        raise ValueError(f"Could not parse strategy label: {label}")
    return parts[0].upper(), parts[1], parts[2], float(parts[-1][2:])


def expiry_from_event(event, signal_time, entry_mode):
    match = re.search(r"expires=([^\s]+)", str(event.get("message") or ""))
    if match:
        return pd.Timestamp(match.group(1))
    wait_bars = 6 if entry_mode == "fib_touch" else 1
    return signal_time + pd.Timedelta(minutes=15 * wait_bars)


def reconstruct_order(event, signal_row):
    direction, _session, conditions, rr = parse_strategy(event["strategy"])
    entry_mode = event.get("entry_mode") or "fib_touch"
    entry = event.get("pending_entry")
    if entry is None and entry_mode == "fib_touch":
        entry = bot.fib_level(signal_row, conditions)
    entry = float(entry) if entry is not None and pd.notna(entry) else None
    risk_distance = max(float(signal_row["atr14"]),
                        abs(float(signal_row["high"]) - float(signal_row["low"])))
    sl = event.get("sl")
    tp = event.get("tp")
    if entry is not None:
        sl = float(sl) if sl is not None else entry + (-risk_distance if direction == "BUY" else risk_distance)
        tp = float(tp) if tp is not None else entry + (risk_distance * rr if direction == "BUY" else -risk_distance * rr)
    signal_time = event_time(event)
    return {
        "strategy": event["strategy"],
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "entry_mode": entry_mode,
        "rr": rr,
        "risk_distance": risk_distance,
        "signal_bar_time": signal_time.isoformat(),
        "expires_bar_time": expiry_from_event(event, signal_time, entry_mode).isoformat(),
        "processing_mode": "LIVE",
    }


def signal_status(state, signal_event):
    strategy = signal_event.get("strategy")
    signal_time = event_time(signal_event)
    if any(item.get("strategy") == strategy for item in state.get("pending", [])):
        return "PENDING"
    if any(item.get("strategy") == strategy for item in state.get("positions", [])):
        return "OPEN"
    later = [
        item for item in state.get("events", [])
        if item.get("strategy") == strategy
        and event_time(item) is not None
        and event_time(item) >= signal_time
    ]
    if any(item.get("kind") == "CLOSE" for item in later):
        return "CLOSED"
    if any(item.get("kind") == "PENDING_EXPIRED" for item in later):
        return "EXPIRED (WAS PENDING)"
    if any(item.get("kind") == "ENTRY_BLOCKED" for item in later):
        return "ENTRY BLOCKED"
    return "SIGNAL"


def load_features(state_dir):
    raw_path = state_dir / "mt5_bars.csv"
    if not raw_path.is_file():
        raise FileNotFoundError(f"Saved MT5 candles were not found: {raw_path}")
    from quant.feature_engine import build_features
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        features = build_features(str(raw_path))
    features["timestamp"] = pd.to_datetime(features["timestamp"], utc=True)
    return features.reset_index(drop=True)


def self_test():
    signal_time = pd.Timestamp("2026-09-15T13:30:00Z")
    event = {
        "kind": "SIGNAL",
        "strategy": "SELL|New York|below_ema100+bearish_fib_618_rejection+small_range|RR2",
        "entry_mode": "fib_touch",
        "pending_entry": 1.3540,
        "bar_time": signal_time.isoformat(),
        "message": f"expires={(signal_time + pd.Timedelta(minutes=90)).isoformat()}",
    }
    row = {"atr14": 0.001, "high": 1.3542, "low": 1.3538}
    order = reconstruct_order(event, row)
    assert math.isclose(order["sl"], 1.3550)
    assert math.isclose(order["tp"], 1.3520)
    assert pd.Timestamp(order["expires_bar_time"]) == signal_time + pd.Timedelta(minutes=90)
    print("SELF-TEST PASSED: latest signal reconstruction")


def main():
    args = cli()
    if args.self_test:
        self_test()
        return 0
    state_path = args.state_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    uk_zone = ZoneInfo("Europe/London")
    wanted_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(uk_zone).date()
    signals = [
        event for event in state.get("events", [])
        if event.get("kind") == "SIGNAL"
        and event.get("processing_mode") != "CATCH_UP"
        and event_time(event) is not None
        and event_time(event).tz_convert(uk_zone).date() == wanted_date
    ]
    if not signals:
        raise RuntimeError(f"No live paper-bot signal was recorded on {wanted_date}.")
    signal_event = signals[-1]
    features = load_features(args.state_dir)
    signal_time = event_time(signal_event)
    rows = features[features["timestamp"] == signal_time]
    if rows.empty:
        raise RuntimeError(f"Saved features do not contain the signal candle {signal_time}.")
    order = reconstruct_order(signal_event, rows.iloc[0])
    status = signal_status(state, signal_event)
    order["chart_status"] = status
    bot.FEATURE_CACHE = features
    bot.CHART_DIR = args.state_dir / "charts"
    chart_path = bot.save_signal_chart(order, signal_time)
    if not chart_path:
        raise RuntimeError("The signal chart could not be generated.")
    body = "\n".join(
        [
            "PAPER BOT SIGNAL CHART",
            "",
            f"UK date: {wanted_date}",
            f"Current status: {status}",
            f"Strategy: {signal_event.get('strategy')}",
            f"Signal candle: {signal_time}",
            f"Entry required: {order.get('entry')}",
            f"Stop loss: {order.get('sl')}",
            f"Take profit: {order.get('tp')}",
            "",
            "The chart is attached. This remains paper-only; no broker order was sent.",
        ]
    )
    if not send_email(
        f"Paper Bot - {wanted_date} Signal Chart - {status}",
        body,
        args.state_dir,
        chart_path,
    ):
        raise RuntimeError("The chart was created but the email could not be sent.")
    print("LATEST SIGNAL CHART EMAILED")
    print(f"Status: {status}")
    print(f"Chart: {chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
