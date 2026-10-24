"""Dummy input curve over a 40-day harvest window. Swap for real data."""

import math


def dummy_moisture(t):
    """Grain moisture (%) on day t: dries in the field, bumps up after rain. Always > 15%."""
    field_drying = 6.0 * math.exp(-t / 12)
    rain = 1.2 * max(0.0, math.sin(2 * math.pi * t / 9))
    return 15.5 + field_drying + rain
