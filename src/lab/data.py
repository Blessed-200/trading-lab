"""Guarded access to the research panel. Vault files are refused by construction."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.lab.splits import VAL_START, VAULT_A_START


def dev_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("dev-s48-*.parquet"))
    if any("vault" in f.name for f in directory.iterdir() if f.is_file() and f.suffix == ".parquet"):
        raise PermissionError("Vault files found in the research directory; remove them.")
    return files


def load_dev(path: Path, until: str = "train") -> pd.DataFrame:
    """Load one dev shard. until='train' keeps rows available before VAL_START;
    until='val' keeps rows before VAULT_A_START (i.e. all of dev)."""
    if "vault" in path.name:
        raise PermissionError(f"Refusing to open a vault file: {path.name}")
    cut = VAL_START if until == "train" else VAULT_A_START
    df = pd.read_parquet(path)
    df = df[df["available_at"] < cut]
    if len(df) and df["available_at"].max() >= VAULT_A_START:
        raise PermissionError("Row at or after the vault boundary slipped into research data")
    df["symbol"] = df["symbol"].astype(str)
    return df
