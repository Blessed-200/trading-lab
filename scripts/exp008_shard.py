#!/usr/bin/env python3
"""EXP-008 per-shard replay of EXP-007 selections on 1-minute data (train only).

usage: exp008_shard.py <raw_dir> <selections.parquet> <out.parquet> <shard> [--shards 48]
Entry: passive limit at the signal-bar close P0, alive 5 minutes, filled only if a 1m
low/high trades THROUGH P0 by 1 bp. Exits: (a) taker at the horizon close; (b) passive
limit at the close of bar H-1 for 2 bars, taker fallback. Unfilled signals are kept
(`filled=False`) so adverse selection can be measured. Also stores the taker baseline
(enter at the open of bar t+1, exit at the horizon close) to cross-check EXP-007.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lab.splits import VAL_START  # noqa: E402

THROUGH = 1e-4
MIN = np.int64(60 * 10**9)


def in_shard(symbol: str, shard: int, shards: int) -> bool:
    return int(hashlib.md5(symbol.encode()).hexdigest(), 16) % shards == shard


def load_1m(raw: Path, symbol: str) -> dict[str, np.ndarray] | None:
    files = sorted((raw / "binance" / "klines" / symbol).glob("*.parquet"))
    files = [f for f in files if pd.Timestamp(f.stem, tz="UTC") < VAL_START]   # never past train
    if not files:
        return None
    k = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
    k = k.sort_values("open_time").drop_duplicates("open_time")
    return {"t": k["open_time"].astype("int64").to_numpy(), "o": k["open"].to_numpy(np.float64),
            "h": k["high"].to_numpy(np.float64), "l": k["low"].to_numpy(np.float64),
            "c": k["close"].to_numpy(np.float64)}


def replay(m: dict[str, np.ndarray], T: np.int64, side: int, H: int) -> dict | None:
    t = m["t"]
    i0 = int(np.searchsorted(t, T))
    n_need = (H + 1) * 5                                    # bars needed from T onward
    if i0 < 1 or i0 + n_need > len(t) or t[i0] != T or t[i0 - 1] != T - MIN:
        return None
    if t[i0 + n_need - 1] - t[i0] != (n_need - 1) * MIN:    # gap inside the window
        return None
    P0 = m["c"][i0 - 1]
    exit_a = m["c"][i0 + H * 5 - 1]
    base = side * (exit_a / m["o"][i0] - 1)                 # taker baseline (enter open t+1)
    # --- passive entry
    fill_k = -1
    for k in range(5):
        j = i0 + k
        if (side > 0 and m["l"][j] <= P0 * (1 - THROUGH)) or (side < 0 and m["h"][j] >= P0 * (1 + THROUGH)):
            fill_k = k
            break
    ref_gross = side * (exit_a / P0 - 1)                    # P0 -> horizon close, any signal
    out = {"base_gross": base, "ref_gross": ref_gross, "filled": fill_k >= 0, "fill_k": fill_k}
    # --- exit (b): passive at close of bar H-1, 10 one-minute bars, taker fallback
    ref = m["c"][i0 + (H - 1) * 5 - 1]
    lo, hi = i0 + (H - 1) * 5, i0 + (H + 1) * 5
    xf = False
    for j in range(lo, hi):
        if (side > 0 and m["h"][j] >= ref * (1 + THROUGH)) or (side < 0 and m["l"][j] <= ref * (1 - THROUGH)):
            xf = True
            break
    exit_b = ref if xf else m["c"][hi - 1]
    out.update({"gross_a": ref_gross, "gross_b": side * (exit_b / P0 - 1), "exit_b_filled": xf})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("raw", type=Path)
    p.add_argument("selections", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("shard", type=int)
    p.add_argument("--shards", type=int, default=48)
    a = p.parse_args()
    sel = pd.read_parquet(a.selections)
    sel = sel[sel["H"].isin([6, 12])]
    assert (sel["available_at"] < VAL_START).all(), "selection past the train boundary"
    sel = sel[sel["symbol"].map(lambda s: in_shard(s, a.shard, a.shards))]
    rows, skipped = [], 0
    for sym, g in sel.groupby("symbol"):
        m = load_1m(a.raw, sym)
        if m is None:
            skipped += len(g)
            continue
        for r in g.itertuples(index=False):
            T = np.int64(pd.Timestamp(r.available_at).value)
            res = replay(m, T, int(r.side), int(r.H))
            if res is None:
                skipped += 1
                continue
            rows.append({"fold": r.fold, "symbol": sym, "available_at": r.available_at, "H": int(r.H),
                         "side": int(r.side), "fwd5": r.fwd, **res})
    pd.DataFrame(rows).to_parquet(a.out, index=False)
    print(f"shard {a.shard}: selections={len(sel)} replayed={len(rows)} skipped={skipped}")


if __name__ == "__main__":
    main()
