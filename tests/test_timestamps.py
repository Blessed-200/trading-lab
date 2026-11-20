from pathlib import Path
import importlib.util
import pandas as pd

spec = importlib.util.spec_from_file_location("collector", Path(__file__).resolve().parents[1] / "scripts" / "collect_data.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_metric_label_change():
    df = pd.DataFrame({
        "create_time": ["2026-07-01 00:00:00"],
        "sum_open_interest_value": [100],
        "count_toptrader_long_short_ratio": [1.5],
    })
    after = collector.normalize_metrics(df.copy(), "2026-07-01")
    before = collector.normalize_metrics(df.copy(), "2026-06-24")
    assert after.iloc[0]["available_at"] == pd.Timestamp("2026-07-01 00:05", tz="UTC")
    assert before.iloc[0]["available_at"] == pd.Timestamp("2026-07-01 00:00", tz="UTC")


def test_aggressor_imbalance():
    df = pd.DataFrame([[1735689600000, 1, 1, 1, 1, 10, 1735689659999,
                        10, 12, 7, 7, 0]], columns=collector.KLINE_FIELDS)
    x = collector.normalize_klines(df)
    assert abs(x.iloc[0]["aggressor_imbalance"] - 0.4) < 1e-12
    assert x.iloc[0]["available_at"] == x.iloc[0]["open_time"] + pd.Timedelta(minutes=1)
