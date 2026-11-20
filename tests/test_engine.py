import numpy as np
import pandas as pd

from src.lab.backtest import Costs, net_returns, summarize
from src.lab.features import add_features, forward_paths


def _bars(closes, opens=None, start="2026-03-01T00:00:00Z"):
    closes = np.asarray(closes, dtype=float)
    opens = closes if opens is None else np.asarray(opens, dtype=float)
    t = pd.date_range(start, periods=len(closes), freq="5min")
    return pd.DataFrame({
        "symbol": "X", "open_time": t, "available_at": t + pd.Timedelta(minutes=5),
        "open": opens, "high": np.maximum(opens, closes) * 1.001,
        "low": np.minimum(opens, closes) * 0.999, "close": closes,
        "volume": 1.0, "quote_volume": 1000.0, "imbalance": 0.0,
        "oi_value": 1e6, "top_ls": 1.0, "n1m": 5})


def test_flat_market_loses_exactly_the_costs():
    c = Costs()
    fwd = pd.Series([0.0, 0.0])
    side = pd.Series([1, -1])
    net = net_returns(fwd, fwd, fwd, side, c)
    assert np.allclose(net, -11 / 1e4)


def test_short_is_mirror_of_long_before_costs():
    c = Costs(taker_bps=0, slip_bps=0)
    fwd = pd.Series([0.01])
    z = pd.Series([0.0])
    assert net_returns(fwd, z, z, pd.Series([1]), c).iloc[0] == 0.01
    assert net_returns(fwd, z, z, pd.Series([-1]), c).iloc[0] == -0.01


def test_stop_is_assumed_hit_when_touched():
    c = Costs(taker_bps=0, slip_bps=0, stop_slip_bps=5)
    fwd = pd.Series([0.02])             # would have ended +2%
    mae = pd.Series([-0.03])            # but dipped -3% inside the window
    net = net_returns(fwd, mae, pd.Series([0.02]), pd.Series([1]), c, stop=0.01)
    assert abs(net.iloc[0] - (-0.01 - 0.0005)) < 1e-12


def test_forward_path_enters_next_open_and_exits_horizon_close():
    d = _bars([100, 101, 102, 103, 104, 105], opens=[100, 100.5, 101.5, 102.5, 103.5, 104.5])
    f = forward_paths(d, horizon=2)
    # signal at row 0 -> enter open of row 1 (100.5), exit close of row 2 (102)
    assert abs(f.loc[0, "entry"] - 100.5) < 1e-12
    assert abs(f.loc[0, "fwd"] - (102 / 100.5 - 1)) < 1e-12
    assert f.loc[4, :].isna().all() and f.loc[5, :].isna().all()


def test_forward_path_nan_across_time_gap():
    d = _bars([100, 101, 102, 103, 104, 105])
    d = d.drop(index=3).reset_index(drop=True)         # a missing bar
    f = forward_paths(d, horizon=3)
    assert f.loc[0, :].isna().all()


def test_features_do_not_use_the_current_bar_in_their_own_normaliser():
    rng = np.random.default_rng(0)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.001, 600))
    d = _bars(closes)
    base = add_features(d)
    d2 = d.copy()
    d2.loc[500, "close"] = d2.loc[500, "close"] * 1.5      # shock the last-but-100 bar
    shocked = add_features(d2)
    # features at rows before the shock are unchanged
    cols = ["sigma", "vol_z", "ret_z", "adv24"]
    assert np.allclose(base.loc[:499, cols].fillna(0), shocked.loc[:499, cols].fillna(0))


def test_summarize_bootstrap_ci_brackets_a_clear_edge():
    rng = np.random.default_rng(1)
    n = 3000
    day = pd.Series(np.repeat(np.arange(300), 10))
    net = pd.Series(rng.normal(0.001, 0.004, n))
    s = summarize(net, day)
    assert s["ci95_lo_bps"] > 0 and s["ci95_lo_bps"] < s["mean_bps"] < s["ci95_hi_bps"]
