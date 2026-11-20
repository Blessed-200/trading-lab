#!/usr/bin/env python3
"""EXP-004: dollar-neutral cross-sectional reversal on the liquid universe (train only).

usage: eval_exp004.py <dev_panel_dir> <out.csv>
Formation return over F bars, rank at close t0, long losers / short winners (equal
weight, quantile q), enter at open t0+1, exit close t0+H, non-overlapping rebalances.
Gross capital = 1 (0.5 long + 0.5 short); full turnover each rebalance, so the net is
gross - round-trip cost (11 bps) per unit of gross capital.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.backtest import Costs  # noqa: E402
from src.lab.data import dev_files, load_dev  # noqa: E402

MIN_ADV24 = 20e6
DAY = 288


def build_wide(panel_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    opens, closes = [], []
    for f in dev_files(panel_dir):
        df = load_dev(f, "train")
        for sym, g in df.groupby("symbol", sort=False):
            g = g.sort_values("open_time")
            adv = g["quote_volume"].astype("float64").shift(1).rolling(DAY, min_periods=DAY // 2).sum()
            ok = adv >= MIN_ADV24
            if not ok.any():
                continue
            idx = g["open_time"]
            o = pd.Series(g["open"].astype("float32").where(ok).to_numpy(), index=idx, name=sym)
            c = pd.Series(g["close"].astype("float32").where(ok).to_numpy(), index=idx, name=sym)
            opens.append(o)
            closes.append(c)
    return pd.concat(opens, axis=1), pd.concat(closes, axis=1)


def main() -> None:
    panel_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    O, C = build_wide(panel_dir)
    O, C = O.sort_index(), C.sort_index()
    full = pd.date_range(C.index.min(), C.index.max(), freq="5min")
    O, C = O.reindex(full), C.reindex(full)
    print("wide matrix:", C.shape, flush=True)
    c, o = C.to_numpy(np.float64), O.to_numpy(np.float64)
    ts = C.index
    cost = Costs().round_trip_bps() / 1e4
    rows = []
    for F, H, q in itertools.product((6, 12, 24), (12, 24, 48), (0.1, 0.2)):
        res = []
        for t0 in range(F, len(ts) - H - 1, H):
            past = c[t0] / c[t0 - F] - 1
            entry, exit_ = o[t0 + 1], c[t0 + H]
            valid = np.isfinite(past) & np.isfinite(entry) & np.isfinite(exit_)
            if valid.sum() < 30:
                continue
            idx = np.flatnonzero(valid)
            order = idx[np.argsort(past[idx])]
            m = max(1, int(len(order) * q))
            losers, winners = order[:m], order[-m:]
            fwd = exit_ / entry - 1
            gross = 0.5 * (fwd[losers].mean() - fwd[winners].mean())
            res.append((ts[t0], gross, gross - cost))
        r = pd.DataFrame(res, columns=["t", "gross", "net"])
        day = r["t"].dt.floor("D")
        g = r.groupby(day)["net"].agg(["sum", "count"])
        rng = np.random.default_rng(7)
        idx = rng.integers(0, len(g), size=(2000, len(g)))
        boot = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
        yr = r.groupby(r["t"].dt.year)["net"].mean() * 1e4
        rows.append({"F": F, "H": H, "q": q, "n": len(r), "gross_bps": r["gross"].mean() * 1e4,
                     "net_bps": r["net"].mean() * 1e4, "ci95_lo_bps": np.percentile(boot, 2.5) * 1e4,
                     "win_rate": float((r["net"] > 0).mean()),
                     "by_year_bps": ";".join(f"{y}:{v:.1f}" for y, v in yr.items())})
    res = pd.DataFrame(rows)
    res.to_csv(out, index=False)
    pd.set_option("display.width", 220)
    print(res.sort_values("net_bps", ascending=False).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
