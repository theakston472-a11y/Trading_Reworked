from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

RESULTS = ROOT / "results"
TOP100_DIR = RESULTS / "top100"
DEEP_DIR = RESULTS / "top100_tests"
OUT_DIR = RESULTS / "big_search"

STRATEGY_LAB = ROOT / "scripts" / "strategy_lab.py"


# =============================================================================
# POOLS
# =============================================================================

POOLS = {
    "london_buy": ("London", "BUY"),
    "london_sell": ("London", "SELL"),
    "new_york_buy": ("New York", "BUY"),
    "new_york_sell": ("New York", "SELL"),
}


# =============================================================================
# CANDIDATE COLLECTION
#
# IMPORTANT:
# The purpose of this stage is NOT to decide which strategies are winners.
#
# The Top-100 stage has already identified promising candidates.
# The Big Search is supposed to test those candidates much more thoroughly.
#
# Therefore we use only very basic safety checks here:
#   - correct pool
#   - valid conditions
#   - at least MIN_TRADES discovery trades
#   - positive discovery result where available
#
# We deliberately DO NOT require:
#   - profit_factor
#   - expectancy
#   - robust_score
#   - RR stability
#
# Those are exactly the things the Big Search is supposed to measure.
# =============================================================================

MIN_TRADES = 20


# =============================================================================
# BIG SEARCH SETTINGS
# =============================================================================

RR_START = 1.0
RR_STOP = 7.0
RR_STEP = 0.1

MAX_OPEN_TRADES = 5

FREQUENCY_TARGET = 0.75

FINAL_N = 50


# =============================================================================
# HELPERS
# =============================================================================

def number(df: pd.DataFrame, column: str, default=0.0):
    """
    Safely convert a dataframe column to numeric.
    Missing columns become the supplied default.
    """
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)

    return pd.to_numeric(
        df[column],
        errors="coerce",
    ).fillna(default)


def load_file(path: Path, source_name: str):
    """
    Load a candidate CSV safely.
    """

    if not path.exists():
        print(f"  Missing: {path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        print(f"  WARNING: Could not read {path}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print(f"  Empty: {path}")
        return pd.DataFrame()

    df["_source"] = source_name

    print(
        f"  Loaded {len(df):,}: {path}"
    )

    return df


def normalise(df: pd.DataFrame):
    """
    Normalise column types without destroying information from either
    discovery or deep-search files.
    """

    if df.empty:
        return df

    # Ensure core strategy identity columns exist.
    for col in [
        "direction",
        "session",
        "conditions",
    ]:
        if col not in df.columns:
            df[col] = ""

    # Numeric fields that may exist in either discovery or deep-search files.
    numeric_columns = [
        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "min_profit_factor",
        "positive_periods",
        "positive_years",
        "years_tested",
        "worst_drawdown_r",
        "max_drawdown_r",
        "rr",
        "score",
        "robust_score",
        "rr_stability",
        "avg_trades_day",
        "condition_count",
        "top100_rank",
        "rank",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    df["direction"] = (
        df["direction"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["session"] = (
        df["session"]
        .astype(str)
        .str.strip()
    )

    df["conditions"] = (
        df["conditions"]
        .astype(str)
        .str.strip()
    )

    return df


# =============================================================================
# BASIC CANDIDATE QUALITY CHECK
# =============================================================================

def quality_filter(df: pd.DataFrame):
    """
    Keep promising candidates without applying the final Big Search
    quality criteria.

    Discovery files and deep-search files use different metric sets.

    Discovery:
        trades
        net_r
        expectancy_r
        min_profit_factor
        positive_periods

    Deep search:
        trades
        net_r
        expectancy_r
        profit_factor
        positive_years
        robust_score
        rr_stability

    We therefore evaluate each row using whatever metrics actually exist.
    """

    if df.empty:
        return df

    keep = pd.Series(True, index=df.index)

    # -------------------------------------------------------------------------
    # Conditions must exist.
    # -------------------------------------------------------------------------

    keep &= df["conditions"].ne("")
    keep &= df["conditions"].ne("nan")

    # -------------------------------------------------------------------------
    # Minimum sample.
    #
    # This is deliberately modest because the Big Search itself is the
    # expensive validation stage.
    # -------------------------------------------------------------------------

    trades = number(
        df,
        "trades",
        default=0,
    )

    keep &= trades >= MIN_TRADES

    # -------------------------------------------------------------------------
    # Positive discovery result.
    #
    # Only apply this when net_r exists and contains usable values.
    #
    # If a row does not have net_r, we don't reject it merely because the
    # column is absent/NaN.
    # -------------------------------------------------------------------------

    if "net_r" in df.columns:

        net_values = pd.to_numeric(
            df["net_r"],
            errors="coerce",
        )

        has_net = net_values.notna()

        keep &= (
            (~has_net)
            | (net_values > 0)
        )

    # -------------------------------------------------------------------------
    # Profit factor.
    #
    # Again, use whichever metric exists.
    #
    # We intentionally don't make this a hard requirement.
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Positive periods / years.
    #
    # If available, require at least one positive period.
    # -------------------------------------------------------------------------

    if "positive_periods" in df.columns:

        positive_periods = pd.to_numeric(
            df["positive_periods"],
            errors="coerce",
        )

        has_positive_periods = positive_periods.notna()

        keep &= (
            (~has_positive_periods)
            | (positive_periods >= 1)
        )

    elif "positive_years" in df.columns:

        positive_years = pd.to_numeric(
            df["positive_years"],
            errors="coerce",
        )

        has_positive_years = positive_years.notna()

        keep &= (
            (~has_positive_years)
            | (positive_years >= 1)
        )

    return df.loc[keep].copy()


# =============================================================================
# DEDUPLICATION
# =============================================================================

def dedupe(df: pd.DataFrame):
    """
    Remove identical strategy definitions.

    The same strategy can appear in:
        - Top 100
        - previous deep search

    We keep the strongest available record.
    """

    if df.empty:
        return df

    keys = [
        c
        for c in [
            "direction",
            "session",
            "conditions",
            "rr",
        ]
        if c in df.columns
    ]

    if not keys:
        return df.drop_duplicates().reset_index(drop=True)

    # Strongest available metrics first.
    sort_columns = [
        c
        for c in [
            "robust_score",
            "score",
            "net_r",
            "expectancy_r",
            "profit_factor",
            "min_profit_factor",
            "trades",
        ]
        if c in df.columns
    ]

    if sort_columns:

        df = df.sort_values(
            sort_columns,
            ascending=False,
            na_position="last",
            kind="stable",
        )

    return (
        df.drop_duplicates(
            subset=keys,
            keep="first",
        )
        .reset_index(drop=True)
    )


# =============================================================================
# COLLECT ONE POOL
# =============================================================================

def collect_pool(pool_name: str):

    session, direction = POOLS[pool_name]

    print()
    print("=" * 80)
    print(f"COLLECTING: {pool_name}")
    print("=" * 80)

    frames = []

    # -------------------------------------------------------------------------
    # Current Top 100
    # -------------------------------------------------------------------------

    top_file = (
        TOP100_DIR
        / f"{pool_name}_top100.csv"
    )

    top_df = load_file(
        top_file,
        "top100",
    )

    if not top_df.empty:
        frames.append(top_df)

    # -------------------------------------------------------------------------
    # Previous deep-search finalists
    # -------------------------------------------------------------------------

    deep_file = (
        DEEP_DIR
        / pool_name
        / "results.csv_top_final.csv"
    )

    deep_df = load_file(
        deep_file,
        "previous_deep_search",
    )

    if not deep_df.empty:
        frames.append(deep_df)

    # -------------------------------------------------------------------------
    # Nothing available.
    # -------------------------------------------------------------------------

    if not frames:

        print("  No candidates found.")

        return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Combine.
    # -------------------------------------------------------------------------

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    combined = normalise(combined)

    # -------------------------------------------------------------------------
    # Enforce correct pool.
    # -------------------------------------------------------------------------

    combined = combined[
        (
            combined["session"]
            .str.lower()
            == session.lower()
        )
        &
        (
            combined["direction"]
            == direction
        )
    ].copy()

    before = len(combined)

    # -------------------------------------------------------------------------
    # Basic quality screen only.
    # -------------------------------------------------------------------------

    screened = quality_filter(
        combined
    )

    after_quality = len(screened)

    # -------------------------------------------------------------------------
    # Remove duplicate strategy definitions.
    # -------------------------------------------------------------------------

    screened = dedupe(
        screened
    )

    after_dedupe = len(screened)

    print(
        f"  Combined:       {before}"
    )

    print(
        f"  Passed quality: {after_quality}"
    )

    print(
        f"  After dedupe:   {after_dedupe}"
    )

    # -------------------------------------------------------------------------
    # Save candidate file.
    # -------------------------------------------------------------------------

    if screened.empty:

        print(
            f"  WARNING: No candidates survived "
            f"basic screening for {pool_name}"
        )

        return screened

    preferred = [
        "direction",
        "session",
        "conditions",
        "condition_count",
        "rr",
        "score",
        "robust_score",
        "rr_stability",
        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "min_profit_factor",
        "worst_drawdown_r",
        "max_drawdown_r",
        "positive_periods",
        "positive_years",
        "years_tested",
        "avg_trades_day",
        "top100_rank",
        "rank",
        "_source",
    ]

    ordered = [
        c
        for c in preferred
        if c in screened.columns
    ]

    remaining = [
        c
        for c in screened.columns
        if c not in ordered
    ]

    screened = screened[
        ordered + remaining
    ]

    pool_dir = (
        OUT_DIR
        / pool_name
    )

    pool_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    out_file = (
        pool_dir
        / "candidates.csv"
    )

    screened.to_csv(
        out_file,
        index=False,
    )

    print(
        f"  Candidate file: {out_file}"
    )

    return screened


# =============================================================================
# RUN BIG SEARCH
# =============================================================================

def run_big_search(
    pool_name: str,
    candidates: pd.DataFrame,
):

    if candidates.empty:

        print(
            f"[{pool_name}] Nothing to search."
        )

        return

    pool_dir = (
        OUT_DIR
        / pool_name
    )

    pool_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    out_file = (
        pool_dir
        / "results.csv"
    )

    db_file = (
        pool_dir
        / "cache.sqlite"
    )

    final_file = (
        pool_dir
        / "results.csv_top_final.csv"
    )

    # -------------------------------------------------------------------------
    # Safety:
    # Don't automatically overwrite a completed Big Search.
    # -------------------------------------------------------------------------

    if (
        final_file.exists()
        and out_file.exists()
    ):

        print()
        print(
            f"[{pool_name}] Existing Big Search detected."
        )

        print(
            f"[{pool_name}] Results: {out_file}"
        )

        print(
            f"[{pool_name}] Skipping completed search."
        )

        print(
            f"[{pool_name}] Delete the pool folder if you deliberately"
        )

        print(
            f"[{pool_name}] want to force a complete rerun."
        )

        return

    candidate_file = (
        pool_dir
        / "candidates.csv"
    )

    print()
    print("=" * 80)
    print(f"BIG SEARCH: {pool_name}")
    print("=" * 80)

    print(
        f"Candidates:       {len(candidates)}"
    )

    print(
        f"RR range:         {RR_START} -> {RR_STOP}"
    )

    print(
        f"RR step:          {RR_STEP}"
    )

    print(
        f"Max open trades:  {MAX_OPEN_TRADES}"
    )

    print(
        f"Frequency target: {FREQUENCY_TARGET}"
    )

    print(
        f"Final N:          {FINAL_N}"
    )

    print()

    # -------------------------------------------------------------------------
    # Strategy Laboratory command.
    # -------------------------------------------------------------------------

    cmd = [
        sys.executable,
        str(STRATEGY_LAB),

        "--candidates",
        str(candidate_file),

        "--max-candidates",
        str(len(candidates)),

        "--rr-start",
        str(RR_START),

        "--rr-stop",
        str(RR_STOP),

        "--rr-step",
        str(RR_STEP),

        "--max-open-trades",
        str(MAX_OPEN_TRADES),

        "--min-trades",
        str(MIN_TRADES),

        "--frequency-target",
        str(FREQUENCY_TARGET),

        "--final-n",
        str(FINAL_N),

        "--out",
        str(out_file),

        "--db",
        str(db_file),

        "--force",
    ]

    print("Running:")

    print(
        " ".join(
            f'"{x}"'
            if " " in str(x)
            else str(x)
            for x in cmd
        )
    )

    print()

    subprocess.run(
        cmd,
        cwd=str(ROOT),
        check=True,
    )

    print()

    print(
        f"[{pool_name}] BIG SEARCH COMPLETE"
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 80)
    print("TRADING BIG SEARCH")
    print("=" * 80)
    print()

    print(
        f"Root: {ROOT}"
    )

    print(
        f"Output: {OUT_DIR}"
    )

    print()

    # -------------------------------------------------------------------------
    # Confirm strategy lab exists.
    # -------------------------------------------------------------------------

    if not STRATEGY_LAB.exists():

        raise FileNotFoundError(
            f"strategy_lab.py not found: {STRATEGY_LAB}"
        )

    all_candidates = []

    # -------------------------------------------------------------------------
    # Collect candidates from all four pools.
    # -------------------------------------------------------------------------

    for pool_name in POOLS:

        candidates = collect_pool(
            pool_name
        )

        if not candidates.empty:

            all_candidates.append(
                (
                    pool_name,
                    candidates,
                )
            )

    # -------------------------------------------------------------------------
    # Collection summary.
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print("CANDIDATE COLLECTION COMPLETE")
    print("=" * 80)

    total = 0

    for pool_name, candidates in all_candidates:

        print(
            f"{pool_name:<20} "
            f"{len(candidates):>5} candidates"
        )

        total += len(candidates)

    print()

    print(
        f"TOTAL CANDIDATES: {total}"
    )

    print()

    # -------------------------------------------------------------------------
    # IMPORTANT:
    #
    # Do not start an expensive search if collection produced nothing.
    # -------------------------------------------------------------------------

    if total == 0:

        print(
            "NO CANDIDATES AVAILABLE."
        )

        print(
            "Big Search will NOT start."
        )

        return

    # -------------------------------------------------------------------------
    # Run one pool at a time.
    #
    # This prevents all four enormous searches from competing for CPU/RAM
    # simultaneously.
    # -------------------------------------------------------------------------

    for pool_name, candidates in all_candidates:

        run_big_search(
            pool_name,
            candidates,
        )

    # -------------------------------------------------------------------------
    # Finished.
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print("BIG SEARCH COMPLETE")
    print("=" * 80)
    print()

    print(
        f"Results: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()