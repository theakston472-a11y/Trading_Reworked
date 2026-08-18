from pathlib import Path
import argparse
import subprocess
import sys
import pandas as pd

from .config import *
from .quality_screen import screen_discovery
from .winners import select_winners
from .visuals import make_examples
from .reporting import make_report


def run(cmd, cwd=ROOT):
    print("\n>", " ".join(map(str, cmd)))
    return subprocess.run(cmd, cwd=str(cwd), check=True)


def promote_pool(source, pool):
    """
    Promote the best 100 candidates for one session/direction pool.

    This deliberately mirrors the ranking logic used by the existing
    scripts/promote_top100.py, but operates on the screened discovery
    file produced by this pipeline.
    """
    session, direction = POOLS[pool]

    out = TOP100_DIR / f"{pool}_top100.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source)

    if df.empty:
        raise RuntimeError(
            f"Discovery file is empty: {source}"
        )

    required = ["direction", "session", "conditions"]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Discovery file is missing required columns: "
            + ", ".join(missing)
        )

    # Select this pool only.
    x = df[
        df["direction"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq(direction.upper())
        &
        df["session"]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq(session.lower())
    ].copy()

    if x.empty:
        raise RuntimeError(
            f"No candidates found for {session} {direction} "
            f"in {source}"
        )

    # Remove duplicate strategy definitions.
    duplicate_cols = [
        column
        for column in [
            "direction",
            "session",
            "conditions",
            "rr",
        ]
        if column in x.columns
    ]

    if duplicate_cols:
        x = x.drop_duplicates(
            subset=duplicate_cols
        )

    # Match the existing promote_top100.py ranking order.
    sort_cols = [
        column
        for column in [
            "score",
            "positive_periods",
            "trades",
            "net_r",
            "expectancy_r",
            "min_profit_factor",
        ]
        if column in x.columns
    ]

    if sort_cols:
        x = x.sort_values(
            sort_cols,
            ascending=False,
            kind="stable",
        )

    # Keep the strongest 100 candidates for this pool.
    x = (
        x.head(100)
        .reset_index(drop=True)
    )

    # Add a clean pool-specific rank.
    x.insert(
        0,
        "top100_rank",
        range(1, len(x) + 1),
    )

    x.to_csv(
        out,
        index=False,
    )

    print(
        f"Promoted {len(x)} strategies "
        f"-> {out}"
    )

    return out


def deep_search(pool, top_file):
    """
    Run the existing Strategy Laboratory against one Top-100 pool.

    The existing strategy_lab.py remains untouched.
    """
    out_dir = DEEP_DIR / pool
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    out = out_dir / "results.csv"
    db = out_dir / "cache.sqlite"

    if not STRATEGY_LAB.exists():
        raise FileNotFoundError(
            f"Existing deep-search engine not found: "
            f"{STRATEGY_LAB}"
        )

    cmd = [
        sys.executable,
        str(STRATEGY_LAB),

        "--candidates",
        str(top_file),

        "--max-candidates",
        "100",

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
        str(out),

        "--db",
        str(db),

        "--force",
    ]

    run(cmd)

    final_file = out.with_name(
        out.name + "_top_final.csv"
    )

    if not final_file.exists():
        raise FileNotFoundError(
            "Strategy Laboratory completed but the "
            f"expected final file was not found:\n"
            f"{final_file}"
        )

    return final_file


def visualise_pool(pool, top_final):
    """
    Generate visual examples and human-review reports
    for the strongest strategies from a deep-search pool.
    """
    df = pd.read_csv(top_final)

    if df.empty:
        print(
            f"No final strategies to visualise for {pool}"
        )
        return

    if not FEATURE_FILE.exists():
        raise FileNotFoundError(
            f"Feature database not found: {FEATURE_FILE}"
        )

    market = pd.read_csv(
        FEATURE_FILE
    )

    if "timestamp" not in market.columns:
        raise RuntimeError(
            "Feature database does not contain "
            "'timestamp' column."
        )

    market["timestamp"] = pd.to_datetime(
        market["timestamp"],
        utc=True,
        errors="coerce",
    )

    market = market.dropna(
        subset=["timestamp"]
    ).reset_index(drop=True)

    pool_dir = WINNERS_DIR / pool
    pool_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    winners = select_winners(
        top_final,
        pool_dir,
        max_winners=10,
    )

    if winners.empty:
        print(
            f"No strategies passed winner gates for {pool}"
        )
        return

    visual_status = []

    for i, (_, row) in enumerate(
        winners.iterrows(),
        start=1,
    ):
        sdir = (
            pool_dir
            / f"strategy_{i:03d}"
        )

        charts = (
            sdir
            / "charts"
        )

        charts.mkdir(
            parents=True,
            exist_ok=True,
        )

        count = make_examples(
            market,
            row,
            charts,
            examples=VISUAL_EXAMPLES,
        )

        chart_files = sorted(
            charts.glob("*.html")
        )

        make_report(
            row,
            sdir,
            chart_files,
        )

        if count:
            visual_status.append(
                "GENERATED"
            )
        else:
            visual_status.append(
                "NO_EXAMPLES"
            )

    winners = winners.copy()

    winners["visual_status"] = (
        visual_status
    )

    winners.to_csv(
        pool_dir / "winners.csv",
        index=False,
    )

    print(
        f"Generated winner reports for {pool}: "
        f"{len(winners)} strategies"
    )


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Non-destructive end-to-end "
            "strategy research pipeline"
        )
    )

    ap.add_argument(
        "--skip-discovery",
        action="store_true",
        help=(
            "Compatibility option. "
            "Discovery is supplied via --discovery-file."
        ),
    )

    ap.add_argument(
        "--skip-deep",
        action="store_true",
        help="Create Top-100 pools but skip deep Strategy Lab testing.",
    )

    ap.add_argument(
        "--skip-visual",
        action="store_true",
        help="Skip visual validation and winner reports.",
    )

    ap.add_argument(
        "--pool",
        choices=list(POOLS),
        action="append",
        help=(
            "Run only the specified pool. "
            "Can be supplied multiple times."
        ),
    )

    ap.add_argument(
        "--discovery-file",
        default=str(DISCOVERY_FILE),
        help="Discovery candidate CSV.",
    )

    args = ap.parse_args()

    pools = (
        args.pool
        or list(POOLS)
    )

    print()
    print("=" * 80)
    print("TRADING RESEARCH PIPELINE")
    print("=" * 80)
    print()

    print(
        f"Root:            {ROOT}"
    )

    print(
        f"Discovery file:  {args.discovery_file}"
    )

    print(
        f"Pools:            {', '.join(pools)}"
    )

    print(
        f"Skip deep:        {args.skip_deep}"
    )

    print(
        f"Skip visual:      {args.skip_visual}"
    )

    print()

    # Create output directories.
    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    TOP100_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DEEP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    WINNERS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Locate discovery data.
    discovery = Path(
        args.discovery_file
    )

    if not discovery.exists():
        raise FileNotFoundError(
            f"Discovery file not found:\n"
            f"{discovery}\n\n"
            "Run your existing discovery stage first "
            "or pass --discovery-file."
        )

    # ------------------------------------------------------------------
    # STAGE 1: QUALITY SCREEN
    # ------------------------------------------------------------------

    print()
    print("=" * 80)
    print("STAGE 1: DISCOVERY QUALITY SCREEN")
    print("=" * 80)
    print()

    screened = (
        RESULTS
        / "discovery_screened.csv"
    )

    screen_discovery(
        discovery,
        screened,
    )

    if not screened.exists():
        raise FileNotFoundError(
            "Quality screen completed but did not create:\n"
            f"{screened}"
        )

    print(
        f"\nScreened discovery file: {screened}"
    )

    # ------------------------------------------------------------------
    # STAGES 2-4: TOP100 → DEEP TEST → VISUAL
    # ------------------------------------------------------------------

    for pool in pools:

        print()
        print("=" * 80)
        print(f"POOL: {pool}")
        print("=" * 80)
        print()

        # --------------------------------------------------------------
        # STAGE 2: TOP 100 PROMOTION
        # --------------------------------------------------------------

        print(
            f"[{pool}] Promoting Top 100..."
        )

        top = promote_pool(
            screened,
            pool,
        )

        if not top.exists():
            raise FileNotFoundError(
                f"Top-100 file was not created:\n"
                f"{top}"
            )

        print(
            f"[{pool}] Top 100 ready: {top}"
        )

        # --------------------------------------------------------------
        # STAGE 3: DEEP STRATEGY LAB
        # --------------------------------------------------------------

        if args.skip_deep:
            print(
                f"[{pool}] Deep search skipped."
            )
            continue

        print(
            f"[{pool}] Starting deep Strategy Lab..."
        )

        final = deep_search(
            pool,
            top,
        )

        print(
            f"[{pool}] Deep search complete:"
        )

        print(
            f"        {final}"
        )

        # --------------------------------------------------------------
        # STAGE 4: VISUAL VALIDATION
        # --------------------------------------------------------------

        if args.skip_visual:
            print(
                f"[{pool}] Visual validation skipped."
            )
            continue

        print(
            f"[{pool}] Generating visual validation..."
        )

        visualise_pool(
            pool,
            final,
        )

        print(
            f"[{pool}] Visual validation complete."
        )

    # ------------------------------------------------------------------
    # COMPLETE
    # ------------------------------------------------------------------

    print()
    print("=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print()

    print(
        f"Top 100:      {TOP100_DIR}"
    )

    print(
        f"Deep search:  {DEEP_DIR}"
    )

    print(
        f"Winners:      {WINNERS_DIR}"
    )

    print()


if __name__ == "__main__":
    main()