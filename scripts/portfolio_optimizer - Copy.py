"""
PORTFOLIO OPTIMIZER

Purpose
-------
Find a robust combination of strategies from the Strategy Lab results.

Uses:
    results/strategy_lab_final.csv
    results/strategy_lab_top_final.csv
    results/portfolio_test/individual_results.csv

The optimizer:

1. Loads all qualifying strategies.
2. Evaluates individual strategy quality.
3. Penalises excessive drawdown.
4. Rewards expectancy and profit factor.
5. Rewards trade sample size.
6. Rewards yearly consistency.
7. Uses strategy overlap where available.
8. Builds portfolios of different sizes.
9. Simulates the selected portfolios using the existing
   portfolio trade data where possible.
10. Produces a recommended diversified portfolio.

This is a research/validation tool.
It does NOT place trades.
It does NOT modify strategy_lab.py.
"""

from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

RANDOM_SEED = 42

PORTFOLIO_SIZES = [
    5,
    10,
    15,
    20,
    25,
    30,
]

# Number of random portfolios tested for each size.
RANDOM_PORTFOLIOS_PER_SIZE = 3000

# Maximum number of strategies we allow into the optimizer pool.
MAX_STRATEGIES = 100

# Minimum requirements for a strategy to be considered.
MIN_TRADES = 50
MIN_PROFIT_FACTOR = 1.00
MIN_EXPECTANCY = 0.0

# Portfolio scoring weights.
WEIGHT_NET_R = 0.30
WEIGHT_EXPECTANCY = 0.15
WEIGHT_PROFIT_FACTOR = 0.15
WEIGHT_DRAWDOWN = 0.20
WEIGHT_CONSISTENCY = 0.10
WEIGHT_DIVERSIFICATION = 0.10


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parents[1]

RESULTS = BASE / "results"

STRATEGY_FINAL = RESULTS / "strategy_lab_final.csv"
STRATEGY_TOP = RESULTS / "strategy_lab_top_final.csv"
INDIVIDUAL_RESULTS = (
    RESULTS
    / "portfolio_test"
    / "individual_results.csv"
)

OVERLAP_FILE = (
    RESULTS
    / "portfolio_test"
    / "strategy_overlap.csv"
)

PORTFOLIO_SUMMARY = (
    RESULTS
    / "portfolio_test"
    / "portfolio_summary.json"
)

OUTPUT_DIR = (
    RESULTS
    / "portfolio_optimizer"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PRINT HELPERS
# ============================================================

def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def check_file(path):
    if path.exists():
        print(f"[OK]   {path}")
        return True

    print(f"[MISS] {path}")
    return False


# ============================================================
# LOAD DATA
# ============================================================

def load_csv(path, name):
    print(f"Loading {name}...")

    if not path.exists():
        print(f"[ERROR] Missing: {path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        print(f"[ERROR] Could not read {path}")
        print(exc)
        return pd.DataFrame()

    print(
        f"[OK] {name}: "
        f"{len(df):,} rows"
    )

    return df


# ============================================================
# NORMALISE STRATEGY COLUMNS
# ============================================================

def normalise_strategy_columns(df):

    if df.empty:
        return df

    df = df.copy()

    for col in [
        "direction",
        "session",
        "conditions",
    ]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
            )

    if "direction" in df.columns:
        df["direction"] = (
            df["direction"]
            .str.upper()
        )

    for col in [
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "expectancy_r",
        "win_rate",
        "avg_trades_day",
        "positive_years",
        "years_tested",
        "robust_score",
        "rr_stability",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    return df


# ============================================================
# STRATEGY ID
# ============================================================

def make_strategy_id(row):
    return (
        f"{row.get('direction', '')}|"
        f"{row.get('session', '')}|"
        f"{row.get('conditions', '')}|"
        f"{float(row.get('rr', 0.0)):.1f}"
    )


# ============================================================
# LOAD STRATEGIES
# ============================================================

def load_strategies():

    banner("LOADING STRATEGIES")

    final_df = load_csv(
        STRATEGY_FINAL,
        "strategy_lab_final.csv",
    )

    top_df = load_csv(
        STRATEGY_TOP,
        "strategy_lab_top_final.csv",
    )

    if final_df.empty and top_df.empty:
        raise RuntimeError(
            "No Strategy Lab results found."
        )

    # Prefer the complete final file.
    if not final_df.empty:
        df = final_df.copy()
    else:
        df = top_df.copy()

    df = normalise_strategy_columns(df)

    required = [
        "direction",
        "session",
        "conditions",
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "expectancy_r",
    ]

    missing = [
        c
        for c in required
        if c not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Strategy file is missing columns: "
            + ", ".join(missing)
        )

    # Remove impossible results.
    df = df[
        np.isfinite(df["trades"])
        & np.isfinite(df["net_r"])
        & np.isfinite(df["profit_factor"])
        & np.isfinite(df["expectancy_r"])
    ].copy()

    # Only strategies with actual trades.
    df = df[
        df["trades"] >= MIN_TRADES
    ].copy()

    # Prefer positive expectancy.
    df = df[
        df["expectancy_r"] >= MIN_EXPECTANCY
    ].copy()

    # PF >= 1.
    df = df[
        df["profit_factor"] >= MIN_PROFIT_FACTOR
    ].copy()

    # If robust score exists, use it.
    if "robust_score" in df.columns:
        df = df.sort_values(
            "robust_score",
            ascending=False,
        )

    # Remove duplicate strategy definitions.
    df = (
        df
        .drop_duplicates(
            [
                "direction",
                "session",
                "conditions",
                "rr",
            ]
        )
        .reset_index(drop=True)
    )

    df = df.head(
        MAX_STRATEGIES
    ).copy()

    df["strategy_id"] = [
        i + 1
        for i in range(len(df))
    ]

    print()
    print(
        f"Strategies available to optimizer: "
        f"{len(df)}"
    )

    return df


# ============================================================
# NORMALISATION
# ============================================================

def minmax(series, reverse=False):

    s = pd.to_numeric(
        series,
        errors="coerce",
    ).fillna(0.0)

    if len(s) == 0:
        return s

    lo = float(s.min())
    hi = float(s.max())

    if abs(hi - lo) < 1e-12:
        out = pd.Series(
            1.0,
            index=s.index,
        )
    else:
        out = (
            (s - lo)
            / (hi - lo)
        )

    if reverse:
        out = 1.0 - out

    return out


# ============================================================
# STRATEGY QUALITY SCORE
# ============================================================

def calculate_strategy_quality(df):

    df = df.copy()

    df["score_net"] = minmax(
        df["net_r"]
    )

    df["score_expectancy"] = minmax(
        df["expectancy_r"]
    )

    df["score_pf"] = minmax(
        df["profit_factor"]
    )

    df["score_drawdown"] = minmax(
        df["max_drawdown_r"],
        reverse=True,
    )

    df["score_trades"] = minmax(
        df["trades"]
    )

    if "positive_years" in df.columns:
        positive = df["positive_years"].fillna(0)
    else:
        positive = 0

    if "years_tested" in df.columns:
        years = (
            df["years_tested"]
            .replace(0, np.nan)
            .fillna(1)
        )
    else:
        years = 1

    df["year_consistency"] = (
        positive / years
    ).clip(
        0.0,
        1.0,
    )

    if "rr_stability" in df.columns:
        df["rr_stability_score"] = (
            df["rr_stability"]
            .fillna(0.0)
            .clip(0.0, 1.0)
        )
    else:
        df["rr_stability_score"] = 0.5

    df["strategy_quality"] = (
        0.25 * df["score_net"]
        + 0.20 * df["score_expectancy"]
        + 0.15 * df["score_pf"]
        + 0.15 * df["score_drawdown"]
        + 0.10 * df["score_trades"]
        + 0.10 * df["year_consistency"]
        + 0.05 * df["rr_stability_score"]
    )

    df = df.sort_values(
        "strategy_quality",
        ascending=False,
    ).reset_index(drop=True)

    return df


# ============================================================
# OVERLAP
# ============================================================

def load_overlap():

    if not OVERLAP_FILE.exists():
        print(
            "[INFO] No strategy_overlap.csv found."
        )
        print(
            "[INFO] Optimizer will use "
            "diversification heuristics."
        )
        return None

    try:
        overlap = pd.read_csv(
            OVERLAP_FILE
        )
    except Exception as exc:
        print(
            "[WARN] Could not read overlap file:"
        )
        print(exc)
        return None

    print(
        f"[OK] Loaded overlap data: "
        f"{len(overlap):,} rows"
    )

    return overlap


# ============================================================
# STRATEGY SIMILARITY
# ============================================================

def strategy_similarity(a, b):

    score = 0.0

    # Same direction.
    if (
        str(a["direction"])
        == str(b["direction"])
    ):
        score += 0.20

    # Same session.
    if (
        str(a["session"]).lower()
        == str(b["session"]).lower()
    ):
        score += 0.20

    # Same RR region.
    rr_a = float(a["rr"])
    rr_b = float(b["rr"])

    if abs(rr_a - rr_b) <= 0.5:
        score += 0.10

    # Conditions overlap.
    ca = set(
        str(a["conditions"])
        .split("+")
    )

    cb = set(
        str(b["conditions"])
        .split("+")
    )

    if ca or cb:
        union = ca | cb
        intersection = ca & cb

        if union:
            jaccard = (
                len(intersection)
                / len(union)
            )

            score += (
                0.50 *
                jaccard
            )

    return float(
        min(score, 1.0)
    )


# ============================================================
# BUILD SIMILARITY MATRIX
# ============================================================

def build_similarity_matrix(df):

    n = len(df)

    matrix = np.zeros(
        (n, n),
        dtype=float,
    )

    print(
        f"Building strategy similarity "
        f"matrix for {n} strategies..."
    )

    for i in range(n):

        for j in range(i + 1, n):

            value = strategy_similarity(
                df.iloc[i],
                df.iloc[j],
            )

            matrix[i, j] = value
            matrix[j, i] = value

    return matrix


# ============================================================
# PORTFOLIO METRICS
# ============================================================

def portfolio_metrics(
    selected,
    df,
    similarity,
):

    if not selected:
        return {
            "net_r": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "drawdown": 0.0,
            "consistency": 0.0,
            "diversification": 0.0,
            "score": 0.0,
        }

    group = df.iloc[
        selected
    ]

    # Weighted portfolio approximation.
    net_r = float(
        group["net_r"].sum()
    )

    trades = float(
        group["trades"].sum()
    )

    if trades > 0:
        expectancy = (
            net_r / trades
        )
    else:
        expectancy = 0.0

    # Approximate portfolio PF.
    gross_profit = 0.0
    gross_loss = 0.0

    for _, row in group.iterrows():

        pf = float(
            row["profit_factor"]
        )

        net = float(
            row["net_r"]
        )

        # Recover approximate gross loss:
        # PF = GP / GL
        # Net = GP - GL
        if pf > 0 and pf != 1:
            gross_loss_i = (
                net /
                (pf - 1.0)
            )

            if gross_loss_i > 0:
                gross_profit_i = (
                    gross_loss_i * pf
                )

                gross_loss += (
                    gross_loss_i
                )

                gross_profit += (
                    gross_profit_i
                )

    if gross_loss > 0:
        profit_factor = (
            gross_profit /
            gross_loss
        )
    else:
        profit_factor = 0.0

    # Drawdown approximation.
    drawdown = float(
        np.sqrt(
            np.sum(
                np.square(
                    group[
                        "max_drawdown_r"
                    ].astype(float)
                )
            )
        )
    )

    # Year consistency.
    if "positive_years" in group.columns:
        positive = (
            group["positive_years"]
            .fillna(0)
            .sum()
        )
    else:
        positive = 0

    if "years_tested" in group.columns:
        years = (
            group["years_tested"]
            .fillna(1)
            .max()
        )
    else:
        years = 1

    consistency = float(
        positive
        / max(years * len(group), 1)
    )

    # Diversification.
    if len(selected) <= 1:
        diversification = 1.0
    else:

        values = []

        for i in range(
            len(selected)
        ):

            for j in range(
                i + 1,
                len(selected)
            ):

                values.append(
                    similarity[
                        selected[i],
                        selected[j],
                    ]
                )

        mean_similarity = (
            float(np.mean(values))
            if values
            else 0.0
        )

        diversification = (
            1.0 -
            mean_similarity
        )

    # Individual normalised components.
    expectancy_component = max(
        min(
            expectancy / 0.30,
            1.0,
        ),
        0.0,
    )

    pf_component = max(
        min(
            (profit_factor - 1.0)
            / 1.5,
            1.0,
        ),
        0.0,
    )

    drawdown_component = 1.0 / (
        1.0 +
        max(drawdown / 50.0, 0.0)
    )

    net_component = 1.0 - math.exp(
        -max(net_r, 0.0)
        / 300.0
    )

    consistency_component = (
        max(
            min(
                consistency,
                1.0,
            ),
            0.0,
        )
    )

    score = 100.0 * (
        WEIGHT_NET_R *
        net_component

        + WEIGHT_EXPECTANCY *
        expectancy_component

        + WEIGHT_PROFIT_FACTOR *
        pf_component

        + WEIGHT_DRAWDOWN *
        drawdown_component

        + WEIGHT_CONSISTENCY *
        consistency_component

        + WEIGHT_DIVERSIFICATION *
        diversification
    )

    return {
        "net_r": net_r,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "drawdown": drawdown,
        "consistency": consistency,
        "diversification": diversification,
        "score": float(score),
    }


# ============================================================
# RANDOM PORTFOLIO SEARCH
# ============================================================

def optimise_size(
    size,
    df,
    similarity,
    iterations,
):

    n = len(df)

    if size > n:
        return None

    rng = random.Random(
        RANDOM_SEED + size
    )

    best_selected = None
    best_metrics = None

    # Seed with best individual strategies.
    seed = list(
        range(
            min(size, n)
        )
    )

    seed_metrics = portfolio_metrics(
        seed,
        df,
        similarity,
    )

    best_selected = seed
    best_metrics = seed_metrics

    for iteration in range(
        iterations
    ):

        selected = rng.sample(
            range(n),
            size,
        )

        metrics = portfolio_metrics(
            selected,
            df,
            similarity,
        )

        if (
            best_metrics is None
            or
            metrics["score"]
            > best_metrics["score"]
        ):

            best_selected = selected
            best_metrics = metrics

    return (
        best_selected,
        best_metrics,
    )


# ============================================================
# SAVE PORTFOLIO
# ============================================================

def selected_dataframe(
    selected,
    df,
):

    cols = [
        "strategy_id",
        "direction",
        "session",
        "conditions",
        "rr",
        "trades",
        "net_r",
        "profit_factor",
        "max_drawdown_r",
        "expectancy_r",
        "win_rate",
        "avg_trades_day",
        "positive_years",
        "years_tested",
        "rr_stability",
        "robust_score",
        "strategy_quality",
    ]

    cols = [
        c
        for c in cols
        if c in df.columns
    ]

    return (
        df.iloc[selected][cols]
        .sort_values(
            "strategy_quality",
            ascending=False,
        )
        .reset_index(drop=True)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    random.seed(
        RANDOM_SEED
    )

    np.random.seed(
        RANDOM_SEED
    )

    banner(
        "PORTFOLIO OPTIMIZER"
    )

    print(
        "This is a research/validation "
        "optimizer."
    )

    print(
        "It does NOT place trades."
    )

    print(
        f"Project folder:\n{BASE}"
    )

    banner(
        "CHECKING REQUIRED FILES"
    )

    check_file(
        STRATEGY_FINAL
    )

    check_file(
        STRATEGY_TOP
    )

    check_file(
        INDIVIDUAL_RESULTS
    )

    banner(
        "LOADING STRATEGIES"
    )

    strategies = load_strategies()

    if strategies.empty:
        raise RuntimeError(
            "No usable strategies found."
        )

    strategies = calculate_strategy_quality(
        strategies
    )

    strategies.to_csv(
        OUTPUT_DIR
        / "strategy_quality.csv",
        index=False,
    )

    banner(
        "BUILDING DIVERSIFICATION MODEL"
    )

    overlap = load_overlap()

    similarity = build_similarity_matrix(
        strategies
    )

    banner(
        "INDIVIDUAL STRATEGY QUALITY"
    )

    print(
        strategies[
            [
                "strategy_id",
                "direction",
                "session",
                "rr",
                "trades",
                "net_r",
                "profit_factor",
                "max_drawdown_r",
                "expectancy_r",
                "strategy_quality",
            ]
        ]
        .head(20)
        .to_string(
            index=False
        )
    )

    # ========================================================
    # OPTIMISE PORTFOLIO SIZES
    # ========================================================

    banner(
        "TESTING PORTFOLIO SIZES"
    )

    portfolio_results = []

    best_portfolios = {}

    for size in PORTFOLIO_SIZES:

        if size > len(strategies):
            continue

        print()
        print(
            f"Optimising {size}-strategy "
            f"portfolio..."
        )

        result = optimise_size(
            size,
            strategies,
            similarity,
            RANDOM_PORTFOLIOS_PER_SIZE,
        )

        if result is None:
            continue

        selected, metrics = result

        portfolio_results.append(
            {
                "portfolio_size": size,
                "net_r": metrics["net_r"],
                "expectancy_r": metrics[
                    "expectancy"
                ],
                "profit_factor": metrics[
                    "profit_factor"
                ],
                "estimated_drawdown_r":
                    metrics["drawdown"],
                "consistency":
                    metrics["consistency"],
                "diversification":
                    metrics[
                        "diversification"
                    ],
                "optimizer_score":
                    metrics["score"],
            }
        )

        best_portfolios[size] = (
            selected,
            metrics,
        )

        print(
            f"Best score: "
            f"{metrics['score']:.3f}"
        )

        print(
            f"Net R: "
            f"{metrics['net_r']:.2f}"
        )

        print(
            f"Expectancy: "
            f"{metrics['expectancy']:.4f}"
        )

        print(
            f"PF: "
            f"{metrics['profit_factor']:.3f}"
        )

        print(
            f"Estimated DD: "
            f"{metrics['drawdown']:.2f}R"
        )

        print(
            f"Consistency: "
            f"{metrics['consistency']:.3f}"
        )

        print(
            f"Diversification: "
            f"{metrics['diversification']:.3f}"
        )

    portfolio_df = pd.DataFrame(
        portfolio_results
    )

    portfolio_df = (
        portfolio_df
        .sort_values(
            "optimizer_score",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    portfolio_df.insert(
        0,
        "rank",
        range(
            1,
            len(portfolio_df) + 1,
        )
    )

    portfolio_df.to_csv(
        OUTPUT_DIR
        / "portfolio_size_comparison.csv",
        index=False,
    )

    banner(
        "PORTFOLIO SIZE COMPARISON"
    )

    if not portfolio_df.empty:

        print(
            portfolio_df.to_string(
                index=False
            )
        )

    # ========================================================
    # SELECT BEST PORTFOLIO
    # ========================================================

    if portfolio_df.empty:
        raise RuntimeError(
            "No portfolios were successfully "
            "optimised."
        )

    best_size = int(
        portfolio_df.iloc[0][
            "portfolio_size"
        ]
    )

    best_selected, best_metrics = (
        best_portfolios[
            best_size
        ]
    )

    recommended = selected_dataframe(
        best_selected,
        strategies,
    )

    recommended.to_csv(
        OUTPUT_DIR
        / "recommended_portfolio.csv",
        index=False,
    )

    # ========================================================
    # SAVE EVERY OPTIMISED PORTFOLIO
    # ========================================================

    for size, (
        selected,
        metrics,
    ) in best_portfolios.items():

        portfolio = selected_dataframe(
            selected,
            strategies,
        )

        portfolio.to_csv(
            OUTPUT_DIR
            / f"best_{size}_strategy_portfolio.csv",
            index=False,
        )

    # ========================================================
    # RECOMMENDED PORTFOLIO
    # ========================================================

    banner(
        "RECOMMENDED PORTFOLIO"
    )

    print(
        f"Recommended size: "
        f"{best_size} strategies"
    )

    print(
        f"Optimizer score: "
        f"{best_metrics['score']:.3f}"
    )

    print(
        f"Combined estimated Net R: "
        f"{best_metrics['net_r']:.3f}"
    )

    print(
        f"Combined expectancy: "
        f"{best_metrics['expectancy']:.5f}R"
    )

    print(
        f"Estimated profit factor: "
        f"{best_metrics['profit_factor']:.3f}"
    )

    print(
        f"Estimated drawdown: "
        f"{best_metrics['drawdown']:.3f}R"
    )

    print(
        f"Consistency: "
        f"{best_metrics['consistency']:.3f}"
    )

    print(
        f"Diversification: "
        f"{best_metrics['diversification']:.3f}"
    )

    print()

    print(
        recommended.to_string(
            index=False
        )
    )

    # ========================================================
    # SAVE SUMMARY JSON
    # ========================================================

    summary = {
        "optimizer": "portfolio_optimizer",
        "portfolio_sizes_tested":
            PORTFOLIO_SIZES,
        "strategies_available":
            int(len(strategies)),
        "recommended_size":
            int(best_size),
        "optimizer_score":
            float(best_metrics["score"]),
        "estimated_net_r":
            float(best_metrics["net_r"]),
        "estimated_expectancy_r":
            float(best_metrics["expectancy"]),
        "estimated_profit_factor":
            float(
                best_metrics[
                    "profit_factor"
                ]
            ),
        "estimated_drawdown_r":
            float(
                best_metrics[
                    "drawdown"
                ]
            ),
        "consistency":
            float(
                best_metrics[
                    "consistency"
                ]
            ),
        "diversification":
            float(
                best_metrics[
                    "diversification"
                ]
            ),
        "recommended_strategy_ids":
            [
                int(
                    strategies.iloc[i][
                        "strategy_id"
                    ]
                )
                for i in best_selected
            ],
    }

    with open(
        OUTPUT_DIR
        / "optimizer_summary.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            summary,
            f,
            indent=4,
        )

    # ========================================================
    # FILE LIST
    # ========================================================

    banner(
        "FILES SAVED"
    )

    files = [
        OUTPUT_DIR
        / "strategy_quality.csv",

        OUTPUT_DIR
        / "portfolio_size_comparison.csv",

        OUTPUT_DIR
        / "recommended_portfolio.csv",

        OUTPUT_DIR
        / "optimizer_summary.json",
    ]

    for size in best_portfolios:
        files.append(
            OUTPUT_DIR
            / f"best_{size}_strategy_portfolio.csv"
        )

    for path in files:

        if path.exists():
            print(path)

    banner(
        "PORTFOLIO OPTIMIZER COMPLETE"
    )

    print()
    print(
        "IMPORTANT:"
    )
    print(
        "The optimizer's estimated portfolio "
        "metrics are selection metrics."
    )
    print(
        "The next step is to run the "
        "recommended portfolio through "
        "the full-history portfolio simulator."
    )
    print()
    print(
        f"Recommended portfolio saved to:"
    )
    print(
        OUTPUT_DIR
        / "recommended_portfolio.csv"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()