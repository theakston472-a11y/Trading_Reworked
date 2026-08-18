from pathlib import Path
import random
import math
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

SIMULATIONS = 100_000
MONTHS = 12
RISK_PER_TRADE = 0.01
ONE_POSITION_ONLY = True

AUDIT_FILE = Path("quant/trade_audit.csv")
OUTPUT_FILE = Path("quant/monte_carlo_results.csv")

# Estimate monthly trade frequency from the audited sample.
# The audit currently covers roughly 1 month.
TRADES_PER_MONTH = None


# =============================================================================
# HELPERS
# =============================================================================

def max_drawdown_r(results):
    """
    Calculate maximum peak-to-trough drawdown in R.
    """
    if not results:
        return 0.0

    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for r in results:
        equity += r
        peak = max(peak, equity)
        drawdown = peak - equity
        max_dd = max(max_dd, drawdown)

    return max_dd


def percentile(values, p):
    """
    Simple percentile calculation without requiring numpy.
    """
    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    position = (len(values) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return float(values[lower])

    fraction = position - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * fraction
    )


def calculate_profit_factor(r_values):
    """
    Profit factor = gross winning R / absolute gross losing R.
    """
    gross_profit = sum(r for r in r_values if r > 0)
    gross_loss = abs(sum(r for r in r_values if r < 0))

    if gross_loss == 0:
        return float("inf")

    return gross_profit / gross_loss


def print_distribution(title, values, suffix=""):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    print(f"5th percentile:       {percentile(values, 0.05):.2f}{suffix}")
    print(f"Median:               {percentile(values, 0.50):.2f}{suffix}")
    print(f"95th percentile:      {percentile(values, 0.95):.2f}{suffix}")


# =============================================================================
# LOAD AUDIT
# =============================================================================

print()
print("#" * 80)
print("MULTI-MONTH MONTE CARLO ROBUSTNESS TEST")
print("#" * 80)

print()
print("Strategy:")
print("SELL | New York")
print("liquidity_sweep_high + bearish_candle + bearish_engulfing")

print()
print("Configuration:")
print(f"Simulation count:        {SIMULATIONS:,}")
print(f"Months simulated:        {MONTHS}")
print(f"Risk per trade:          {RISK_PER_TRADE * 100:.2f}%")
print(f"One position only:       {ONE_POSITION_ONLY}")

print()
print("Loading trade audit...")

if not AUDIT_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {AUDIT_FILE}"
    )

df = pd.read_csv(AUDIT_FILE)

if df.empty:
    raise ValueError("Trade audit is empty.")

print(f"Audited trades loaded: {len(df)}")


# =============================================================================
# PREPARE TRADE RESULTS
# =============================================================================

if "r" not in df.columns:
    raise ValueError(
        "trade_audit.csv does not contain an 'r' column."
    )

if "entry_timestamp" not in df.columns:
    raise ValueError(
        "trade_audit.csv does not contain 'entry_timestamp'."
    )

if "exit_timestamp" not in df.columns:
    raise ValueError(
        "trade_audit.csv does not contain 'exit_timestamp'."
    )

df["entry_timestamp"] = pd.to_datetime(
    df["entry_timestamp"],
    utc=True
)

df["exit_timestamp"] = pd.to_datetime(
    df["exit_timestamp"],
    utc=True
)

df["r"] = pd.to_numeric(
    df["r"],
    errors="coerce"
)

df = df.dropna(
    subset=["entry_timestamp", "exit_timestamp", "r"]
)

df = df.sort_values("entry_timestamp").reset_index(drop=True)


# =============================================================================
# ORIGINAL AUDIT
# =============================================================================

original_r = df["r"].tolist()

original_wins = sum(r > 0 for r in original_r)
original_losses = sum(r < 0 for r in original_r)

original_trades = len(original_r)

original_win_rate = (
    original_wins / original_trades * 100
    if original_trades
    else 0
)

original_expectancy = (
    sum(original_r) / original_trades
    if original_trades
    else 0
)

original_pf = calculate_profit_factor(original_r)
original_net_r = sum(original_r)
original_dd = max_drawdown_r(original_r)

print()
print("=" * 80)
print("ORIGINAL AUDIT")
print("=" * 80)

print(f"Trades:           {original_trades}")
print(f"Wins:             {original_wins}")
print(f"Losses:           {original_losses}")
print(f"Win rate:         {original_win_rate:.2f}%")
print(f"Profit factor:    {original_pf:.3f}")
print(f"Net R:            {original_net_r:.2f}")
print(f"Expectancy:       {original_expectancy:.4f} R")
print(f"Max drawdown:     {original_dd:.2f} R")


# =============================================================================
# ONE POSITION AT A TIME
# =============================================================================

if ONE_POSITION_ONLY:

    print()
    print("Applying one-position-at-a-time constraint...")

    accepted = []
    last_exit = None
    removed = 0

    for _, row in df.iterrows():

        entry = row["entry_timestamp"]
        exit_time = row["exit_timestamp"]

        if last_exit is not None and entry < last_exit:
            removed += 1
            continue

        accepted.append(row)
        last_exit = exit_time

    constrained_df = pd.DataFrame(accepted)

else:

    constrained_df = df.copy()
    removed = 0


constrained_r = constrained_df["r"].tolist()

constrained_trades = len(constrained_r)

constrained_wins = sum(r > 0 for r in constrained_r)
constrained_losses = sum(r < 0 for r in constrained_r)

constrained_win_rate = (
    constrained_wins / constrained_trades * 100
    if constrained_trades
    else 0
)

constrained_loss_rate = (
    constrained_losses / constrained_trades * 100
    if constrained_trades
    else 0
)

constrained_expectancy = (
    sum(constrained_r) / constrained_trades
    if constrained_trades
    else 0
)

constrained_pf = calculate_profit_factor(constrained_r)
constrained_net_r = sum(constrained_r)
constrained_dd = max_drawdown_r(constrained_r)

print(f"Trades after constraint: {constrained_trades}")
print(f"Overlapping trades removed: {removed}")

print()
print("=" * 80)
print("ONE-POSITION RESULTS")
print("=" * 80)

print(f"Trades:           {constrained_trades}")
print(f"Wins:             {constrained_wins}")
print(f"Losses:           {constrained_losses}")
print(f"Win rate:         {constrained_win_rate:.2f}%")
print(f"Loss rate:        {constrained_loss_rate:.2f}%")
print(f"Profit factor:    {constrained_pf:.3f}")
print(f"Net R:            {constrained_net_r:.2f}")
print(f"Expectancy:       {constrained_expectancy:.4f} R")
print(f"Max drawdown:     {constrained_dd:.2f} R")


# =============================================================================
# TRADE FREQUENCY
# =============================================================================

# Your current audit period is July 1 -> August 8.
# Calculate the number of calendar days represented by the audit.

audit_start = constrained_df["entry_timestamp"].min()
audit_end = constrained_df["exit_timestamp"].max()

audit_days = (
    audit_end - audit_start
).total_seconds() / 86400.0

if audit_days <= 0:
    audit_days = 30.0

trades_per_day = constrained_trades / audit_days
trades_per_month = trades_per_day * 30.4375

TRADES_PER_MONTH = max(
    1,
    round(trades_per_month)
)

expected_trades = TRADES_PER_MONTH * MONTHS

print()
print(f"Audit duration:          {audit_days:.1f} days")
print(f"Estimated trades/month:  {TRADES_PER_MONTH}")
print(f"Expected trades over {MONTHS} months: {expected_trades}")


# =============================================================================
# HISTORICAL R OUTCOME POOL
# =============================================================================

# We resample the observed trade outcomes with replacement.
#
# This preserves the observed +1R / -1R distribution while randomising
# the order of wins and losses.
#
# It answers:
#
# "If future trades have the same statistical properties as the audited
# trades, what could different 12-month sequences look like?"
#
# It does NOT guarantee future performance.

historical_outcomes = constrained_r.copy()

if not historical_outcomes:
    raise ValueError("No trade outcomes available for simulation.")


# =============================================================================
# MONTE CARLO
# =============================================================================

print()
print(
    f"Running {SIMULATIONS:,} Monte Carlo simulations "
    f"over {MONTHS} months..."
)

simulation_rows = []

ending_r_values = []
ending_return_values = []
drawdown_values = []

win_counts = []
loss_counts = []
win_rates = []
loss_rates = []
profit_factors = []
expectancies = []
average_r_values = []
trade_counts = []

profitable_count = 0
negative_count = 0
zero_or_negative_count = 0


for simulation in range(1, SIMULATIONS + 1):

    # Randomly sample the historical R outcomes.
    simulated = random.choices(
        historical_outcomes,
        k=expected_trades
    )

    wins = sum(r > 0 for r in simulated)
    losses = sum(r < 0 for r in simulated)

    total_trades = len(simulated)

    win_rate = (
        wins / total_trades * 100
        if total_trades
        else 0
    )

    loss_rate = (
        losses / total_trades * 100
        if total_trades
        else 0
    )

    net_r = sum(simulated)

    avg_r = (
        net_r / total_trades
        if total_trades
        else 0
    )

    pf = calculate_profit_factor(simulated)

    dd = max_drawdown_r(simulated)

    # Fixed 1% risk interpretation:
    #
    # +1R = +1%
    # -1R = -1%
    #
    # This is deliberately a simple R-based interpretation rather than
    # compounding account balance after every trade.
    return_pct = net_r * RISK_PER_TRADE * 100

    if net_r > 0:
        profitable_count += 1
    else:
        negative_count += 1

    if net_r <= 0:
        zero_or_negative_count += 1

    ending_r_values.append(net_r)
    ending_return_values.append(return_pct)
    drawdown_values.append(dd)

    win_counts.append(wins)
    loss_counts.append(losses)
    win_rates.append(win_rate)
    loss_rates.append(loss_rate)
    profit_factors.append(pf)
    expectancies.append(avg_r)
    average_r_values.append(avg_r)
    trade_counts.append(total_trades)

    simulation_rows.append(
        {
            "simulation": simulation,
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "profit_factor": pf,
            "average_r_per_trade": avg_r,
            "net_r": net_r,
            "return_percent": return_pct,
            "max_drawdown_r": dd,
        }
    )

    if simulation % 10_000 == 0:
        print(
            f"Progress: {simulation:,} / {SIMULATIONS:,}"
        )


# =============================================================================
# DISTRIBUTIONS
# =============================================================================

print_distribution(
    "ENDING R DISTRIBUTION",
    ending_r_values,
    " R"
)

print_distribution(
    "ENDING RETURN DISTRIBUTION",
    ending_return_values,
    "%"
)

print_distribution(
    "WIN COUNT DISTRIBUTION",
    win_counts
)

print_distribution(
    "LOSS COUNT DISTRIBUTION",
    loss_counts
)

print_distribution(
    "WIN RATE DISTRIBUTION",
    win_rates,
    "%"
)

print_distribution(
    "PROFIT FACTOR DISTRIBUTION",
    profit_factors
)

print_distribution(
    "AVERAGE R PER TRADE DISTRIBUTION",
    average_r_values,
    " R"
)


# =============================================================================
# PROBABILITY
# =============================================================================

probability_profitable = (
    profitable_count / SIMULATIONS * 100
)

probability_negative = (
    negative_count / SIMULATIONS * 100
)

probability_zero_or_negative = (
    zero_or_negative_count / SIMULATIONS * 100
)

print()
print("=" * 80)
print("PROBABILITY")
print("=" * 80)

print(
    f"Probability profitable:       "
    f"{probability_profitable:.2f}%"
)

print(
    f"Probability negative:         "
    f"{probability_negative:.2f}%"
)

print(
    f"Probability zero/negative:    "
    f"{probability_zero_or_negative:.2f}%"
)


# =============================================================================
# DRAWDOWN DISTRIBUTION
# =============================================================================

print()
print("=" * 80)
print("MAX DRAWDOWN DISTRIBUTION")
print("=" * 80)

print(
    f"Median max DD:        "
    f"{percentile(drawdown_values, 0.50):.2f} R"
)

print(
    f"95th percentile DD:   "
    f"{percentile(drawdown_values, 0.95):.2f} R"
)

print(
    f"99th percentile DD:   "
    f"{percentile(drawdown_values, 0.99):.2f} R"
)

print(
    f"Worst simulated DD:   "
    f"{max(drawdown_values):.2f} R"
)


# =============================================================================
# 1% RISK INTERPRETATION
# =============================================================================

median_return = percentile(
    ending_return_values,
    0.50
)

p05_return = percentile(
    ending_return_values,
    0.05
)

p95_return = percentile(
    ending_return_values,
    0.95
)

p95_dd = percentile(
    drawdown_values,
    0.95
)

p99_dd = percentile(
    drawdown_values,
    0.99
)

print()
print("=" * 80)
print("1% RISK INTERPRETATION")
print("=" * 80)

print(
    f"Median ending return: "
    f"{median_return:.2f}%"
)

print(
    f"5th percentile return: "
    f"{p05_return:.2f}%"
)

print(
    f"95th percentile return: "
    f"{p95_return:.2f}%"
)

print(
    f"95th percentile max DD: "
    f"{p95_dd:.2f}%"
)

print(
    f"99th percentile max DD: "
    f"{p99_dd:.2f}%"
)


# =============================================================================
# 12-MONTH SUMMARY
# =============================================================================

median_wins = percentile(
    win_counts,
    0.50
)

median_losses = percentile(
    loss_counts,
    0.50
)

median_win_rate = percentile(
    win_rates,
    0.50
)

median_loss_rate = percentile(
    loss_rates,
    0.50
)

median_pf = percentile(
    profit_factors,
    0.50
)

median_expectancy = percentile(
    expectancies,
    0.50
)

print()
print("#" * 80)
print("12-MONTH TYPICAL SIMULATION")
print("#" * 80)

print()
print(f"Expected trades:       {expected_trades}")
print(f"Median wins:           {median_wins:.0f}")
print(f"Median losses:         {median_losses:.0f}")
print(f"Median win rate:       {median_win_rate:.2f}%")
print(f"Median loss rate:      {median_loss_rate:.2f}%")
print(f"Median profit factor:  {median_pf:.3f}")
print(f"Median expectancy:     {median_expectancy:.4f} R")
print(f"Median net R:          {percentile(ending_r_values, 0.50):.2f} R")
print(f"Median return:         {median_return:.2f}%")
print(f"Median max DD:         {percentile(drawdown_values, 0.50):.2f} R")


# =============================================================================
# 5TH PERCENTILE YEAR
# =============================================================================

print()
print("#" * 80)
print("5TH PERCENTILE YEAR")
print("#" * 80)

print()
print(f"Wins:                  {percentile(win_counts, 0.05):.0f}")
print(f"Losses:                {percentile(loss_counts, 0.05):.0f}")
print(f"Win rate:              {percentile(win_rates, 0.05):.2f}%")
print(f"Profit factor:         {percentile(profit_factors, 0.05):.3f}")
print(f"Net R:                 {percentile(ending_r_values, 0.05):.2f} R")
print(f"Return:                {percentile(ending_return_values, 0.05):.2f}%")
print(f"Max DD:                {percentile(drawdown_values, 0.95):.2f} R")


# =============================================================================
# 95TH PERCENTILE YEAR
# =============================================================================

print()
print("#" * 80)
print("95TH PERCENTILE YEAR")
print("#" * 80)

print()
print(f"Wins:                  {percentile(win_counts, 0.95):.0f}")
print(f"Losses:                {percentile(loss_counts, 0.95):.0f}")
print(f"Win rate:              {percentile(win_rates, 0.95):.2f}%")
print(f"Profit factor:         {percentile(profit_factors, 0.95):.3f}")
print(f"Net R:                 {percentile(ending_r_values, 0.95):.2f} R")
print(f"Return:                {percentile(ending_return_values, 0.95):.2f}%")
print(f"Max DD:                {percentile(drawdown_values, 0.95):.2f} R")


# =============================================================================
# SAVE RESULTS
# =============================================================================

print()
print("Generating simulation results file...")

results_df = pd.DataFrame(simulation_rows)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

results_df.to_csv(
    OUTPUT_FILE,
    index=False
)

print()
print("Results saved to:")
print(OUTPUT_FILE.resolve())

print()
print("#" * 80)
print("MONTE CARLO TEST COMPLETE")
print("#" * 80)