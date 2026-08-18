# Trading Research Project — Cleaned

## What is here

- `data/` — raw market data. `GBPUSD_15_FULL.csv` is the main 2020–2026 dataset.
- `quant/` — feature engineering, strategy search, backtesting and validation code.
- `analysis/` — technical-analysis feature modules.
- `core/` — trading/decision/risk infrastructure.
- `research/` — research/live-monitoring experiments.
- `testing/` — unit/integration tests.
- `strategies/` — not a separate folder yet; candidate strategy files remain in `quant/new_search/` and `quant/*.csv` to preserve existing imports.
- `scripts/` — new repeatable audit/validation scripts.
- `results/` — results produced by the new validation pass.
- `archive/` — old/empty/backup files removed from the active tree.

## Recommended workflow

1. Build/update the feature database.
2. Generate a candidate pool.
3. Run `scripts/validate_top100_2025_current.py`.
4. Inspect `results/top100_2025_current_summary.csv`.
5. Treat 2025–current results as research evidence, not proof of future profitability.
6. Before live use, run a genuinely untouched out-of-sample period and include spread/slippage/commission assumptions.

## Important data note

The supplied feature database ends on 2026-08-07, so “current” in this project means the latest available candle, not 2026-08-12.


## Recommended command sequence

From `C:\Trading` after extracting this ZIP:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\discover_strategies.ps1
.\scripts\promote_top100.ps1
.\scripts\run_top100.ps1
```

Discovery is the broad/cheap stage. It uses the persistent registry so previously discovered condition combinations are skipped. Promotion selects the best newly discovered candidates. The Top-100 stage is the expensive 1.0R-to-7.0R detailed lab.

For a first small discovery test, use `-MaxNew 100 -MaxConditions 3`. For a broad run, the default is up to 5,000 newly discovered candidates with combinations up to 4 conditions.
