#!/usr/bin/env python3
"""Evaluate a registered EXP grid on an events parquet (train or val).

usage: eval_grid.py <events.parquet> <exp001|exp002> <out.csv> [--stress 1.0]
One position per symbol at a time (events inside an open holding window are skipped).
Net of Hyperliquid base-tier fees + slippage. No stops (none are in the registered grids).
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.backtest import Costs, net_returns, summarize  # noqa: E402

BAR_NS = 5 * 60 * 10**9


def one_at_a_time(ev: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Greedy: within a symbol, skip signals that fire while a position is still open."""
    ev = ev.sort_values(["symbol", "available_at"])
    keep = np.zeros(len(ev), dtype=bool)
    sym = ev["symbol"].to_numpy()
    t = ev["available_at"].astype("int64").to_numpy()
    last_sym, free_at = None, 0
    for i in range(len(ev)):
        if sym[i] != last_sym:
            last_sym, free_at = sym[i], 0
        if t[i] >= free_at:
            keep[i] = True
            free_at = t[i] + (horizon + 1) * BAR_NS
    return ev[keep]


def run_one(sub: pd.DataFrame, side: int, h: int, costs: Costs) -> dict:
    sub = one_at_a_time(sub, h)
    sub = sub.dropna(subset=[f"fwd_{h}"])
    if sub.empty:
        return {"n": 0}
    s = pd.Series(side, index=sub.index)
    net = net_returns(sub[f"fwd_{h}"], sub[f"mae_{h}"], sub[f"mfe_{h}"], s, costs)
    gross = (side * sub[f"fwd_{h}"]).mean() * 1e4
    day = sub["available_at"].dt.floor("D")
    out = summarize(net, day)
    out["gross_bps"] = float(gross)
    out["symbols"] = int(sub["symbol"].nunique())
    top = net.groupby(sub["symbol"]).sum().sort_values(ascending=False)
    pos = top[top > 0].sum()
    out["top5_pnl_share"] = float(top.head(5).clip(lower=0).sum() / pos) if pos > 0 else np.nan
    yr = net.groupby(sub["available_at"].dt.year).mean() * 1e4
    out["by_year_bps"] = ";".join(f"{y}:{v:.1f}" for y, v in yr.items())
    return out


def exp001(ev: pd.DataFrame, costs: Costs) -> list[dict]:
    ev = ev[ev["exp1"]]
    rows = []
    for k, v, d, h in itertools.product((2, 3, 4), (2, 3, 5), (0.0, 0.005, 0.01), (3, 6, 12)):
        oi_ok = (ev["oi_chg15"] <= -d) if d > 0 else pd.Series(True, index=ev.index)
        long_ = ev[(ev["ret_z"] <= -k) & (ev["vol_z"] >= v) & (ev["imbalance"] <= -0.3) & oi_ok]
        short = ev[(ev["ret_z"] >= k) & (ev["vol_z"] >= v) & (ev["imbalance"] >= 0.3) & oi_ok]
        rows.append({"exp": "001", "side": "long_dip", "k": k, "v": v, "d": d, "H": h,
                     **run_one(long_, +1, h, costs)})
        rows.append({"exp": "001b", "side": "short_pump", "k": k, "v": v, "d": d, "H": h,
                     **run_one(short, -1, h, costs)})
    return rows


def exp002(ev: pd.DataFrame, costs: Costs) -> list[dict]:
    ev = ev[ev["exp2"]]
    rows = []
    # momentum if OI rises with the imbalance; fade if OI falls (both registered)
    for thr, oi, h in itertools.product((0.2, 0.35, 0.5), (0.005, 0.01), (3, 6, 12)):
        up = ev[(ev["imb_ma3"] >= thr) & (ev["oi_chg15"] >= oi)]
        dn = ev[(ev["imb_ma3"] <= -thr) & (ev["oi_chg15"] >= oi)]
        rows.append({"exp": "002", "side": "mom_long", "thr": thr, "oi": oi, "H": h, **run_one(up, +1, h, costs)})
        rows.append({"exp": "002", "side": "mom_short", "thr": thr, "oi": oi, "H": h, **run_one(dn, -1, h, costs)})
        up_f = ev[(ev["imb_ma3"] >= thr) & (ev["oi_chg15"] <= -oi)]
        dn_f = ev[(ev["imb_ma3"] <= -thr) & (ev["oi_chg15"] <= -oi)]
        rows.append({"exp": "002", "side": "fade_short", "thr": thr, "oi": oi, "H": h, **run_one(up_f, -1, h, costs)})
        rows.append({"exp": "002", "side": "fade_long", "thr": thr, "oi": oi, "H": h, **run_one(dn_f, +1, h, costs)})
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("events", type=Path)
    p.add_argument("exp", choices=["exp001", "exp002"])
    p.add_argument("out", type=Path)
    p.add_argument("--stress", type=float, default=1.0)
    a = p.parse_args()
    ev = pd.read_parquet(a.events)
    costs = Costs(stress=a.stress)
    rows = exp001(ev, costs) if a.exp == "exp001" else exp002(ev, costs)
    res = pd.DataFrame(rows)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(a.out, index=False)
    print(f"{len(res)} variants -> {a.out}")


if __name__ == "__main__":
    main()
