#!/usr/bin/env python3
"""EXP-006: excursion atlas (MFE/MAE) and quantile exit policies (train only).

usage: eval_exp006.py <dev_panel_dir> <events_train.parquet> <out_dir> [--rate 0.04]
1) Atlas: quantiles of the best/worst excursion in the next 30 and 60 minutes, long view.
2) Policy simulation on UNCONDITIONAL entries (null test) and on the EXP-001 long-dip
   events. TP/SL are per-coin quantiles of the atlas. If TP and SL are both reachable
   inside the window the ordering is unknown -> the stop is assumed (conservative).
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.backtest import Costs  # noqa: E402
from src.lab.data import dev_files, load_dev  # noqa: E402
from src.lab.features import add_features, forward_paths  # noqa: E402

HS = (6, 12)


def build_sample(panel_dir: Path, rate: float) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    parts = []
    for f in dev_files(panel_dir):
        df = load_dev(f, "train")
        for sym, g in df.groupby("symbol", sort=False):
            d = add_features(g)
            ok = (d["adv24"] >= 5e6) & d["contig"] & d["sigma"].notna()
            pick = ok & (rng.random(len(d)) < rate)
            if not pick.any():
                continue
            o = d.loc[pick, ["symbol", "available_at", "adv24"]].copy()
            for h in HS:
                fp = forward_paths(d, h).loc[pick]
                o[f"fwd_{h}"], o[f"mae_{h}"], o[f"mfe_{h}"] = fp["fwd"].to_numpy(), fp["mae_long"].to_numpy(), fp["mfe_long"].to_numpy()
            parts.append(o)
    return pd.concat(parts, ignore_index=True).dropna()


def atlas(s: pd.DataFrame) -> None:
    s = s.copy()
    s["liq"] = pd.qcut(s["adv24"], 3, labels=["baja", "media", "alta"])
    qs = (0.3, 0.5, 0.7, 0.9)
    print("\n=== ATLAS (bps). Subida máxima y caída máxima dentro de la ventana, entrando a mercado ===")
    for h in HS:
        print(f"\nVentana {h * 5} min")
        for liq, g in s.groupby("liq", observed=True):
            up = [g[f"mfe_{h}"].quantile(q) * 1e4 for q in qs]
            dn = [-g[f"mae_{h}"].quantile(1 - q) * 1e4 for q in qs]
            print(f"  liquidez {liq:5s} n={len(g):>8,} | subida máx p30/50/70/90: " + "/".join(f"{x:5.0f}" for x in up)
                  + " | caída máx p30/50/70/90: " + "/".join(f"{x:5.0f}" for x in dn))


def coin_levels(s: pd.DataFrame, h: int, q_tp: float, q_sl: float) -> pd.DataFrame:
    g = s.groupby("symbol")
    tbl = pd.DataFrame({"n": g.size(),
                        "up": g[f"mfe_{h}"].quantile(q_tp), "dn": -g[f"mae_{h}"].quantile(1 - q_tp),
                        "up_sl": g[f"mfe_{h}"].quantile(q_sl), "dn_sl": -g[f"mae_{h}"].quantile(1 - q_sl)})
    return tbl[tbl["n"] >= 100]


def simulate(ev: pd.DataFrame, lv: pd.DataFrame, h: int, side: int, costs: Costs) -> dict:
    x = ev.join(lv, on="symbol", how="inner")
    fwd, mae, mfe = x[f"fwd_{h}"], x[f"mae_{h}"], x[f"mfe_{h}"]
    if side > 0:
        tp, sl = x["up"], x["dn_sl"]
        fav, adv, held = mfe, -mae, fwd
    else:
        tp, sl = x["dn"], x["up_sl"]
        fav, adv, held = -mae, mfe, -fwd
    hit_tp, hit_sl = fav >= tp, adv >= sl
    stop_px = -sl - costs.stop_slip_bps / 1e4
    both = hit_tp & hit_sl
    cons = np.where(hit_sl, stop_px, np.where(hit_tp, tp, held))                  # ambiguous -> stop
    neut = np.where(both, 0.5 * tp + 0.5 * stop_px, cons)                          # ambiguous -> 50/50
    rt = costs.round_trip_bps() / 1e4
    return {"n": len(x), "p_tp": float((hit_tp & ~hit_sl).mean()), "p_sl": float((hit_sl & ~hit_tp).mean()),
            "p_both": float(both.mean()),
            "gross_neutral": float(np.mean(neut) * 1e4), "net_neutral": float(np.mean(neut - rt) * 1e4),
            "net_conserv": float(np.mean(cons - rt) * 1e4),
            "avg_tp_bps": float(tp.mean() * 1e4), "avg_sl_bps": float(sl.mean() * 1e4)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("panel_dir", type=Path)
    p.add_argument("events", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--rate", type=float, default=0.04)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    cache = a.out_dir / "excursion_sample.parquet"
    if cache.exists():
        s = pd.read_parquet(cache)
    else:
        s = build_sample(a.panel_dir, a.rate)
        s.to_parquet(cache, index=False)
    print("muestra:", len(s), "barras líquidas,", s["symbol"].nunique(), "monedas")
    atlas(s)
    costs = Costs()
    ev1 = pd.read_parquet(a.events)
    ev1 = ev1[ev1["exp1"] & (ev1["ret_z"] <= -4) & (ev1["vol_z"] >= 5) & (ev1["imbalance"] <= -0.3)]
    ev1 = ev1.rename(columns={f"fwd_{h}": f"fwd_{h}" for h in HS})
    rows = []
    for h, qtp, qsl in itertools.product(HS, (0.5, 0.7), (0.5, 0.7)):
        lv = coin_levels(s, h, qtp, qsl)
        for name, ev in (("incondicional", s), ("EXP001_dip_k4v5", ev1)):
            for side in (+1, -1):
                if name != "incondicional" and side < 0:
                    continue
                r = simulate(ev, lv, h, side, costs)
                rows.append({"entradas": name, "lado": "largo" if side > 0 else "corto", "ventana_min": h * 5,
                             "TP_q": qtp, "SL_q": qsl, **r})
    res = pd.DataFrame(rows)
    res.to_csv(a.out_dir / "exp006_policies.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n=== POLÍTICAS TP/SL por cuantil (neto de 11 bps) ===")
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
