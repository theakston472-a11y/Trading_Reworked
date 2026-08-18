from pathlib import Path
import pandas as pd
import html

def make_report(winner, out_dir, chart_files):
    out_dir.mkdir(parents=True, exist_ok=True)
    def val(k, default="N/A"):
        x = winner.get(k, default)
        if pd.isna(x):
            return default
        return x

    conditions = str(val("conditions"))
    direction = str(val("direction")).upper()
    session = str(val("session"))
    rr = val("rr")
    status = val("paper_status", "PAPER_PENDING")

    sections = {
        "Conditions": [x.strip() for x in conditions.split("+") if x.strip()],
        "Entry": [
            "Signal candle satisfies every listed condition.",
            "Existing backtester enters on the next candle open.",
        ],
        "Stop": [
            "ATR14-based stop using the existing backtester.",
            "Do not change stop logic between research and paper testing without revalidation.",
        ],
        "Target": [f"Preferred tested RR: {rr}R"],
        "Invalidation": [
            "The setup is invalid if the configured conditions are not all true.",
            "A paper-bot implementation must use the same feature definitions as the backtest.",
        ],
        "What to look for": [
            "The session must match the strategy.",
            "Every listed feature must be true on the signal candle.",
            "Check the actual chart examples before approving paper testing.",
        ],
        "Weaknesses / cautions": [
            "Historical performance is not a guarantee.",
            "Low trade counts and one-year-only performance are not acceptable as final winners.",
            "Visual examples are for understanding the rule, not cherry-picking trades.",
        ],
    }

    rows = []
    for title, items in sections.items():
        body = "<ol>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in items) + "</ol>"
        rows.append(f"<section><h2>{html.escape(title)}</h2>{body}</section>")

    metrics = [
        ("RR", rr), ("Trades", val("trades")), ("Net R", val("net_r")),
        ("Profit Factor", val("profit_factor")), ("Max Drawdown R", val("max_drawdown_r")),
        ("Avg Trades/Day", val("avg_trades_day")), ("Positive Years", val("positive_years")),
        ("RR Stability", val("rr_stability")), ("Robust Score", val("robust_score")),
        ("Paper Status", status),
    ]
    metric_html = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k,v in metrics
    )

    links = "".join(
        f'<li><a href="{html.escape(Path(f).name)}">{html.escape(Path(f).stem)}</a></li>'
        for f in chart_files
    )

    page = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{html.escape(direction)} {html.escape(session)} strategy</title>
<style>
body{{font-family:Arial,sans-serif;background:#101318;color:#eee;margin:0;padding:30px}}
.card{{background:#181d24;border-radius:12px;padding:22px;margin:18px 0}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border-bottom:1px solid #333;text-align:left}}
a{{color:#7db7ff}} h1{{margin-bottom:4px}} .status{{font-weight:bold}}
</style></head><body>
<h1>{html.escape(direction)} — {html.escape(session)}</h1>
<p>{html.escape(conditions)}</p>
<div class="card"><h2>Performance</h2><table>{metric_html}</table></div>
{''.join(rows)}
<div class="card"><h2>Interactive market examples</h2><ul>{links}</ul></div>
</body></html>"""
    report_file = out_dir / "report.html"
    report_file.write_text(page, encoding="utf-8")
    return report_file
