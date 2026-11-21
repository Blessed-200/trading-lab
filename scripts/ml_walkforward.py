#!/usr/bin/env python3
"""EXP-007: direct LightGBM walk-forward on TRAIN only.

usage: ml_walkforward.py <dev_panel_dir> <out_dir> [--rate 0.04]
Folds: train on the 12 months before each test quarter (2-day purge), test the quarter.
Test quarters: 2024Q3, 2024Q4, 2025Q1, 2025Q2 (all inside train; val and vaults untouched).
Target: forward return over H bars divided by sigma*sqrt(H), clipped at +-5.
Trading rule: take the top 1% / 5% of |prediction| inside the test fold, side = sign.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.backtest import Costs  # noqa: E402
from src.lab.data import dev_files, load_dev  # noqa: E402
from src.lab.features import add_features, forward_paths  # noqa: E402

HS = (6, 12, 48)
FOLDS = [("2024Q3", "2024-07-01", "2024-10-01"), ("2024Q4", "2024-10-01", "2025-01-01"),
         ("2025Q1", "2025-01-01", "2025-04-01"), ("2025Q2", "2025-04-01", "2025-07-01")]
FEATS = ["ret", "ret_cc", "ret_z", "ret_1h_z", "ret_4h_z", "ret_24h_z", "log_sigma", "vol_z", "qv_ratio",
         "imbalance", "imb_ma3", "imb_ma12", "oi_chg15", "oi_chg1h", "top_ls_l1", "range_z", "close_pos",
         "upper_wick", "lower_wick", "hour_sin", "hour_cos", "dow", "log_adv24", "btc_ret_z", "btc_1h_z",
         "rel_btc_1h"]
PARAMS = dict(objective="regression", n_estimators=300, learning_rate=0.05, num_leaves=31,
              min_child_samples=2000, colsample_bytree=0.8, subsample=0.7, subsample_freq=1,
              reg_lambda=10.0, n_jobs=2, verbose=-1, random_state=7)


def btc_context(panel_dir: Path) -> pd.DataFrame:
    for f in dev_files(panel_dir):
        df = load_dev(f, "train")
        b = df[df["symbol"] == "BTCUSDT"]
        if len(b):
            d = add_features(b)
            sig = d["sigma"]
            d["btc_1h_z"] = (d["close"] / d["close"].shift(12) - 1) / (sig * np.sqrt(12))
            return d.set_index("available_at")[["ret_z", "btc_1h_z"]].rename(columns={"ret_z": "btc_ret_z"})
    raise RuntimeError("BTCUSDT not found")


def featurize(g: pd.DataFrame) -> pd.DataFrame:
    d = add_features(g)
    sig = d["sigma"]
    c = d["close"].astype("float64")
    d["ret_1h_z"] = (c / c.shift(12) - 1) / (sig * np.sqrt(12))
    d["ret_4h_z"] = (c / c.shift(48) - 1) / (sig * np.sqrt(48))
    d["ret_24h_z"] = (c / c.shift(288) - 1) / (sig * np.sqrt(288))
    d["log_sigma"] = np.log10(sig.replace(0, np.nan))
    qv = d["quote_volume"].astype("float64")
    d["qv_ratio"] = qv / qv.shift(1).rolling(288, min_periods=144).mean()
    d["imb_ma12"] = d["imbalance"].rolling(12, min_periods=6).mean()
    oi_u = (d["oi_value"].astype("float64") / c).shift(1)           # same 1-bar lag as oi_chg15
    d["oi_chg1h"] = oi_u / oi_u.shift(12) - 1
    d["top_ls_l1"] = d["top_ls"].astype("float64").shift(1)
    rng = (d["high"] - d["low"]).astype("float64").replace(0, np.nan)
    d["range_z"] = (d["high"] / d["low"] - 1) / sig
    d["close_pos"] = (d["close"] - d["low"]) / rng
    d["upper_wick"] = (d["high"] - np.maximum(d["open"], d["close"])) / rng
    d["lower_wick"] = (np.minimum(d["open"], d["close"]) - d["low"]) / rng
    hr = d["available_at"].dt.hour + d["available_at"].dt.minute / 60
    d["hour_sin"], d["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    d["dow"] = d["available_at"].dt.dayofweek.astype(float)
    d["log_adv24"] = np.log10(d["adv24"].replace(0, np.nan))
    return d


def build_sample(panel_dir: Path, rate: float) -> pd.DataFrame:
    rng = np.random.default_rng(13)
    btc = btc_context(panel_dir)
    parts = []
    files = dev_files(panel_dir)
    for i, f in enumerate(files):
        df = load_dev(f, "train")
        for sym, g in df.groupby("symbol", sort=False):
            d = featurize(g)
            ok = (d["adv24"] >= 5e6) & d["contig"] & d["sigma"].notna()
            pick = ok & (rng.random(len(d)) < rate)
            if not pick.any():
                continue
            o = d.loc[pick, ["symbol", "available_at", "sigma"] + [c for c in FEATS if c in d.columns]].copy()
            for h in HS:
                o[f"fwd_{h}"] = forward_paths(d, h).loc[pick, "fwd"].to_numpy()
            parts.append(o)
        print(f"[{i + 1}/{len(files)}] files processed", flush=True)
    s = pd.concat(parts, ignore_index=True)
    s = s.merge(btc, left_on="available_at", right_index=True, how="left")
    s["rel_btc_1h"] = s["ret_1h_z"] - s["btc_1h_z"]
    for c in FEATS:
        s[c] = s[c].astype("float32")
    return s.dropna(subset=[f"fwd_{h}" for h in HS])


def boot_ci(net: pd.Series, day: pd.Series) -> float:
    g = net.groupby(day).agg(["sum", "count"])
    if len(g) < 5:
        return float("nan")
    rng = np.random.default_rng(7)
    idx = rng.integers(0, len(g), size=(1000, len(g)))
    return float(np.percentile(g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1), 2.5) * 1e4)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("panel_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--rate", type=float, default=0.04)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    cache = a.out_dir / "ml_sample.parquet"
    s = pd.read_parquet(cache) if cache.exists() else build_sample(a.panel_dir, a.rate)
    if not cache.exists():
        s.to_parquet(cache, index=False)
    print("muestra:", len(s), flush=True)
    cost = Costs().round_trip_bps() / 1e4
    rows, imps, picks = [], [], []
    for name, t0, t1 in FOLDS:
        t0, t1 = pd.Timestamp(t0, tz="UTC"), pd.Timestamp(t1, tz="UTC")
        tr = s[(s["available_at"] >= t0 - pd.DateOffset(months=12)) & (s["available_at"] < t0 - pd.Timedelta(days=2))]
        te = s[(s["available_at"] >= t0) & (s["available_at"] < t1)].copy()
        for h in HS:
            y = (tr[f"fwd_{h}"] / (tr["sigma"] * np.sqrt(h))).clip(-5, 5)
            m = lgb.LGBMRegressor(**PARAMS).fit(tr[FEATS], y)
            te["pred"] = m.predict(te[FEATS])
            real = te[f"fwd_{h}"]
            ic = spearmanr(te["pred"], real).correlation
            imps.append(pd.Series(m.booster_.feature_importance("gain"), index=FEATS, name=(name, h)))
            for q in (0.01, 0.05):
                thr = te["pred"].abs().quantile(1 - q)
                sel = te[te["pred"].abs() >= thr]
                side = np.sign(sel["pred"])
                gross = side * sel[f"fwd_{h}"]
                net = gross - cost
                if q == 0.01:
                    picks.append(pd.DataFrame({"fold": name, "H": h, "symbol": sel["symbol"].to_numpy(),
                                               "available_at": sel["available_at"].to_numpy(), "side": side.to_numpy(),
                                               "pred": sel["pred"].to_numpy(), "fwd": sel[f"fwd_{h}"].to_numpy()}))
                rows.append({"fold": name, "H": h, "top": q, "n_train": len(tr), "n": len(sel), "IC": ic,
                             "gross_bps": gross.mean() * 1e4, "net_bps": net.mean() * 1e4,
                             "ci95_lo_bps": boot_ci(net, sel["available_at"].dt.floor("D")),
                             "win": float((net > 0).mean())})
            print(f"{name} H={h} IC={ic:+.4f}", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(a.out_dir / "exp007_folds.csv", index=False)
    pd.concat(picks).to_parquet(a.out_dir / "exp007_selections.parquet", index=False)
    pd.set_option("display.width", 200)
    print("\n=== RESULTADOS POR PLIEGUE (neto de 11 bps) ===")
    print(res.round(3).to_string(index=False))
    print("\n=== RESUMEN por H y umbral: pliegues con neto>0 / IC95 inferior>0 ===")
    agg = res.groupby(["H", "top"]).agg(net_mean=("net_bps", "mean"), gross_mean=("gross_bps", "mean"),
                                        pos_folds=("net_bps", lambda x: int((x > 0).sum())),
                                        ci_pos_folds=("ci95_lo_bps", lambda x: int((x > 0).sum())),
                                        IC_mean=("IC", "mean"))
    print(agg.round(3).to_string())
    imp = pd.concat(imps, axis=1).mean(axis=1)
    print("\nVariables más usadas (ganancia media, %):")
    print((100 * imp / imp.sum()).sort_values(ascending=False).head(10).round(1).to_string())


if __name__ == "__main__":
    main()
