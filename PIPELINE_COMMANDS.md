# Research Pipeline Commands

From `C:\Trading\Trading_Reworked`:

## Install chart dependency

```powershell
python -m pip install -r .\pipeline\requirements.txt
```

## Run the complete pipeline

```powershell
.\scripts\run_research_pipeline.ps1
```

## Run one pool after discovery/top100 already exists

```powershell
.\scripts\run_research_pipeline.ps1 -SkipDiscovery -Pool london_buy
.\scripts\run_research_pipeline.ps1 -SkipDiscovery -Pool london_sell
.\scripts\run_research_pipeline.ps1 -SkipDiscovery -Pool new_york_buy
.\scripts\run_research_pipeline.ps1 -SkipDiscovery -Pool new_york_sell
```

## Visual validation only

```powershell
.\scripts\run_visual_validation.ps1 -Pool london_sell
```

## Build paper-trading candidate list

```powershell
.\scripts\make_paper_candidates.ps1
```

## Outputs

```text
results\
├── discovery_screened.csv
├── top100\
│   ├── london_buy_top100.csv
│   ├── london_sell_top100.csv
│   ├── new_york_buy_top100.csv
│   └── new_york_sell_top100.csv
├── top100_tests\
│   └── <pool>\
│       ├── results.csv_final.csv
│       ├── results.csv_top_final.csv
│       ├── results.csv_periods.csv
│       └── cache.sqlite
└── winners\
    └── <pool>\
        └── strategy_001\
            ├── report.html
            └── charts\
                ├── winner_01.html
                └── loser_01.html
```

The existing research system remains in place. This layer orchestrates it and adds visual/reporting/paper-candidate stages.
