# Project audit — key corrections

## High-priority issues found

1. **`quant/top100_test.py` ignores the RR stored in the candidate file.**
   The candidate file contains an `rr` column, but the script calls `backtest_strategy()` without passing it, so the backtester defaults to RR=2.0. This can materially change results.

2. **The main backtester permits overlapping positions.**
   `quant/backtester.py` evaluates every matching signal independently. There is no “one position at a time” guard. If signals occur while a previous trade is still open, both can be counted. That can inflate trade count and portfolio results.

3. **The new-combination search and the validator use different entry conventions.**
   `quant/new_search/new_combination_search.py` enters at the signal candle close, while `quant/backtester.py` enters at the next candle open. Results from the two systems are therefore not directly comparable.

4. **Several searches reward tiny samples.**
   `quant/strategy_search.py` uses `MIN_TRADES = 5`, while the ranking includes profit factor/expectancy. A strategy with 5 wins can dominate the ranking (`PF=999`) despite being statistically weak. Use a much larger minimum sample for serious shortlisting.

5. **The supplied “top 100” contains many duplicate strategies.**
   `quant/new_search/new_combination_top100.csv` has 100 rows but only 27 unique `(direction, session, conditions)` combinations. The duplicates are mostly the same rule set appearing with different condition counts/redundant conditions.

6. **Hard-coded dates are stale/future relative to the supplied data.**
   Several scripts use end dates after the latest candle. The supplied data ends 2026-08-07.

7. **One script contains a machine-specific Windows path.**
   `quant/walk_forward_validation.py` uses `D:\Trading\quant`, which will break when the project is moved to another machine.

8. **Duplicate/backup clutter existed.**
   There were 87 compiled `__pycache__` files plus duplicate feature databases and several backup source files. The clean copy removes these from the active tree and places empty sources in `archive/empty_sources/`.

## Research-quality recommendation

Use the supplied strategy search only as a **candidate generator**. Then re-run the candidates through one canonical backtester with:

- next-bar entry
- one-position-at-a-time
- explicit RR
- explicit spread/slippage/commission
- minimum trade count
- yearly breakdown
- maximum drawdown
- profit factor
- expectancy
- bootstrap/Monte Carlo
- a genuinely untouched out-of-sample period

Do not treat a high historical score alone as evidence that a strategy is ready for live trading.
