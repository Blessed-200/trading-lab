"""Collapse 1m Binance archives into a compact 5m research panel.

Each 5m bar is stamped with `available_at` = bar close. Open interest and the
top-trader ratio are joined as-of (backward) at that instant with a staleness
tolerance, so a bar never sees a value published after it closed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=5)
FLOAT_COLS = ["open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_base", "oi_value", "top_ls"]


def resample_5m(k: pd.DataFrame) -> pd.DataFrame:
    """1m klines -> 5m bars. Incomplete bars keep `n1m` < 5 so callers can drop them."""
    k = k.sort_values("open_time").drop_duplicates("open_time")
    g = k.set_index("open_time").resample("5min", label="left", closed="left")
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
                quote_volume=("quote_volume", "sum"),
                taker_buy_base=("taker_buy_base_volume", "sum"),
                n1m=("close", "count"))
    out = out[out["n1m"] > 0].reset_index()
    vol = out["volume"].where(out["volume"] > 0)
    out["imbalance"] = (2 * out["taker_buy_base"] - out["volume"]) / vol
    out["available_at"] = out["open_time"] + BAR
    return out


def join_metrics(bars: pd.DataFrame, metrics: pd.DataFrame | None) -> pd.DataFrame:
    bars = bars.sort_values("available_at")
    if metrics is None or metrics.empty:
        bars["oi_value"] = np.nan
        bars["top_ls"] = np.nan
        return bars
    m = (metrics.rename(columns={"available_at": "m_at",
                                 "sum_open_interest_value": "oi_value",
                                 "count_toptrader_long_short_ratio": "top_ls"})
         [["m_at", "oi_value", "top_ls"]].dropna(subset=["m_at"])
         .sort_values("m_at").drop_duplicates("m_at"))
    return pd.merge_asof(bars, m, left_on="available_at", right_on="m_at",
                         direction="backward", tolerance=pd.Timedelta(minutes=15)
                         ).drop(columns=["m_at"])


def load_symbol(root: Path, symbol: str) -> pd.DataFrame | None:
    kfiles = sorted((root / "binance" / "klines" / symbol).glob("*.parquet"))
    if not kfiles:
        return None
    k = pd.concat([pd.read_parquet(f) for f in kfiles], ignore_index=True)
    mfiles = sorted((root / "binance" / "metrics" / symbol).glob("*.parquet"))
    m = pd.concat([pd.read_parquet(f) for f in mfiles], ignore_index=True) if mfiles else None
    bars = join_metrics(resample_5m(k), m)
    bars["symbol"] = symbol
    for c in FLOAT_COLS + ["imbalance"]:
        bars[c] = bars[c].astype("float32")
    bars["n1m"] = bars["n1m"].astype("int8")
    return bars[["symbol", "open_time", "available_at", "open", "high", "low", "close",
                 "volume", "quote_volume", "imbalance", "oi_value", "top_ls", "n1m"]]
