from pathlib import Path
import pandas as pd
import html
import webbrowser
from datetime import datetime


# ============================================================
# SETTINGS
# ============================================================

ROOT = Path(r"D:\Trading\Trading_Reworked")
BIG = ROOT / "results" / "big_search"
OUT = ROOT / "results" / "reports"

OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD BIG SEARCH RESULTS
# ============================================================

files = sorted(BIG.glob("*/results.csv_final.csv"))

if not files:
    raise SystemExit(
        f"No BIG SEARCH result files found under {BIG}"
    )


frames = []

for f in files:
    try:
        df = pd.read_csv(f)

        if not df.empty:
            df["search"] = f.parent.name
            frames.append(df)

    except Exception as e:
        print(f"Skipping {f}: {e}")


if not frames:
    raise SystemExit("No readable result CSVs found.")


all_df = pd.concat(frames, ignore_index=True)


# ============================================================
# BASIC CLEANUP
# ============================================================

numeric_cols = [
    "rr",
    "trades",
    "net_r",
    "expectancy_r",
    "profit_factor",
    "max_drawdown_r",
    "win_rate",
    "avg_trades_day",
    "max_concurrent",
    "avg_hold_bars",
    "positive_years",
    "years_tested",
    "worst_year_pf",
    "avg_year_expectancy_r",
    "base_score",
    "rr_stability",
    "robust_score",
]

for col in numeric_cols:
    if col in all_df.columns:
        all_df[col] = pd.to_numeric(
            all_df[col],
            errors="coerce"
        )


# ============================================================
# REMOVE EXACT DUPLICATE RR RESULTS
#
# Same direction + session + conditions + RR
# is treated as the same individual test.
# ============================================================

dedupe_cols = [
    c
    for c in [
        "direction",
        "session",
        "conditions",
        "rr",
    ]
    if c in all_df.columns
]


if dedupe_cols:

    score_col = (
        "robust_score"
        if "robust_score" in all_df.columns
        else "base_score"
    )

    all_df = (
        all_df
        .sort_values(score_col, ascending=False)
        .drop_duplicates(
            dedupe_cols,
            keep="first"
        )
        .reset_index(drop=True)
    )


# ============================================================
# STATUS
# ============================================================

def status(row):

    trades = float(row.get("trades", 0) or 0)
    pf = float(row.get("profit_factor", 0) or 0)
    exp = float(row.get("expectancy_r", 0) or 0)
    years = float(row.get("years_tested", 0) or 0)

    if (
        trades >= 100
        and pf >= 1.20
        and exp >= 0.10
        and years >= 2
    ):
        return "STRONG"

    if (
        trades >= 50
        and pf >= 1.10
        and exp > 0
        and years >= 2
    ):
        return "PROMISING"

    if (
        trades >= 20
        and pf >= 1.00
        and exp > 0
    ):
        return "WATCH"

    return "REJECT"


all_df["status"] = all_df.apply(status, axis=1)


# ============================================================
# STRATEGY FAMILY
#
# IMPORTANT:
# RR IS NOT PART OF THE FAMILY KEY.
#
# This means:
#
# BUY + New York + conditions
#
# with RR 6.2, 6.3, 6.4 ... 6.9
#
# becomes ONE strategy family.
# ============================================================

family_cols = [
    c
    for c in [
        "direction",
        "session",
        "conditions",
    ]
    if c in all_df.columns
]


if len(family_cols) < 3:
    raise SystemExit(
        "Could not create strategy families. "
        "Expected direction, session and conditions columns."
    )


all_df["family_key"] = (
    all_df[family_cols]
    .fillna("")
    .astype(str)
    .agg(" | ".join, axis=1)
)


# ============================================================
# BUILD FAMILY RESULTS
# ============================================================

family_rows = []


for family_key, group in all_df.groupby(
    "family_key",
    sort=False
):

    # Best RR result = highest robust score
    group_sorted = group.sort_values(
        "robust_score",
        ascending=False
    )

    best = group_sorted.iloc[0]

    rr_values = sorted(
        pd.to_numeric(
            group["rr"],
            errors="coerce"
        )
        .dropna()
        .unique()
        .tolist()
    )

    if rr_values:

        rr_min = min(rr_values)
        rr_max = max(rr_values)

        if len(rr_values) > 1:
            rr_range = f"{rr_min:.1f} - {rr_max:.1f}"
        else:
            rr_range = f"{rr_min:.1f}"

    else:
        rr_min = None
        rr_max = None
        rr_range = "N/A"


    # --------------------------------------------------------
    # RR stability
    #
    # We use the BIG SEARCH rr_stability values when present.
    # Also show how many RR versions were tested.
    # --------------------------------------------------------

    if "rr_stability" in group.columns:

        stability_values = pd.to_numeric(
            group["rr_stability"],
            errors="coerce"
        ).dropna()

        if len(stability_values):

            family_rr_stability = float(
                stability_values.mean()
            )

        else:
            family_rr_stability = None

    else:
        family_rr_stability = None


    # --------------------------------------------------------
    # Count positive RR versions
    # --------------------------------------------------------

    if "expectancy_r" in group.columns:

        positive_rr_count = int(
            (
                pd.to_numeric(
                    group["expectancy_r"],
                    errors="coerce"
                ) > 0
            ).sum()
        )

    else:
        positive_rr_count = 0


    # --------------------------------------------------------
    # RR stability label
    # --------------------------------------------------------

    rr_count = len(rr_values)

    if rr_count >= 5 and positive_rr_count >= rr_count * 0.80:
        rr_stability_label = "STRONG"

    elif rr_count >= 3 and positive_rr_count >= rr_count * 0.60:
        rr_stability_label = "GOOD"

    elif positive_rr_count > 0:
        rr_stability_label = "MIXED"

    else:
        rr_stability_label = "WEAK"


    family_rows.append({

        "direction": best.get("direction", ""),
        "session": best.get("session", ""),
        "conditions": best.get("conditions", ""),

        "family_key": family_key,

        "best_rr": best.get("rr"),
        "rr_min": rr_min,
        "rr_max": rr_max,
        "rr_range": rr_range,

        "rr_versions": rr_count,
        "positive_rr_versions": positive_rr_count,

        "rr_stability": family_rr_stability,
        "rr_stability_label": rr_stability_label,

        "trades": best.get("trades"),
        "net_r": best.get("net_r"),
        "expectancy_r": best.get("expectancy_r"),
        "profit_factor": best.get("profit_factor"),
        "max_drawdown_r": best.get("max_drawdown_r"),
        "win_rate": best.get("win_rate"),
        "avg_trades_day": best.get("avg_trades_day"),

        "max_concurrent": best.get("max_concurrent"),
        "avg_hold_bars": best.get("avg_hold_bars"),

        "positive_years": best.get("positive_years"),
        "years_tested": best.get("years_tested"),

        "worst_year_pf": best.get("worst_year_pf"),
        "avg_year_expectancy_r": best.get(
            "avg_year_expectancy_r"
        ),

        "base_score": best.get("base_score"),
        "robust_score": best.get("robust_score"),

        "status": best.get("status"),

    })


family_df = pd.DataFrame(family_rows)


# ============================================================
# FAMILY RANKING
# ============================================================

family_score_col = (
    "robust_score"
    if "robust_score" in family_df.columns
    else "base_score"
)


family_df = (
    family_df
    .sort_values(
        family_score_col,
        ascending=False
    )
    .reset_index(drop=True)
)


family_df["family_rank"] = (
    range(1, len(family_df) + 1)
)


# ============================================================
# ADD FAMILY RANK BACK TO INDIVIDUAL RESULTS
# ============================================================

rank_map = dict(
    zip(
        family_df["family_key"],
        family_df["family_rank"]
    )
)


all_df["family_rank"] = (
    all_df["family_key"]
    .map(rank_map)
)


# Individual RR ranking remains useful
all_df = (
    all_df
    .sort_values(
        "robust_score",
        ascending=False
    )
    .reset_index(drop=True)
)


all_df["overall_rank"] = (
    range(1, len(all_df) + 1)
)


# ============================================================
# FORMAT HELPER
# ============================================================

def fmt(v, digits=2):

    try:

        if pd.isna(v):
            return "N/A"

        return f"{float(v):,.{digits}f}"

    except Exception:

        return str(v)


def safe_text(v):

    if pd.isna(v):
        return ""

    return html.escape(str(v))


# ============================================================
# EXCEL REPORT
# ============================================================

xlsx = OUT / "strategy_report.xlsx"


with pd.ExcelWriter(
    xlsx,
    engine="openpyxl"
) as writer:

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = pd.DataFrame({

        "Metric": [

            "Generated",

            "Search result folders",

            "Individual RR results",

            "Unique strategy families",

            "Strong families",

            "Promising families",

            "Watch families",

            "Reject families",

            "Families with 5+ RR versions",

        ],

        "Value": [

            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            len(files),

            len(all_df),

            len(family_df),

            int(
                (
                    family_df["status"]
                    == "STRONG"
                ).sum()
            ),

            int(
                (
                    family_df["status"]
                    == "PROMISING"
                ).sum()
            ),

            int(
                (
                    family_df["status"]
                    == "WATCH"
                ).sum()
            ),

            int(
                (
                    family_df["status"]
                    == "REJECT"
                ).sum()
            ),

            int(
                (
                    family_df["rr_versions"]
                    >= 5
                ).sum()
            ),

        ],

    })

    summary.to_excel(
        writer,
        sheet_name="Summary",
        index=False
    )


    # --------------------------------------------------------
    # FAMILY TOP 100
    # --------------------------------------------------------

    family_display_cols = [

        "family_rank",
        "status",

        "direction",
        "session",
        "conditions",

        "best_rr",
        "rr_range",
        "rr_versions",
        "positive_rr_versions",

        "rr_stability",
        "rr_stability_label",

        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_r",
        "win_rate",
        "avg_trades_day",

        "positive_years",
        "years_tested",
        "worst_year_pf",
        "avg_year_expectancy_r",

        "robust_score",

    ]


    family_display_cols = [
        c
        for c in family_display_cols
        if c in family_df.columns
    ]


    family_df.head(100)[
        family_display_cols
    ].to_excel(
        writer,
        sheet_name="Family Top 100",
        index=False
    )


    # --------------------------------------------------------
    # RR DETAILS
    # --------------------------------------------------------

    rr_display_cols = [

        "family_rank",
        "overall_rank",

        "status",

        "direction",
        "session",
        "conditions",

        "rr",

        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_r",
        "win_rate",
        "avg_trades_day",

        "positive_years",
        "years_tested",
        "worst_year_pf",
        "avg_year_expectancy_r",

        "rr_stability",
        "robust_score",

    ]


    rr_display_cols = [
        c
        for c in rr_display_cols
        if c in all_df.columns
    ]


    all_df[
        rr_display_cols
    ].to_excel(
        writer,
        sheet_name="RR Details",
        index=False
    )


    # --------------------------------------------------------
    # ALL RESULTS
    # --------------------------------------------------------

    all_df[
        rr_display_cols
    ].to_excel(
        writer,
        sheet_name="All Results",
        index=False
    )


    # --------------------------------------------------------
    # EXCEL FORMATTING
    # --------------------------------------------------------

    for sheet in writer.sheets.values():

        sheet.freeze_panes = "A2"

        sheet.auto_filter.ref = (
            sheet.dimensions
        )

        for col in sheet.columns:

            max_len = max(
                len(
                    str(
                        cell.value
                        or ""
                    )
                )
                for cell in col[:200]
            )

            sheet.column_dimensions[
                col[0].column_letter
            ].width = min(
                max(max_len + 2, 10),
                45
            )


# ============================================================
# HTML EASY VIEW
# ============================================================

html_file = OUT / "strategy_report.html"


family_top = family_df.head(100)


cards = []


for _, r in family_top.iterrows():

    cls = str(
        r["status"]
    ).lower()


    # --------------------------------------------------------
    # Find all RR versions for this family
    # --------------------------------------------------------

    family_rows_for_html = all_df[
        all_df["family_key"]
        == r["family_key"]
    ].sort_values(
        "rr",
        ascending=True
    )


    rr_rows = []


    for _, rr_row in family_rows_for_html.iterrows():

        rr_rows.append(
            f"""
            <tr>
                <td>{fmt(rr_row.get('rr'), 1)}</td>
                <td>{fmt(rr_row.get('trades'), 0)}</td>
                <td>{fmt(rr_row.get('net_r'))}</td>
                <td>{fmt(rr_row.get('expectancy_r'))}</td>
                <td>{fmt(rr_row.get('profit_factor'))}</td>
                <td>{fmt(rr_row.get('max_drawdown_r'))}</td>
                <td>{fmt(rr_row.get('robust_score'))}</td>
            </tr>
            """
        )


    cards.append(
        f"""
        <div class="card {cls}">

            <div class="rank">
                FAMILY #{int(r['family_rank'])}
                — {safe_text(r.get('status', ''))}
            </div>

            <h2>
                {safe_text(r.get('direction', ''))}
                —
                {safe_text(r.get('session', ''))}
            </h2>

            <div class="conditions">
                {safe_text(r.get('conditions', ''))}
            </div>

            <div class="family-summary">

                <div>
                    <b>Best RR</b>
                    <span>{fmt(r.get('best_rr'), 1)}</span>
                </div>

                <div>
                    <b>RR Range</b>
                    <span>{safe_text(r.get('rr_range', ''))}</span>
                </div>

                <div>
                    <b>RR Versions</b>
                    <span>{fmt(r.get('rr_versions'), 0)}</span>
                </div>

                <div>
                    <b>Positive RR</b>
                    <span>
                        {fmt(r.get('positive_rr_versions'), 0)}
                    </span>
                </div>

                <div>
                    <b>RR Stability</b>
                    <span>
                        {safe_text(
                            r.get(
                                'rr_stability_label',
                                ''
                            )
                        )}
                    </span>
                </div>

                <div>
                    <b>Robust Score</b>
                    <span>{fmt(r.get('robust_score'))}</span>
                </div>

            </div>


            <div class="grid">

                <div>
                    <b>Trades</b>
                    <span>
                        {fmt(r.get('trades'), 0)}
                    </span>
                </div>

                <div>
                    <b>Net R</b>
                    <span>
                        {fmt(r.get('net_r'))}
                    </span>
                </div>

                <div>
                    <b>Expectancy</b>
                    <span>
                        {fmt(r.get('expectancy_r'))}
                    </span>
                </div>

                <div>
                    <b>Profit Factor</b>
                    <span>
                        {fmt(r.get('profit_factor'))}
                    </span>
                </div>

                <div>
                    <b>Max DD</b>
                    <span>
                        {fmt(r.get('max_drawdown_r'))}
                    </span>
                </div>

                <div>
                    <b>Win Rate</b>
                    <span>
                        {fmt(r.get('win_rate'))}%
                    </span>
                </div>

                <div>
                    <b>Trades/Day</b>
                    <span>
                        {fmt(r.get('avg_trades_day'))}
                    </span>
                </div>

                <div>
                    <b>Years Tested</b>
                    <span>
                        {fmt(r.get('years_tested'), 0)}
                    </span>
                </div>

            </div>


            <details>

                <summary>
                    Show all RR results for this family
                </summary>

                <table>

                    <thead>

                        <tr>
                            <th>RR</th>
                            <th>Trades</th>
                            <th>Net R</th>
                            <th>Expectancy</th>
                            <th>PF</th>
                            <th>Max DD</th>
                            <th>Robust</th>
                        </tr>

                    </thead>

                    <tbody>

                        {''.join(rr_rows)}

                    </tbody>

                </table>

            </details>

        </div>
        """
    )


# ============================================================
# HTML DOCUMENT
# ============================================================

html_text = f"""
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<title>
Trading Strategy Lab — Strategy Families
</title>


<style>

body {{
    font-family: Arial, sans-serif;
    background: #f4f6f8;
    margin: 0;
    color: #17202a;
}}

header {{
    background: #1f2937;
    color: white;
    padding: 24px 30px;
    position: sticky;
    top: 0;
    z-index: 10;
}}

h1 {{
    margin: 0 0 8px;
}}

.summary {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 14px;
}}

.badge {{
    background: white;
    color: #111;
    padding: 8px 12px;
    border-radius: 8px;
}}

main {{
    max-width: 1250px;
    margin: 25px auto;
    padding: 0 18px;
}}

.card {{
    background: white;
    border-radius: 12px;
    padding: 18px;
    margin: 16px 0;
    box-shadow: 0 2px 8px #0001;
    border-left: 7px solid #777;
}}

.card.strong {{
    border-left-color: #16803c;
}}

.card.promising {{
    border-left-color: #2878d0;
}}

.card.watch {{
    border-left-color: #d99a00;
}}

.card.reject {{
    border-left-color: #c0392b;
}}

.rank {{
    font-weight: bold;
    color: #555;
}}

.conditions {{
    background: #f0f2f4;
    padding: 10px;
    border-radius: 7px;
    margin: 10px 0;
    word-break: break-word;
}}

.family-summary {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin: 12px 0;
}}

.family-summary div {{
    background: #eef2f7;
    padding: 10px;
    border-radius: 7px;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
    margin-top: 10px;
}}

.grid div {{
    background: #f8fafc;
    padding: 10px;
    border-radius: 7px;
}}

.grid b,
.family-summary b {{
    display: block;
    font-size: 12px;
    color: #687078;
}}

.grid span,
.family-summary span {{
    display: block;
    font-size: 18px;
    font-weight: bold;
    margin-top: 4px;
}}

details {{
    margin-top: 18px;
}}

summary {{
    cursor: pointer;
    font-weight: bold;
    padding: 10px;
    background: #f0f2f4;
    border-radius: 7px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
    font-size: 14px;
}}

th,
td {{
    padding: 8px;
    border-bottom: 1px solid #ddd;
    text-align: right;
}}

th {{
    background: #eef2f7;
}}

th:first-child,
td:first-child {{
    text-align: left;
}}

.note {{
    background: white;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
}}

</style>

</head>


<body>


<header>

<h1>
Trading Strategy Lab — Strategy Families
</h1>

<div>
Generated
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>


<div class="summary">

<span class="badge">
Families: {len(family_df)}
</span>

<span class="badge">
Strong: {(family_df.status == "STRONG").sum()}
</span>

<span class="badge">
Promising: {(family_df.status == "PROMISING").sum()}
</span>

<span class="badge">
Watch: {(family_df.status == "WATCH").sum()}
</span>

<span class="badge">
Reject: {(family_df.status == "REJECT").sum()}
</span>

</div>

</header>


<main>


<div class="note">

<b>How this report works:</b>

RR variations of the same
Direction + Session + Conditions
are grouped into one strategy family.

The family ranking uses the best RR result,
while the RR table shows whether the strategy
continues to work across different RR values.

This prevents one strategy from filling the
Top 100 with repeated RR versions.

</div>


{''.join(cards)}


</main>


</body>

</html>
"""


html_file.write_text(
    html_text,
    encoding="utf-8"
)


# ============================================================
# FINISHED
# ============================================================

print()
print("=" * 60)
print("STRATEGY FAMILY REPORT COMPLETE")
print("=" * 60)

print(f"Created: {html_file}")
print(f"Created: {xlsx}")

print(
    f"Loaded {len(files)} BIG SEARCH result files."
)

print(
    f"Individual RR results: {len(all_df)}"
)

print(
    f"Unique strategy families: {len(family_df)}"
)

print(
    f"Family Top 100: {min(100, len(family_df))}"
)

print("=" * 60)

webbrowser.open(
    html_file.as_uri()
)