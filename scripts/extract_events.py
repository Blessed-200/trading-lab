#!/usr/bin/env python3
"""Extract candidate events (train only) for EXP-001 / EXP-002 with forward paths.

usage: extract_events.py <dev_panel_dir> <out_dir> [--until train|val]
The loosest superset of each registered grid is stored, so every variant can be
evaluated later by filtering, with no re-reading of the panel.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.data import dev_files, load_dev  # noqa: E402
from src.lab.features import add_features, forward_paths  # noqa: E402

HORIZONS = (3, 6, 12)
MIN_ADV24 = 5e6          # point-in-time: trailing 24h $ volume known at t
KEEP = ["symbol", "available_at", "ret_z", "vol_z", "imbalance", "imb_ma3", "oi_chg15",
        "adv24", "sigma", "quote_volume"]


def process(df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for sym, g in df.groupby("symbol", sort=False):
        d = add_features(g)
        liquid = (d["adv24"] >= MIN_ADV24) & d["contig"] & d["sigma"].notna()
        exp1 = (d["ret_z"].abs() >= 2) & (d["vol_z"] >= 2) & (d["imbalance"].abs() >= 0.3)
        exp2 = (d["imb_ma3"].abs() >= 0.2) & (d["oi_chg15"].abs() >= 0.005)
        sel = liquid & (exp1 | exp2)
        if not sel.any():
            continue
        ev = d.loc[sel, KEEP].copy()
        ev["exp1"] = exp1[sel].to_numpy()
        ev["exp2"] = exp2[sel].to_numpy()
        for h in HORIZONS:
            f = forward_paths(d, h).loc[sel]
            ev[f"fwd_{h}"] = f["fwd"].to_numpy()
            ev[f"mae_{h}"] = f["mae_long"].to_numpy()
            ev[f"mfe_{h}"] = f["mfe_long"].to_numpy()
        parts.append(ev)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("panel_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--until", default="train", choices=["train", "val"])
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    files = dev_files(a.panel_dir)
    for i, f in enumerate(files):
        df = load_dev(f, a.until)
        ev = process(df)
        chunks.append(ev)
        print(f"[{i + 1}/{len(files)}] {f.name}: bars={len(df):,} events={len(ev):,}", flush=True)
    events = pd.concat(chunks, ignore_index=True)
    out = a.out_dir / f"events_{a.until}.parquet"
    events.to_parquet(out, compression="zstd", index=False)
    print("saved", out, len(events), "events; exp1:", int(events["exp1"].sum()),
          "exp2:", int(events["exp2"].sum()))


if __name__ == "__main__":
    main()
