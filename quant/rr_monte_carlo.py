from pathlib import Path
import math
import random
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

SIMULATIONS = 100_000
MONTHS = 12
RISK_PER_TRADE = 0.01

MIN_RR = 1.0
MAX_RR = 6.0
RR_STEP = 0.5

AUDIT_FILE = Path("quant/trade_audit.csv")
OUTPUT_FILE = Path("quant/rr_monte_carlo_results.csv")

RANDOM_SEED = 42


# ============================================================
# HELPERS
# ============================================================

def profit_factor(results):
    wins = sum(r for r in results if r > 0)
    losses = abs(sum(r for r in results if r < 0))

    if losses == 0:
        return float("inf")

    return wins / losses


def max_drawdown(results):
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for r in results:
        equity += r

        if equity > peak:
            peak = equity

        dd = peak - equity

        if dd > max_dd:
            max_dd = dd

    return max_dd


def one_position_constraint(df):
    df = df.sort_values("entry_timestamp").copy()

    selected = []
    last_exit = None

    for _, row in df.iterrows():
        entry = pd.Timestamp(row["entry_timestamp"])
        exit_time = pd.Timestamp(row["exit_timestamp"])

        if last_exit is None or entry >= last_exit:
            selected.append(row)
            last_exit = exit_time

    return pd.DataFrame(selected)


def rr_result(original_r, original_rr, target_rr):
    """
    Convert an original 1R win/loss into the outcome produced
    by the requested RR.

    Original winner:
        +1R -> +target_RR

    Original loser:
        -1R -> -1R

    This assumes the original audit represents whether price
    reached the target before the stop.
    """

    if original_r > 0:
        return target_rr

    return -1.0


def simulate_year(win_probability, target_rr, trades_per_year):
    results = []

    for _ in range(trades_per_year):
        if random.random() < win_probability:
            results.append(target_rr)
        else:
            results.append(-1.0)

    return results


# ============================================================
# LOAD AUDIT
# ============================================================

print()
print("=" * 80)
print("MULTI-RR MONTE CARLO ROBUSTNESS TEST")
print("=" * 80)
print()

print("Strategy:")
print("SELL | New York")
print("liquidity_sweep_high + bearish_candle + bearish_engulfing")
print()

print("Configuration:")
print(f"Simulation count:        {SIMULATIONS:,}")
print(f"Months simulated:        {MONTHS}")
print(f"Risk per trade:          {RISK_PER_TRADE:.2%}")
print("One position only:       True")
print(f"RR range:                {MIN_RR:.1f} -> {MAX_RR:.1f}")
print(f"RR step:                 {RR_STEP:.1f}")
print()

if not AUDIT_FILE.exists():
    raise FileNotFoundError(
        f"Could not find audit file: {AUDIT_FILE}"
    )

print("Loading trade audit...")

df = pd.read_csv(AUDIT_FILE)

if df.empty:
    raise ValueError("Trade audit is empty.")

required_columns = [
    "entry_timestamp",
    "exit_timestamp",
    "r",
]

missing = [
    col for col in required_columns
    if col not in df.columns
]

if missing:
    raise ValueError(
        f"Missing required columns: {missing}"
    )

df["entry_timestamp"] = pd.to_datetime(
    df["entry_timestamp"],
    utc=True,
)

df["exit_timestamp"] = pd.to_datetime(
    df["exit_timestamp"],
    utc=True,
)

df["r"] = pd.to_numeric(
    df["r"],
    errors="coerce",
)

df = df.dropna(
    subset=[
        "entry_timestamp",
        "exit_timestamp",
        "r",
    ]
)

print(f"Audited trades loaded: {len(df)}")


# ============================================================
# ORIGINAL AUDIT
# ============================================================

original_results = df["r"].tolist()

original_wins = sum(1 for r in original_results if r > 0)
original_losses = sum(1 for r in original_results if r < 0)

original_net_r = sum(original_results)

original_win_rate = (
    original_wins / len(original_results)
    if original_results
    else 0
)

original_pf = profit_factor(original_results)
original_dd = max_drawdown(original_results)

print()
print("=" * 80)
print("ORIGINAL AUDIT")
print("=" * 80)

print(f"Trades:           {len(original_results)}")
print(f"Wins:             {original_wins}")
print(f"Losses:           {original_losses}")
print(f"Win rate:         {original_win_rate:.2%}")
print(f"Profit factor:    {original_pf:.3f}")
print(f"Net R:            {original_net_r:.2f}")
print(f"Expectancy:       {original_net_r / len(original_results):.4f} R")
print(f"Max drawdown:     {original_dd:.2f} R")


# ============================================================
# ONE POSITION AT A TIME
# ============================================================

print()
print("Applying one-position-at-a-time constraint...")

constrained = one_position_constraint(df)

removed = len(df) - len(constrained)

print(f"Trades after constraint: {len(constrained)}")
print(f"Overlapping trades removed: {removed}")

if len(constrained) < 2:
    raise ValueError(
        "Not enough trades after one-position constraint."
    )

base_results = constrained["r"].tolist()

wins = sum(1 for r in base_results if r > 0)
losses = sum(1 for r in base_results if r < 0)

win_probability = wins / len(base_results)

loss_probability = losses / len(base_results)

audit_net_r = sum(base_results)
audit_pf = profit_factor(base_results)
audit_dd = max_drawdown(base_results)

print()
print("=" * 80)
print("ONE-POSITION RESULTS")
print("=" * 80)

print(f"Trades:           {len(base_results)}")
print(f"Wins:             {wins}")
print(f"Losses:           {losses}")
print(f"Win rate:         {win_probability:.2%}")
print(f"Loss rate:        {loss_probability:.2%}")
print(f"Profit factor:    {audit_pf:.3f}")
print(f"Net R:            {audit_net_r:.2f}")
print(
    f"Expectancy:       "
    f"{audit_net_r / len(base_results):.4f} R"
)
print(f"Max drawdown:     {audit_dd:.2f} R")


# ============================================================
# ESTIMATE TRADE FREQUENCY
# ============================================================

first_entry = constrained["entry_timestamp"].min()
last_entry = constrained["entry_timestamp"].max()

duration_days = (
    last_entry - first_entry
).total_seconds() / 86400.0

if duration_days <= 0:
    raise ValueError("Invalid audit duration.")

trades_per_day = len(constrained) / duration_days
trades_per_month = trades_per_day * 30.4375

expected_trades = round(
    trades_per_month * MONTHS
)

print()
print(f"Audit duration:          {duration_days:.1f} days")
print(f"Estimated trades/month:  {trades_per_month:.1f}")
print(
    f"Expected trades over "
    f"{MONTHS} months: {expected_trades}"
)


# ============================================================
# RR VALUES
# ============================================================

rr_values = []

rr = MIN_RR

while rr <= MAX_RR + 1e-9:
    rr_values.append(round(rr, 2))
    rr += RR_STEP


# ============================================================
# MONTE CARLO
# ============================================================

random.seed(RANDOM_SEED)

all_summary = []
all_simulation_rows = []

print()
print("=" * 80)
print("RUNNING MULTI-RR MONTE CARLO")
print("=" * 80)
print()

for target_rr in rr_values:

    print(
        f"Testing {target_rr:.1f}R..."
    )

    ending_r_values = []
    ending_return_values = []

    win_counts = []
    loss_counts = []
    win_rates = []
    pf_values = []
    expectancy_values = []
    dd_values = []

    for simulation in range(SIMULATIONS):

        results = simulate_year(
            win_probability=win_probability,
            target_rr=target_rr,
            trades_per_year=expected_trades,
        )

        ending_r = sum(results)

        wins_sim = sum(
            1 for r in results
            if r > 0
        )

        losses_sim = sum(
            1 for r in results
            if r < 0
        )

        total_trades = (
            wins_sim + losses_sim
        )

        win_rate = (
            wins_sim / total_trades
            if total_trades
            else 0
        )

        pf = profit_factor(results)

        expectancy = (
            ending_r / total_trades
            if total_trades
            else 0
        )

        dd = max_drawdown(results)

        ending_r_values.append(ending_r)
        ending_return_values.append(
            ending_r * RISK_PER_TRADE * 100
        )

        win_counts.append(wins_sim)
        loss_counts.append(losses_sim)
        win_rates.append(win_rate)
        pf_values.append(pf)
        expectancy_values.append(expectancy)
        dd_values.append(dd)

        if simulation % 10_000 == 0 and simulation > 0:
            print(
                f"  Progress: "
                f"{simulation:,} / {SIMULATIONS:,}"
            )

    profitable = sum(
        1 for r in ending_r_values
        if r > 0
    )

    negative = sum(
        1 for r in ending_r_values
        if r < 0
    )

    zero_or_negative = sum(
        1 for r in ending_r_values
        if r <= 0
    )

    summary = {
        "target_rr": target_rr,

        "expected_trades": expected_trades,

        "median_wins": float(
            pd.Series(win_counts).median()
        ),

        "median_losses": float(
            pd.Series(loss_counts).median()
        ),

        "median_win_rate": float(
            pd.Series(win_rates).median()
        ),

        "median_profit_factor": float(
            pd.Series(pf_values).median()
        ),

        "median_expectancy_r": float(
            pd.Series(expectancy_values).median()
        ),

        "median_net_r": float(
            pd.Series(ending_r_values).median()
        ),

        "median_return_pct": float(
            pd.Series(ending_return_values).median()
        ),

        "p5_net_r": float(
            pd.Series(ending_r_values).quantile(0.05)
        ),

        "p95_net_r": float(
            pd.Series(ending_r_values).quantile(0.95)
        ),

        "p5_return_pct": float(
            pd.Series(ending_return_values).quantile(0.05)
        ),

        "p95_return_pct": float(
            pd.Series(ending_return_values).quantile(0.95)
        ),

        "p5_win_rate": float(
            pd.Series(win_rates).quantile(0.05)
        ),

        "p95_win_rate": float(
            pd.Series(win_rates).quantile(0.95)
        ),

        "p5_pf": float(
            pd.Series(pf_values).quantile(0.05)
        ),

        "p95_pf": float(
            pd.Series(pf_values).quantile(0.95)
        ),

        "median_max_dd": float(
            pd.Series(dd_values).median()
        ),

        "p95_max_dd": float(
            pd.Series(dd_values).quantile(0.95)
        ),

        "p99_max_dd": float(
            pd.Series(dd_values).quantile(0.99)
        ),

        "worst_max_dd": float(
            max(dd_values)
        ),

        "probability_profitable": (
            profitable / SIMULATIONS
        ),

        "probability_negative": (
            negative / SIMULATIONS
        ),

        "probability_zero_or_negative": (
            zero_or_negative / SIMULATIONS
        ),
    }

    all_summary.append(summary)


# ============================================================
# DISPLAY RESULTS
# ============================================================

summary_df = pd.DataFrame(all_summary)

print()
print("=" * 100)
print("MULTI-RR SUMMARY")
print("=" * 100)

display_columns = [
    "target_rr",
    "expected_trades",
    "median_wins",
    "median_losses",
    "median_win_rate",
    "median_profit_factor",
    "median_expectancy_r",
    "median_net_r",
    "median_return_pct",
    "p5_net_r",
    "p95_net_r",
    "median_max_dd",
    "p95_max_dd",
    "p99_max_dd",
]

print(
    summary_df[
        display_columns
    ].to_string(
        index=False,
        formatters={
            "target_rr": "{:.1f}".format,
            "median_wins": "{:.0f}".format,
            "median_losses": "{:.0f}".format,
            "median_win_rate": "{:.2%}".format,
            "median_profit_factor": "{:.3f}".format,
            "median_expectancy_r": "{:.4f}".format,
            "median_net_r": "{:.2f}".format,
            "median_return_pct": "{:.2f}%".format,
            "p5_net_r": "{:.2f}".format,
            "p95_net_r": "{:.2f}".format,
            "median_max_dd": "{:.2f}".format,
            "p95_max_dd": "{:.2f}".format,
            "p99_max_dd": "{:.2f}".format,
        }
    )
)


# ============================================================
# FIND BEST RR
# ============================================================

best_by_median_r = summary_df.loc[
    summary_df["median_net_r"].idxmax()
]

best_by_p5_r = summary_df.loc[
    summary_df["p5_net_r"].idxmax()
]

best_by_return_dd = summary_df.copy()

best_by_return_dd["return_dd_ratio"] = (
    best_by_return_dd["median_return_pct"]
    / best_by_return_dd["p95_max_dd"].replace(
        0,
        math.nan
    )
)

best_by_return_dd = best_by_return_dd.loc[
    best_by_return_dd["return_dd_ratio"].idxmax()
]


print()
print("=" * 80)
print("BEST RR RESULTS")
print("=" * 80)

print()
print("Highest median 12-month R:")
print(
    f"{best_by_median_r['target_rr']:.1f}R"
)
print(
    f"Median net R: "
    f"{best_by_median_r['median_net_r']:.2f}R"
)
print(
    f"Median return: "
    f"{best_by_median_r['median_return_pct']:.2f}%"
)
print(
    f"95th percentile DD: "
    f"{best_by_median_r['p95_max_dd']:.2f}R"
)

print()
print("Best 5th-percentile outcome:")
print(
    f"{best_by_p5_r['target_rr']:.1f}R"
)
print(
    f"5th percentile net R: "
    f"{best_by_p5_r['p5_net_r']:.2f}R"
)
print(
    f"5th percentile return: "
    f"{best_by_p5_r['p5_return_pct']:.2f}%"
)

print()
print("Best median return / 95% DD ratio:")
print(
    f"{best_by_return_dd['target_rr']:.1f}R"
)
print(
    f"Median return: "
    f"{best_by_return_dd['median_return_pct']:.2f}%"
)
print(
    f"95th percentile DD: "
    f"{best_by_return_dd['p95_max_dd']:.2f}R"
)
print(
    f"Return/DD ratio: "
    f"{best_by_return_dd['return_dd_ratio']:.2f}"
)


# ============================================================
# DETAILED RR REPORT
# ============================================================

print()
print("=" * 80)
print("RR-BY-RR REPORT")
print("=" * 80)

for _, row in summary_df.iterrows():

    print()
    print(
        f"#################### "
        f"{row['target_rr']:.1f}R "
        f"####################"
    )

    print(
        f"Expected trades:       "
        f"{row['expected_trades']:.0f}"
    )

    print(
        f"Median wins:            "
        f"{row['median_wins']:.0f}"
    )

    print(
        f"Median losses:          "
        f"{row['median_losses']:.0f}"
    )

    print(
        f"Median win rate:        "
        f"{row['median_win_rate']:.2%}"
    )

    print(
        f"Median profit factor:   "
        f"{row['median_profit_factor']:.3f}"
    )

    print(
        f"Median expectancy:      "
        f"{row['median_expectancy_r']:.4f}R"
    )

    print(
        f"Median net R:           "
        f"{row['median_net_r']:.2f}R"
    )

    print(
        f"Median return @ 1%:    "
        f"{row['median_return_pct']:.2f}%"
    )

    print(
        f"5th percentile R:       "
        f"{row['p5_net_r']:.2f}R"
    )

    print(
        f"95th percentile R:      "
        f"{row['p95_net_r']:.2f}R"
    )

    print(
        f"Median max DD:          "
        f"{row['median_max_dd']:.2f}R"
    )

    print(
        f"95th percentile DD:     "
        f"{row['p95_max_dd']:.2f}R"
    )

    print(
        f"99th percentile DD:     "
        f"{row['p99_max_dd']:.2f}R"
    )

    print(
        f"Probability profitable: "
        f"{row['probability_profitable']:.2%}"
    )


# ============================================================
# SAVE
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

summary_df.to_csv(
    OUTPUT_FILE,
    index=False
)

print()
print("=" * 80)
print("RESULTS SAVED")
print("=" * 80)

print(
    f"{OUTPUT_FILE.resolve()}"
)

print()
print("=" * 80)
print("MULTI-RR MONTE CARLO COMPLETE")
print("=" * 80)