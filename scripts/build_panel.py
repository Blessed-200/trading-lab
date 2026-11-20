#!/usr/bin/env python3
"""Build the 5m panel for one unzipped shard and split it into dev / vault_a / vault_b.

usage: build_panel.py <data_dir> <out_dir> <shard>
Writes <out_dir>/{dev,vault_a,vault_b}-s48-<shard>.parquet plus a JSON sidecar
with row counts, time range and sha256 (used to prove vaults were never altered).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.panel import load_symbol  # noqa: E402
from src.lab.splits import PARTS, part_of  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(data: Path, out: Path, shard: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    symbols = sorted(p.name for p in (data / "binance" / "klines").iterdir() if p.is_dir())
    frames = [f for s in symbols if (f := load_symbol(data, s)) is not None]
    panel = pd.concat(frames, ignore_index=True)
    panel["symbol"] = panel["symbol"].astype("category")
    panel["part"] = part_of(panel["available_at"]).to_numpy()
    side = {"shard": shard, "symbols": len(symbols), "parts": {}}
    for part in PARTS:
        sub = panel[panel["part"] == part].drop(columns="part").sort_values(["symbol", "open_time"])
        path = out / f"{part}-s48-{shard}.parquet"
        sub.to_parquet(path, compression="zstd", index=False)
        side["parts"][part] = {
            "rows": int(len(sub)), "file": path.name, "sha256": sha256(path),
            "first": str(sub["available_at"].min()) if len(sub) else None,
            "last": str(sub["available_at"].max()) if len(sub) else None}
    (out / f"sidecar-s48-{shard}.json").write_text(json.dumps(side, indent=2))
    print(json.dumps(side, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
