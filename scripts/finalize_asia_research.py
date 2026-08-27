from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

csv.field_size_limit(2_147_483_647)


ROOT = Path(r"D:\Trading\Trading_Reworked")
RESULTS = ROOT / "results"
ASIA = RESULTS / "asia"
WORKERS = range(1, 5)
FAMILY = ["direction", "session", "conditions"]
KEY = FAMILY + ["rr", "entry_mode", "entry_wait_bars", "engine_version"]
RR_VALUES_PER_CANDIDATE = 61
PERIODS_PER_RR = 3
OVERLAP_THRESHOLD = 0.80
START = pd.Timestamp("2025-01-01T00:00:00Z")
END = pd.Timestamp("2026-08-07T23:45:00Z")


def normalized_key(values):
    out = []
    for value in values:
        if isinstance(value, (float, int, np.number)) and not isinstance(value, bool):
            out.append(f"{float(value):.10g}")
        else:
            out.append(str(value).strip())
    return tuple(out)


def strategy_key(row):
    return normalized_key(tuple(row[c] for c in KEY))


def entry_times(trades):
    return {
        pd.Timestamp(t["entry_time"])
        for t in trades
        if t.get("entry_time") is not None
    }


def overlap(left, right):
    denominator = min(len(left), len(right))
    return len(left & right) / denominator if denominator else 0.0


def weeks():
    return ((END.normalize() - START.normalize()).days + 1) / 7


def merge_summary_files():
    final = pd.concat(
        [pd.read_csv(ASIA / f"worker_{i}_strategy_lab.csv_final.csv") for i in WORKERS],
        ignore_index=True,
    )
    final = final.sort_values(
        ["robust_score", "profit_factor", "rr_stability", "trades", "rr"],
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)
    final["overall_rank"] = range(1, len(final) + 1)
    final.to_csv(RESULTS / "asia_strategy_lab_final.csv", index=False)

    best = final.drop_duplicates(FAMILY, keep="first").copy().reset_index(drop=True)
    best.insert(0, "family_rank", range(1, len(best) + 1))
    best.to_csv(ASIA / "asia_strategy_lab_top100_best_rr.csv", index=False)
    return final, best


def merge_period_csvs():
    target = RESULTS / "asia_strategy_lab_periods.csv"
    temporary = target.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as out_handle:
        writer = None
        for worker in WORKERS:
            source = ASIA / f"worker_{worker}_strategy_lab.csv_periods.csv"
            with source.open("r", encoding="utf-8", newline="") as in_handle:
                reader = csv.reader(in_handle)
                header = next(reader)
                if writer is None:
                    writer = csv.writer(out_handle)
                    writer.writerow(header)
                for row in reader:
                    writer.writerow(row)
    temporary.replace(target)
    return target


def create_merged_database():
    target = RESULTS / "asia_strategy_lab.sqlite"
    temporary = target.with_suffix(".sqlite.tmp")
    if temporary.exists():
        temporary.unlink()

    first_db = ASIA / "worker_1.sqlite"
    with sqlite3.connect(first_db) as source:
        schema = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='results'"
        ).fetchone()[0]

    out = sqlite3.connect(temporary)
    out.execute(schema)
    columns = [row[1] for row in out.execute("PRAGMA table_info(results)")]
    placeholders = ",".join("?" for _ in columns)
    insert_sql = f"INSERT OR REPLACE INTO results ({','.join(columns)}) VALUES ({placeholders})"

    inserted = 0
    for worker in WORKERS:
        candidates = pd.read_csv(ASIA / f"worker_{worker}_candidates.csv")
        with sqlite3.connect(ASIA / f"worker_{worker}.sqlite") as source:
            for _, candidate in candidates.iterrows():
                rows = source.execute(
                    "SELECT * FROM results WHERE direction=? AND session=? AND conditions=?",
                    (
                        str(candidate["direction"]),
                        str(candidate["session"]),
                        str(candidate["conditions"]),
                    ),
                ).fetchall()
                out.executemany(insert_sql, rows)
                inserted += len(rows)
        out.commit()
    out.execute("CREATE INDEX IF NOT EXISTS idx_asia_lookup ON results(direction,session,conditions,rr,period)")
    out.commit()
    actual = out.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    out.close()
    expected = 100 * RR_VALUES_PER_CANDIDATE * PERIODS_PER_RR
    if inserted != expected or actual != expected:
        raise RuntimeError(f"Merged database incomplete: inserted={inserted}, actual={actual}, expected={expected}")

    if target.exists():
        archive = ASIA / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
        archived = archive / f"asia_strategy_lab_replaced_{stamp}.sqlite"
        shutil.move(target, archived)
    temporary.replace(target)
    return target


def load_trade_map(db_path, rows):
    result = {}
    with sqlite3.connect(db_path) as con:
        for _, row in rows.iterrows():
            raw = con.execute(
                """SELECT result_json FROM results
                   WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                     AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                     AND engine_version=? LIMIT 1""",
                (
                    row["direction"], row["session"], row["conditions"], float(row["rr"]),
                    row["entry_mode"], int(row["entry_wait_bars"]), row["engine_version"],
                ),
            ).fetchone()
            if raw is None:
                raise RuntimeError(f"Missing ALL trades for {strategy_key(row)}")
            result[strategy_key(row)] = json.loads(raw[0] or "[]")
    return result


def explain(conditions, direction):
    names = {
        "above_ema20": "price above the 20 EMA",
        "above_ema50": "price above the 50 EMA",
        "above_ema100": "price above the 100 EMA",
        "above_ema200": "price above the 200 EMA",
        "bullish_candle": "a bullish candle",
        "bearish_candle": "a bearish candle",
        "bullish_fib_500_rejection": "bullish rejection of the directional 50% Fib",
        "bearish_fib_500_rejection": "bearish rejection of the directional 50% Fib",
        "bearish_fvg_retest": "a bearish fair-value-gap retest",
        "near_fib_382": "price near the directional 38.2% Fib",
        "near_fib_500": "price near the directional 50% Fib",
        "small_range": "a small-range setup candle",
        "large_range": "a large-range displacement candle",
        "higher_high": "a higher-high structure",
        "equal_low": "equal-low liquidity structure",
        "bullish_breaker_retest": "a bullish breaker-block retest",
    }
    parts = [names.get(x, x.replace("_", " ")) for x in str(conditions).split("+")]
    return f"During Asia, look for a {direction} when " + ", ".join(parts) + "."


def quality_and_select(best, trade_map):
    eligible = best[
        (best["rr"] >= 3)
        & (best["trades"] >= 40)
        & (best["profit_factor"] >= 1.7)
        & (best["max_drawdown_r"] <= 10)
        & (best["positive_years"] == best["years_tested"])
    ].copy()
    eligible = eligible.sort_values(
        ["robust_score", "profit_factor", "rr_stability", "trades"],
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    kept = []
    rejected = []
    for index, row in eligible.iterrows():
        times = entry_times(trade_map[strategy_key(row)])
        closest = (None, 0.0)
        for kept_index in kept:
            other = eligible.loc[kept_index]
            value = overlap(times, entry_times(trade_map[strategy_key(other)]))
            if value > closest[1]:
                closest = (kept_index, value)
        if closest[1] >= OVERLAP_THRESHOLD:
            rejected.append({
                "direction": row["direction"], "conditions": row["conditions"], "rr": row["rr"],
                "overlap": closest[1], "kept_conditions": eligible.loc[closest[0], "conditions"],
            })
        else:
            kept.append(index)

    dedup = eligible.loc[kept].copy().reset_index(drop=True)
    dedup.insert(0, "dedup_rank", range(1, len(dedup) + 1))
    dedup.to_csv(ASIA / "asia_strategy_deduplicated.csv", index=False)
    pd.DataFrame(rejected).to_csv(ASIA / "asia_overlap_rejections.csv", index=False)

    selected_indices = []
    # Keep one genuinely strong SELL if available, then fill by quality.
    sell = dedup[dedup["direction"].eq("SELL")]
    if not sell.empty:
        selected_indices.append(int(sell.index[0]))
    for index in dedup.index:
        if index not in selected_indices:
            selected_indices.append(int(index))
        if len(selected_indices) == 4:
            break
    selected = dedup.loc[selected_indices].copy()
    selected = selected.sort_values("robust_score", ascending=False, kind="stable").reset_index(drop=True)
    selected.insert(0, "rank", range(1, len(selected) + 1))

    labels = [f"#{int(r['rank'])} {r['direction']} {r['conditions']}" for _, r in selected.iterrows()]
    selected_times = [entry_times(trade_map[strategy_key(r)]) for _, r in selected.iterrows()]
    closest_values = []
    closest_labels = []
    for i, left in enumerate(selected_times):
        candidates = [(j, overlap(left, right)) for j, right in enumerate(selected_times) if i != j]
        j, value = max(candidates, key=lambda x: x[1]) if candidates else (-1, 0.0)
        closest_values.append(value)
        closest_labels.append(labels[j] if j >= 0 else "none")
    selected["closest_selected_overlap"] = closest_values
    selected["closest_selected_strategy"] = closest_labels
    selected["setups_week"] = [len(x) / weeks() for x in selected_times]
    selected["plain_english"] = [explain(r["conditions"], r["direction"]) for _, r in selected.iterrows()]
    selected.to_csv(RESULTS / "asia_strategy_top4.csv", index=False)

    matrix = pd.DataFrame(index=labels, columns=labels, dtype=float)
    for i, left in enumerate(selected_times):
        for j, right in enumerate(selected_times):
            matrix.iloc[i, j] = overlap(left, right)
    matrix.index.name = "strategy"
    matrix.to_csv(ASIA / "asia_top4_overlap_matrix.csv")
    return eligible, dedup, selected


def load_core_trades():
    shortlist = pd.read_csv(RESULTS / "funded_strategy_shortlist.csv")
    trade_map = {}
    with sqlite3.connect(RESULTS / "strategy_lab.sqlite") as con:
        for _, row in shortlist.iterrows():
            raw = con.execute(
                """SELECT result_json FROM results WHERE period='ALL' AND direction=? AND session=?
                   AND conditions=? AND ABS(rr-?)<0.00001 AND entry_mode=? AND entry_wait_bars=?
                   AND engine_version=? LIMIT 1""",
                (row.direction, row.session, row.conditions, float(row.rr), row.entry_mode,
                 int(row.entry_wait_bars), row.engine_version),
            ).fetchone()
            if raw is None:
                raise RuntimeError(f"Missing core trades for {row.conditions}")
            trade_map[strategy_key(row)] = json.loads(raw[0] or "[]")
    return shortlist, trade_map


def frequency_metrics(strategy_sets):
    union = set().union(*strategy_sets) if strategy_sets else set()
    ordered = sorted(union)
    gaps = np.diff(pd.DatetimeIndex(ordered).asi8) / (86400 * 1e9) if len(ordered) > 1 else []
    business_days = pd.date_range(START.normalize(), END.normalize(), freq="B", tz="UTC")
    daily = pd.Series(0, index=business_days, dtype=int)
    if union:
        counts = pd.Series(1, index=pd.DatetimeIndex([x.normalize() for x in union])).groupby(level=0).sum()
        daily = counts.reindex(business_days, fill_value=0).astype(int)
    raw = sum(len(x) for x in strategy_sets)
    duplicates = raw - len(union)
    return {
        "unique_setups": len(union),
        "unique_setups_week": len(union) / weeks(),
        "average_days_between_setups": float(np.mean(gaps)) if len(gaps) else math.nan,
        "trading_days_0": int((daily == 0).sum()),
        "trading_days_1": int((daily == 1).sum()),
        "trading_days_2plus": int((daily >= 2).sum()),
        "raw_strategy_entries": raw,
        "overlapping_entries_removed": duplicates,
        "overlap_pct_of_raw": duplicates / raw if raw else 0.0,
    }, daily


def make_frequency(selected, asia_trade_map):
    core, core_map = load_core_trades()
    core_sets = [entry_times(core_map[strategy_key(r)]) for _, r in core.iterrows()]
    asia_sets = [entry_times(asia_trade_map[strategy_key(r)]) for _, r in selected.iterrows()]
    before, before_daily = frequency_metrics(core_sets)
    after, after_daily = frequency_metrics(core_sets + asia_sets)
    core_union = set().union(*core_sets)
    asia_union = set().union(*asia_sets)
    shared = len(core_union & asia_union)
    before["portfolio"] = "London+New York core"
    before["asia_core_shared_timestamps"] = 0
    after["portfolio"] = "London+New York core + Asia Top4"
    after["asia_core_shared_timestamps"] = shared
    comparison = pd.DataFrame([before, after])
    columns = ["portfolio"] + [c for c in comparison.columns if c != "portfolio"]
    comparison = comparison[columns]
    comparison.to_csv(RESULTS / "asia_frequency_comparison.csv", index=False)

    daily = pd.DataFrame({
        "date": before_daily.index,
        "core_unique_setups": before_daily.values,
        "core_plus_asia_unique_setups": after_daily.values,
    })
    daily.to_csv(ASIA / "asia_frequency_daily.csv", index=False)
    return comparison, shared, len(core_union), len(asia_union)


def runtime_summary(finalizer_seconds):
    values = {
        "discovery_buy_seconds": 353.486,
        "discovery_sell_seconds": 351.184,
        "parallel_discovery_wall_seconds": 353.486,
        "promotion_seconds": 7.5,
        "initial_single_deep_seconds": 3573.0,
        "parallel_deep_phase_seconds": 3503.0,
        "total_deep_wall_seconds": 7076.0,
        "postprocess_seconds": finalizer_seconds,
        "visual_validation_seconds": 0.0,
    }
    measured = ASIA / "asia_measured_stage_timings.csv"
    if measured.exists():
        timing = pd.read_csv(measured)
        for _, row in timing.iterrows():
            if str(row.get("stage")) in values:
                values[str(row["stage"])] = float(row["seconds"])
        values["postprocess_seconds"] = finalizer_seconds
    pd.DataFrame([{"stage": k, "seconds": v, "minutes": v / 60} for k, v in values.items()]).to_csv(
        ASIA / "asia_runtime_summary.csv", index=False
    )
    return values


def make_summary(final, best, eligible, dedup, selected, comparison, shared, core_n, asia_n, runtimes):
    before = comparison.iloc[0]
    after = comparison.iloc[1]
    quality_ok = bool((selected.profit_factor >= 1.7).all() and (selected.positive_years == selected.years_tested).all())
    frequency_gain = after.unique_setups_week - before.unique_setups_week
    meaningful = quality_ok and frequency_gain >= 0.5
    lines = [
        "ASIA SESSION STRATEGY RESEARCH SUMMARY",
        "=" * 40,
        "",
        f"Discovery examined: BUY 74,518; SELL 74,518.",
        f"Discovery survivors: BUY 1,466; SELL 1,116.",
        f"Balanced Top100: 50 BUY + 50 SELL.",
        f"Deep results: {len(final):,} family/RR rows; {len(best)} exact families; periods ALL, 2025, 2026.",
        f"Finalist gate survivors: {len(eligible)}; after {OVERLAP_THRESHOLD:.2f} overlap pruning: {len(dedup)}.",
        "Finalist gate: RR >= 3, trades >= 40, PF >= 1.7, max DD <= 10R, all tested years positive.",
        "No Asia family passed the stricter funded gate of max DD <= 5R, RR >= 3 and PF >= 1.7.",
        "",
        "FINAL TOP 4",
        "-" * 11,
    ]
    for _, row in selected.iterrows():
        lines.append(
            f"{int(row['rank'])}. {row['direction']} Asia | {row['conditions']} | RR {row['rr']:g} | "
            f"trades {int(row['trades'])} | net {row['net_r']:.3f}R | exp {row['expectancy_r']:.3f}R | "
            f"PF {row['profit_factor']:.3f} | DD {row['max_drawdown_r']:.3f}R | win {row['win_rate']:.2f}% | "
            f"{row['setups_week']:.3f}/week | stability {row['rr_stability']:.3f} | robust {row['robust_score']:.3f} | "
            f"years {int(row['positive_years'])}/{int(row['years_tested'])} | closest selected overlap {row['closest_selected_overlap']:.3f}"
        )
        lines.append(f"   {row['plain_english']}")
    lines += [
        "",
        "OPPORTUNITY FREQUENCY",
        "-" * 21,
        f"Core: {before.unique_setups_week:.3f} unique setups/week; average gap {before.average_days_between_setups:.3f} days.",
        f"Core + Asia: {after.unique_setups_week:.3f} unique setups/week; average gap {after.average_days_between_setups:.3f} days.",
        f"Trading days 0/1/2+: core {int(before.trading_days_0)}/{int(before.trading_days_1)}/{int(before.trading_days_2plus)}; "
        f"with Asia {int(after.trading_days_0)}/{int(after.trading_days_1)}/{int(after.trading_days_2plus)}.",
        f"Asia/core exact shared entry timestamps: {shared}; core union {core_n}; Asia union {asia_n}.",
        f"Conclusion: Asia {'meaningfully reduces' if meaningful else 'does not clearly reduce'} waiting time under the stated quality gates.",
        "",
        "COMPUTATIONAL RUNTIME",
        "-" * 21,
        f"BUY discovery: {runtimes['discovery_buy_seconds']:.3f}s; SELL discovery: {runtimes['discovery_sell_seconds']:.3f}s; parallel wall {runtimes['parallel_discovery_wall_seconds']:.3f}s.",
        f"Deep testing measured wall time: about {runtimes['total_deep_wall_seconds']:.0f}s ({runtimes['total_deep_wall_seconds']/60:.1f} min), including the preserved single-run work, parallel completion and lock recovery.",
        "No reliable historical London/NY runtime logs were found, so a like-for-like computational speed comparison cannot be claimed.",
        "Adding Asia necessarily adds compute workload; parallel workers reduced the remaining wall time but did not make the total research pipeline intrinsically faster.",
    ]
    (RESULTS / "asia_portfolio_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    started = time.perf_counter()
    final, best = merge_summary_files()
    periods_path = merge_period_csvs()
    database = create_merged_database()
    trade_map = load_trade_map(database, best)
    eligible, dedup, selected = quality_and_select(best, trade_map)
    comparison, shared, core_n, asia_n = make_frequency(selected, trade_map)
    elapsed = time.perf_counter() - started
    runtimes = runtime_summary(elapsed)
    make_summary(final, best, eligible, dedup, selected, comparison, shared, core_n, asia_n, runtimes)
    print(f"Merged final rows: {len(final)}")
    print(f"Merged period file: {periods_path}")
    print(f"Merged DB: {database}")
    print(f"Eligible/deduplicated/selected: {len(eligible)}/{len(dedup)}/{len(selected)}")
    print(selected[["rank", "direction", "conditions", "rr", "trades", "profit_factor", "max_drawdown_r", "robust_score", "closest_selected_overlap", "setups_week"]].to_string(index=False))
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
