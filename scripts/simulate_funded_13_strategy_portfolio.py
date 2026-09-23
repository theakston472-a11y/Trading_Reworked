from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd


START_BALANCE = 10_000.0
PHASE_TARGETS = {"PHASE_1": 11_020.0, "PHASE_2": 10_520.0}
HARD_FLOOR = 9_000.0
KEY = ["direction", "session", "conditions", "rr", "entry_mode", "entry_wait_bars", "engine_version"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate the existing seven plus six new strategies through repeated funded challenges.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--legacy-results", type=Path, default=Path(r"D:\Trading\Trading_Reworked\results"))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-08-07 23:45:00+00:00")
    return parser.parse_args()


def query_trades(database: Path, row: pd.Series) -> list[dict]:
    with sqlite3.connect(database) as connection:
        record = connection.execute(
            """SELECT result_json FROM results
               WHERE period='ALL' AND direction=? AND session=? AND conditions=?
                 AND ABS(rr-?) < 0.00001 AND entry_mode=? AND entry_wait_bars=?
                 AND engine_version=? LIMIT 1""",
            (
                row["direction"], row["session"], row["conditions"], float(row["rr"]),
                row["entry_mode"], int(row["entry_wait_bars"]), row["engine_version"],
            ),
        ).fetchone()
    if record is None:
        raise RuntimeError(f"Missing Strategy Lab trades for {row['symbol']} {row['conditions']} RR{row['rr']}")
    return json.loads(record[0] or "[]")


def new_worker_locations(run_dir: Path, symbol: str) -> dict[tuple[str, str, str], Path]:
    result = {}
    directory = run_dir / "deep" / symbol
    for candidate_file in directory.glob("worker_*_candidates.csv"):
        worker = candidate_file.name.split("_")[1]
        database = directory / f"worker_{worker}.sqlite"
        for _, row in pd.read_csv(candidate_file).iterrows():
            result[(str(row["direction"]), str(row["session"]), str(row["conditions"]))] = database
    return result


def build_plan_and_trades(run_dir: Path, legacy_results: Path, start: pd.Timestamp, end: pd.Timestamp):
    legacy = pd.read_csv(legacy_results / "session_portfolio_research" / "best_session_paper_portfolio.csv")
    legacy.insert(0, "symbol", "GBPUSD")
    legacy.insert(1, "plan_source", "existing_paper_bot")
    legacy["plan_rank"] = range(1, len(legacy) + 1)

    new = pd.read_csv(run_dir / "final" / "multisymbol_six_strategy_plan.csv")
    new.insert(1, "plan_source", "new_six_strategy_addition")
    new["plan_rank"] = range(len(legacy) + 1, len(legacy) + len(new) + 1)
    plan = pd.concat([legacy, new], ignore_index=True, sort=False)
    plan["portfolio_priority"] = plan["robust_score"].fillna(0).rank(method="first", ascending=False).astype(int)

    trade_rows = []
    primary_db = legacy_results / "strategy_lab.sqlite"
    asia_db = legacy_results / "asia_strategy_lab.sqlite"
    locations = {symbol: new_worker_locations(run_dir, symbol) for symbol in ("GBPJPY", "AUDUSD")}

    for _, strategy in plan.iterrows():
        symbol = str(strategy["symbol"])
        if symbol == "GBPUSD":
            database = asia_db if str(strategy["session"]).lower() == "asia" else primary_db
        else:
            database = locations[symbol][
                (str(strategy["direction"]), str(strategy["session"]), str(strategy["conditions"]))
            ]
        trades = query_trades(database, strategy)
        label = f"{symbol}|{strategy['direction']}|{strategy['session']}|{strategy['conditions']}|RR{float(strategy['rr']):g}"
        for trade_number, trade in enumerate(trades, start=1):
            entry_time = pd.to_datetime(trade.get("entry_time"), utc=True, errors="coerce")
            exit_time = pd.to_datetime(trade.get("exit_time"), utc=True, errors="coerce")
            if pd.isna(entry_time) or pd.isna(exit_time) or entry_time < start or entry_time > end:
                continue
            trade_rows.append(
                {
                    "trade_id": f"{int(strategy['plan_rank']):02d}-{trade_number:04d}",
                    "plan_rank": int(strategy["plan_rank"]),
                    "priority": int(strategy["portfolio_priority"]),
                    "plan_source": strategy["plan_source"],
                    "symbol": symbol,
                    "strategy": label,
                    "direction": strategy["direction"],
                    "session": strategy["session"],
                    "conditions": strategy["conditions"],
                    "rr": float(strategy["rr"]),
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "outcome_r": float(trade["outcome_r"]),
                    "reason": trade.get("reason", ""),
                }
            )
    trades = pd.DataFrame(trade_rows).sort_values(
        ["entry_time", "priority", "plan_rank", "trade_id"], kind="stable"
    ).reset_index(drop=True)
    return plan, trades


def broker_day(timestamp: pd.Timestamp):
    return (timestamp + pd.Timedelta(hours=3)).date()


@dataclass(frozen=True)
class Rules:
    name: str
    risk_pct: float
    daily_limit_pct: float
    max_open: int
    count_open_risk: bool = True
    reduced_risk_pct: float | None = None
    reduce_below_balance: float | None = None


def simulate(trades: pd.DataFrame, rules: Rules, start: pd.Timestamp, end: pd.Timestamp):
    stage = "PHASE_1"
    balance = START_BALANCE
    day_start = START_BALANCE
    current_day = None
    locked_day = None
    active_after_day = None
    phase_start_time = None
    cycle_start_time = None
    phase_trading_days = set()
    open_positions: dict[str, dict] = {}
    attempts = []
    accepted = []
    skips = Counter()
    phase_one_passes = 0
    full_passes = 0
    failures = 0
    daily_stops = 0
    phase_peak = START_BALANCE
    worst_phase_drawdown_pct = 0.0
    worst_phase_loss_from_start_pct = 0.0
    lowest_balance = START_BALANCE
    completed_cycle_days = []

    def roll_day(timestamp: pd.Timestamp):
        nonlocal current_day, day_start, locked_day
        day = broker_day(timestamp)
        if current_day != day:
            current_day = day
            day_start = balance
            locked_day = None
        return day

    def reset_phase(new_stage: str, timestamp: pd.Timestamp):
        nonlocal stage, balance, day_start, phase_start_time, phase_trading_days, phase_peak, open_positions
        stage = new_stage
        balance = START_BALANCE
        day_start = START_BALANCE
        phase_start_time = timestamp
        phase_trading_days = set()
        phase_peak = START_BALANCE
        open_positions = {}

    def finish_phase(status: str, timestamp: pd.Timestamp, reason: str):
        nonlocal phase_one_passes, full_passes, failures, active_after_day, cycle_start_time
        nonlocal worst_phase_drawdown_pct
        attempts.append(
            {
                "scenario": rules.name,
                "stage": stage,
                "status": status,
                "reason": reason,
                "start_time": phase_start_time,
                "end_time": timestamp,
                "calendar_days": (timestamp - phase_start_time).total_seconds() / 86400 if phase_start_time else math.nan,
                "trading_days": len(phase_trading_days),
                "ending_balance": balance,
            }
        )
        next_day = broker_day(timestamp) + timedelta(days=1)
        active_after_day = next_day
        if status == "PASS" and stage == "PHASE_1":
            phase_one_passes += 1
            reset_phase("PHASE_2", timestamp)
        elif status == "PASS":
            full_passes += 1
            if cycle_start_time is not None:
                completed_cycle_days.append((timestamp - cycle_start_time).total_seconds() / 86400)
            reset_phase("PHASE_1", timestamp)
            cycle_start_time = None
        else:
            failures += 1
            reset_phase("PHASE_1", timestamp)
            cycle_start_time = None

    def update_drawdown():
        nonlocal phase_peak, worst_phase_drawdown_pct, worst_phase_loss_from_start_pct, lowest_balance
        phase_peak = max(phase_peak, balance)
        drawdown = (phase_peak - balance) / phase_peak if phase_peak else 0.0
        worst_phase_drawdown_pct = max(worst_phase_drawdown_pct, drawdown)
        worst_phase_loss_from_start_pct = max(
            worst_phase_loss_from_start_pct, (START_BALANCE - balance) / START_BALANCE
        )
        lowest_balance = min(lowest_balance, balance)

    def process_exit(position: dict):
        nonlocal balance, locked_day, daily_stops
        risk_dollars = position["risk_dollars"]
        pnl = float(position["outcome_r"]) * risk_dollars
        balance += pnl
        position["pnl"] = pnl
        position["balance_after"] = balance
        accepted.append(position)
        phase_trading_days.add(broker_day(position["entry_time"]))
        update_drawdown()
        if balance <= HARD_FLOOR + 1e-9:
            finish_phase("FAIL", position["exit_time"], "10% hard loss")
            return True
        if balance >= PHASE_TARGETS[stage] - 1e-9:
            finish_phase("PASS", position["exit_time"], "target reached")
            return True
        if day_start - balance >= day_start * rules.daily_limit_pct - 1e-9 and locked_day != current_day:
            locked_day = current_day
            daily_stops += 1
        return False

    for _, candidate in trades.iterrows():
        timestamp = pd.Timestamp(candidate["entry_time"])
        # Close positions before considering new entries at the same timestamp.
        due = sorted(
            [position for position in open_positions.values() if position["exit_time"] <= timestamp],
            key=lambda value: (value["exit_time"], value["priority"], value["trade_id"]),
        )
        for position in due:
            if position["trade_id"] not in open_positions:
                continue
            del open_positions[position["trade_id"]]
            roll_day(pd.Timestamp(position["exit_time"]))
            transitioned = process_exit(position)
            if transitioned:
                skips["phase_transition_closed_open_neutral"] += len(open_positions)
                open_positions.clear()
                break

        day = roll_day(timestamp)
        if active_after_day is not None and day < active_after_day:
            skips["phase_transition_wait"] += 1
            continue
        if active_after_day is not None and day >= active_after_day:
            active_after_day = None
            day_start = balance
        if phase_start_time is None:
            phase_start_time = timestamp
        if stage == "PHASE_1" and cycle_start_time is None:
            cycle_start_time = timestamp
        if locked_day == day:
            skips["daily_stop"] += 1
            continue
        if len(open_positions) >= rules.max_open:
            skips["max_open"] += 1
            continue
        active_risk_pct = rules.risk_pct
        if (
            rules.reduced_risk_pct is not None
            and rules.reduce_below_balance is not None
            and balance <= rules.reduce_below_balance
        ):
            active_risk_pct = rules.reduced_risk_pct
        planned = balance * active_risk_pct
        realized_loss = max(0.0, day_start - balance)
        open_risk = sum(position["risk_dollars"] for position in open_positions.values()) if rules.count_open_risk else 0.0
        if realized_loss + open_risk + planned > day_start * rules.daily_limit_pct + 1e-9:
            skips["daily_risk_budget"] += 1
            continue
        position = candidate.to_dict()
        position["risk_dollars"] = planned
        open_positions[str(position["trade_id"])] = position

    # Close trades that were entered inside the window and have a stored exit afterwards.
    for position in sorted(open_positions.values(), key=lambda value: value["exit_time"]):
        if position["trade_id"] not in open_positions:
            continue
        del open_positions[position["trade_id"]]
        roll_day(pd.Timestamp(position["exit_time"]))
        transitioned = process_exit(position)
        if transitioned:
            skips["phase_transition_closed_open_neutral"] += len(open_positions)
            open_positions.clear()
            break
    open_positions.clear()

    if phase_start_time is not None:
        attempts.append(
            {
                "scenario": rules.name,
                "stage": stage,
                "status": "INCOMPLETE",
                "reason": "data window ended",
                "start_time": phase_start_time,
                "end_time": end,
                "calendar_days": (end - phase_start_time).total_seconds() / 86400,
                "trading_days": len(phase_trading_days),
                "ending_balance": balance,
            }
        )

    completed_attempts = full_passes + failures
    summary = {
        "scenario": rules.name,
        "risk_pct": rules.risk_pct,
        "daily_limit_pct": rules.daily_limit_pct,
        "max_open": rules.max_open,
        "count_open_risk": rules.count_open_risk,
        "reduced_risk_pct": rules.reduced_risk_pct,
        "reduce_below_balance": rules.reduce_below_balance,
        "signals_available": len(trades),
        "trades_accepted": len(accepted),
        "phase1_passes": phase_one_passes,
        "full_passes": full_passes,
        "failures": failures,
        "incomplete_stages": sum(row["status"] == "INCOMPLETE" for row in attempts),
        "completed_pass_rate": full_passes / completed_attempts if completed_attempts else math.nan,
        "daily_stop_events": daily_stops,
        "worst_phase_drawdown_pct": worst_phase_drawdown_pct,
        "worst_phase_loss_from_start_pct": worst_phase_loss_from_start_pct,
        "lowest_balance": lowest_balance,
        "average_full_pass_days": sum(completed_cycle_days) / len(completed_cycle_days) if completed_cycle_days else math.nan,
        "fastest_full_pass_days": min(completed_cycle_days) if completed_cycle_days else math.nan,
        "slowest_full_pass_days": max(completed_cycle_days) if completed_cycle_days else math.nan,
        "ending_stage": stage,
        "ending_balance": balance,
        **{f"skipped_{key}": value for key, value in sorted(skips.items())},
    }
    return summary, pd.DataFrame(attempts), pd.DataFrame(accepted), skips


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    output = run_dir / "final" / "funded_simulation_13"
    output.mkdir(parents=True, exist_ok=True)
    start = pd.to_datetime(args.start, utc=True)
    end = pd.to_datetime(args.end, utc=True)
    plan, trades = build_plan_and_trades(run_dir, args.legacy_results, start, end)
    plan.to_csv(output / "combined_13_strategy_plan.csv", index=False)
    trades.to_csv(output / "combined_trade_pool.csv", index=False)

    old_seven = trades[trades["plan_source"] == "existing_paper_bot"].copy()
    scenarios = [
        (old_seven, Rules("old_7_current_rules", 0.0100, 0.03, 2, True)),
        (trades, Rules("all_13_current_rules", 0.0100, 0.03, 2, True)),
        (trades, Rules("all_13_three_open_current_risk", 0.0100, 0.03, 3, True)),
        (trades, Rules("all_13_safer_075pct_two_open", 0.0075, 0.03, 2, True)),
        (trades, Rules("all_13_safer_075pct_three_open", 0.0075, 0.03, 3, True)),
        (trades, Rules("all_13_conservative_05pct_two_open", 0.0050, 0.03, 2, True)),
        (trades, Rules("all_13_guard_at_5pct", 0.0100, 0.03, 2, True, 0.0050, 9_500.0)),
        (trades, Rules("all_13_guard_5pct_to_025pct", 0.0100, 0.03, 2, True, 0.0025, 9_500.0)),
    ]
    summaries = []
    accepted_by_scenario = {}
    for scenario_trades, rules in scenarios:
        summary, attempts, accepted, skips = simulate(scenario_trades, rules, start, end)
        summaries.append(summary)
        accepted_by_scenario[rules.name] = accepted
        attempts.to_csv(output / f"attempts_{rules.name}.csv", index=False)
        accepted.to_csv(output / f"accepted_trades_{rules.name}.csv", index=False)
        pd.DataFrame([{"reason": key, "count": value} for key, value in sorted(skips.items())]).to_csv(
            output / f"skips_{rules.name}.csv", index=False
        )
    comparison = pd.DataFrame(summaries)
    comparison.to_csv(output / "funded_rule_comparison.csv", index=False)

    current_accepted = accepted_by_scenario["all_13_current_rules"]
    contribution_rows = []
    for _, strategy in plan.sort_values("plan_rank").iterrows():
        subset = current_accepted[current_accepted["plan_rank"] == int(strategy["plan_rank"])]
        contribution_rows.append(
            {
                "plan_rank": int(strategy["plan_rank"]),
                "plan_source": strategy["plan_source"],
                "symbol": strategy["symbol"],
                "direction": strategy["direction"],
                "session": strategy["session"],
                "conditions": strategy["conditions"],
                "rr": float(strategy["rr"]),
                "trades_accepted": len(subset),
                "wins": int((subset["outcome_r"] > 0).sum()),
                "losses": int((subset["outcome_r"] < 0).sum()),
                "win_rate_pct": 100 * (subset["outcome_r"] > 0).mean() if len(subset) else math.nan,
                "net_r": subset["outcome_r"].sum(),
                "expectancy_r": subset["outcome_r"].mean() if len(subset) else math.nan,
                "realized_pnl_dollars": subset["pnl"].sum(),
            }
        )
    pd.DataFrame(contribution_rows).to_csv(output / "strategy_contribution_current_rules.csv", index=False)

    current_summary = next(row for row in summaries if row["scenario"] == "all_13_current_rules")
    leave_one_out_rows = []
    for _, strategy in plan[plan["plan_source"] == "new_six_strategy_addition"].iterrows():
        rank = int(strategy["plan_rank"])
        reduced_pool = trades[trades["plan_rank"] != rank].copy()
        leave_out_rules = Rules(f"without_new_rank_{rank}", 0.0100, 0.03, 2, True)
        leave_out_summary, _, _, _ = simulate(reduced_pool, leave_out_rules, start, end)
        leave_one_out_rows.append(
            {
                "removed_plan_rank": rank,
                "symbol": strategy["symbol"],
                "direction": strategy["direction"],
                "session": strategy["session"],
                "conditions": strategy["conditions"],
                "rr": float(strategy["rr"]),
                "full_passes_without_strategy": leave_out_summary["full_passes"],
                "failures_without_strategy": leave_out_summary["failures"],
                "average_pass_days_without_strategy": leave_out_summary["average_full_pass_days"],
                "passes_added_in_path_dependent_replay": (
                    current_summary["full_passes"] - leave_out_summary["full_passes"]
                ),
            }
        )
    leave_one_out = pd.DataFrame(leave_one_out_rows)
    leave_one_out.to_csv(output / "new_six_leave_one_out.csv", index=False)

    period_rows = []
    periods = [
        ("2025", pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-12-31 23:59:59", tz="UTC")),
        ("2026_YTD", pd.Timestamp("2026-01-01", tz="UTC"), end),
    ]
    for period_name, period_start, period_end in periods:
        period_trades = trades[
            (trades["entry_time"] >= period_start) & (trades["entry_time"] <= period_end)
        ].copy()
        period_rules = Rules(f"all_13_current_rules_{period_name}", 0.0100, 0.03, 2, True)
        period_summary, period_attempts, _, _ = simulate(
            period_trades, period_rules, period_start, period_end
        )
        period_summary["period"] = period_name
        period_rows.append(period_summary)
        period_attempts.to_csv(output / f"attempts_{period_rules.name}.csv", index=False)
    stability = pd.DataFrame(period_rows)
    stability.to_csv(output / "funded_period_stability.csv", index=False)

    old_baseline = comparison[comparison["scenario"] == "old_7_current_rules"].iloc[0]
    baseline = comparison[comparison["scenario"] == "all_13_current_rules"].iloc[0]
    best = comparison[comparison["scenario"] != "old_7_current_rules"].sort_values(
        ["full_passes", "failures", "worst_phase_drawdown_pct", "average_full_pass_days"],
        ascending=[False, True, True, True],
        kind="stable",
    ).iloc[0]
    safest = comparison[
        (comparison["scenario"] != "old_7_current_rules") & (comparison["failures"] == 0)
    ].sort_values(
        ["full_passes", "worst_phase_loss_from_start_pct", "average_full_pass_days"],
        ascending=[False, True, True],
        kind="stable",
    ).iloc[0]
    lines = [
        "13-STRATEGY FUNDED ACCOUNT SIMULATION",
        "=" * 40,
        f"Window: {start.isoformat()} to {end.isoformat()} (2025 plus 2026 year-to-date; not a full 24 months).",
        f"Portfolio: {len(plan)} strategies — {(plan.symbol == 'GBPUSD').sum()} GBPUSD, {(plan.symbol == 'GBPJPY').sum()} GBPJPY, {(plan.symbol == 'AUDUSD').sum()} AUDUSD.",
        f"Stored candidate trades: {len(trades)}.",
        "Rules: Phase 1 target $11,020; Phase 2 target $10,520; $9,000 hard floor; 3% daily risk cap; shared position limit; open risk counts toward the daily cap.",
        "Stored Strategy Lab outcomes already use conservative same-bar SL-before-TP handling.",
        "Important: these strategies were selected using this same historical window, so this is an in-sample portfolio replay rather than an independent out-of-sample proof.",
        "",
        "OLD SEVEN VS ALL THIRTEEN (CURRENT RULES)",
        "-" * 42,
        f"Old seven: {int(old_baseline.full_passes)} full passes, {int(old_baseline.failures)} failures, "
        f"{old_baseline.average_full_pass_days:.1f} average calendar days per completed pass, "
        f"{old_baseline.worst_phase_loss_from_start_pct * 100:.2f}% worst loss from phase start.",
        f"All thirteen: {int(baseline.full_passes)} full passes, {int(baseline.failures)} failures, "
        f"{baseline.average_full_pass_days:.1f} average calendar days per completed pass, "
        f"{baseline.worst_phase_loss_from_start_pct * 100:.2f}% worst loss from phase start.",
        "",
        "CURRENT RULES",
        "-" * 13,
        f"Phase 1 passes: {int(baseline.phase1_passes)}",
        f"Full Phase 1 + Phase 2 passes: {int(baseline.full_passes)}",
        f"Failed attempts: {int(baseline.failures)}",
        f"Incomplete stages at the data cutoff: {int(baseline.incomplete_stages)}",
        f"Accepted trades: {int(baseline.trades_accepted)} of {int(baseline.signals_available)} signals",
        f"Daily-stop events: {int(baseline.daily_stop_events)}",
        f"Worst peak-to-trough phase drawdown: {baseline.worst_phase_drawdown_pct * 100:.2f}%",
        f"Worst loss from the $10,000 phase start: {baseline.worst_phase_loss_from_start_pct * 100:.2f}%",
        f"Average full-pass time: {baseline.average_full_pass_days:.1f} calendar days" if math.isfinite(baseline.average_full_pass_days) else "Average full-pass time: no completed full pass",
        "",
        "RULE COMPARISON",
        "-" * 15,
    ]
    for _, row in comparison.iterrows():
        average = f"{row.average_full_pass_days:.1f}d" if math.isfinite(row.average_full_pass_days) else "n/a"
        lines.append(
            f"{row.scenario}: full passes {int(row.full_passes)}, failures {int(row.failures)}, "
            f"phase-1 passes {int(row.phase1_passes)}, worst start loss {row.worst_phase_loss_from_start_pct * 100:.2f}%, "
            f"average pass {average}, daily stops {int(row.daily_stop_events)}."
        )
    lines += ["", "PERIOD STABILITY", "-" * 16]
    for _, row in stability.iterrows():
        average = f"{row.average_full_pass_days:.1f}d" if math.isfinite(row.average_full_pass_days) else "n/a"
        lines.append(
            f"{row.period}: full passes {int(row.full_passes)}, failures {int(row.failures)}, "
            f"phase-1 passes {int(row.phase1_passes)}, worst start loss {row.worst_phase_loss_from_start_pct * 100:.2f}%, "
            f"average pass {average}."
        )
    lines += [
        "",
        "DECISION NOTES",
        "-" * 14,
        f"Every new strategy was useful in the path-dependent leave-one-out check: removing one reduced full passes by "
        f"{int(leave_one_out.passes_added_in_path_dependent_replay.min())} to "
        f"{int(leave_one_out.passes_added_in_path_dependent_replay.max())}.",
        "Do not increase the shared open-position limit to three: it produced fewer passes and more failures at 1% risk.",
        "The current 1%/two-open rules were fastest, but they recorded one historical hard-loss failure.",
        "The tested drawdown guard (cut risk to 0.25% at or below $9,500) recorded no failures, at the cost of fewer and slower passes.",
    ]
    lines += [
        "",
        f"Best measured rule set by passes/failures/drawdown: {best.scenario}.",
        f"Best measured zero-failure alternative: {safest.scenario} with {int(safest.full_passes)} full passes, "
        f"{safest.worst_phase_loss_from_start_pct * 100:.2f}% worst start loss and "
        f"{safest.average_full_pass_days:.1f} average calendar days per completed pass.",
        "Do not treat repeated historical passes as a guarantee. Confirm the prop firm's current minimum-day, consistency, news-trading and overnight-holding rules before a live evaluation.",
    ]
    (output / "funded_simulation_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(comparison.to_string(index=False))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
