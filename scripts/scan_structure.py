#!/usr/bin/env python3
"""Open exploration on TRAIN: gross forward return by quantile bin of each feature.

usage: scan_structure.py <dev_panel_dir> <out.csv> [--rate 0.03]
Looks only for where |gross edge| could exceed round-trip costs (11 bps). Every feature
x horizon looked at is counted as a trial (printed at the end).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.data import dev_files, load_dev  # noqa: E402
from src.lab.features import add_features, forward_paths  # noqa: E402

FEATURES = ["ret_z", "vol_z", "imbalance", "imb_ma3", "oi_chg15", "ret_1h_z", "ret_4h_z",
            "range_z", "close_pos", "hour_utc", "btc_ret_z"]
HORIZONS = (6, 12, 48)


def sample_file(df: pd.DataFrame, rate: float, rng: np.random.Generator) -> pd.DataFrame:
    parts = []
    for _, g in df.groupby("symbol", sort=False):
        d = add_features(g)
        sig = d["sigma"]
        d["ret_1h_z"] = (d["close"] / d["close"].shift(12) - 1) / (sig * np.sqrt(12))
        d["ret_4h_z"] = (d["close"] / d["close"].shift(48) - 1) / (sig * np.sqrt(48))
        d["range_z"] = (d["high"] / d["low"] - 1) / sig
        rng_ = (d["high"] - d["low"]).replace(0, np.nan)
        d["close_pos"] = (d["close"] - d["low"]) / rng_
        d["hour_utc"] = d["available_at"].dt.hour.astype(float)
        ok = (d["adv24"] >= 5e6) & d["contig"] & sig.notna()
        pick = ok & (rng.random(len(d)) < rate)
        if not pick.any():
            continue
        out = d.loc[pick, ["symbol", "available_at"] + [f for f in FEATURES if f in d.columns]].copy()
        for h in HORIZONS:
            out[f"fwd_{h}"] = forward_paths(d, h).loc[pick, "fwd"].to_numpy()
        parts.append(out)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("panel_dir", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--rate", type=float, default=0.03)
    a = p.parse_args()
    rng = np.random.default_rng(11)
    files = dev_files(a.panel_dir)
    # BTC context (needed for btc_ret_z) comes from the shard that holds BTCUSDT
    btc = None
    for f in files:
        df = load_dev(f, "train")
        if (df["symbol"] == "BTCUSDT").any():
            b = add_features(df[df["symbol"] == "BTCUSDT"])
            btc = b.set_index("available_at")["ret_z"].rename("btc_ret_z")
            break
    chunks = []
    for i, f in enumerate(files):
        s = sample_file(load_dev(f, "train"), a.rate, rng)
        if len(s):
            s = s.merge(btc, left_on="available_at", right_index=True, how="left")
            chunks.append(s)
        print(f"[{i + 1}/{len(files)}] sampled {len(s):,}", flush=True)
    data = pd.concat(chunks, ignore_index=True)
    data.to_parquet(a.out.with_suffix('.sample.parquet'), index=False)
    rows = []
    for feat in FEATURES:
        col = data[feat] if feat != "btc_ret_z" else data["btc_ret_z"]
        if feat == "hour_utc":
            bins = col
        else:
            bins = pd.qcut(col.rank(method="first"), 20, labels=False, duplicates="drop")
        for h in HORIZONS:
            g = data.groupby(bins)[f"fwd_{h}"].agg(["mean", "count", "std"])
            for b, r in g.iterrows():
                rows.append({"feature": feat, "H": h, "bin": b, "n": int(r["count"]),
                             "gross_bps": r["mean"] * 1e4,
                             "t": r["mean"] / (r["std"] / np.sqrt(r["count"])) if r["std"] > 0 else np.nan})
    res = pd.DataFrame(rows)
    res.to_csv(a.out, index=False)
    trials = len(FEATURES) * len(HORIZONS)
    print(f"\nrows={len(data):,} trials(feature x horizon)={trials}")
    big = res[(res["gross_bps"].abs() > 11) & (res["t"].abs() > 4) & (res["n"] > 2000)]
    print("bins con |bruto|>11 bps y |t|>4 (n>2000):", len(big))
    print(big.sort_values("gross_bps", key=abs, ascending=False).head(15).round(2).to_string(index=False))
    print("\nmayor |bruto| por feature (cualquier t):")
    for feat in FEATURES:
        r = res[res.feature == feat].copy()
        r["abs"] = r["gross_bps"].abs()
        t = r.sort_values("abs", ascending=False).iloc[0]
        print(f"  {feat:10s} H={int(t.H):>2} bin={int(t.bin):>2} gross={t.gross_bps:7.1f} bps t={t.t:6.1f} n={int(t.n)}")


if __name__ == "__main__":
    main()
