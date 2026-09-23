"""Download broker-matched M15 history for new research symbols from MT5.

This script is intentionally read-only with respect to the trading account.  It
only requests historical bars and writes new symbol-specific CSV files.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "research_symbols"
DEFAULT_TERMINAL = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
BAR_COLUMNS = ["timestamp", "open", "high", "low", "close"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download full MT5 M15 history for research symbols."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["GBPJPY", "AUDUSD"],
        help="Symbols to download (default: GBPJPY AUDUSD).",
    )
    parser.add_argument(
        "--start",
        default="2020-01-01",
        help="UTC start date in YYYY-MM-DD format (default: 2020-01-01).",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional UTC end date in YYYY-MM-DD format (default: now).",
    )
    parser.add_argument(
        "--terminal",
        type=Path,
        default=DEFAULT_TERMINAL,
        help="Path to terminal64.exe.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for new symbol-specific CSV files.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=180,
        help="Number of calendar days requested per MT5 call.",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def utc_date(value: str, *, inclusive_end: bool = False) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if inclusive_end:
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def normalized_symbol(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def resolve_symbol(mt5, requested: str) -> str:
    """Resolve common broker prefixes/suffixes without silently changing pair."""
    if mt5.symbol_info(requested) is not None:
        return requested

    wanted = normalized_symbol(requested)
    candidates = []
    for item in mt5.symbols_get() or []:
        name = str(item.name)
        normalized = normalized_symbol(name)
        if normalized == wanted or normalized.startswith(wanted):
            candidates.append(name)

    if not candidates:
        raise RuntimeError(f"MT5 does not provide a symbol matching {requested!r}.")

    candidates.sort(key=lambda name: (len(name), name))
    return candidates[0]


def download_symbol(mt5, symbol: str, start: datetime, end: datetime, chunk_days: int) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    current = start
    request_number = 0

    while current < end:
        request_end = min(current + timedelta(days=chunk_days), end)
        request_number += 1
        rates = mt5.copy_rates_range(
            symbol,
            mt5.TIMEFRAME_M15,
            current,
            request_end,
        )
        if rates is None:
            raise RuntimeError(
                f"MT5 failed while downloading {symbol} request {request_number}: "
                f"{mt5.last_error()}"
            )
        if len(rates):
            frame = pd.DataFrame(rates)
            frame["timestamp"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            chunks.append(frame[BAR_COLUMNS])
        print(
            f"{symbol}: request {request_number} "
            f"{current.date()} to {request_end.date()} ({len(rates)} bars)",
            flush=True,
        )
        current = request_end

    if not chunks:
        raise RuntimeError(f"MT5 returned no historical bars for {symbol}.")

    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(subset="timestamp", keep="last")
    result = result.sort_values("timestamp").reset_index(drop=True)
    result = result.dropna(subset=BAR_COLUMNS)
    if result.empty:
        raise RuntimeError(f"No valid OHLC rows remained for {symbol}.")
    if not result["timestamp"].is_monotonic_increasing:
        raise RuntimeError(f"Timestamps are not ordered for {symbol}.")
    return result


def safe_output_path(directory: Path, requested_symbol: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9]+", "", requested_symbol.upper())
    return directory / f"{safe}_M15_2020_present.csv"


def write_summary(output_dir: Path, rows: list[dict]) -> None:
    summary_csv = output_dir / "download_summary.csv"
    summary_json = output_dir / "download_summary.json"
    pd.DataFrame(rows).to_csv(summary_csv, index=False)
    summary_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Summary: {summary_csv}")


def self_test() -> None:
    assert normalized_symbol("GBP/JPY.a") == "GBPJPYA"
    assert utc_date("2020-01-01").tzinfo == timezone.utc
    assert safe_output_path(Path("data"), "GBP/JPY").name == "GBPJPY_M15_2020_present.csv"
    print("SELF-TEST PASSED: multi-symbol MT5 downloader")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.chunk_days < 1:
        raise SystemExit("--chunk-days must be at least 1.")

    start = utc_date(args.start)
    end = utc_date(args.end, inclusive_end=True) if args.end else datetime.now(timezone.utc)
    if end <= start:
        raise SystemExit("The end date must be after the start date.")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise SystemExit(
            "MetaTrader5 is not installed in this Python environment. "
            "Run this with the VPS project's .venv Python."
        ) from exc

    terminal = args.terminal.resolve()
    if not terminal.is_file():
        raise SystemExit(f"MT5 terminal was not found: {terminal}")
    if not mt5.initialize(path=str(terminal)):
        raise SystemExit(f"MT5 initialization failed: {mt5.last_error()}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict] = []
    try:
        for requested in args.symbols:
            actual = resolve_symbol(mt5, requested)
            if not mt5.symbol_select(actual, True):
                raise RuntimeError(f"MT5 could not select {actual}: {mt5.last_error()}")
            print(f"\nDownloading {requested} using broker symbol {actual}...")
            frame = download_symbol(mt5, actual, start, end, args.chunk_days)
            output_path = safe_output_path(output_dir, requested)
            frame.to_csv(output_path, index=False)
            summaries.append(
                {
                    "requested_symbol": requested.upper(),
                    "broker_symbol": actual,
                    "timeframe": "M15",
                    "rows": len(frame),
                    "first_bar_utc": frame.iloc[0]["timestamp"].isoformat(),
                    "last_bar_utc": frame.iloc[-1]["timestamp"].isoformat(),
                    "output_file": str(output_path),
                }
            )
            print(f"Saved {len(frame):,} bars: {output_path}")
        write_summary(output_dir, summaries)
    finally:
        mt5.shutdown()

    print("\nDOWNLOAD COMPLETE — no orders were sent; account access was read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
