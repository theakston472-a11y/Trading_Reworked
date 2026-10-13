from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import pandas as pd

from finalize_multisymbol_research import (
    FAMILY,
    START,
    add_gates,
    annotate_selection,
    entry_times,
    frequency_metrics,
    load_legacy_portfolio,
    load_trades,
    locate_worker_databases,
    ordered,
    prune_overlap,
    strategy_key,
    top10_each,
)


DEFAULT_SYMBOLS = ("GBPUSD", "GBPJPY", "AUDUSD")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize the three-symbol V10 SMC research scan."
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--feature-root", required=True, type=Path)
    parser.add_argument("--legacy-results", type=Path, default=Path(r"D:\Trading\Trading_Reworked\results"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    return parser.parse_args()


def completed_symbol_dir(run_dir: Path, symbol: str) -> Path:
    preferred = run_dir / "deep_completed" / symbol
    fallback = run_dir / "deep" / symbol
    if preferred.exists():
        return preferred
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"No deep-test directory found for {symbol}")


def choose_balanced_top4(candidates: pd.DataFrame) -> pd.DataFrame:
    chosen: list[int] = []
    for direction in ("BUY", "SELL"):
        pool = candidates[candidates["direction"].eq(direction)]
        direction_choices: list[int] = []
        used_symbols: set[str] = set()
        for index, row in pool.iterrows():
            symbol = str(row["symbol"])
            if symbol not in used_symbols:
                direction_choices.append(int(index))
                used_symbols.add(symbol)
            if len(direction_choices) == 2:
                break
        if len(direction_choices) < 2:
            for index in pool.index:
                if int(index) not in direction_choices:
                    direction_choices.append(int(index))
                if len(direction_choices) == 2:
                    break
        chosen.extend(direction_choices)
    result = ordered(candidates.loc[sorted(set(chosen))]).head(4).reset_index(drop=True)
    return result


def choose_symbol_direction_top6(candidates: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        for direction in ("BUY", "SELL"):
            pool = candidates[
                candidates["symbol"].eq(symbol) & candidates["direction"].eq(direction)
            ]
            if not pool.empty:
                rows.append(pool.iloc[[0]])
    if not rows:
        return pd.DataFrame(columns=candidates.columns)
    return ordered(pd.concat(rows, ignore_index=True)).reset_index(drop=True)


def latest_timestamps(feature_root: Path, symbols: list[str]) -> dict[str, pd.Timestamp]:
    result: dict[str, pd.Timestamp] = {}
    for symbol in symbols:
        file = feature_root / symbol / "feature_database.csv"
        timestamps = pd.read_csv(file, usecols=["timestamp"])["timestamp"]
        result[symbol] = pd.to_datetime(timestamps.iloc[-1], utc=True)
    return result


def discovery_counts(run_dir: Path, symbols: list[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
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
        examined = []
        for _, row in counts.iterrows():
            stem = f"{symbol.lower()}_{str(row['session']).lower().replace(' ', '_')}_{str(row['direction']).lower()}"
            log = run_dir / "logs" / f"{stem}.log"
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            matches = re.findall(r"New combinations examined:\s*([\d,]+)", text)
            examined.append(int(matches[-1].replace(",", "")) if matches else 0)
        counts.insert(3, "combinations_examined", examined)
        rows.append(counts)
    return pd.concat(rows, ignore_index=True)


def runtime_summary() -> pd.DataFrame:
    # Feature and discovery timings came from the uninterrupted stage logs.
    # Deep timings are active observed compute time because the run was paused/resumed.
    rows = [
        {"stage": "feature_build", "scope": "GBPUSD", "seconds": 139.612, "precision": "measured"},
        {"stage": "feature_build", "scope": "GBPJPY", "seconds": 85.903, "precision": "measured"},
        {"stage": "feature_build", "scope": "AUDUSD", "seconds": 85.974, "precision": "measured"},
        {"stage": "discovery", "scope": "Asia_all_symbols", "seconds": 72.1, "precision": "measured_wall"},
        {"stage": "discovery", "scope": "London_all_symbols", "seconds": 273.7, "precision": "measured_wall"},
        {"stage": "discovery", "scope": "New_York_all_symbols", "seconds": 57.9, "precision": "measured_wall"},
        {"stage": "deep_test", "scope": "GBPUSD", "seconds": 3090.0, "precision": "approx_active_paused_run"},
        {"stage": "deep_test", "scope": "GBPJPY", "seconds": 1063.0, "precision": "observed_active_resumed_run"},
        {"stage": "deep_test", "scope": "AUDUSD", "seconds": 844.0, "precision": "observed_active_resumed_run"},
    ]
    frame = pd.DataFrame(rows)
    frame["minutes"] = frame["seconds"] / 60.0
    return frame


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    feature_root = args.feature_root.resolve()
    symbols = [str(symbol).upper() for symbol in args.symbols]
    output_dir = run_dir / "final_v10"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_best = []
    trade_map: dict[tuple[str, ...], list[dict]] = {}
    strict_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}

    for symbol in symbols:
        symbol_dir = completed_symbol_dir(run_dir, symbol)
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
    quality_all = best_all[best_all["passes_quality_gate"]].copy().reset_index(drop=True)
    strict_all = best_all[best_all["passes_funded_gate"]].copy().reset_index(drop=True)

    strict_dedup, strict_rejected = prune_overlap(strict_all, trade_map)
    strict_dedup.insert(0, "dedup_rank", range(1, len(strict_dedup) + 1))
    strict_dedup.to_csv(output_dir / "smc_v10_funded_deduplicated.csv", index=False)
    strict_rejected.to_csv(output_dir / "smc_v10_funded_overlap_rejections.csv", index=False)

    quality_dedup, quality_rejected = prune_overlap(quality_all, trade_map)
    quality_dedup.insert(0, "dedup_rank", range(1, len(quality_dedup) + 1))
    quality_dedup.to_csv(output_dir / "smc_v10_quality_deduplicated.csv", index=False)
    quality_rejected.to_csv(output_dir / "smc_v10_quality_overlap_rejections.csv", index=False)

    timestamps = latest_timestamps(feature_root, symbols)
    comparison_end = min(timestamps.values())
    weeks = ((comparison_end.normalize() - START.normalize()).days + 1) / 7

    top4_source = choose_balanced_top4(quality_dedup)
    top4, top4_sets, top4_matrix = annotate_selection(top4_source, trade_map, weeks)
    top4.to_csv(output_dir / "smc_v10_final_top4.csv", index=False)
    top4_matrix.to_csv(output_dir / "smc_v10_final_top4_overlap_matrix.csv")

    top6_source = choose_symbol_direction_top6(quality_dedup, symbols)
    top6, top6_sets, top6_matrix = annotate_selection(top6_source, trade_map, weeks, "plan_rank")
    top6.to_csv(output_dir / "smc_v10_balanced_top6.csv", index=False)
    top6_matrix.to_csv(output_dir / "smc_v10_balanced_top6_overlap_matrix.csv")

    frequency_rows = []
    strict_sets = [
        entry_times(trade_map[strategy_key(row)])
        for _, row in strict_dedup.iterrows()
    ]
    try:
        legacy, legacy_sets = load_legacy_portfolio(args.legacy_results)
    except (FileNotFoundError, RuntimeError):
        legacy, legacy_sets = pd.DataFrame(), []
    if legacy_sets:
        before = frequency_metrics(legacy_sets, comparison_end)
        before["portfolio"] = "Current GBPUSD core"
        frequency_rows.append(before)
        after_strict = frequency_metrics(legacy_sets + strict_sets, comparison_end)
        after_strict["portfolio"] = "Current core + strict V10 set"
        frequency_rows.append(after_strict)
        after4 = frequency_metrics(legacy_sets + top4_sets, comparison_end)
        after4["portfolio"] = "Current core + V10 Top4"
        frequency_rows.append(after4)
        after6 = frequency_metrics(legacy_sets + top6_sets, comparison_end)
        after6["portfolio"] = "Current core + balanced V10 Top6"
        frequency_rows.append(after6)
    else:
        strict_only = frequency_metrics(strict_sets, comparison_end)
        strict_only["portfolio"] = "Strict V10 set only"
        frequency_rows.append(strict_only)
        top4_only = frequency_metrics(top4_sets, comparison_end)
        top4_only["portfolio"] = "V10 Top4 only"
        frequency_rows.append(top4_only)
        top6_only = frequency_metrics(top6_sets, comparison_end)
        top6_only["portfolio"] = "V10 balanced Top6 only"
        frequency_rows.append(top6_only)
    frequency = pd.DataFrame(frequency_rows)
    frequency = frequency[["portfolio"] + [column for column in frequency.columns if column != "portfolio"]]
    frequency.to_csv(output_dir / "smc_v10_frequency_comparison.csv", index=False)

    discovery = discovery_counts(run_dir, symbols)
    discovery.to_csv(output_dir / "smc_v10_discovery_counts.csv", index=False)
    runtimes = runtime_summary()
    runtimes.to_csv(output_dir / "smc_v10_runtime_summary.csv", index=False)

    lines = [
        "SMC V10 THREE-SYMBOL RESEARCH SUMMARY",
        "=" * 40,
        f"Engine: 2026-10-10-v10-smc-guide-expansion",
        f"Fair frequency window: {START.isoformat()} to {comparison_end.isoformat()}.",
        f"Symbols: {', '.join(symbols)}.",
        f"Discovery: {int(discovery['combinations_examined'].sum()):,} combinations examined; "
        f"{int(discovery['saved_candidates'].sum()):,} candidates saved; "
        f"{int(discovery['quality_survivors'].sum()):,} quality survivors.",
        f"Deep sweep: {len(symbols) * 100:,} promoted candidates x 61 RR levels x 3 periods = "
        f"{len(symbols) * 100 * 61 * 3:,} RR-period tests.",
        f"Strict funded-gate families: {strict_counts}.",
        f"Quality-gate families: {quality_counts}.",
        f"After 0.80 entry-time overlap pruning: strict {len(strict_dedup)}, quality {len(quality_dedup)}.",
        "Strict gate: RR >= 3, trades >= 40, PF >= 1.7, max DD <= 5R, stability >= 0.80, all years positive.",
        "Quality gate: identical except max DD <= 10R.",
        "",
        "FINAL TOP 4",
        "-" * 20,
    ]
    for _, row in top4.iterrows():
        lines.append(
            f"{int(row['rank'])}. {row['symbol']} {row['direction']} {row['session']} | {row['conditions']} | "
            f"RR {row['rr']:g} | trades {int(row['trades'])} | net {row['net_r']:.2f}R | "
            f"expectancy {row['expectancy_r']:.3f}R | PF {row['profit_factor']:.3f} | "
            f"DD {row['max_drawdown_r']:.2f}R | win {row['win_rate']:.2f}% | "
            f"{row['setups_week']:.3f}/week | stability {row['rr_stability']:.3f} | "
            f"robust {row['robust_score']:.3f} | years {int(row['positive_years'])}/{int(row['years_tested'])} | "
            f"closest overlap {row['closest_selected_overlap']:.3f} | {row['tier']}"
        )
        lines.append(f"   {row['plain_english']}")
    lines.extend(["", "FREQUENCY", "-" * 20])
    for _, row in frequency.iterrows():
        lines.append(
            f"{row['portfolio']}: {row['unique_setups_week']:.3f} unique setups/week; "
            f"average gap {row['average_days_between_setups']:.3f} days; "
            f"days 0/1/2+ = {int(row['trading_days_0'])}/{int(row['trading_days_1'])}/{int(row['trading_days_2plus'])}; "
            f"overlap {row['overlap_pct_of_raw']:.2%}."
        )
    lines.extend(
        [
            "",
            "RUNTIME NOTE",
            "-" * 20,
            "Feature and discovery stage times are measured. Deep tests were paused/resumed, so their rows report active observed compute time rather than a clean uninterrupted benchmark.",
            "No live or paper-bot strategy list was changed by this research run.",
        ]
    )
    (output_dir / "smc_v10_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Strict counts: {strict_counts}")
    print(f"Quality counts: {quality_counts}")
    print(f"Deduplicated strict/quality: {len(strict_dedup)}/{len(quality_dedup)}")
    print(top4[["rank", "symbol", "direction", "session", "conditions", "rr", "trades", "profit_factor", "max_drawdown_r", "robust_score", "closest_selected_overlap"]].to_string(index=False))
    print(frequency.to_string(index=False))
    print(f"Saved: {output_dir}")


if __name__ == "__main__":
    main()
