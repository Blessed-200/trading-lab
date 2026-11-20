import pandas as pd
from src.lab.dataset import asof_features, frozen_time_split


def test_no_metrics_from_future_interval():
    t = pd.to_datetime(["2026-08-01T00:03:00Z", "2026-08-01T00:04:00Z",
                        "2026-08-01T00:05:00Z", "2026-08-01T00:06:00Z"])
    candles = pd.DataFrame({"available_at": t, "close": [1, 2, 3, 4]})
    metrics = pd.DataFrame({"available_at": pd.to_datetime(
        ["2026-08-01T00:05:00Z"]), "sum_open_interest_value": [99]})
    funding = pd.DataFrame({"available_at": pd.to_datetime(
        ["2026-08-01T00:05:00Z"]), "fundingRate": [0.01]})
    x = asof_features(candles, metrics, funding)
    assert pd.isna(x.iloc[0]["sum_open_interest_value"])
    assert pd.isna(x.iloc[1]["sum_open_interest_value"])
    assert x.iloc[2]["sum_open_interest_value"] == 99
    assert pd.isna(x.iloc[1]["fundingRate"])


def test_chronological_vault():
    f = pd.DataFrame({"available_at": pd.to_datetime(
        ["2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z"])})
    tr, va, vault = frozen_time_split(f, "2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z")
    assert (len(tr), len(va), len(vault)) == (1, 1, 1)
