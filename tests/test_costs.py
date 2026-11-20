from src.lab.costs import ExecutionCosts


def test_flat_market_loses_execution_costs():
    c = ExecutionCosts(taker_fee_bps=5, slippage_bps_per_side=2)
    expected = (1 - 0.0007) ** 2 - 1
    assert abs(c.round_trip_return(0.0) - expected) < 1e-14
