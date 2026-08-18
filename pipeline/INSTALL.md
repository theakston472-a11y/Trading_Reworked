# Install / merge into Trading_Reworked

This upgrade is designed to be copied into the existing project without deleting its files.

1. Copy the `pipeline` folder into the project root.
2. Copy the three PowerShell scripts into `scripts`.
3. Do NOT delete the existing `quant`, `results`, `scripts/strategy_lab.py`, databases or caches.
4. Install Plotly if needed:

```powershell
python -m pip install -r .\pipeline\requirements.txt
```

Then from the project root:

```powershell
.\scripts\run_research_pipeline.ps1
```

For a single pool:

```powershell
.\scripts\run_research_pipeline.ps1 -SkipDiscovery -Pool london_sell
```

After winners exist:

```powershell
.\scripts\make_paper_candidates.ps1
```

Open:

```text
results\winners\<pool>\strategy_001\report.html
```

The chart files in `charts` are interactive HTML charts.

## If your current discovery script writes somewhere else

Use:

```powershell
python -m pipeline --discovery-file ".\path\to\your\discovery.csv"
```
