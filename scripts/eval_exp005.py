#!/usr/bin/env python3
"""EXP-005: contrarian trading of extreme Hyperliquid funding (train only).

usage: eval_exp005.py <dev_panel_dir> <hl_data_dir> <universe.json> <out.csv>
Signal at funding timestamp T: 8h mean funding vs its rolling 30d quantile (current
observation excluded). Strict inequality, because funding sits on a floor most of the
time and ">=" would fire permanently. Funding PnL over the hold is included.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.backtest import Costs  # noqa: E402
from src.lab.data import dev_files  # noqa: E402
from src.lab.splits import VAL_START  # noqa: E402

BAR = pd.Timedelta(minutes=5)


def price_series(panel_dir: Path, symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, list[pd.DataFrame]] = {}
    for f in dev_files(panel_dir):
        t = ds.dataset(f).to_table(columns=["symbol", "open_time", "available_at", "open", "close",
                                            "quote_volume"],
                                   filter=ds.field("symbol").isin(symbols)).to_pandas()
        t["symbol"] = t["symbol"].astype(str)
        t = t[t["available_at"] < VAL_START]
        for s, g in t.groupby("symbol"):
            out.setdefault(s, []).append(g)
    res = {}
    for s, parts in out.items():
        g = pd.concat(parts).sort_values("open_time").set_index("open_time")
        g["adv24"] = g["quote_volume"].astype("float64").shift(1).rolling(288, min_periods=144).sum()
        res[s] = g
    return res


def main() -> None:
    panel_dir, hl_dir, uni, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    umap = {r["hl_coin"]: r["symbol"] for r in json.load(open(uni))["symbols"] if r["hl_coin"]}
    prices = price_series(panel_dir, sorted(set(umap.values())))
    cost = Costs().round_trip_bps() / 1e4
    trades = []
    for coin, sym in umap.items():
        fp = hl_dir / "hyperliquid" / "funding" / f"{coin}.parquet"
        if sym not in prices or not fp.exists():
            continue
        px = prices[sym]
        fd = pd.read_parquet(fp)[["time", "fundingRate"]].sort_values("time")
        fd = fd[fd["time"] < VAL_START].drop_duplicates("time").set_index("time")["fundingRate"]
        if len(fd) < 800:
            continue
        m8 = fd.rolling(8, min_periods=8).mean()
        for p, H in [(p, H) for p in (0.90, 0.95, 0.99) for H in (8, 24)]:
            hi = m8.shift(1).rolling(720, min_periods=500).quantile(p)
            lo = m8.shift(1).rolling(720, min_periods=500).quantile(1 - p)
            sig = np.where(m8 > hi, -1, np.where(m8 < lo, 1, 0))     # contrarian
            free_at = pd.Timestamp.min.tz_localize("UTC")
            for T, s in zip(m8.index, sig):
                if s == 0 or T < free_at:
                    continue
                i = px.index.searchsorted(T, side="right")           # first bar strictly after T
                j = i + H * 12 - 1
                if j >= len(px) or i >= len(px):
                    continue
                if px.index[j] - px.index[i] != BAR * (H * 12 - 1):  # gap inside the window
                    continue
                if not px["adv24"].iloc[i] >= 5e6:
                    continue
                entry, exit_ = float(px["open"].iloc[i]), float(px["close"].iloc[j])
                t0, t1 = px.index[i], px.index[j] + BAR
                fsum = fd[(fd.index > t0) & (fd.index <= t1)].sum()
                gross_px = s * (exit_ / entry - 1)
                fund_pnl = -s * fsum                                 # long pays positive funding
                trades.append({"coin": coin, "p": p, "H": H, "t": t0, "side": int(s),
                               "px_bps": gross_px * 1e4, "fund_bps": fund_pnl * 1e4,
                               "net_bps": (gross_px + fund_pnl - cost) * 1e4})
                free_at = t1
    tr = pd.DataFrame(trades)
    rows = []
    for (p, H), g in tr.groupby(["p", "H"]):
        day = g["t"].dt.floor("D")
        by = g.groupby(day)["net_bps"].agg(["sum", "count"])
        rng = np.random.default_rng(7)
        idx = rng.integers(0, len(by), size=(2000, len(by)))
        boot = by["sum"].to_numpy()[idx].sum(1) / by["count"].to_numpy()[idx].sum(1)
        yr = g.groupby(g["t"].dt.year)["net_bps"].mean()
        rows.append({"p": p, "H": H, "n": len(g), "coins": g["coin"].nunique(),
                     "px_bps": g["px_bps"].mean(), "fund_bps": g["fund_bps"].mean(),
                     "net_bps": g["net_bps"].mean(), "ci95_lo_bps": np.percentile(boot, 2.5),
                     "win_rate": float((g["net_bps"] > 0).mean()),
                     "by_year_bps": ";".join(f"{y}:{v:.1f}" for y, v in yr.items())})
    res = pd.DataFrame(rows)
    res.to_csv(out, index=False)
    pd.set_option("display.width", 220)
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
