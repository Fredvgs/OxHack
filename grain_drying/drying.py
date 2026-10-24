"""Cost of having a store dry your grain, using Camgrain's published charges.

Source: https://www.camgrain.co.uk/charges-for-2025 (cereals & pulses, harvest 2026).
The handling charge (£9.90/t) and throughput loss (0.75%) are paid whatever the
moisture, so they're left out: this is the cost of the moisture alone.
"""

import math
from dataclasses import dataclass

TARGET_MOISTURE = 14.0         # % the store dries cereals down to
WEIGHT_LOSS_PER_POINT = 1.25   # % weight deducted per point of moisture removed
FREE_UP_TO = 15.0              # % at or below which there is no drying charge
CHARGE_PER_HALF_POINT = 2.00   # £/t for each 0.5% band above FREE_UP_TO


@dataclass(frozen=True)
class DryingCost:
    moisture: float
    drying_charge: float     # £/t
    weight_loss_cost: float  # £/t: value of the weight deducted

    @property
    def total(self):
        return self.drying_charge + self.weight_loss_cost


def drying_charge(moisture):
    """£/t: 15.1-15.5% -> £2, 15.6-16.0% -> £4, ... +£2 per 0.5% band."""
    excess = round(moisture, 1) - FREE_UP_TO
    if excess <= 0:
        return 0.0
    return CHARGE_PER_HALF_POINT * math.ceil(round(excess / 0.5, 6))


def weight_loss_pct(moisture):
    """% of delivered weight deducted for drying down to TARGET_MOISTURE."""
    return WEIGHT_LOSS_PER_POINT * max(0.0, moisture - TARGET_MOISTURE)


def drying_cost(moisture, grain_price):
    """Cost per delivered tonne of drying grain at `moisture`; grain_price in £/t."""
    return DryingCost(
        moisture=moisture,
        drying_charge=drying_charge(moisture),
        weight_loss_cost=grain_price * weight_loss_pct(moisture) / 100,
    )


def cost_curve(moisture_fn, times, grain_price=180.0):
    """Drying cost at each time, given moisture(t) in %."""
    return [drying_cost(moisture_fn(t), grain_price) for t in times]
