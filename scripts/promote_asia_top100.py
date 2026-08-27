from pathlib import Path
import pandas as pd


ROOT = Path(r"D:\Trading\Trading_Reworked")
ASIA = ROOT / "results" / "asia"


def main():
    frames = []
    counts = []
    for direction in ("BUY", "SELL"):
        path = ASIA / "discovery" / f"asia_{direction.lower()}.csv"
        df = pd.read_csv(path)
        examined = len(df)
        df["trades"] = pd.to_numeric(df["trades"], errors="coerce").fillna(0)
        df = df[df["trades"] >= 30].copy()
        df = df.drop_duplicates(["direction", "session", "conditions"])
        sort_cols = [c for c in ("score", "positive_periods", "trades", "net_r", "expectancy_r", "min_profit_factor") if c in df]
        df = df.sort_values(sort_cols, ascending=False, kind="stable")
        df.insert(0, "screen_rank", range(1, len(df) + 1))
        counts.append({"direction": direction, "discovery_survivors": examined, "screened_survivors": len(df)})
        frames.append(df)

    screened = pd.concat(frames, ignore_index=True)
    screened.to_csv(ASIA / "asia_discovery_screened.csv", index=False)
    pd.DataFrame(counts).to_csv(ASIA / "asia_discovery_counts.csv", index=False)

    promoted = []
    for direction in ("BUY", "SELL"):
        x = screened[screened["direction"].eq(direction)].head(50).copy()
        promoted.append(x)
    top = pd.concat(promoted, ignore_index=True)
    top = top.sort_values(["score", "direction"], ascending=[False, True], kind="stable").reset_index(drop=True)
    top.insert(0, "top100_rank", range(1, len(top) + 1))
    top.to_csv(ASIA / "asia_top100_candidates.csv", index=False)
    print(pd.DataFrame(counts).to_string(index=False))
    print(f"Promoted: {len(top)} ({(top.direction == 'BUY').sum()} BUY, {(top.direction == 'SELL').sum()} SELL)")


if __name__ == "__main__":
    main()
