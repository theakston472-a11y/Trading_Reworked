"""Build one versioned feature database without replacing an existing file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant.feature_engine import FEATURE_ENGINE_VERSION, build_features
from quant.smc_guide_features import SMC_GUIDE_FEATURE_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fresh project feature database.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    target = args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"Refusing to replace existing feature database: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    frame = build_features(str(source))
    frame.to_csv(target, index=False)
    elapsed = time.perf_counter() - started
    metadata = {
        "symbol": args.symbol.upper(),
        "input": str(source),
        "output": str(target),
        "feature_engine_version": FEATURE_ENGINE_VERSION,
        "smc_guide_feature_version": SMC_GUIDE_FEATURE_VERSION,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "first_timestamp": str(frame["timestamp"].iloc[0]),
        "last_timestamp": str(frame["timestamp"].iloc[-1]),
        "seconds": elapsed,
    }
    metadata_path = target.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
