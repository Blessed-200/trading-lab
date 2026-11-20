#!/usr/bin/env python3
"""Audit on-disk Binance coverage for whatever is present in <root>.

Reports facts only (rows, invalid candles, minute gaps); it makes no claim about
predictive quality. Minute gaps can be legitimate (exchange maintenance).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd


def audit(root: Path) -> dict:
    records = []
    base = root / "binance" / "klines"
    for sym_dir in sorted(p for p in base.glob("*") if p.is_dir()):
        paths = sorted(sym_dir.glob("*.parquet"))
        rows, invalid, gaps = 0, 0, 0
        previous = None
        for path in paths:
            df = pd.read_parquet(path, columns=["open_time", "available_at", "high", "low"])
            rows += len(df)
            invalid += int((df["available_at"] <= df["open_time"]).sum())
            invalid += int((df["high"] < df["low"]).sum())
            if len(df):
                if previous is not None:
                    gaps += int((df["open_time"].iloc[0] - previous) != pd.Timedelta(minutes=1))
                gaps += int((df["open_time"].diff().dropna() != pd.Timedelta(minutes=1)).sum())
                previous = df["open_time"].iloc[-1]
        records.append({"symbol": sym_dir.name, "days": len(paths), "rows": rows,
                        "invalid": invalid, "minute_gaps": gaps})
    report = {"created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
              "symbols": len(records),
              "total_kline_rows": sum(x["rows"] for x in records),
              "invalid_rows": sum(x["invalid"] for x in records),
              "per_symbol": records}
    (root / "audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "per_symbol"}, indent=2))
    if report["invalid_rows"]:
        raise SystemExit("Audit failed: invalid candles found")
    return report


if __name__ == "__main__":
    audit(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
