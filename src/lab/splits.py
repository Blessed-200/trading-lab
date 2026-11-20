"""Frozen chronological partitions. These constants are the contract: changing
them after any vault has been opened invalidates every result.

dev      2023-06-01 .. 2025-12-31   free exploration (walk-forward inside)
  train  2023-06-01 .. 2025-06-30
  val    2025-07-01 .. 2025-12-31   candidate selection, limited budget
vault A  2026-01-01 .. 2026-05-31   opened once per finalist
vault B  2026-06-01 .. end of data  opened once, only for the survivor of A
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VAL_START = pd.Timestamp("2025-07-01", tz="UTC")
VAULT_A_START = pd.Timestamp("2026-01-01", tz="UTC")
VAULT_B_START = pd.Timestamp("2026-06-01", tz="UTC")
PARTS = ("dev", "vault_a", "vault_b")


def part_of(available_at: pd.Series) -> pd.Series:
    """Label each row dev / vault_a / vault_b by when it became available."""
    ts = pd.to_datetime(available_at, utc=True)
    edges = np.array([VAULT_A_START.value, VAULT_B_START.value], dtype="int64")
    idx = np.searchsorted(edges, ts.astype("int64").to_numpy(), side="right")
    return pd.Series(np.array(PARTS, dtype=object)[idx], index=available_at.index)
