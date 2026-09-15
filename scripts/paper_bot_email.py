"""Credential-free email integration for the VPS paper bot.

The Yahoo app password is stored by PowerShell as a Windows DPAPI-protected
credential. Python passes only a temporary subject/body payload to the sender.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


INTERESTING_EVENTS = {
    "BOT_STARTED",
    "SIGNAL",
    "PENDING_EXPIRED",
    "OPEN",
    "CLOSE",
    "PHASE_LOCKED",
    "DAILY_LOCK",
    "HARD_MAX_LOSS_LOCK",
}


def is_configured(state_dir: Path) -> bool:
    state_dir = Path(state_dir)
    return (state_dir / "email_config.json").is_file() and (
        state_dir / "email_credentials.xml"
    ).is_file()


def send_email(
    subject: str,
    body: str,
    state_dir: Path,
    attachment_path: str | Path | None = None,
) -> bool:
    state_dir = Path(state_dir)
    if not is_configured(state_dir):
        return False
    sender = Path(__file__).with_name("send_paper_bot_email.ps1")
    if not sender.is_file():
        print(f"WARNING: email sender missing: {sender}", file=sys.stderr, flush=True)
        return False

    payload = state_dir / f".email_payload_{uuid4().hex}.json"
    attachment = Path(attachment_path) if attachment_path else None
    payload_data = {"subject": str(subject), "body": str(body)}
    if attachment is not None and attachment.is_file():
        payload_data["attachment_path"] = str(attachment)
    payload.write_text(
        json.dumps(payload_data, ensure_ascii=False),
        encoding="utf-8",
    )
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(sender),
        "-PayloadPath",
        str(payload),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "unknown sender error").strip()
            print(f"WARNING: email could not be sent: {message}", file=sys.stderr, flush=True)
            return False
        return True
    except Exception as exc:
        print(f"WARNING: email could not be sent: {exc}", file=sys.stderr, flush=True)
        return False
    finally:
        payload.unlink(missing_ok=True)


def _field_lines(details: dict) -> list[str]:
    labels = [
        ("strategy", "Strategy"),
        ("entry_mode", "Entry mode"),
        ("pending_entry", "Price required for entry"),
        ("entry", "Entry"),
        ("sl", "Stop loss"),
        ("tp", "Take profit"),
        ("reason", "Reason"),
        ("result_r", "Result R"),
        ("pnl", "P/L"),
        ("balance", "Paper balance"),
        ("bar_time", "Candle time"),
        ("processing_mode", "Mode"),
        ("message", "Details"),
    ]
    return [f"{label}: {details[key]}" for key, label in labels if details.get(key) is not None]


def notify_event(kind: str, details: dict, state: dict, state_dir: Path) -> bool:
    if kind not in INTERESTING_EVENTS or details.get("processing_mode") == "CATCH_UP":
        return False
    name = kind.replace("_", " ").title()
    strategy = details.get("strategy")
    chart_path = details.get("chart_path")
    subject = f"Paper Bot - {name}" + (f" - {strategy}" if strategy else "")
    lines = [
        f"Event: {name}",
        f"Time UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Stage: {state.get('stage')}",
        f"Paper balance: {state.get('balance', 0):,.2f}",
        f"Open positions: {len(state.get('positions', []))}",
        f"Pending entries: {len(state.get('pending', []))}",
        "",
        *_field_lines(details),
        "Chart: attached" if chart_path and Path(chart_path).is_file() else "",
        "",
        "Paper-only monitoring: no broker order was sent.",
    ]
    return send_email(subject, "\n".join(lines), state_dir, chart_path)


def send_daily_summary(state: dict, state_dir: Path, last_bar_time) -> bool:
    closes = [item for item in state.get("events", []) if item.get("kind") == "CLOSE"]
    london_now = datetime.now(ZoneInfo("Europe/London"))

    def is_live_close_today(item: dict) -> bool:
        if item.get("processing_mode") == "CATCH_UP":
            return False
        try:
            event_time = datetime.fromisoformat(str(item.get("time")))
            return event_time.astimezone(ZoneInfo("Europe/London")).date() == london_now.date()
        except (TypeError, ValueError):
            return False

    live_closes = [item for item in closes if item.get("processing_mode") != "CATCH_UP"]
    today_closes = [item for item in live_closes if is_live_close_today(item)]
    today_result_r = sum(float(item.get("result_r", 0) or 0) for item in today_closes)
    today_wins = sum(float(item.get("result_r", 0) or 0) > 0 for item in today_closes)
    today_losses = sum(float(item.get("result_r", 0) or 0) < 0 for item in today_closes)
    body = "\n".join(
        [
            "DAILY PAPER BOT SUMMARY",
            "",
            f"Time UK: {london_now.isoformat()}",
            f"Stage: {state.get('stage')}",
            f"Paper balance: {state.get('balance', 0):,.2f}",
            f"Open positions: {len(state.get('positions', []))}",
            f"Pending entries: {len(state.get('pending', []))}",
            f"Live trades closed today: {len(today_closes)}",
            f"Today's live result: {today_result_r:+.3f}R ({today_wins} wins / {today_losses} losses)",
            f"All live trades recorded: {len(live_closes)}",
            f"Last processed candle: {last_bar_time}",
            f"Locked: {state.get('locked')}",
            "",
            "Catch-up/replayed trades are excluded from today's figures.",
            "Paper-only monitoring: no broker order was sent.",
        ]
    )
    return send_email("Paper Bot - Daily Summary", body, state_dir)
