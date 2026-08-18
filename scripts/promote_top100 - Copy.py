from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

DEFAULT_TOP = 100

TARGET_POOLS = [
    ("New York", "BUY"),
    ("New York", "SELL"),
    ("London", "BUY"),
    ("London", "SELL"),
]


def load_candidates(discovery_dir):
    files = sorted(
        Path(discovery_dir).rglob("*_candidates.csv")
    )

    if not files:
        raise SystemExit(
            f"No discovery candidate CSV files found in {discovery_dir}"
        )

    frames = []

    for path in files:
        try:
            df = pd.read_csv(path)
        except Exception as exc:
            print(f"WARNING: Could not read {path}: {exc}")
            continue

        if df.empty:
            continue

        print(f"Loaded {len(df):,} candidates: {path}")
        frames.append(df)

    if not frames:
        raise SystemExit("No usable candidate CSV files found.")

    df = pd.concat(frames, ignore_index=True)

    required = [
        "direction",
        "session",
        "conditions",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise SystemExit(
            "Missing required columns: "
            + ", ".join(missing)
        )

    for col in [
        "score",
        "positive_periods",
        "trades",
        "net_r",
        "expectancy_r",
        "min_profit_factor",
        "worst_drawdown_r",
        "avg_trades_day",
        "condition_count",
        "rr",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    return df.drop_duplicates()


def promote_pool(df, session, direction, top_n):
    pool = df[
        (
            df["session"]
            .astype(str)
            .str.strip()
            .str.lower()
            == session.lower()
        )
        &
        (
            df["direction"]
            .astype(str)
            .str.strip()
            .str.upper()
            == direction.upper()
        )
    ].copy()

    if pool.empty:
        return pool

    duplicate_cols = [
        col
        for col in [
            "direction",
            "session",
            "conditions",
            "rr",
        ]
        if col in pool.columns
    ]

    pool = pool.drop_duplicates(
        subset=duplicate_cols
    )

    sort_cols = [
        col
        for col in [
            "score",
            "positive_periods",
            "trades",
            "net_r",
            "expectancy_r",
            "min_profit_factor",
        ]
        if col in pool.columns
    ]

    if sort_cols:
        pool = pool.sort_values(
            sort_cols,
            ascending=False,
            kind="stable",
        )

    pool = pool.head(top_n).reset_index(drop=True)

    pool.insert(
        0,
        "top100_rank",
        range(1, len(pool) + 1),
    )

    return pool


def main():
    parser = argparse.ArgumentParser(
        description="Promote discovery candidates into Top-100 pools."
    )

    parser.add_argument(
        "--discovery-dir",
        default=r".\results\discovery",
    )

    parser.add_argument(
        "--output-dir",
        default=r".\results\top100",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
    )

    args = parser.parse_args()

    discovery_dir = Path(args.discovery_dir)
    output_dir = Path(args.output_dir)

    print()
    print("=" * 70)
    print("TOP-100 STRATEGY PROMOTION")
    print("=" * 70)
    print()
    print(f"Discovery dir: {discovery_dir}")
    print(f"Output dir:    {output_dir}")
    print(f"Top per pool:  {args.top}")
    print()

    df = load_candidates(
        discovery_dir
    )

    print()
    print(f"Combined candidates: {len(df):,}")
    print()

    print("=" * 70)
    print("DISCOVERY COUNTS")
    print("=" * 70)

    print(
        df.groupby(
            ["session", "direction"]
        ).size().to_string()
    )

    print()
    print("=" * 70)
    print("PROMOTING POOLS")
    print("=" * 70)
    print()

    total = 0

    for session, direction in TARGET_POOLS:

        pool = promote_pool(
            df,
            session,
            direction,
            args.top,
        )

        filename = (
            session.lower().replace(" ", "_")
            + "_"
            + direction.lower()
            + f"_top{args.top}.csv"
        )

        output_path = (
            output_dir / filename
        )

        if pool.empty:
            print(
                f"WARNING: No candidates found for "
                f"{session} {direction}"
            )
            continue

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        pool.to_csv(
            output_path,
            index=False,
        )

        total += len(pool)

        print(
            f"{session:<10} "
            f"{direction:<5} -> "
            f"{len(pool):>3} strategies"
        )

        print(
            f"             {output_path}"
        )

    print()
    print("=" * 70)
    print("PROMOTION COMPLETE")
    print("=" * 70)
    print()
    print(f"TOTAL PROMOTED: {total}")
    print()
    print("No changes were made to strategy_lab.py.")
    print("No trades were placed.")
    print("The discovery registry was not modified.")
    print()


if __name__ == "__main__":
    main()
