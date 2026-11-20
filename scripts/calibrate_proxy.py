#!/usr/bin/env python3
"""Calibrate Binance candle-close proxy to matching Hyperliquid candle closes.

Candle close differences are NOT executable bid-ask spreads.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd


def calibrate(root: Path) -> dict:
    rows = json.loads((root / "universe.json").read_text())["symbols"]
    universe = [{"coin": r["hl_coin"], "symbol": r["symbol"]} for r in rows if r["hl_coin"]]
    results = []
    for row in universe:
        coin, symbol = row["coin"], row["symbol"]
        native_path = root / "hyperliquid" / "candles" / "1m" / f"{coin}.parquet"
        if not native_path.exists():
            results.append({"coin": coin, "status": "no_hl_1m_candles"})
            continue
        hl = pd.read_parquet(native_path, columns=["open_time", "c"])
        paths = sorted((root / "binance" / "klines" / symbol).glob("*.parquet"))
        if not paths:
            results.append({"coin": coin, "status": "no_binance_candles"})
            continue
        earliest = hl["open_time"].min()
        latest = hl["open_time"].max()
        b = []
        for path in paths:
            # Files are daily and cheap to filter. Do not extrapolate missing candles.
            d = pd.read_parquet(path, columns=["open_time", "close"])
            d = d[(d["open_time"] >= earliest) & (d["open_time"] <= latest)]
            if not d.empty:
                b.append(d)
        if not b:
            results.append({"coin": coin, "status": "no_overlap"})
            continue
        common = hl.merge(pd.concat(b, ignore_index=True), on="open_time",
                          how="inner", validate="one_to_one")
        if len(common) < 100:
            results.append({"coin": coin, "status": "insufficient_overlap", "n": len(common)})
            continue
        basis = (common["c"] / common["close"] - 1) * 10000
        returns_h = common["c"].pct_change()
        returns_b = common["close"].pct_change()
        results.append({"coin": coin, "status": "ok", "n": len(common),
                        "median_signed_close_basis_bps": float(basis.median()),
                        "p95_abs_close_basis_bps": float(basis.abs().quantile(.95)),
                        "return_1m_correlation": float(returns_h.corr(returns_b))})
    report = {"warning": "Close-price basis is NOT executable bid/ask spread",
              "results": results}
    (root / "proxy_calibration.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    calibrate(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
