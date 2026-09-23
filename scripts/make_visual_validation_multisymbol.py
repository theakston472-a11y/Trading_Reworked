from __future__ import annotations

import argparse
import html
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pandas as pd

os.environ.setdefault("MPLBACKEND", "Agg")
_matplotlib_cache = Path(tempfile.gettempdir()) / "paperbot_matplotlib"
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

import make_visual_validation as visual
from finalize_multisymbol_research import family_key, locate_worker_databases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render trade-validation charts for the multi-symbol finalists.")
    parser.add_argument("--run-dir", required=True, type=Path)
    return parser.parse_args()


def build_selected_database(
    symbol_dir: Path,
    strategies: pd.DataFrame,
    target: Path,
) -> None:
    locations = locate_worker_databases(symbol_dir)
    first_database = next(iter(locations.values()))
    with sqlite3.connect(first_database) as source:
        schema = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='results'"
        ).fetchone()[0]
    if target.exists():
        target.unlink()
    with sqlite3.connect(target) as output:
        output.execute(schema)
        columns = [row[1] for row in output.execute("PRAGMA table_info(results)")]
        placeholders = ",".join("?" for _ in columns)
        insert_sql = f"INSERT OR REPLACE INTO results ({','.join(columns)}) VALUES ({placeholders})"
        for _, strategy in strategies.iterrows():
            source_path = locations[family_key(strategy)]
            with sqlite3.connect(source_path) as source:
                row = source.execute(
                    """SELECT * FROM results
                       WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                         AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                         AND engine_version=? LIMIT 1""",
                    (
                        strategy["direction"], strategy["session"], strategy["conditions"],
                        float(strategy["rr"]), strategy["entry_mode"],
                        int(strategy["entry_wait_bars"]), strategy["engine_version"],
                    ),
                ).fetchone()
            if row is None:
                raise RuntimeError(f"Missing selected result for {family_key(strategy)}")
            output.execute(insert_sql, row)
        output.commit()


def build_index(output_dir: Path, selected: pd.DataFrame, elapsed: float) -> Path:
    rows = []
    for _, row in selected.iterrows():
        symbol = str(row["symbol"])
        report = f"{symbol}/strategy_report.html"
        tier = "Strict ≤5R" if bool(row["passes_funded_gate"]) else "Quality ≤10R"
        rows.append(
            "<tr>"
            f"<td>{int(row['rank'])}</td>"
            f"<td><a href='{html.escape(report)}'>{html.escape(symbol)}</a></td>"
            f"<td>{html.escape(str(row['direction']))}</td>"
            f"<td>{html.escape(str(row['session']))}</td>"
            f"<td>{html.escape(str(row['conditions']))}</td>"
            f"<td>{float(row['rr']):.1f}</td>"
            f"<td>{int(row['trades'])}</td>"
            f"<td>{float(row['profit_factor']):.2f}</td>"
            f"<td>{float(row['max_drawdown_r']):.2f}R</td>"
            f"<td>{html.escape(tier)}</td>"
            "</tr>"
        )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GBPJPY + AUDUSD Final Strategy Validation</title>
<style>
body{{background:#080b10;color:#e8edf4;font:16px/1.45 Arial,sans-serif;margin:0;padding:32px}}
.wrap{{max-width:1400px;margin:auto}}h1{{margin-top:0}}p{{color:#aeb8c5}}
table{{width:100%;border-collapse:collapse;background:#111722}}th,td{{padding:12px;border:1px solid #263142;text-align:left}}
th{{background:#182131;color:#8fdcff}}a{{color:#5fd3ff}}.note{{padding:16px;background:#101924;border-left:4px solid #5fd3ff;margin:20px 0}}
</style></head><body><div class="wrap">
<h1>GBPJPY + AUDUSD Final Strategy Validation</h1>
<p>Four trade examples per finalist: two wins and two losses where available. Open either symbol to view the full black-background trade charts.</p>
<div class="note">AUDUSD finalists pass the broader quality gate but not the strict 5R drawdown gate. They should remain research/paper candidates until separately approved for deployment.</div>
<table><thead><tr><th>Rank</th><th>Symbol / report</th><th>Direction</th><th>Session</th><th>Conditions</th><th>RR</th><th>Trades</th><th>PF</th><th>Max DD</th><th>Tier</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p>Chart generation time: {elapsed:.2f} seconds.</p>
</div></body></html>"""
    index = output_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    root = Path(__file__).resolve().parents[1]
    final_dir = run_dir / "final"
    selected = pd.read_csv(final_dir / "multisymbol_final_top4.csv")
    output_dir = final_dir / "visual_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    for symbol in ("GBPJPY", "AUDUSD"):
        strategies = selected[selected["symbol"].eq(symbol)].copy()
        if strategies.empty:
            continue
        symbol_output = output_dir / symbol
        symbol_output.mkdir(parents=True, exist_ok=True)
        top_file = symbol_output / f"{symbol.lower()}_top_strategies.csv"
        database = symbol_output / f"{symbol.lower()}_selected.sqlite"
        strategies.to_csv(top_file, index=False)
        build_selected_database(run_dir / "deep" / symbol, strategies, database)

        visual.FEATURE_FILE = root / "quant" / "research_symbols" / symbol / "feature_database.csv"
        visual.TOP_FILE = top_file
        visual.DB_FILE = database
        visual.OUTPUT_DIR = symbol_output
        visual.CHART_DIR = symbol_output / "charts"
        visual.TOP_N = len(strategies)
        visual.WIN_EXAMPLES = 2
        visual.LOSS_EXAMPLES = 2
        visual.BARS_BEFORE = 32
        visual.BARS_AFTER = 18
        visual.main()

    elapsed = time.perf_counter() - started
    index = build_index(output_dir, selected, elapsed)
    pd.DataFrame([{"stage": "visual_validation", "seconds": elapsed, "minutes": elapsed / 60}]).to_csv(
        final_dir / "visual_runtime.csv", index=False
    )
    print(f"Combined report: {index}")
    print(f"Elapsed: {elapsed:.3f} seconds")


if __name__ == "__main__":
    main()
