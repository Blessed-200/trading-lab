"""Per-symbol features on the 5m panel. Every value at row t uses only bars <= t.

Rolling statistics used to normalise bar t are computed on bars STRICTLY before t
(`shift(1)`), so an extreme bar cannot dilute its own z-score.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DAY = 288  # 5m bars per day


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """df: one symbol, sorted by open_time, columns from src.lab.panel.load_symbol."""
    d = df.sort_values("open_time").reset_index(drop=True).copy()
    d["contig"] = d["open_time"].diff() == pd.Timedelta(minutes=5)
    d["ret"] = d["close"] / d["open"] - 1                      # the bar's own move
    d["ret_cc"] = d["close"] / d["close"].shift(1) - 1
    r = d["ret_cc"].shift(1)
    d["sigma"] = r.rolling(DAY, min_periods=DAY // 2).std()
    d["ret_z"] = d["ret"] / d["sigma"]
    qv = d["quote_volume"].astype("float64")
    prev_mean = qv.shift(1).rolling(DAY, min_periods=DAY // 2).mean()
    prev_std = qv.shift(1).rolling(DAY, min_periods=DAY // 2).std()
    d["vol_z"] = (qv - prev_mean) / prev_std.replace(0, np.nan)
    d["adv24"] = qv.shift(1).rolling(DAY, min_periods=DAY // 2).sum()   # trailing 24h $ volume
    # contract-unit OI: strips the mechanical price effect from USD OI
    oi_units = d["oi_value"].astype("float64") / d["close"].astype("float64")
    d["oi_chg15"] = oi_units / oi_units.shift(3) - 1
    d["imb_ma3"] = d["imbalance"].rolling(3, min_periods=2).mean()
    return d


def forward_paths(d: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Entry at the OPEN of t+1; exit at the CLOSE of t+horizon (horizon >= 1).

    Also returns the worst/best excursion over the holding window (from highs/lows)
    so stops can be evaluated honestly. Rows without a complete, gap-free future
    window get NaN.
    """
    o = d["open"].astype("float64").shift(-1)
    c = d["close"].astype("float64").shift(-horizon)
    lo = d["low"].astype("float64")[::-1].rolling(horizon, min_periods=horizon).min()[::-1].shift(-1)
    hi = d["high"].astype("float64")[::-1].rolling(horizon, min_periods=horizon).max()[::-1].shift(-1)
    t = d["open_time"]
    span = t.shift(-horizon) - t.shift(-1)
    ok = span == pd.Timedelta(minutes=5 * (horizon - 1))
    out = pd.DataFrame({
        "entry": o, "fwd": c / o - 1, "mae_long": lo / o - 1, "mfe_long": hi / o - 1})
    out.loc[~ok.fillna(False), :] = np.nan
    return out
