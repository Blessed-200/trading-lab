import numpy as np
import pandas as pd

from src.lab.panel import join_metrics, resample_5m
from src.lab.splits import part_of


def _klines(n=10, start="2026-03-01T00:00:00Z"):
    t = pd.date_range(start, periods=n, freq="1min")
    close = np.arange(1, n + 1, dtype=float)
    return pd.DataFrame({
        "open_time": t, "open": close - 0.5, "high": close + 1, "low": close - 1,
        "close": close, "volume": 10.0, "quote_volume": 10.0 * close,
        "taker_buy_base_volume": 7.0})


def test_resample_ohlcv_and_imbalance():
    b = resample_5m(_klines(10))
    assert len(b) == 2
    first = b.iloc[0]
    assert first["open"] == 0.5 and first["close"] == 5 and first["high"] == 6 and first["low"] == 0
    assert first["volume"] == 50 and first["n1m"] == 5
    assert abs(first["imbalance"] - 0.4) < 1e-12  # (2*35-50)/50
    assert first["available_at"] == first["open_time"] + pd.Timedelta(minutes=5)


def test_incomplete_bar_is_flagged():
    b = resample_5m(_klines(7))
    assert list(b["n1m"]) == [5, 2]


def test_metrics_never_from_the_future():
    b = resample_5m(_klines(15))
    m = pd.DataFrame({"available_at": pd.to_datetime(["2026-03-01T00:05:00Z", "2026-03-01T00:12:00Z"],
                                                     utc=True),
                      "sum_open_interest_value": [100.0, 200.0],
                      "count_toptrader_long_short_ratio": [1.0, 2.0]})
    x = join_metrics(b, m).sort_values("available_at").reset_index(drop=True)
    # bar closing 00:05 may see the 00:05 value; bar closing 00:10 still sees 100;
    # bar closing 00:15 may see the 00:12 value.
    assert list(x["oi_value"]) == [100.0, 100.0, 200.0]


def test_metrics_staleness_tolerance():
    b = resample_5m(_klines(15, "2026-03-01T01:00:00Z"))
    m = pd.DataFrame({"available_at": pd.to_datetime(["2026-03-01T00:00:00Z"], utc=True),
                      "sum_open_interest_value": [100.0],
                      "count_toptrader_long_short_ratio": [1.0]})
    assert join_metrics(b, m)["oi_value"].isna().all()


def test_part_of_boundaries():
    ts = pd.Series(pd.to_datetime(["2025-12-31T23:59:59Z", "2026-01-01T00:00:00Z",
                                   "2026-05-31T23:59:59Z", "2026-06-01T00:00:00Z"], utc=True))
    assert list(part_of(ts)) == ["dev", "vault_a", "vault_a", "vault_b"]
