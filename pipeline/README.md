# Strategy Research Pipeline

This is a non-destructive orchestration layer for the existing Trading_Reworked system.

## Workflow

1. Discovery
2. Quick quality screen
3. Top-100 promotion for London Buy/Sell and New York Buy/Sell
4. RR deep search using the existing `scripts/strategy_lab.py`
5. Robust winner selection
6. Visual trade validation
7. Human-readable strategy reports
8. Paper-trading candidates
9. Paper bot preparation

The pipeline does not delete or overwrite the existing research databases.

## Main command

From the project root:

```powershell
python -m pipeline
```

Optional:

```powershell
python -m pipeline --skip-discovery
python -m pipeline --skip-deep
python -m pipeline --skip-visual
python -m pipeline --pool london_sell
```

## Important

The existing `scripts/strategy_lab.py` is treated as the deep-search engine. The pipeline supplies each pool its own output and cache directory so the four searches can be run safely in separate PowerShell windows too.

Charts are interactive HTML files. Open them in Edge/Chrome. They use Plotly candlesticks and annotate entry, stop, target, indicators and detected feature conditions.

Before paper trading, winners remain `PAPER_PENDING`. No live-trading code is activated by this pipeline.
