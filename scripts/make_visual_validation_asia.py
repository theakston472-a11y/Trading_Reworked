from pathlib import Path
import time

import make_visual_validation as visual
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
visual.TOP_FILE = ROOT / "results" / "asia_strategy_top4.csv"
visual.DB_FILE = ROOT / "results" / "asia_strategy_lab.sqlite"
visual.OUTPUT_DIR = ROOT / "results" / "visual_validation_asia"
visual.CHART_DIR = visual.OUTPUT_DIR / "charts"
visual.TOP_N = 4
visual.WIN_EXAMPLES = 2
visual.LOSS_EXAMPLES = 2
visual.BARS_BEFORE = 32
visual.BARS_AFTER = 18


if __name__ == "__main__":
    started = time.perf_counter()
    visual.main()
    elapsed = time.perf_counter() - started

    runtime_file = ROOT / "results" / "asia" / "asia_runtime_summary.csv"
    if runtime_file.exists():
        runtime = pd.read_csv(runtime_file)
        runtime = runtime[runtime["stage"] != "visual_validation_seconds"]
        runtime = pd.concat(
            [runtime, pd.DataFrame([{
                "stage": "visual_validation_seconds",
                "seconds": elapsed,
                "minutes": elapsed / 60,
            }])],
            ignore_index=True,
        )
        runtime.to_csv(runtime_file, index=False)

    summary_file = ROOT / "results" / "asia_portfolio_summary.txt"
    if summary_file.exists():
        lines = [
            line for line in summary_file.read_text(encoding="utf-8").splitlines()
            if not line.startswith("Visual validation:")
        ]
        lines.append(f"Visual validation: {elapsed:.3f}s for 16 charts and the HTML report.")
        summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
