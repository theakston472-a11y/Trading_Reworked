"""Quality-screen and promote balanced multi-session Top 100 pools."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SYMBOLS = ("GBPJPY", "AUDUSD")
SESSIONS = ("Asia", "London", "New York")
DIRECTIONS = ("BUY", "SELL")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--per-direction", type=int, default=50)
    parser.add_argument("--session-cap", type=int, default=20)
    return parser.parse_args()


def pool_path(discovery: Path, symbol: str, session: str, direction: str) -> Path:
    session_key = session.lower().replace(" ", "_")
    return discovery / f"{symbol.lower()}_{session_key}_{direction.lower()}.csv"


def quality_screen(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    numeric = (
        "score",
        "trades",
        "net_r",
        "expectancy_r",
        "min_profit_factor",
        "worst_drawdown_r",
        "avg_trades_day",
        "positive_periods",
        "periods_tested",
    )
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result[
        (result["trades"] >= 30)
        & (result["positive_periods"] == result["periods_tested"])
        & (result["min_profit_factor"] >= 1.0)
    ].copy()
    result = result.drop_duplicates(["direction", "session", "conditions"])
    sort_columns = [
        "score",
        "min_profit_factor",
        "expectancy_r",
        "net_r",
        "trades",
    ]
    return result.sort_values(sort_columns, ascending=False, kind="stable")


def balanced_direction_pool(frame: pd.DataFrame, limit: int, session_cap: int) -> pd.DataFrame:
    selected = []
    selected_keys: set[tuple[str, str, str]] = set()
    for session in SESSIONS:
        session_rows = frame[frame["session"].eq(session)].head(session_cap)
        for _, row in session_rows.iterrows():
            key = (str(row["direction"]), str(row["session"]), str(row["conditions"]))
            if key not in selected_keys:
                selected.append(row)
                selected_keys.add(key)
    if len(selected) < limit:
        for _, row in frame.iterrows():
            key = (str(row["direction"]), str(row["session"]), str(row["conditions"]))
            if key in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(key)
            if len(selected) >= limit:
                break
    if not selected:
        return frame.head(0).copy()
    promoted = pd.DataFrame(selected)
    return promoted.sort_values("score", ascending=False, kind="stable").head(limit)


def main() -> int:
    args = parse_args()
    run = args.run_dir.resolve()
    discovery = run / "discovery"
    promotion = run / "promotion"
    promotion.mkdir(parents=True, exist_ok=True)

    for symbol in SYMBOLS:
        frames = []
        counts = []
        for session in SESSIONS:
            for direction in DIRECTIONS:
                path = pool_path(discovery, symbol, session, direction)
                if not path.is_file():
                    raise FileNotFoundError(path)
                frame = pd.read_csv(path)
                frame.insert(0, "symbol", symbol)
                screened = quality_screen(frame)
                frames.append(screened)
                counts.append(
                    {
                        "symbol": symbol,
                        "session": session,
                        "direction": direction,
                        "saved_candidates": len(frame),
                        "quality_survivors": len(screened),
                    }
                )

        screened_all = pd.concat(frames, ignore_index=True)
        symbol_dir = promotion / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        screened_all.to_csv(symbol_dir / "discovery_screened.csv", index=False)
        pd.DataFrame(counts).to_csv(symbol_dir / "discovery_counts.csv", index=False)

        promoted_parts = []
        for direction in DIRECTIONS:
            direction_pool = screened_all[screened_all["direction"].eq(direction)]
            promoted_parts.append(
                balanced_direction_pool(
                    direction_pool,
                    limit=args.per_direction,
                    session_cap=args.session_cap,
                )
            )
        top = pd.concat(promoted_parts, ignore_index=True)
        top = top.sort_values("score", ascending=False, kind="stable").reset_index(drop=True)
        top.insert(0, "top100_rank", range(1, len(top) + 1))
        top.to_csv(symbol_dir / "top100_candidates.csv", index=False)

        print(f"{symbol}: promoted {len(top)} candidates")
        print(
            top.groupby(["direction", "session"])
            .size()
            .rename("candidates")
            .reset_index()
            .to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
