"""Persistent strategy-discovery registry.

Use this before generating a new search batch. It remembers strategies by a
canonical fingerprint, so condition order does not create duplicates.
"""
from __future__ import annotations
import argparse, hashlib, sqlite3
from pathlib import Path
import pandas as pd

def canonical_conditions(value):
    parts=[p.strip() for p in str(value).split("+") if p.strip()]
    return "+".join(sorted(set(parts), key=str.lower))

def fingerprint(direction, session, conditions):
    raw=f"{str(direction).strip().upper()}|{str(session).strip().lower()}|{canonical_conditions(conditions).lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()

def init_db(path):
    con=sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS strategies(
        fingerprint TEXT PRIMARY KEY,
        direction TEXT NOT NULL,
        session TEXT NOT NULL,
        conditions TEXT NOT NULL,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        discoveries INTEGER DEFAULT 1
    )""")
    con.commit()
    return con

def register(con, df):
    new=[]
    for _,r in df.iterrows():
        d=str(r["direction"]).strip().upper()
        s=str(r["session"]).strip()
        c=canonical_conditions(r["conditions"])
        fp=fingerprint(d,s,c)
        row=con.execute("SELECT fingerprint FROM strategies WHERE fingerprint=?",(fp,)).fetchone()
        if row:
            con.execute("UPDATE strategies SET last_seen=CURRENT_TIMESTAMP, discoveries=discoveries+1 WHERE fingerprint=?",(fp,))
        else:
            con.execute(
                "INSERT INTO strategies(fingerprint,direction,session,conditions) VALUES(?,?,?,?)",
                (fp,d,s,c)
            )
            new.append(fp)
    con.commit()
    return set(new)

def main():
    ap=argparse.ArgumentParser(description="Filter a candidate CSV to strategies never seen before.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--new-only", action="store_true")
    args=ap.parse_args()

    base=Path(__file__).resolve().parents[1]
    db=Path(args.db) if args.db else base/"results"/"strategy_registry.sqlite"
    db.parent.mkdir(parents=True,exist_ok=True)

    df=pd.read_csv(args.input)
    required={"direction","session","conditions"}
    missing=required-set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")

    # Canonicalise and remove duplicates in this batch first.
    df=df.copy()
    df["conditions"]=df["conditions"].map(canonical_conditions)
    df["fingerprint"]=[fingerprint(r.direction,r.session,r.conditions) for r in df.itertuples()]
    df=df.drop_duplicates("fingerprint").drop(columns="fingerprint")

    con=init_db(db)
    if args.new_only:
        new_fps=register(con, df)
        df["fingerprint"]=[fingerprint(r.direction,r.session,r.conditions) for r in df.itertuples()]
        out=df[df["fingerprint"].isin(new_fps)].drop(columns="fingerprint")
    else:
        register(con, df)
        out=df

    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(args.output,index=False)

    print(f"Input candidates: {len(df)}")
    print(f"New candidates in this search: {len(out) if args.new_only else 'not filtered'}")
    print(f"Registry: {db}")
    print(f"Output: {args.output}")

if __name__=="__main__":
    main()
