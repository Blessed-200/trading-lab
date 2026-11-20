"""Point-in-time feature assembly with exact source-availability boundaries."""
from __future__ import annotations
import pandas as pd


def asof_features(candles: pd.DataFrame, metrics: pd.DataFrame,
                  funding: pd.DataFrame) -> pd.DataFrame:
    """Join only events published by the candle's decision timestamp.

    The merged close is Binance's *proxy* close, not a Hyperliquid fill.
    A candidate signal at available_at(t) may trade only at t+1 or later.
    """
    k = candles.sort_values("available_at").copy()
    if k["available_at"].duplicated().any():
        raise ValueError("Duplicate candle availability timestamps")
    for name, frame in (("metrics", metrics), ("funding", funding)):
        if "available_at" not in frame.columns:
            raise ValueError(f"Missing available_at in {name}")
        if frame["available_at"].isna().any():
            raise ValueError(f"Null availability timestamps in {name}")
    m = metrics.sort_values("available_at").copy()
    f = funding.sort_values("available_at").copy()
    if not m.empty:
        m = m.drop(columns=["create_time"], errors="ignore")
        m = m.rename(columns={"available_at": "metrics_available_at"})
        k = pd.merge_asof(k, m, left_on="available_at",
                          right_on="metrics_available_at", direction="backward",
                          allow_exact_matches=True)
        if (k["metrics_available_at"] > k["available_at"]).any():
            raise AssertionError("Metrics lookahead")
    if not f.empty:
        f = f.drop(columns=["time"], errors="ignore")
        f = f.rename(columns={"available_at": "funding_available_at"})
        k = pd.merge_asof(k, f, left_on="available_at",
                          right_on="funding_available_at", direction="backward",
                          allow_exact_matches=True)
        if (k["funding_available_at"] > k["available_at"]).any():
            raise AssertionError("Funding lookahead")
    return k


def frozen_time_split(frame: pd.DataFrame, train_end: str,
                      validation_end: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ts = frame["available_at"]
    a = pd.Timestamp(train_end)
    b = pd.Timestamp(validation_end)
    if a.tzinfo is None or b.tzinfo is None or not a < b:
        raise ValueError("Use ordered, timezone-aware UTC split boundaries")
    train = frame[ts < a].copy()
    validation = frame[(ts >= a) & (ts < b)].copy()
    vault = frame[ts >= b].copy()
    return train, validation, vault
