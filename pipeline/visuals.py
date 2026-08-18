from pathlib import Path
import re
import pandas as pd
import numpy as np

def parse_conditions(text):
    parts = re.split(r"\s*\+\s*", str(text))
    return [x.strip() for x in parts if x.strip()]

def _bool_series(s):
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0).astype(float) != 0
    return s.astype(str).str.strip().str.lower().isin(["true","1","yes","y"])

def _window_for_trade(df, entry_time, exit_time, before=80, after=100):
    idx = df.index[df["timestamp"].eq(entry_time)]
    if len(idx) == 0:
        idx = df.index[df["timestamp"].eq(pd.Timestamp(entry_time))]
    if len(idx) == 0:
        return None
    pos = df.index.get_loc(idx[0])
    return df.iloc[max(0, pos-before):min(len(df), pos+after+1)].copy()

def build_trade_rows(df, conditions, direction, rr, session=None, max_bars=48):
    # Import the existing engine instead of duplicating its trade logic.
    import sys
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from quant.backtester import backtest_strategy

    data = df.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
    for c in conditions:
        if c in data.columns:
            data[c] = _bool_series(data[c])

    result = backtest_strategy(
        data, {c: True for c in conditions},
        direction=direction,
        risk_reward=float(rr),
        stop_mode="atr",
        stop_multiplier=1.0,
        max_bars=int(max_bars),
        session=session,
    )
    trades = result.get("trades", pd.DataFrame()).copy()
    if trades.empty:
        return trades
    return trades

def render_trade_chart(df, trade, conditions, rr, out_file, title):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as e:
        raise RuntimeError("Plotly is required. Run: pip install -r pipeline/requirements.txt") from e

    data = df.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
    entry_time = pd.Timestamp(trade["entry_time"])
    exit_time = pd.Timestamp(trade["exit_time"]) if "exit_time" in trade else entry_time

    idx = data.index[data["timestamp"].eq(entry_time)]
    if len(idx) == 0:
        return
    pos = data.index.get_loc(idx[0])
    before, after = 80, 100
    w = data.iloc[max(0, pos-before):min(len(data), pos+after+1)].copy()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=w["timestamp"], open=w["open"], high=w["high"],
        low=w["low"], close=w["close"], name="GBPUSD"
    ))

    for ema in ("20","50","100","200"):
        c = f"ema{ema}"
        if c in w.columns:
            fig.add_trace(go.Scatter(x=w["timestamp"], y=w[c], mode="lines", name=c.upper()))

    entry = float(trade["entry"])
    stop_distance = float(trade["stop_distance"])
    direction = str(trade["direction"]).upper()
    stop = entry - stop_distance if direction == "BUY" else entry + stop_distance
    target = entry + stop_distance * float(rr) if direction == "BUY" else entry - stop_distance * float(rr)

    fig.add_hline(y=entry, line_dash="dash", annotation_text=f"ENTRY {entry:.5f}")
    fig.add_hline(y=stop, line_dash="dot", annotation_text=f"STOP {stop:.5f}")
    fig.add_hline(y=target, line_dash="dot", annotation_text=f"TARGET {target:.5f}")

    # Highlight candles where the strategy conditions are true.
    cond_mask = np.ones(len(w), dtype=bool)
    for c in conditions:
        if c in w.columns:
            cond_mask &= _bool_series(w[c]).to_numpy()
    hits = w.loc[cond_mask]
    if not hits.empty:
        fig.add_trace(go.Scatter(
            x=hits["timestamp"], y=hits["high"],
            mode="markers", marker=dict(size=8, symbol="triangle-down"),
            name="Condition match",
            text=[" + ".join(conditions)] * len(hits),
            hovertemplate="%{x}<br>%{text}<extra></extra>"
        ))

    outcome = str(trade.get("result", "UNKNOWN"))
    fig.update_layout(
        title=title + f" | {direction} | {outcome} | {float(trade['r']):.2f}R",
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=True,
        template="plotly_dark",
        hovermode="x unified",
        height=800,
    )
    fig.write_html(str(out_file), include_plotlyjs="inline", full_html=True)

def make_examples(df, winner_row, out_dir, examples=6):
    conditions = parse_conditions(winner_row["conditions"])
    direction = str(winner_row["direction"]).upper()
    session = winner_row.get("session")
    if pd.isna(session) or str(session).lower() == "all":
        session = None
    rr = float(winner_row["rr"])

    trades = build_trade_rows(df, conditions, direction, rr, session=session)
    if trades.empty:
        return 0

    trades = trades.copy()
    # Existing backtester exposes signal_time/entry_time but not exit_time.
    # Reconstruct the exit timestamp from the source index using bars_held.
    ts = pd.to_datetime(df["timestamp"], utc=True)
    exit_times = []
    for _, t in trades.iterrows():
        entry_idx = df.index[df["timestamp"].eq(pd.Timestamp(t["entry_time"]))]
        if len(entry_idx):
            p = df.index.get_loc(entry_idx[0])
            exit_pos = min(len(df)-1, p + int(t["bars_held"]) - 1)
            exit_times.append(ts.iloc[exit_pos])
        else:
            exit_times.append(pd.NaT)
    trades["exit_time"] = exit_times

    out_dir.mkdir(parents=True, exist_ok=True)
    wins = trades[trades["result"].eq("WIN")].head(examples)
    losses = trades[trades["result"].eq("LOSS")].head(examples)

    count = 0
    for label, subset in (("winner", wins), ("loser", losses)):
        for i, (_, t) in enumerate(subset.iterrows(), start=1):
            fn = out_dir / f"{label}_{i:02d}.html"
            render_trade_chart(
                df, t, conditions, rr, fn,
                f"{direction} {winner_row['session']} | {' + '.join(conditions)}"
            )
            count += 1
    return count
