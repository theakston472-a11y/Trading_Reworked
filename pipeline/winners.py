from pathlib import Path
import pandas as pd
import numpy as np
import json

METRIC_COLUMNS = [
    "robust_score", "rr_stability", "profit_factor",
    "net_r", "max_drawdown_r", "avg_trades_day",
    "positive_years", "years_tested", "trades"
]

def _n(row, col, default=0.0):
    try:
        x = float(row.get(col, default))
        return x if np.isfinite(x) else default
    except Exception:
        return default

def winner_score(row):
    # This is intentionally conservative: profit is not enough.
    pf = _n(row, "profit_factor")
    stability = _n(row, "rr_stability")
    robust = _n(row, "robust_score")
    dd = max(_n(row, "max_drawdown_r"), 0.0)
    freq = _n(row, "avg_trades_day")
    positive_years = _n(row, "positive_years")
    years = max(_n(row, "years_tested", 2), 1)

    consistency = positive_years / years
    dd_penalty = 1.0 / (1.0 + dd / 25.0)
    freq_factor = min(freq / 0.75, 1.5) if freq > 0 else 0.0

    return (
        robust * 0.45
        + stability * 15.0 * 0.20
        + min(max(pf - 1.0, 0.0), 2.0) * 10.0 * 0.15
        + consistency * 10.0 * 0.10
        + freq_factor * 5.0 * 0.05
        + dd_penalty * 5.0 * 0.05
    )

def select_winners(top_final_file: Path, out_dir: Path, max_winners=10):
    df = pd.read_csv(top_final_file)
    if df.empty:
        return pd.DataFrame()

    df["_winner_score"] = df.apply(winner_score, axis=1)

    # Hard safety gates: these prevent tiny/high-PF samples from becoming winners.
    if "trades" in df.columns:
        df = df[pd.to_numeric(df["trades"], errors="coerce").fillna(0) >= 30]
    if "years_tested" in df.columns:
        df = df[pd.to_numeric(df["years_tested"], errors="coerce").fillna(0) >= 2]
    if "positive_years" in df.columns:
        df = df[pd.to_numeric(df["positive_years"], errors="coerce").fillna(0) >= 1]
    if "profit_factor" in df.columns:
        df = df[pd.to_numeric(df["profit_factor"], errors="coerce").fillna(0) >= 1.05]
    if "rr_stability" in df.columns:
        df = df[pd.to_numeric(df["rr_stability"], errors="coerce").fillna(0) >= 0.70]

    df = df.sort_values("_winner_score", ascending=False).head(max_winners).copy()
    df.insert(0, "winner_rank", range(1, len(df) + 1))
    df["paper_status"] = "PAPER_PENDING"
    df["visual_status"] = "PENDING"
    df["human_review_status"] = "REQUIRED"

    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "winners.csv", index=False)

    # JSON is useful to the future paper bot.
    records = df.replace({np.nan: None}).to_dict(orient="records")
    with open(out_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)

    return df
