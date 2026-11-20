"""Conservative synthetic cost model; real fee schedule must be verified."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCosts:
    taker_fee_bps: float
    slippage_bps_per_side: float
    funding_bps_signed: float = 0.0

    def round_trip_return(self, raw_return: float) -> float:
        """Approximate net simple notional return for one unlevered round trip.

        Signed funding is a cost if positive, credit if negative.
        Not a fill simulator; approximate only. Impact/latency excluded.
        """
        per_side = (self.taker_fee_bps + self.slippage_bps_per_side) / 10_000
        return (1 + raw_return) * (1 - per_side) ** 2 - 1 - self.funding_bps_signed / 10_000
