"""Event-trade accounting with explicit costs.

A trade is described by its gross return path; the net return subtracts
round-trip fees and slippage. Short returns are the mirror of long returns.
Stops are evaluated conservatively: if the stop level is touched anywhere in
the holding window the stop fill is assumed (we do not know the intrabar order),
and the exit slips by `stop_slip_bps` extra.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    taker_bps: float = 4.5          # Hyperliquid base tier, per side
    slip_bps: float = 1.0           # per side, liquid symbols
    stop_slip_bps: float = 3.0      # extra when a stop triggers
    stress: float = 1.0             # multiply fees+slippage (1.5 = stress case)

    def round_trip_bps(self) -> float:
        return 2 * (self.taker_bps + self.slip_bps) * self.stress


def net_returns(fwd: pd.Series, mae_long: pd.Series, mfe_long: pd.Series, side: pd.Series,
                costs: Costs, stop: float | None = None) -> pd.Series:
    """Net simple return per trade. side: +1 long, -1 short. stop: positive fraction."""
    side = side.astype("float64")
    gross = side * fwd
    if stop is not None:
        adverse = np.where(side > 0, -mae_long, mfe_long)       # worst move against us
        hit = adverse >= stop
        gross = pd.Series(np.where(hit, -stop - costs.stop_slip_bps / 1e4, gross), index=fwd.index)
    return gross - costs.round_trip_bps() / 1e4


def summarize(net: pd.Series, day: pd.Series | None = None) -> dict:
    """Trade-level summary. If `day` is given, the CI is a day-block bootstrap."""
    net = net.dropna()
    n = len(net)
    if n == 0:
        return {"n": 0}
    wins = net[net > 0].sum()
    losses = -net[net < 0].sum()
    out = {"n": n, "mean_bps": float(net.mean() * 1e4), "median_bps": float(net.median() * 1e4),
           "win_rate": float((net > 0).mean()),
           "profit_factor": float(wins / losses) if losses > 0 else float("inf")}
    if day is not None and n >= 30:
        g = net.groupby(day.loc[net.index]).agg(["sum", "count"])
        rng = np.random.default_rng(7)
        idx = rng.integers(0, len(g), size=(2000, len(g)))
        s, c = g["sum"].to_numpy(), g["count"].to_numpy()
        boot = s[idx].sum(1) / c[idx].sum(1)
        out["ci95_lo_bps"] = float(np.percentile(boot, 2.5) * 1e4)
        out["ci95_hi_bps"] = float(np.percentile(boot, 97.5) * 1e4)
        out["days"] = int(len(g))
    return out
