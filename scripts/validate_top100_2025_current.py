from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
FEATURE_FILE = BASE / "quant" / "feature_database.csv"
CANDIDATE_FILE = BASE / "quant" / "new_search" / "new_combination_results.csv"
OUT_PERIODS = BASE / "results" / "top100_2025_current_corrected_periods.csv"
OUT_SUMMARY = BASE / "results" / "top100_2025_current_summary.csv"

MAX_BARS = 48
TOP_N = 100
MIN_TRADES = 20

def backtest(df, direction, session, conditions, rr):
    work = df.copy()
    if session != "All":
        work = work[work["session"].astype(str).str.lower() == str(session).lower()]
    work = work.reset_index(drop=True)

    mask = np.ones(len(work), dtype=bool)
    for c in [x.strip() for x in str(conditions).split("+") if x.strip()]:
        if c not in work.columns:
            return None
        mask &= work[c].fillna(False).astype(bool).to_numpy()

    idxs = np.flatnonzero(mask)
    if not len(idxs):
        return None

    op = work["open"].to_numpy(float)
    hi = work["high"].to_numpy(float)
    lo = work["low"].to_numpy(float)
    cl = work["close"].to_numpy(float)
    atr = work["atr14"].to_numpy(float)
    results = []
    next_free = -1

    for i in idxs:
        if i <= next_free or i + 1 >= len(work):
            continue

        entry_i = i + 1
        entry = op[entry_i]
        atr_i = atr[i] if np.isfinite(atr[i]) else 0.0
        distance = max(hi[i] - entry, atr_i)
        if not np.isfinite(distance) or distance <= 0:
            continue

        if direction == "SELL":
            stop = entry + distance
            target = entry - distance * rr
        else:
            stop = entry - distance
            target = entry + distance * rr

        end = min(len(work) - 1, entry_i + MAX_BARS - 1)
        result = None

        for j in range(entry_i, end + 1):
            if direction == "SELL":
                hit_stop = hi[j] >= stop
                hit_target = lo[j] <= target
            else:
                hit_stop = lo[j] <= stop
                hit_target = hi[j] >= target

            # Conservative intrabar rule: if both are touched, stop wins.
            if hit_stop:
                result = -1.0
                exit_i = j
                break
            if hit_target:
                result = float(rr)
                exit_i = j
                break

        if result is None:
            exit_i = end
            result = ((entry - cl[exit_i]) if direction == "SELL"
                      else (cl[exit_i] - entry)) / distance

        results.append(result)
        next_free = exit_i

    if not results:
        return None

    arr = np.asarray(results, dtype=float)
    wins, losses = arr[arr > 0], arr[arr < 0]
    gross_profit = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 0.0
    equity = np.cumsum(arr)
    drawdown = np.maximum.accumulate(np.r_[0.0, equity])[1:] - equity

    return {
        "trades": len(arr),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(arr) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss else (999.0 if gross_profit else 0.0),
        "net_r": arr.sum(),
        "expectancy_r": arr.mean(),
        "max_drawdown_r": drawdown.max() if len(drawdown) else 0.0,
    }

def main():
    df = pd.read_csv(FEATURE_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    candidates = pd.read_csv(CANDIDATE_FILE)
    candidates = (
        candidates.sort_values("score", ascending=False)
        .drop_duplicates(["direction", "session", "conditions"])
        .head(TOP_N)
        .copy()
    )

    latest = df["timestamp"].max()
    periods = {
        "2025": (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-12-31 23:59:59", tz="UTC")),
        "2026_YTD": (pd.Timestamp("2026-01-01", tz="UTC"), latest),
    }

    rows = []
    for _, s in candidates.iterrows():
        for period, (start, end) in periods.items():
            sub = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]
            result = backtest(
                sub,
                str(s["direction"]).strip().upper(),
                str(s["session"]).strip(),
                str(s["conditions"]),
                float(s["rr"]),
            )
            if result is None:
                result = {k: 0.0 for k in ["trades","wins","losses","win_rate","profit_factor","net_r","expectancy_r","max_drawdown_r"]}
            rows.append({
                "direction": s["direction"],
                "session": s["session"],
                "conditions": s["conditions"],
                "rr": s["rr"],
                "candidate_score": s["score"],
                "period": period,
                **result,
            })

    periods_df = pd.DataFrame(rows)
    periods_df.to_csv(OUT_PERIODS, index=False)

    summary = (
        periods_df.groupby(["direction","session","conditions","rr"], as_index=False)
        .agg(
            trades=("trades","sum"),
            net_r=("net_r","sum"),
            avg_expectancy_r=("expectancy_r","mean"),
            min_profit_factor=("profit_factor","min"),
            avg_profit_factor=("profit_factor","mean"),
            worst_drawdown_r=("max_drawdown_r","max"),
            positive_periods=("net_r", lambda x: int((x > 0).sum())),
        )
    )
    summary["score2"] = (
        summary["avg_expectancy_r"] * summary["positive_periods"]
        / (summary["worst_drawdown_r"] + 1.0)
    )
    summary = summary.sort_values(["positive_periods","score2","trades"], ascending=False)
    summary.to_csv(OUT_SUMMARY, index=False)

    print(f"Candidates tested: {len(candidates)} unique strategies")
    print(f"Data: {df['timestamp'].min()} -> {latest}")
    print(f"Saved: {OUT_PERIODS}")
    print(f"Saved: {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
