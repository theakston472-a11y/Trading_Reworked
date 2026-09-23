"""Small VPS bootstrap for the multi-symbol historical-data downloader."""

from pathlib import Path
from urllib.request import urlopen
import runpy


URL = (
    "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/"
    "pairdata/scripts/download_research_symbols_mt5.py"
)
TARGET = Path(__file__).resolve().parent / "scripts" / "download_research_symbols_mt5.py"


TARGET.parent.mkdir(parents=True, exist_ok=True)
payload = urlopen(URL, timeout=60).read()
if len(payload) < 1_000 or b"DOWNLOAD COMPLETE" not in payload:
    raise RuntimeError("The downloaded history tool failed its content check.")
TARGET.write_bytes(payload)
runpy.run_path(str(TARGET), run_name="__main__")
