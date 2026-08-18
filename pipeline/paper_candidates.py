from pathlib import Path
import pandas as pd
import json

ROOT = Path(__file__).resolve().parents[1]
WINNERS = ROOT / "results" / "winners"

def main():
    rows = []
    for f in WINNERS.glob("*/winners.csv"):
        df = pd.read_csv(f)
        if not df.empty:
            df["pool"] = f.parent.name
            rows.append(df)
    if not rows:
        print("No winners found.")
        return
    all_df = pd.concat(rows, ignore_index=True)
    all_df = all_df[all_df["paper_status"].eq("PAPER_PENDING")].copy()
    out = WINNERS / "paper_trading_candidates.csv"
    all_df.to_csv(out, index=False)
    print(f"Saved: {out}")
    print(f"Candidates: {len(all_df)}")
    print("\nNothing is connected to a live account by this script.")
if __name__ == "__main__":
    main()
