"""Compare the current 13-strategy paper plan with one strict V10 addition.

The current thirteen use their saved, previously audited trade pool. The new
GBPJPY strategy is loaded from the fresh V10 Strategy Lab database. This keeps
the comparison non-destructive and preserves the stored entry/exit timestamps.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import simulate_funded_13_strategy_portfolio as funded


DEFAULT_BASE = (
    ROOT
    / "results"
    / "research_symbols"
    / "runs"
    / "20260923_194103"
    / "final"
    / "funded_simulation_13"
)
DEFAULT_V10 = Path(
    r"D:\Trading\Trading_Reworked\results\smc_v10_scans\20261010_193500_full"
)
NEW_KEY = {
    "symbol": "GBPJPY",
    "strategy_id": "GJ05",
    "direction": "BUY",
    "session": "New York",
    "conditions": "above_ema200+bullish_choch+new_york_kill_zone",
    "rr": 3.0,
    "entry_mode": "auto",
    "entry_wait_bars": 6,
    "engine_version": "2026-10-10-v10-smc-guide-expansion",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--v10-run", type=Path, default=DEFAULT_V10)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "funded_simulation_14_v10",
    )
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-08-07 23:45:00+00:00")
    return parser.parse_args()


def locate_v10_database(run_dir: Path) -> Path:
    roots = [run_dir / "deep_completed" / "GBPJPY", run_dir / "deep" / "GBPJPY"]
    for root in roots:
        for candidate_file in sorted(root.glob("worker_*_candidates.csv")):
            candidates = pd.read_csv(candidate_file)
            matched = candidates[
                (candidates["direction"].astype(str) == NEW_KEY["direction"])
                & (candidates["session"].astype(str) == NEW_KEY["session"])
                & (candidates["conditions"].astype(str) == NEW_KEY["conditions"])
            ]
            if matched.empty:
                continue
            worker = candidate_file.name.split("_")[1]
            database = root / f"worker_{worker}.sqlite"
            if database.is_file():
                return database
    raise FileNotFoundError("Could not locate the strict V10 GBPJPY Strategy Lab database")


def load_new_strategy(v10_run: Path) -> pd.Series:
    strict_file = v10_run / "final_v10" / "smc_v10_funded_deduplicated.csv"
    strict = pd.read_csv(strict_file)
    matched = strict[
        (strict["symbol"].astype(str) == NEW_KEY["symbol"])
        & (strict["direction"].astype(str) == NEW_KEY["direction"])
        & (strict["session"].astype(str) == NEW_KEY["session"])
        & (strict["conditions"].astype(str) == NEW_KEY["conditions"])
        & (strict["rr"].astype(float).sub(NEW_KEY["rr"]).abs() < 0.00001)
    ]
    if len(matched) != 1:
        raise RuntimeError(f"Expected one strict V10 strategy row, found {len(matched)}")
    return matched.iloc[0].copy()


def load_new_trades(
    database: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    with sqlite3.connect(database) as connection:
        result = connection.execute(
            """SELECT result_json FROM results
               WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                 AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                 AND engine_version=? LIMIT 1""",
            (
                NEW_KEY["direction"],
                NEW_KEY["session"],
                NEW_KEY["conditions"],
                NEW_KEY["rr"],
                NEW_KEY["entry_mode"],
                NEW_KEY["entry_wait_bars"],
                NEW_KEY["engine_version"],
            ),
        ).fetchone()
    if result is None:
        raise RuntimeError("Strict V10 Strategy Lab result was not found")

    label = (
        f"{NEW_KEY['symbol']}|{NEW_KEY['direction']}|{NEW_KEY['session']}|"
        f"{NEW_KEY['conditions']}|RR{NEW_KEY['rr']:g}"
    )
    rows = []
    for trade_number, trade in enumerate(json.loads(result[0] or "[]"), start=1):
        entry_time = pd.to_datetime(trade.get("entry_time"), utc=True, errors="coerce")
        exit_time = pd.to_datetime(trade.get("exit_time"), utc=True, errors="coerce")
        if pd.isna(entry_time) or pd.isna(exit_time) or not (start <= entry_time <= end):
            continue
        rows.append(
            {
                "trade_id": f"14-{trade_number:04d}",
                "plan_rank": 14,
                "plan_source": "v10_strict_addition",
                "symbol": NEW_KEY["symbol"],
                "strategy": label,
                "direction": NEW_KEY["direction"],
                "session": NEW_KEY["session"],
                "conditions": NEW_KEY["conditions"],
                "rr": NEW_KEY["rr"],
                "entry_time": entry_time,
                "exit_time": exit_time,
                "outcome_r": float(trade["outcome_r"]),
                "reason": trade.get("reason", ""),
            }
        )
    return pd.DataFrame(rows)


def frequency(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    times = pd.DatetimeIndex(
        pd.to_datetime(trades["entry_time"], utc=True).drop_duplicates()
    ).sort_values()
    weeks = (end - start).total_seconds() / (7 * 86400)
    gaps = times.to_series().diff().dt.total_seconds().div(86400).dropna()
    return {
        "unique_setups": len(times),
        "unique_setups_week": len(times) / weeks,
        "average_days_between_setups": gaps.mean() if not gaps.empty else math.nan,
    }


def main() -> int:
    args = parse_args()
    base_dir = args.base_dir.resolve()
    v10_run = args.v10_run.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    start = pd.to_datetime(args.start, utc=True)
    end = pd.to_datetime(args.end, utc=True)

    plan13 = pd.read_csv(base_dir / "combined_13_strategy_plan.csv")
    trades13 = pd.read_csv(base_dir / "combined_trade_pool.csv")
    trades13["entry_time"] = pd.to_datetime(trades13["entry_time"], utc=True)
    trades13["exit_time"] = pd.to_datetime(trades13["exit_time"], utc=True)

    strategy = load_new_strategy(v10_run)
    plan14 = plan13.copy()
    addition = {column: math.nan for column in plan14.columns}
    for key in plan14.columns:
        if key in strategy.index:
            addition[key] = strategy[key]
    addition.update(NEW_KEY)
    addition["plan_source"] = "v10_strict_addition"
    addition["plan_rank"] = 14
    plan14 = pd.concat([plan14, pd.DataFrame([addition])], ignore_index=True)
    plan14["portfolio_priority"] = (
        pd.to_numeric(plan14["robust_score"], errors="coerce")
        .fillna(0)
        .rank(method="first", ascending=False)
        .astype(int)
    )
    priorities = plan14.set_index("plan_rank")["portfolio_priority"].to_dict()
    trades13["priority"] = trades13["plan_rank"].map(priorities).astype(int)

    database = locate_v10_database(v10_run)
    new_trades = load_new_trades(database, start, end)
    new_trades["priority"] = int(priorities[14])
    trades14 = pd.concat([trades13, new_trades], ignore_index=True, sort=False).sort_values(
        ["entry_time", "priority", "plan_rank", "trade_id"], kind="stable"
    ).reset_index(drop=True)

    funded.PHASE_TARGETS = {"PHASE_1": 11_030.0, "PHASE_2": 10_520.0}
    rules13 = funded.Rules("current_13_exact_rules", 0.01, 0.03, 2, True)
    rules14 = funded.Rules("recommended_14_exact_rules", 0.01, 0.03, 2, True)
    summary13, attempts13, accepted13, skips13 = funded.simulate(
        trades13, rules13, start, end
    )
    summary14, attempts14, accepted14, skips14 = funded.simulate(
        trades14, rules14, start, end
    )

    comparison = pd.DataFrame([summary13, summary14])
    comparison.to_csv(output / "funded_13_vs_14_comparison.csv", index=False)
    plan14.to_csv(output / "recommended_14_strategy_plan.csv", index=False)
    trades14.to_csv(output / "combined_14_trade_pool.csv", index=False)
    attempts13.to_csv(output / "attempts_current_13.csv", index=False)
    attempts14.to_csv(output / "attempts_recommended_14.csv", index=False)
    accepted13.to_csv(output / "accepted_current_13.csv", index=False)
    accepted14.to_csv(output / "accepted_recommended_14.csv", index=False)
    pd.DataFrame(
        [{"reason": key, "count": value} for key, value in sorted(skips13.items())]
    ).to_csv(output / "skips_current_13.csv", index=False)
    pd.DataFrame(
        [{"reason": key, "count": value} for key, value in sorted(skips14.items())]
    ).to_csv(output / "skips_recommended_14.csv", index=False)

    contribution = accepted14[accepted14["plan_rank"] == 14].copy()
    contribution.to_csv(output / "new_strategy_accepted_trades.csv", index=False)
    contribution_summary = {
        "signals_available": len(new_trades),
        "trades_accepted": len(contribution),
        "wins": int((contribution["outcome_r"] > 0).sum()),
        "losses": int((contribution["outcome_r"] < 0).sum()),
        "win_rate_pct": (
            100 * (contribution["outcome_r"] > 0).mean() if len(contribution) else math.nan
        ),
        "net_r": contribution["outcome_r"].sum(),
        "expectancy_r": (
            contribution["outcome_r"].mean() if len(contribution) else math.nan
        ),
        "realized_pnl_dollars": contribution["pnl"].sum(),
    }
    pd.DataFrame([contribution_summary]).to_csv(
        output / "new_strategy_contribution.csv", index=False
    )

    frequency13 = frequency(trades13, start, end)
    frequency14 = frequency(trades14, start, end)
    pd.DataFrame(
        [
            {"portfolio": "current_13", **frequency13},
            {"portfolio": "recommended_14", **frequency14},
        ]
    ).to_csv(output / "setup_frequency_comparison.csv", index=False)

    def fmt_days(value: float) -> str:
        return f"{value:.1f}" if math.isfinite(value) else "n/a"

    lines = [
        "RECOMMENDED 14TH STRATEGY FUNDED SIMULATION",
        "=" * 45,
        f"Window: {start.isoformat()} to {end.isoformat()}.",
        "Added: GBPJPY BUY, New York, above EMA200 + bullish CHoCH + New York kill zone, RR 3.0.",
        "Reason: the higher-ranked strict Asia SELL already exists as GJ02; this is the strongest genuinely new strict, direction-diversifying family.",
        "Strict research metrics: 43 trades, 34.40R net, 0.80R expectancy, PF 2.67, 3.0R max drawdown, 46.51% win rate, positive in both tested years.",
        "Rules: 1% risk, maximum two open positions, 3% daily cap including open risk, Phase 1 $11,030, Phase 2 $10,520, $9,000 hard floor.",
        "Conservative same-bar SL-before-TP handling is inherited from the stored Strategy Lab outcomes.",
        "",
        "CURRENT 13 VS RECOMMENDED 14",
        "-" * 29,
        f"Current 13: {summary13['full_passes']} full passes, {summary13['failures']} failures, {fmt_days(summary13['average_full_pass_days'])} average pass days, {summary13['worst_phase_loss_from_start_pct'] * 100:.2f}% worst loss from phase start.",
        f"Recommended 14: {summary14['full_passes']} full passes, {summary14['failures']} failures, {fmt_days(summary14['average_full_pass_days'])} average pass days, {summary14['worst_phase_loss_from_start_pct'] * 100:.2f}% worst loss from phase start.",
        f"New strategy accepted contribution: {contribution_summary['trades_accepted']} trades, {contribution_summary['net_r']:.2f}R, {contribution_summary['expectancy_r']:.2f}R expectancy, {contribution_summary['win_rate_pct']:.2f}% win rate.",
        f"Setup frequency: {frequency13['unique_setups_week']:.2f}/week -> {frequency14['unique_setups_week']:.2f}/week; average gap {frequency13['average_days_between_setups']:.2f} -> {frequency14['average_days_between_setups']:.2f} days.",
        "",
        "LIMITATION",
        "-" * 10,
        "The current thirteen use their previously audited V9 stored trade pool; the added strategy uses fresh V10 stored trades. This is an in-sample historical replay, not a guarantee or an independent out-of-sample test.",
    ]
    (output / "funded_14_summary.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
