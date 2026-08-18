from __future__ import annotations

from pathlib import Path
import pandas as pd


# ============================================================
# SETTINGS
# ============================================================

ROOT = Path(r"D:\Trading\Trading_Reworked")

BIG_SEARCH_DIR = ROOT / "results" / "big_search"

OUTPUT_FILE = ROOT / "quant" / "top100_candidates.csv"

TOP_N = 100


# ============================================================
# LOAD BIG SEARCH RESULTS
# ============================================================

def load_big_search_results():

    files = sorted(
        BIG_SEARCH_DIR.glob(
            "*/results.csv_final.csv"
        )
    )

    if not files:

        raise SystemExit(
            f"No BIG SEARCH result files found under "
            f"{BIG_SEARCH_DIR}"
        )

    frames = []

    print()
    print("=" * 70)
    print("LOADING BIG SEARCH RESULTS")
    print("=" * 70)
    print()

    for path in files:

        try:

            df = pd.read_csv(path)

        except Exception as exc:

            print(
                f"WARNING: Could not read {path}: {exc}"
            )

            continue

        if df.empty:
            continue

        df["search"] = path.parent.name

        frames.append(df)

        print(
            f"Loaded {len(df):,} results: "
            f"{path.parent.name}"
        )

    if not frames:

        raise SystemExit(
            "No usable BIG SEARCH result CSVs found."
        )

    combined = pd.concat(
        frames,
        ignore_index=True
    )

    return combined


# ============================================================
# CLEAN NUMERIC COLUMNS
# ============================================================

def clean_numbers(df):

    numeric_columns = [

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

    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    return df


# ============================================================
# REMOVE EXACT DUPLICATE RR TESTS
# ============================================================

def remove_duplicate_rr_tests(df):

    duplicate_columns = [

        "direction",
        "session",
        "conditions",
        "rr",

    ]

    duplicate_columns = [

        column
        for column in duplicate_columns
        if column in df.columns

    ]

    if not duplicate_columns:

        return df

    score_column = (

        "robust_score"

        if "robust_score" in df.columns

        else "base_score"

    )

    df = (

        df
        .sort_values(
            score_column,
            ascending=False
        )
        .drop_duplicates(
            subset=duplicate_columns,
            keep="first"
        )
        .reset_index(drop=True)

    )

    return df


# ============================================================
# CREATE STRATEGY FAMILIES
#
# RR IS DELIBERATELY NOT INCLUDED.
#
# Example:
#
# BUY + New York + conditions + RR 6.2
# BUY + New York + conditions + RR 6.3
# BUY + New York + conditions + RR 6.9
#
# = ONE FAMILY
# ============================================================

def create_family_key(df):

    required = [

        "direction",
        "session",
        "conditions",

    ]

    missing = [

        column
        for column in required
        if column not in df.columns

    ]

    if missing:

        raise SystemExit(
            "BIG SEARCH results are missing: "
            + ", ".join(missing)
        )

    df["family_key"] = (

        df[
            [
                "direction",
                "session",
                "conditions",
            ]
        ]
        .fillna("")
        .astype(str)
        .agg(" | ".join, axis=1)

    )

    return df


# ============================================================
# BUILD UNIQUE FAMILY CANDIDATES
# ============================================================

def build_family_candidates(df):

    score_column = (

        "robust_score"

        if "robust_score" in df.columns

        else "base_score"

    )

    family_candidates = []

    for family_key, group in df.groupby(
        "family_key",
        sort=False
    ):

        # Best RR version represents the family
        group = group.sort_values(
            score_column,
            ascending=False
        )

        best = group.iloc[0].copy()

        # RR versions tested
        rr_values = (

            pd.to_numeric(
                group["rr"],
                errors="coerce"
            )
            .dropna()
            .unique()
            .tolist()

            if "rr" in group.columns

            else []

        )

        rr_values = sorted(rr_values)

        # Count positive expectancy RR versions
        positive_rr_versions = 0

        if "expectancy_r" in group.columns:

            expectancy_values = pd.to_numeric(
                group["expectancy_r"],
                errors="coerce"
            )

            positive_rr_versions = int(
                (
                    expectancy_values > 0
                ).sum()
            )

        # Add family information to the selected row
        best["family_key"] = family_key

        best["family_rr_versions"] = len(
            rr_values
        )

        best["family_positive_rr_versions"] = (
            positive_rr_versions
        )

        if rr_values:

            best["family_rr_min"] = min(
                rr_values
            )

            best["family_rr_max"] = max(
                rr_values
            )

        else:

            best["family_rr_min"] = None
            best["family_rr_max"] = None

        family_candidates.append(best)

    if not family_candidates:

        raise SystemExit(
            "No strategy families could be created."
        )

    result = pd.DataFrame(
        family_candidates
    )

    return result


# ============================================================
# RANK FAMILY CANDIDATES
# ============================================================

def rank_families(df):

    score_column = (

        "robust_score"

        if "robust_score" in df.columns

        else "base_score"

    )

    df = (

        df
        .sort_values(
            score_column,
            ascending=False,
            kind="stable"
        )
        .reset_index(drop=True)

    )

    df.insert(
        0,
        "top100_rank",
        range(
            1,
            len(df) + 1
        )
    )

    return df


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("PROMOTE BIG SEARCH STRATEGY FAMILIES TO TOP 100")
    print("=" * 70)
    print()

    print(
        f"BIG SEARCH directory:"
        f"\n  {BIG_SEARCH_DIR}"
    )

    print(
        f"\nOutput:"
        f"\n  {OUTPUT_FILE}"
    )

    print(
        f"\nMaximum families:"
        f"\n  {TOP_N}"
    )

    print()

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    df = load_big_search_results()

    print()
    print(
        f"Total BIG SEARCH rows loaded: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------
    # CLEAN
    # --------------------------------------------------------

    df = clean_numbers(df)

    # --------------------------------------------------------
    # REMOVE EXACT RR DUPLICATES
    # --------------------------------------------------------

    before = len(df)

    df = remove_duplicate_rr_tests(df)

    print(
        f"After exact RR deduplication: "
        f"{len(df):,}"
    )

    print(
        f"Duplicate RR rows removed: "
        f"{before - len(df):,}"
    )

    # --------------------------------------------------------
    # CREATE FAMILIES
    # --------------------------------------------------------

    df = create_family_key(df)

    family_count_before = (
        df["family_key"]
        .nunique()
    )

    print(
        f"\nUnique strategy families found: "
        f"{family_count_before:,}"
    )

    # --------------------------------------------------------
    # SELECT BEST RR RESULT FOR EACH FAMILY
    # --------------------------------------------------------

    family_df = build_family_candidates(
        df
    )

    print(
        f"Unique family candidates: "
        f"{len(family_df):,}"
    )

    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    family_df = rank_families(
        family_df
    )

    # --------------------------------------------------------
    # TAKE TOP 100
    # --------------------------------------------------------

    top100 = family_df.head(
        TOP_N
    ).copy()

    print()
    print("=" * 70)
    print("TOP 100 FAMILY SELECTION")
    print("=" * 70)
    print()

    print(
        f"Families available: "
        f"{len(family_df):,}"
    )

    print(
        f"Families promoted: "
        f"{len(top100):,}"
    )

    # --------------------------------------------------------
    # CREATE OUTPUT DIRECTORY
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    top100.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()
    print("=" * 70)
    print("PROMOTION COMPLETE")
    print("=" * 70)
    print()

    print(
        f"Created:"
        f"\n  {OUTPUT_FILE}"
    )

    print()

    # --------------------------------------------------------
    # SHOW THE TOP 20
    # --------------------------------------------------------

    display_columns = [

        "top100_rank",
        "direction",
        "session",
        "conditions",
        "rr",
        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_r",
        "robust_score",
        "family_rr_versions",

    ]

    display_columns = [

        column
        for column in display_columns
        if column in top100.columns

    ]

    print(
        top100[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )

    print()
    print(
        "These are UNIQUE STRATEGY FAMILIES."
    )

    print(
        "Different RR versions of the same "
        "conditions are not counted as separate "
        "Top-100 candidates."
    )

    print()


if __name__ == "__main__":
    main()