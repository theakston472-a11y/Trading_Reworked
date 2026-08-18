"""
portfolio_validation.py

FULL-HISTORY PORTFOLIO VALIDATION

Purpose
-------
Takes the portfolios produced by portfolio_optimizer.py and validates
them using the existing portfolio_test.py simulator.

Portfolios tested:
    5 strategies
    10 strategies
    15 strategies
    20 strategies
    25 strategies
    30 strategies

This is a validation program.
It does NOT place trades.

Project:
    C:\\Trading\\Trading_Reworked
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import pandas as pd


# ======================================================================
# PROJECT PATHS
# ======================================================================

PROJECT_ROOT = Path(r"D:\\Trading\\Trading_Reworked")

SCRIPTS_DIR = PROJECT_ROOT / "scripts"

RESULTS_DIR = PROJECT_ROOT / "results"

OPTIMIZER_DIR = RESULTS_DIR / "portfolio_optimizer"

PORTFOLIO_TEST_DIR = RESULTS_DIR / "portfolio_test"

VALIDATION_DIR = RESULTS_DIR / "portfolio_validation"

PORTFOLIO_TEST_SCRIPT = SCRIPTS_DIR / "portfolio_test.py"


# ======================================================================
# PORTFOLIOS TO TEST
# ======================================================================

PORTFOLIO_SIZES = [5, 10, 15, 20, 25, 30]


# ======================================================================
# HELPERS
# ======================================================================

def line(char="=", length=70):
    print(char * length)


def heading(title):
    print()
    line()
    print(title)
    line()


def check_file(path: Path, description: str):
    if not path.exists():
        print(f"[MISSING] {description}")
        print(f"          {path}")
        return False

    print(f"[OK]      {path}")
    return True


def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


# ======================================================================
# CHECK PROJECT
# ======================================================================

def check_project():

    heading("PORTFOLIO VALIDATION")

    print("This is a research/validation program.")
    print("It does NOT place trades.")
    print()
    print(f"Project folder:")
    print(PROJECT_ROOT)

    if not PROJECT_ROOT.exists():
        print()
        print("[ERROR] Project folder does not exist.")
        return False

    if not SCRIPTS_DIR.exists():
        print()
        print("[ERROR] scripts folder does not exist.")
        return False

    if not OPTIMIZER_DIR.exists():
        print()
        print("[ERROR] portfolio_optimizer results folder does not exist.")
        print()
        print("Run the optimizer first:")
        print("python .\\scripts\\portfolio_optimizer.py")
        return False

    if not PORTFOLIO_TEST_SCRIPT.exists():
        print()
        print("[ERROR] portfolio_test.py does not exist.")
        print()
        print(f"Expected:")
        print(PORTFOLIO_TEST_SCRIPT)
        return False

    return True


# ======================================================================
# LOAD PORTFOLIO FILE
# ======================================================================

def load_portfolio(size: int):

    path = OPTIMIZER_DIR / f"best_{size}_strategy_portfolio.csv"

    print()
    print(f"Loading {size}-strategy portfolio...")
    print(path)

    if not path.exists():
        print(f"[ERROR] Missing portfolio:")
        print(path)
        return None

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        print(f"[ERROR] Could not read portfolio:")
        print(exc)
        return None

    if df.empty:
        print("[ERROR] Portfolio is empty.")
        return None

    print(f"[OK] Loaded {len(df)} strategies.")

    return df


# ======================================================================
# BACKUP CURRENT PORTFOLIO INPUTS
# ======================================================================

def backup_existing_files():

    backup_dir = VALIDATION_DIR / "_backup"

    backup_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        PORTFOLIO_TEST_DIR / "selected_strategies.csv",
        PORTFOLIO_TEST_DIR / "portfolio_strategies.csv",
        RESULTS_DIR / "selected_strategies.csv",
        RESULTS_DIR / "portfolio_strategies.csv",
    ]

    backed_up = []

    for path in candidates:

        if path.exists():

            destination = backup_dir / path.name

            try:
                shutil.copy2(path, destination)
                backed_up.append((path, destination))
            except Exception:
                pass

    return backed_up


# ======================================================================
# FIND HOW PORTFOLIO_TEST EXPECTS STRATEGIES
# ======================================================================

def detect_input_file():

    candidates = [
        PORTFOLIO_TEST_DIR / "selected_strategies.csv",
        PORTFOLIO_TEST_DIR / "portfolio_strategies.csv",
        RESULTS_DIR / "selected_strategies.csv",
        RESULTS_DIR / "portfolio_strategies.csv",
        OPTIMIZER_DIR / "recommended_portfolio.csv",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


# ======================================================================
# PREPARE SELECTED STRATEGIES
# ======================================================================

def prepare_selected_strategies(portfolio: pd.DataFrame):

    """
    Creates the strategy selection file expected by the portfolio tester.

    The optimizer normally preserves strategy_id, direction, session,
    conditions and RR information.

    We keep every available column rather than stripping the portfolio
    down unnecessarily.
    """

    target = PORTFOLIO_TEST_DIR / "selected_strategies.csv"

    PORTFOLIO_TEST_DIR.mkdir(parents=True, exist_ok=True)

    output = portfolio.copy()

    # Make sure strategy_id exists.
    if "strategy_id" not in output.columns:

        possible = [
            "id",
            "strategy",
            "strategy_id_x",
        ]

        found = None

        for column in possible:
            if column in output.columns:
                found = column
                break

        if found is None:
            raise ValueError(
                "Portfolio does not contain a strategy_id column."
            )

        output["strategy_id"] = output[found]

    # Ensure strategy_id is numeric where possible.
    output["strategy_id"] = pd.to_numeric(
        output["strategy_id"],
        errors="coerce"
    )

    output = output.dropna(subset=["strategy_id"])

    output["strategy_id"] = output["strategy_id"].astype(int)

    output.to_csv(target, index=False)

    return target


# ======================================================================
# RUN PORTFOLIO TEST
# ======================================================================

def run_portfolio_test(size: int):

    print()
    line("-")
    print(f"RUNNING ACTUAL FULL-HISTORY TEST: {size} STRATEGIES")
    line("-")

    command = [
        sys.executable,
        str(PORTFOLIO_TEST_SCRIPT),
    ]

    print()
    print("Command:")
    print(" ".join(f'"{x}"' if " " in x else x for x in command))
    print()

    start_time = datetime.now()

    process = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
    )

    elapsed = datetime.now() - start_time

    print(process.stdout)

    if process.stderr:
        print()
        print("PYTHON STDERR:")
        print(process.stderr)

    print()
    print(f"Test runtime: {elapsed}")

    if process.returncode != 0:
        print()
        print(f"[ERROR] portfolio_test.py failed.")
        print(f"Exit code: {process.returncode}")
        return False

    return True


# ======================================================================
# COPY RESULTS FOR THIS PORTFOLIO
# ======================================================================

def save_test_results(size: int):

    destination = VALIDATION_DIR / f"portfolio_{size}"

    destination.mkdir(parents=True, exist_ok=True)

    files = [
        "individual_results.csv",
        "yearly_results.csv",
        "portfolio_trades.csv",
        "rejected_trades.csv",
        "portfolio_equity.csv",
        "strategy_contribution.csv",
        "portfolio_yearly.csv",
        "strategy_overlap.csv",
        "portfolio_summary.json",
    ]

    copied = 0

    for filename in files:

        source = PORTFOLIO_TEST_DIR / filename

        if source.exists():

            target = destination / filename

            try:
                shutil.copy2(source, target)
                copied += 1
            except Exception as exc:
                print(
                    f"[WARNING] Could not copy {filename}: {exc}"
                )

    print()
    print(f"Saved {copied} result files for {size}-strategy portfolio.")

    return destination


# ======================================================================
# READ SUMMARY
# ======================================================================

def read_summary(size: int):

    folder = VALIDATION_DIR / f"portfolio_{size}"

    summary_path = folder / "portfolio_summary.json"

    if not summary_path.exists():
        return None

    try:

        with open(
            summary_path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:
        return None


# ======================================================================
# READ RESULTS FROM CSV IF JSON DOES NOT CONTAIN EVERYTHING
# ======================================================================

def extract_results(size: int):

    folder = VALIDATION_DIR / f"portfolio_{size}"

    summary = read_summary(size)

    result = {
        "portfolio_size": size,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "net_r": 0.0,
        "expectancy_r": 0.0,
        "max_drawdown_r": 0.0,
        "average_trades_day": 0.0,
        "accepted_trades": 0,
        "rejected_trades": 0,
    }

    # --------------------------------------------------------------
    # JSON
    # --------------------------------------------------------------

    if isinstance(summary, dict):

        aliases = {
            "trades": [
                "trades",
                "portfolio_trades",
                "total_trades",
            ],

            "wins": [
                "wins",
            ],

            "losses": [
                "losses",
            ],

            "win_rate": [
                "win_rate",
            ],

            "profit_factor": [
                "profit_factor",
            ],

            "net_r": [
                "net_r",
                "net_R",
            ],

            "expectancy_r": [
                "expectancy_r",
                "expectancy_R",
            ],

            "max_drawdown_r": [
                "max_drawdown_r",
                "max_drawdown_R",
            ],

            "average_trades_day": [
                "average_trades_day",
                "avg_trades_day",
            ],

            "accepted_trades": [
                "accepted_trades",
            ],

            "rejected_trades": [
                "rejected_trades",
            ],
        }

        for destination, keys in aliases.items():

            for key in keys:

                if key in summary:

                    result[destination] = safe_float(
                        summary[key]
                    )

                    break

    # --------------------------------------------------------------
    # PORTFOLIO TRADES CSV
    # --------------------------------------------------------------

    trades_file = folder / "portfolio_trades.csv"

    if trades_file.exists():

        try:

            trades = pd.read_csv(trades_file)

            if not trades.empty:

                result["trades"] = len(trades)

                result["accepted_trades"] = len(trades)

                # Find R column.
                r_column = None

                for column in [
                    "net_r",
                    "r",
                    "R",
                    "result_r",
                    "pnl_r",
                ]:

                    if column in trades.columns:

                        r_column = column
                        break

                if r_column:

                    r_values = pd.to_numeric(
                        trades[r_column],
                        errors="coerce"
                    ).dropna()

                    if len(r_values):

                        result["net_r"] = float(
                            r_values.sum()
                        )

                        result["expectancy_r"] = float(
                            r_values.mean()
                        )

                        result["wins"] = int(
                            (r_values > 0).sum()
                        )

                        result["losses"] = int(
                            (r_values < 0).sum()
                        )

                        result["win_rate"] = (
                            result["wins"]
                            / len(r_values)
                            * 100
                        )

                        gross_profit = float(
                            r_values[r_values > 0].sum()
                        )

                        gross_loss = abs(
                            float(
                                r_values[r_values < 0].sum()
                            )
                        )

                        if gross_loss > 0:

                            result["profit_factor"] = (
                                gross_profit
                                / gross_loss
                            )

        except Exception:
            pass

    # --------------------------------------------------------------
    # REJECTED TRADES
    # --------------------------------------------------------------

    rejected_file = folder / "rejected_trades.csv"

    if rejected_file.exists():

        try:

            rejected = pd.read_csv(
                rejected_file
            )

            result["rejected_trades"] = len(
                rejected
            )

        except Exception:
            pass

    # --------------------------------------------------------------
    # EQUITY / DRAWDOWN
    # --------------------------------------------------------------

    equity_file = folder / "portfolio_equity.csv"

    if equity_file.exists():

        try:

            equity = pd.read_csv(
                equity_file
            )

            if not equity.empty:

                equity_column = None

                for column in [
                    "equity_r",
                    "equity",
                    "net_r",
                    "cumulative_r",
                    "cum_r",
                ]:

                    if column in equity.columns:

                        equity_column = column
                        break

                if equity_column:

                    values = pd.to_numeric(
                        equity[equity_column],
                        errors="coerce"
                    ).dropna()

                    if len(values):

                        running_max = values.cummax()

                        drawdown = (
                            running_max - values
                        )

                        result["max_drawdown_r"] = float(
                            drawdown.max()
                        )

        except Exception:
            pass

    # --------------------------------------------------------------
    # DAILY TRADE RATE
    # --------------------------------------------------------------

    trades_file = folder / "portfolio_trades.csv"

    if trades_file.exists():

        try:

            trades = pd.read_csv(
                trades_file
            )

            date_column = None

            for column in [
                "timestamp",
                "datetime",
                "date",
                "entry_time",
                "entry_datetime",
            ]:

                if column in trades.columns:

                    date_column = column
                    break

            if date_column:

                dates = pd.to_datetime(
                    trades[date_column],
                    errors="coerce"
                ).dropna()

                if len(dates):

                    days = (
                        dates.max().date()
                        - dates.min().date()
                    ).days + 1

                    if days > 0:

                        result["average_trades_day"] = (
                            len(trades) / days
                        )

        except Exception:
            pass

    return result


# ======================================================================
# BUILD COMPARISON
# ======================================================================

def build_comparison(results):

    df = pd.DataFrame(results)

    if df.empty:
        return df

    # --------------------------------------------------------------
    # Return / drawdown
    # --------------------------------------------------------------

    df["return_to_drawdown"] = 0.0

    mask = df["max_drawdown_r"] > 0

    df.loc[mask, "return_to_drawdown"] = (
        df.loc[mask, "net_r"]
        / df.loc[mask, "max_drawdown_r"]
    )

    # --------------------------------------------------------------
    # Simple validation score
    #
    # This is NOT a trading signal.
    #
    # It rewards:
    #   - net R
    #   - PF
    #   - expectancy
    #   - lower DD
    #
    # It deliberately does not simply rank by net R.
    # --------------------------------------------------------------

    df["validation_score"] = (
        df["return_to_drawdown"] * 30.0
        + df["profit_factor"] * 20.0
        + df["expectancy_r"] * 25.0
    )

    df = df.sort_values(
        "validation_score",
        ascending=False
    ).reset_index(drop=True)

    df.insert(
        0,
        "rank",
        range(1, len(df) + 1)
    )

    return df


# ======================================================================
# MAIN
# ======================================================================

def main():

    if not check_project():
        return 1

    # --------------------------------------------------------------
    # Prepare validation folder
    # --------------------------------------------------------------

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------------
    # Check all optimizer portfolios
    # --------------------------------------------------------------

    heading("CHECKING OPTIMIZER PORTFOLIOS")

    portfolios = {}

    for size in PORTFOLIO_SIZES:

        portfolio = load_portfolio(size)

        if portfolio is None:

            print()
            print(
                f"[ERROR] Cannot validate {size}-strategy portfolio."
            )

            return 1

        portfolios[size] = portfolio

    # --------------------------------------------------------------
    # Backup current selected strategy file
    # --------------------------------------------------------------

    heading("BACKING UP EXISTING PORTFOLIO INPUT")

    backups = backup_existing_files()

    if backups:

        for original, backup in backups:

            print(
                f"[BACKUP] {original.name}"
            )

    else:

        print(
            "No existing selected-strategy input needed backing up."
        )

    # --------------------------------------------------------------
    # Run each portfolio
    # --------------------------------------------------------------

    results = []

    for size in PORTFOLIO_SIZES:

        heading(
            f"VALIDATING {size}-STRATEGY PORTFOLIO"
        )

        portfolio = portfolios[size]

        print()
        print(
            f"Strategies selected: {len(portfolio)}"
        )

        # Show IDs.
        if "strategy_id" in portfolio.columns:

            ids = portfolio[
                "strategy_id"
            ].tolist()

            print()
            print("Strategy IDs:")
            print(ids)

        # ----------------------------------------------------------
        # Install selected portfolio as portfolio_test input
        # ----------------------------------------------------------

        try:

            selected_file = (
                prepare_selected_strategies(
                    portfolio
                )
            )

        except Exception as exc:

            print()
            print(
                "[ERROR] Could not prepare selected strategies."
            )

            print(exc)

            return 1

        print()
        print(
            f"Selected strategies written to:"
        )
        print(selected_file)

        # ----------------------------------------------------------
        # Run actual simulator
        # ----------------------------------------------------------

        success = run_portfolio_test(size)

        if not success:

            print()
            print(
                f"[ERROR] Validation failed for "
                f"{size}-strategy portfolio."
            )

            return 1

        # ----------------------------------------------------------
        # Copy results before next portfolio overwrites them
        # ----------------------------------------------------------

        save_test_results(size)

        # ----------------------------------------------------------
        # Extract summary
        # ----------------------------------------------------------

        result = extract_results(size)

        results.append(result)

        print()
        print(
            f"{size}-STRATEGY PORTFOLIO SUMMARY"
        )

        print(
            f"Trades:          {safe_int(result['trades'])}"
        )

        print(
            f"Net R:           {result['net_r']:.3f}"
        )

        print(
            f"Expectancy:      {result['expectancy_r']:.4f}R"
        )

        print(
            f"Profit factor:   {result['profit_factor']:.3f}"
        )

        print(
            f"Max drawdown:    {result['max_drawdown_r']:.3f}R"
        )

        print(
            f"Win rate:        {result['win_rate']:.2f}%"
        )

    # --------------------------------------------------------------
    # Build final comparison
    # --------------------------------------------------------------

    heading("FINAL SIX-YEAR PORTFOLIO COMPARISON")

    comparison = build_comparison(results)

    if comparison.empty:

        print(
            "[ERROR] No results were produced."
        )

        return 1

    display_columns = [
        "rank",
        "portfolio_size",
        "trades",
        "net_r",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_r",
        "win_rate",
        "average_trades_day",
        "return_to_drawdown",
        "validation_score",
    ]

    display_columns = [
        column
        for column in display_columns
        if column in comparison.columns
    ]

    print(
        comparison[
            display_columns
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}"
        )
    )

    # --------------------------------------------------------------
    # Save comparison
    # --------------------------------------------------------------

    comparison_path = (
        VALIDATION_DIR
        / "portfolio_validation_comparison.csv"
    )

    comparison.to_csv(
        comparison_path,
        index=False
    )

    # --------------------------------------------------------------
    # Determine best portfolio
    # --------------------------------------------------------------

    best = comparison.iloc[0]

    best_size = int(
        best["portfolio_size"]
    )

    # --------------------------------------------------------------
    # Save JSON summary
    # --------------------------------------------------------------

    summary = {
        "created": datetime.now().isoformat(),

        "description": (
            "Full-history validation of optimizer-selected "
            "portfolio sizes."
        ),

        "portfolio_sizes_tested": PORTFOLIO_SIZES,

        "best_portfolio_size": best_size,

        "best_validation_score": safe_float(
            best["validation_score"]
        ),

        "best_net_r": safe_float(
            best["net_r"]
        ),

        "best_expectancy_r": safe_float(
            best["expectancy_r"]
        ),

        "best_profit_factor": safe_float(
            best["profit_factor"]
        ),

        "best_max_drawdown_r": safe_float(
            best["max_drawdown_r"]
        ),

        "best_win_rate": safe_float(
            best["win_rate"]
        ),

        "comparison_file": str(
            comparison_path
        ),

        "validation_folder": str(
            VALIDATION_DIR
        ),
    }

    summary_path = (
        VALIDATION_DIR
        / "portfolio_validation_summary.json"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=4
        )

    # --------------------------------------------------------------
    # Final output
    # --------------------------------------------------------------

    heading("VALIDATION COMPLETE")

    print(
        f"Best validated portfolio size: "
        f"{best_size} strategies"
    )

    print(
        f"Actual Net R: "
        f"{safe_float(best['net_r']):.3f}"
    )

    print(
        f"Actual Expectancy: "
        f"{safe_float(best['expectancy_r']):.4f}R"
    )

    print(
        f"Actual Profit Factor: "
        f"{safe_float(best['profit_factor']):.3f}"
    )

    print(
        f"Actual Max Drawdown: "
        f"{safe_float(best['max_drawdown_r']):.3f}R"
    )

    print(
        f"Actual Win Rate: "
        f"{safe_float(best['win_rate']):.2f}%"
    )

    print()
    print("Files saved:")
    print(comparison_path)
    print(summary_path)

    print()
    print(
        f"Individual validation folders:"
    )

    for size in PORTFOLIO_SIZES:

        print(
            VALIDATION_DIR
            / f"portfolio_{size}"
        )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "These results are historical validation only."
    )

    print(
        "Do not treat the highest Net R alone as the "
        "best live portfolio."
    )

    print(
        "We should inspect drawdown, yearly performance, "
        "strategy overlap and stability before selecting "
        "the final portfolio."
    )

    return 0


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
