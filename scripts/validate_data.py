#!/usr/bin/env python3
"""Audit on-disk coverage. Intentionally does not claim predictive quality."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd


def audit(root: Path) -> dict:
    universe = json.loads((root / "universe.json").read_text())["selected"]
    manifest = json.loads((root / "manifest.json").read_text())
    records = []
    for item in universe:
        symbol = item["symbol"]
        paths = sorted((root / "binance" / "klines" / symbol).glob("*.parquet"))
        rows, invalid, gaps = 0, 0, 0
        previous = None
        for path in paths:
            df = pd.read_parquet(path, columns=["open_time", "available_at", "high", "low"])
            rows += len(df)
            invalid += int((df["available_at"] <= df["open_time"]).sum())
            invalid += int((df["high"] < df["low"]).sum())
            if previous is not None and len(df):
                gaps += int((df["open_time"].iloc[0] - previous) != pd.Timedelta(minutes=1))
            if len(df):
                gaps += int((df["open_time"].diff().dropna() != pd.Timedelta(minutes=1)).sum())
                previous = df["open_time"].iloc[-1]
        records.append({"symbol": symbol, "days": len(paths), "rows": rows,
                        "invalid": invalid, "discontinuities": gaps})
    report = {"created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
              "expected_daily_files": manifest["archive_expected_files"],
              "archive_success": manifest["archives_success"],
              "per_symbol": records,
              "total_kline_rows": sum(x["rows"] for x in records),
              "invalid_rows": sum(x["invalid"] for x in records)}
    (root / "audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["total_kline_rows"] == 0 or report["invalid_rows"]:
        raise SystemExit("Audit failed")


if __name__ == "__main__":
    audit(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
