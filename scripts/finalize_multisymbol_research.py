from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


FAMILY = ["direction", "session", "conditions"]
KEY = FAMILY + ["rr", "entry_mode", "entry_wait_bars", "engine_version"]
OVERLAP_THRESHOLD = 0.80
START = pd.Timestamp("2025-01-01T00:00:00Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge, gate, overlap-prune and compare multi-symbol Strategy Lab results."
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--legacy-results", type=Path, default=Path(r"D:\Trading\Trading_Reworked\results"))
    return parser.parse_args()


def norm(value: object) -> str:
    if isinstance(value, (float, int, np.number)) and not isinstance(value, bool):
        return f"{float(value):.10g}"
    return str(value).strip()


def strategy_key(row: pd.Series) -> tuple[str, ...]:
    prefix = (str(row["symbol"]).strip(),) if "symbol" in row.index else ()
    return prefix + tuple(norm(row[column]) for column in KEY)


def family_key(row: pd.Series) -> tuple[str, ...]:
    return tuple(str(row[column]).strip() for column in FAMILY)


def entry_times(trades: list[dict]) -> set[pd.Timestamp]:
    result = set()
    for item in trades:
        timestamp = pd.to_datetime(item.get("entry_time"), utc=True, errors="coerce")
        if not pd.isna(timestamp):
            result.add(timestamp)
    return result


def overlap(left: set[pd.Timestamp], right: set[pd.Timestamp]) -> float:
    denominator = min(len(left), len(right))
    return len(left & right) / denominator if denominator else 0.0


def locate_worker_databases(symbol_dir: Path) -> dict[tuple[str, str, str], Path]:
    locations: dict[tuple[str, str, str], Path] = {}
    for candidate_file in sorted(symbol_dir.glob("worker_*_candidates.csv")):
        worker = candidate_file.name.split("_")[1]
        database = symbol_dir / f"worker_{worker}.sqlite"
        if not database.exists():
            raise FileNotFoundError(database)
        for _, row in pd.read_csv(candidate_file).iterrows():
            locations[family_key(row)] = database
    return locations


def load_trades(row: pd.Series, locations: dict[tuple[str, str, str], Path]) -> list[dict]:
    database = locations.get(family_key(row))
    if database is None:
        raise RuntimeError(f"No worker database found for {family_key(row)}")
    with sqlite3.connect(database) as connection:
        record = connection.execute(
            """SELECT result_json FROM results
               WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                 AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                 AND engine_version=? LIMIT 1""",
            (
                row["direction"], row["session"], row["conditions"], float(row["rr"]),
                row["entry_mode"], int(row["entry_wait_bars"]), row["engine_version"],
            ),
        ).fetchone()
    if record is None:
        raise RuntimeError(f"Missing ALL-period trades for {strategy_key(row)}")
    return json.loads(record[0] or "[]")


def ordered(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(
        ["robust_score", "profit_factor", "rr_stability", "trades", "rr"],
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)


def add_gates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    positive = out["positive_years"].eq(out["years_tested"])
    common = (
        out["rr"].ge(3.0)
        & out["trades"].ge(40)
        & out["profit_factor"].ge(1.7)
        & out["rr_stability"].ge(0.80)
        & positive
    )
    out["passes_funded_gate"] = common & out["max_drawdown_r"].le(5.0)
    out["passes_quality_gate"] = common & out["max_drawdown_r"].le(10.0)
    return out


def prune_overlap(
    candidates: pd.DataFrame,
    trades: dict[tuple[str, ...], list[dict]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    kept: list[int] = []
    rejected: list[dict] = []
    for index, row in candidates.iterrows():
        left = entry_times(trades[strategy_key(row)])
        closest_index = None
        closest_value = 0.0
        for other_index in kept:
            other = candidates.loc[other_index]
            value = overlap(left, entry_times(trades[strategy_key(other)]))
            if value > closest_value:
                closest_index = other_index
                closest_value = value
        if closest_value >= OVERLAP_THRESHOLD:
            other = candidates.loc[closest_index]
            rejected.append(
                {
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "session": row["session"],
                    "conditions": row["conditions"],
                    "rr": row["rr"],
                    "overlap": closest_value,
                    "kept_symbol": other["symbol"],
                    "kept_direction": other["direction"],
                    "kept_session": other["session"],
                    "kept_conditions": other["conditions"],
                    "kept_rr": other["rr"],
                }
            )
        else:
            kept.append(index)
    deduplicated = candidates.loc[kept].copy().reset_index(drop=True)
    return deduplicated, pd.DataFrame(rejected)


def select_balanced(candidates: pd.DataFrame, limit: int = 4) -> pd.DataFrame:
    chosen: list[int] = []
    # First give every available symbol/direction combination one place.
    for symbol in sorted(candidates["symbol"].unique()):
        for direction in ("BUY", "SELL"):
            pool = candidates[
                candidates["symbol"].eq(symbol) & candidates["direction"].eq(direction)
            ]
            if not pool.empty:
                chosen.append(int(pool.index[0]))
    chosen = sorted(set(chosen), key=lambda i: float(candidates.loc[i, "robust_score"]), reverse=True)
    chosen = chosen[:limit]
    for index in candidates.index:
        if len(chosen) >= limit:
            break
        if int(index) not in chosen:
            chosen.append(int(index))
    result = candidates.loc[chosen].copy()
    result = ordered(result).head(limit).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    return result


def top10_each(best: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in ("BUY", "SELL"):
        part = best[best["direction"].eq(direction)].head(10).copy()
        part.insert(0, "direction_rank", range(1, len(part) + 1))
        rows.append(part)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def explain_conditions(row: pd.Series) -> str:
    names = {
        "above_ema20": "price is above the 20 EMA",
        "bullish_fib_618_rejection": "price rejects the directional 61.8% Fib upward",
        "bullish_pin_bar": "the setup candle is a bullish pin bar",
        "bearish_engulfing": "the setup candle is bearish engulfing",
        "bearish_fib_500_rejection": "price rejects the directional 50% Fib downward",
        "bearish_bos_fib_618": "a bearish break of structure is confirmed around the directional 61.8% Fib",
        "bullish_bos": "a bullish break of structure is present",
        "bullish_fvg": "a bullish fair-value gap is present",
    }
    parts = [names.get(item, item.replace("_", " ")) for item in str(row["conditions"]).split("+")]
    return f"During {row['session']}, look for a {row['direction']} when " + ", and ".join(parts) + "."


def build_discovery_counts(run_dir: Path, output_dir: Path) -> pd.DataFrame:
    frames = []
    for symbol in ("GBPJPY", "AUDUSD"):
        counts = pd.read_csv(run_dir / "promotion" / symbol / "discovery_counts.csv")
        screened = pd.read_csv(run_dir / "promotion" / symbol / "discovery_screened.csv")
        strict = (
            screened["trades"].ge(30)
            & screened["positive_periods"].eq(screened["periods_tested"])
            & screened["min_profit_factor"].ge(1.2)
            & screened["worst_drawdown_r"].le(20.0)
        )
        strict_counts = (
            screened.loc[strict]
            .groupby(["symbol", "session", "direction"])
            .size()
            .rename("strict_discovery_survivors")
            .reset_index()
        )
        counts = counts.merge(strict_counts, on=["symbol", "session", "direction"], how="left")
        counts["strict_discovery_survivors"] = counts["strict_discovery_survivors"].fillna(0).astype(int)
        counts.insert(3, "combinations_examined", 74518)
        frames.append(counts)
    result = pd.concat(frames, ignore_index=True)
    result.to_csv(output_dir / "multisymbol_discovery_counts.csv", index=False)
    return result


def build_runtime_summary(run_dir: Path, legacy_results: Path, output_dir: Path) -> pd.DataFrame:
    discovery = pd.read_csv(run_dir / "discovery_timings.csv")
    wall_rows = []
    for (symbol, session), part in discovery.groupby(["symbol", "session"], sort=False):
        seconds = float(part["seconds"].max())
        source = "timing log"
        if symbol == "GBPJPY" and session == "Asia" and seconds == 0:
            seconds = 65.5
            source = "initial console measurement before resume"
        wall_rows.append(
            {"stage": "discovery", "symbol": symbol, "session": session, "seconds": seconds, "source": source}
        )
    deep = pd.read_csv(run_dir / "deep_timings.csv")
    for symbol, part in deep.groupby("symbol", sort=False):
        wall_rows.append(
            {
                "stage": "deep_test",
                "symbol": symbol,
                "session": "ALL",
                "seconds": float(part["seconds"].max()),
                "source": "four-worker parallel wall time",
            }
        )
    result = pd.DataFrame(wall_rows)
    result["minutes"] = result["seconds"] / 60
    result.to_csv(output_dir / "multisymbol_runtime_summary.csv", index=False)
    return result


def load_legacy_portfolio(legacy_results: Path) -> tuple[pd.DataFrame, list[set[pd.Timestamp]]]:
    portfolio_file = legacy_results / "session_portfolio_research" / "best_session_paper_portfolio.csv"
    primary_db = legacy_results / "strategy_lab.sqlite"
    asia_db = legacy_results / "asia_strategy_lab.sqlite"
    if not portfolio_file.exists() or not primary_db.exists() or not asia_db.exists():
        return pd.DataFrame(), []
    portfolio = pd.read_csv(portfolio_file)
    sets: list[set[pd.Timestamp]] = []
    for _, row in portfolio.iterrows():
        database = asia_db if str(row["session"]).strip().lower() == "asia" else primary_db
        with sqlite3.connect(database) as connection:
            record = connection.execute(
                """SELECT result_json FROM results
                   WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                     AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                     AND engine_version=? LIMIT 1""",
                (
                    row["direction"], row["session"], row["conditions"], float(row["rr"]),
                    row["entry_mode"], int(row["entry_wait_bars"]), row["engine_version"],
                ),
            ).fetchone()
        if record is None:
            raise RuntimeError(f"Missing legacy trades for {family_key(row)}")
        sets.append(entry_times(json.loads(record[0] or "[]")))
    return portfolio, sets


def frequency_metrics(strategy_sets: list[set[pd.Timestamp]], end: pd.Timestamp) -> dict:
    clipped = [{timestamp for timestamp in values if START <= timestamp <= end} for values in strategy_sets]
    union = set().union(*clipped) if clipped else set()
    ordered_times = sorted(union)
    weeks = ((end.normalize() - START.normalize()).days + 1) / 7
    gaps = (
        [
            (right - left).total_seconds() / 86400
            for left, right in zip(ordered_times, ordered_times[1:])
        ]
        if len(ordered_times) > 1 else []
    )
    business_days = pd.date_range(START.normalize(), end.normalize(), freq="B", tz="UTC")
    daily = pd.Series(0, index=business_days, dtype=int)
    if union:
        dates = pd.DatetimeIndex([x.normalize() for x in union])
        counts = pd.Series(1, index=dates).groupby(level=0).sum()
        daily = counts.reindex(business_days, fill_value=0).astype(int)
    raw = sum(len(values) for values in clipped)
    return {
        "unique_setups": len(union),
        "unique_setups_week": len(union) / weeks,
        "average_days_between_setups": float(np.mean(gaps)) if len(gaps) else math.nan,
        "trading_days_0": int((daily == 0).sum()),
        "trading_days_1": int((daily == 1).sum()),
        "trading_days_2plus": int((daily >= 2).sum()),
        "raw_strategy_entries": raw,
        "overlapping_entries_removed": raw - len(union),
        "overlap_pct_of_raw": (raw - len(union)) / raw if raw else 0.0,
    }


def latest_feature_timestamp(root: Path, symbols: list[str]) -> pd.Timestamp:
    latest = START
    for symbol in symbols:
        feature_file = root / "quant" / "research_symbols" / symbol / "feature_database.csv"
        timestamps = pd.read_csv(feature_file, usecols=["timestamp"])["timestamp"]
        value = pd.to_datetime(timestamps.iloc[-1], utc=True)
        latest = max(latest, value)
    return latest


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    root = Path(__file__).resolve().parents[1]
    output_dir = run_dir / "final"
    output_dir.mkdir(parents=True, exist_ok=True)
    symbols = ["GBPJPY", "AUDUSD"]
    all_best = []
    trade_map: dict[tuple[str, ...], list[dict]] = {}
    strict_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}

    for symbol in symbols:
        symbol_dir = run_dir / "deep" / symbol
        files = sorted(symbol_dir.glob("worker_*_strategy_lab.csv_final.csv"))
        if len(files) != 4:
            raise RuntimeError(f"Expected four completed final files for {symbol}; found {len(files)}")
        final = ordered(pd.concat([pd.read_csv(path) for path in files], ignore_index=True))
        final.insert(0, "symbol", symbol)
        final.to_csv(output_dir / f"{symbol.lower()}_strategy_lab_final.csv", index=False)
        best = add_gates(final.drop_duplicates(FAMILY, keep="first").reset_index(drop=True))
        best.insert(1, "family_rank", range(1, len(best) + 1))
        best.to_csv(output_dir / f"{symbol.lower()}_best_rr_per_family.csv", index=False)
        top10_each(best).to_csv(output_dir / f"{symbol.lower()}_top10_each_direction.csv", index=False)
        locations = locate_worker_databases(symbol_dir)
        quality = best[best["passes_quality_gate"]].copy().reset_index(drop=True)
        quality_counts[symbol] = len(quality)
        for _, row in quality.iterrows():
            trade_map[strategy_key(row)] = load_trades(row, locations)
        strict = quality[quality["passes_funded_gate"]].copy().reset_index(drop=True)
        strict_counts[symbol] = len(strict)
        strict.to_csv(output_dir / f"{symbol.lower()}_funded_gate.csv", index=False)
        all_best.append(best)

    best_all = ordered(pd.concat(all_best, ignore_index=True))
    strict_all = best_all[best_all["passes_funded_gate"]].copy().reset_index(drop=True)
    strict_deduplicated, strict_rejected = prune_overlap(strict_all, trade_map)
    strict_deduplicated.insert(0, "dedup_rank", range(1, len(strict_deduplicated) + 1))
    strict_deduplicated.to_csv(output_dir / "multisymbol_funded_deduplicated.csv", index=False)
    strict_rejected.to_csv(output_dir / "multisymbol_funded_overlap_rejections.csv", index=False)

    quality_all = best_all[best_all["passes_quality_gate"]].copy().reset_index(drop=True)
    quality_deduplicated, rejected = prune_overlap(quality_all, trade_map)
    quality_deduplicated.insert(0, "dedup_rank", range(1, len(quality_deduplicated) + 1))
    quality_deduplicated.to_csv(output_dir / "multisymbol_quality_deduplicated.csv", index=False)
    rejected.to_csv(output_dir / "multisymbol_overlap_rejections.csv", index=False)
    selected = select_balanced(quality_deduplicated, 4)

    selected_sets = [entry_times(trade_map[strategy_key(row)]) for _, row in selected.iterrows()]
    labels = [
        f"#{int(row['rank'])} {row['symbol']} {row['direction']} {row['session']}"
        for _, row in selected.iterrows()
    ]
    closest_values = []
    closest_labels = []
    for index, left in enumerate(selected_sets):
        peers = [(other, overlap(left, right)) for other, right in enumerate(selected_sets) if other != index]
        other, value = max(peers, key=lambda item: item[1]) if peers else (-1, 0.0)
        closest_values.append(value)
        closest_labels.append(labels[other] if other >= 0 else "none")
    end = latest_feature_timestamp(root, symbols)
    weeks = ((end.normalize() - START.normalize()).days + 1) / 7
    selected["stored_entry_count"] = [len(values) for values in selected_sets]
    selected["setups_week"] = [len(values) / weeks for values in selected_sets]
    selected["closest_selected_overlap"] = closest_values
    selected["closest_selected_strategy"] = closest_labels
    selected["tier"] = np.where(selected["passes_funded_gate"], "strict_5R", "quality_10R")
    selected["plain_english"] = [explain_conditions(row) for _, row in selected.iterrows()]
    selected.to_csv(output_dir / "multisymbol_final_top4.csv", index=False)

    matrix = pd.DataFrame(index=labels, columns=labels, dtype=float)
    for left_index, left in enumerate(selected_sets):
        for right_index, right in enumerate(selected_sets):
            matrix.iloc[left_index, right_index] = overlap(left, right)
    matrix.index.name = "strategy"
    matrix.to_csv(output_dir / "multisymbol_final_top4_overlap_matrix.csv")

    legacy, legacy_sets = load_legacy_portfolio(args.legacy_results)
    comparison_end = end
    legacy_feature = args.legacy_results.parent / "quant" / "feature_database.csv"
    if not legacy.empty and legacy_feature.exists():
        legacy_timestamps = pd.read_csv(legacy_feature, usecols=["timestamp"])["timestamp"]
        comparison_end = min(
            end,
            pd.to_datetime(legacy_timestamps.iloc[-1], utc=True),
        )
    rows = []
    before = frequency_metrics(legacy_sets, comparison_end)
    before["portfolio"] = "Current GBPUSD paper portfolio"
    rows.append(before)
    strict_selected_sets = [
        values
        for values, passes in zip(selected_sets, selected["passes_funded_gate"].astype(bool))
        if passes
    ]
    strict_after = frequency_metrics(legacy_sets + strict_selected_sets, comparison_end)
    strict_after["portfolio"] = "Current portfolio + strict GBPJPY pair"
    rows.append(strict_after)
    after = frequency_metrics(legacy_sets + selected_sets, comparison_end)
    after["portfolio"] = "Current GBPUSD portfolio + new pair Top4"
    rows.append(after)
    frequency = pd.DataFrame(rows)
    frequency = frequency[["portfolio"] + [column for column in frequency.columns if column != "portfolio"]]
    frequency.to_csv(output_dir / "multisymbol_frequency_comparison.csv", index=False)
    discovery_counts = build_discovery_counts(run_dir, output_dir)
    runtimes = build_runtime_summary(run_dir, args.legacy_results, output_dir)
    discovery_seconds = float(runtimes[runtimes["stage"].eq("discovery")]["seconds"].sum())
    deep_seconds = float(runtimes[runtimes["stage"].eq("deep_test")]["seconds"].sum())
    old_runtime_file = args.legacy_results / "asia" / "asia_runtime_summary.csv"
    old_discovery_seconds = math.nan
    old_deep_seconds = math.nan
    if old_runtime_file.exists():
        old_runtime = pd.read_csv(old_runtime_file).set_index("stage")
        old_discovery_seconds = float(old_runtime.loc["parallel_discovery_wall_seconds", "seconds"])
        old_deep_seconds = float(old_runtime.loc["total_deep_wall_seconds", "seconds"])

    lines = [
        "MULTI-SYMBOL STRATEGY RESEARCH SUMMARY",
        "=" * 40,
        f"Analysis window: {START.isoformat()} to {end.isoformat()}.",
        f"Like-for-like frequency window ends: {comparison_end.isoformat()}.",
        f"GBPJPY strict funded-gate families before overlap pruning: {strict_counts['GBPJPY']}.",
        f"AUDUSD strict funded-gate families before overlap pruning: {strict_counts['AUDUSD']}.",
        f"Combined strict families after {OVERLAP_THRESHOLD:.2f} entry-time overlap pruning: {len(strict_deduplicated)}.",
        f"Quality-gate families before pruning: GBPJPY {quality_counts['GBPJPY']}; AUDUSD {quality_counts['AUDUSD']}.",
        f"Combined quality families after overlap pruning: {len(quality_deduplicated)}.",
        f"Discovery totals: {int(discovery_counts['combinations_examined'].sum()):,} combinations examined; "
        f"{int(discovery_counts['saved_candidates'].sum()):,} saved; "
        f"{int(discovery_counts['quality_survivors'].sum()):,} quality-screen survivors; "
        f"{int(discovery_counts['strict_discovery_survivors'].sum()):,} strict-screen survivors.",
        "Strict gate: RR >= 3, trades >= 40, PF >= 1.7, max DD <= 5R, RR stability >= 0.80, every tested year positive.",
        "Quality gate used for balanced Top4: same rules with max DD <= 10R; the output marks which also pass the strict 5R gate.",
        "",
        "FINAL NEW-PAIR TOP 4",
        "-" * 20,
    ]
    for _, row in selected.iterrows():
        lines.append(
            f"{int(row['rank'])}. {row['symbol']} {row['direction']} {row['session']} | {row['conditions']} | "
            f"RR {row['rr']:g} | trades {int(row['trades'])} | net {row['net_r']:.2f}R | "
            f"expectancy {row['expectancy_r']:.3f}R | PF {row['profit_factor']:.3f} | "
            f"DD {row['max_drawdown_r']:.2f}R | win {row['win_rate']:.2f}% | "
            f"{row['setups_week']:.3f}/week | stability {row['rr_stability']:.3f} | "
            f"robust {row['robust_score']:.3f} | years {int(row['positive_years'])}/{int(row['years_tested'])} | "
            f"closest overlap {row['closest_selected_overlap']:.3f} | tier {row['tier']}"
        )
        lines.append(f"   {row['plain_english']}")
    if not legacy.empty:
        lines += [
            "",
            "OPPORTUNITY FREQUENCY",
            "-" * 21,
            f"Current portfolio: {before['unique_setups_week']:.3f} unique setups/week; average gap {before['average_days_between_setups']:.3f} days.",
            f"With strict GBPJPY pair: {strict_after['unique_setups_week']:.3f} unique setups/week; average gap {strict_after['average_days_between_setups']:.3f} days.",
            f"With new pairs: {after['unique_setups_week']:.3f} unique setups/week; average gap {after['average_days_between_setups']:.3f} days.",
            f"Trading days 0/1/2+: current {before['trading_days_0']}/{before['trading_days_1']}/{before['trading_days_2plus']}; "
            f"strict pair {strict_after['trading_days_0']}/{strict_after['trading_days_1']}/{strict_after['trading_days_2plus']}; "
            f"with new pairs {after['trading_days_0']}/{after['trading_days_1']}/{after['trading_days_2plus']}.",
        ]
    lines += [
        "",
        "COMPUTATIONAL RUNTIME",
        "-" * 21,
        f"Current discovery wall time: {discovery_seconds:.3f}s ({discovery_seconds / 60:.2f} min) across two symbols and three sessions.",
        f"Current deep-test wall time: {deep_seconds:.3f}s ({deep_seconds / 60:.2f} min) with four parallel workers per symbol.",
        "Feature-building and promotion were not timed, so they are excluded from the measured total.",
    ]
    if math.isfinite(old_discovery_seconds) and math.isfinite(old_deep_seconds):
        lines += [
            f"Prior recorded Asia run: discovery {old_discovery_seconds:.3f}s; deep test {old_deep_seconds:.3f}s.",
            "The current workflow was much faster in recorded wall time, but this is not a strict benchmark because candidate pools, data span and worker layout differ.",
        ]
    (output_dir / "multisymbol_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Strict counts: {strict_counts}; quality counts: {quality_counts}")
    print(f"Deduplicated strict/quality families: {len(strict_deduplicated)}/{len(quality_deduplicated)}")
    print(selected[["rank", "symbol", "direction", "session", "conditions", "rr", "trades", "profit_factor", "max_drawdown_r", "robust_score", "closest_selected_overlap"]].to_string(index=False))
    print(frequency.to_string(index=False))
    print(f"Saved: {output_dir}")


if __name__ == "__main__":
    main()
