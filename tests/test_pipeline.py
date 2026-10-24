"""Tests for the whole pipeline. Run:  uv run pytest"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from harvest.forecast import load_forecast
from harvest.simulate import run_season
from harvest.value import drying_cost_gbp_per_t, field_values

ROOT = Path(__file__).parent.parent


def demo_params():
    return yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))


def tiny_farm():
    """Hand-made case where we know the answer.

    One machine starts at field 0. Four dry hours. Driving between fields takes 2 hours.
    Field 0: 4 ha worth £50/ha. Field 1: 2 ha worth £80/ha. The machine cuts 1 ha per hour.
    Staying on field 0 earns 4 x £50 = £200 (the best possible).
    Driving to field 1 earns 2 x £80 = £160 (2 hours lost to driving).
    """
    params = demo_params()
    params.update(
        season_hours=4,
        plan_hours=4,
        sensor_every_hours=4,
        loss_pct_per_hour=0,
        drying_pct_per_hour=0,
        crops={
            "cheap": {"price_gbp_per_t": 50, "yield_t_per_ha": 1},
            "dear": {"price_gbp_per_t": 80, "yield_t_per_ha": 1},
        },
        fields=[
            {"name": "f0", "crop": "cheap", "area_ha": 4, "start_moisture_pct": 14},
            {"name": "f1", "crop": "dear", "area_ha": 2, "start_moisture_pct": 14},
        ],
        machines=[{"name": "m0", "ha_per_hour": 1, "start": "f0"}],
        travel_hours=[[0, 2, 2], [2, 0, 2], [2, 2, 0]],
    )
    dry_weather = {
        "rain_mm": np.zeros((2, 2, 4)),  # [member, field, hour]
        "humidity_pct": np.full((2, 2, 4), 60.0),
    }
    return params, dry_weather


def stay_on_field_0(value, state, params):
    return np.zeros((1, value.shape[1]), dtype=int)


def drive_to_field_1(value, state, params):
    return np.ones((1, value.shape[1]), dtype=int)


def test_forecast_loads_as_member_field_hour_arrays():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    n_members, n_fields, n_hours = weather["rain_mm"].shape
    assert n_fields == len(params["fields"])
    assert n_members > 1 and n_hours >= params["season_hours"]


def test_value_has_one_number_per_field_and_hour():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    moisture = np.array([field["start_moisture_pct"] for field in params["fields"]])
    value = field_values(weather, moisture, params)
    assert value.shape == weather["rain_mm"].shape[1:]
    assert (value >= 0).all()


def test_drying_cost_follows_camgrain_bands():
    params = demo_params()
    params["fields"] = [{"name": "f0", "crop": "free"}, {"name": "f1", "crop": "dear"}]
    params["crops"] = {"free": {"price_gbp_per_t": 0}, "dear": {"price_gbp_per_t": 200}}
    moisture = np.array([[[14.0, 15.0, 15.1, 15.5, 15.6, 16.0]] * 2])  # [member, field, hour]
    cost = drying_cost_gbp_per_t(moisture, params)
    assert cost[0, 0] == pytest.approx([0, 0, 2, 2, 4, 4])  # price 0 leaves only the charge
    # at 16%: £4 charge + 2 points x 1.25% of a £200 tonne = £5 of weight lost
    assert cost[0, 1, -1] == pytest.approx(9)


def test_simulator_counts_driving_and_harvesting():
    params, weather = tiny_farm()
    assert run_season(weather, params, stay_on_field_0)["total_gbp"] == pytest.approx(200)
    assert run_season(weather, params, drive_to_field_1)["total_gbp"] == pytest.approx(160)


def test_planner_finds_the_best_answer_on_the_tiny_farm():
    params, weather = tiny_farm()
    assert run_season(weather, params)["total_gbp"] == pytest.approx(200)


def test_demo_runs_end_to_end():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    result = run_season(weather, params)
    assert result["total_gbp"] > 0
    assert result["remaining_ha"].min() >= 0
    assert result["harvesting"].shape == (len(params["machines"]), params["season_hours"])
    assert len(result["plans"]) == params["season_hours"] // params["sensor_every_hours"]
