from pathlib import Path
import pandas as pd
import numpy as np

def _num(df, col, default=0.0):
    return pd.to_numeric(df[col], errors="coerce").fillna(default) if col in df.columns else pd.Series(default, index=df.index)

def screen_discovery(input_file: Path, output_file: Path, min_trades=30, min_pf=1.05, max_dd=None):
    df = pd.read_csv(input_file)
    if df.empty:
        raise RuntimeError(f"No discovery rows found in {input_file}")

    if "trades" in df.columns:
        df = df[_num(df, "trades") >= min_trades].copy()

    if "profit_factor" in df.columns:
        df = df[_num(df, "profit_factor") >= min_pf].copy()

    if max_dd is not None and "max_drawdown_r" in df.columns:
        df = df[_num(df, "max_drawdown_r") <= max_dd].copy()

    # Prefer a robustness-oriented score when the source has one.
    score_col = next((c for c in ("strategy_score", "robust_score", "score", "net_r") if c in df.columns), None)
    if score_col:
        df["_quality_score"] = _num(df, score_col)
        df = df.sort_values("_quality_score", ascending=False)
        df = df.drop(columns=["_quality_score"])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)
    return df

def split_pools(df):
    required = {"direction", "session"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Discovery file missing columns: {sorted(missing)}")

    out = {}
    for name, (session, direction) in {
        "london_buy": ("London", "BUY"),
        "london_sell": ("London", "SELL"),
        "new_york_buy": ("New York", "BUY"),
        "new_york_sell": ("New York", "SELL"),
    }.items():
        x = df[
            df["direction"].astype(str).str.upper().eq(direction)
            & df["session"].astype(str).str.lower().eq(session.lower())
        ].copy()
        out[name] = x
    return out
