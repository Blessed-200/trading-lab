#!/usr/bin/env python3
"""Aggregate EXP-008 shard results (train only) against the pre-registered criterion.

usage: agg_exp008.py <results_dir>
Net per SIGNAL counts an unfilled entry as 0. Costs: maker 1.5 bps/side; taker 4.5 + 1 slip.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

MAKER, TAKER = 1.5, 5.5


def ci_lo(x: pd.Series, day: pd.Series) -> float:
    g = x.groupby(day).agg(["sum", "count"])
    if len(g) < 5:
        return float("nan")
    rng = np.random.default_rng(7)
    idx = rng.integers(0, len(g), size=(1000, len(g)))
    return float(np.percentile(g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1), 2.5))


def main() -> None:
    d = pd.concat([pd.read_parquet(f) for f in sorted(Path(sys.argv[1]).glob("exp008-s48-*.parquet"))],
                  ignore_index=True)
    d["day"] = pd.to_datetime(d["available_at"], utc=True).dt.floor("D")
    print(f"señales reproducidas: {len(d):,} | monedas: {d.symbol.nunique()} | tasa de relleno entrada: "
          f"{100 * d.filled.mean():.1f}%")
    # --- baseline (taker/taker, entry at open t+1): must match EXP-007
    d["net_taker"] = d["base_gross"] * 1e4 - 2 * TAKER
    # --- passive entry variants (per signal: unfilled -> 0)
    d["cost_a"] = MAKER + TAKER                                          # maker in, taker out
    d["net_a"] = np.where(d.filled, d.gross_a * 1e4 - d.cost_a, 0.0)
    d["cost_b"] = MAKER + np.where(d.exit_b_filled, MAKER, TAKER)       # maker in, maker/taker out
    d["net_b"] = np.where(d.filled, d.gross_b * 1e4 - d.cost_b, 0.0)
    pd.set_option("display.width", 220)
    rows = []
    for (h, fold), g in d.groupby(["H", "fold"]):
        for name, col in (("taker/taker (EXP-007)", "net_taker"), ("maker in / taker out", "net_a"),
                          ("maker in / maker-out+fallback", "net_b")):
            rows.append({"H": h, "fold": fold, "variant": name, "n": len(g), "net_per_signal": g[col].mean(),
                         "ci95_lo": ci_lo(g[col], g["day"])})
    t = pd.DataFrame(rows)
    print("\n=== NETO POR SEÑAL (bps), por pliegue ===")
    print(t.round(2).to_string(index=False))
    s = t.groupby(["H", "variant"]).agg(net_mean=("net_per_signal", "mean"),
                                        folds_pos=("net_per_signal", lambda x: int((x > 0).sum())),
                                        folds_ci_pos=("ci95_lo", lambda x: int((x > 0).sum())))
    print("\n=== RESUMEN (criterio: >=3 de 4 pliegues con IC95 inferior > 0) ===")
    print(s.round(2).to_string())
    # --- adverse selection: same measure (P0 -> horizon close, bps) for filled vs unfilled
    adv = d.groupby(["H", "filled"]).agg(n=("ref_gross", "size"), gross_bps=("ref_gross", lambda x: x.mean() * 1e4))
    print("\n=== SELECCIÓN ADVERSA: retorno bruto P0->cierre, llenadas vs no llenadas (bps) ===")
    print(adv.round(2).to_string())
    f = d[d.filled]
    print(f"\nllenadas: neto por operación (a) = {f.net_a.mean():.2f} bps | (b) = {f.net_b.mean():.2f} bps"
          f" | salida (b) rellena {100 * f.exit_b_filled.mean():.1f}%")
    print("\nPor año (neto por señal, variante a / b):")
    d["year"] = pd.to_datetime(d["available_at"], utc=True).dt.year
    print(d.groupby(["H", "year"])[["net_taker", "net_a", "net_b"]].mean().round(2).to_string())


if __name__ == "__main__":
    main()
