"""Tests for the whole pipeline. Run:  uv run pytest"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from harvest import planner
from harvest.forecast import load_forecast
from harvest.planner import field_alone, machine_prices, plan_lagrangian
from harvest.simulate import run_season
from harvest.value import drying_cost_gbp_per_t, field_values, start_moisture

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
        temp_start_moisture_pct=14,
        crops={
            "cheap": {"price_gbp_per_t": 50, "yield_t_per_ha": 1},
            "dear": {"price_gbp_per_t": 80, "yield_t_per_ha": 1},
        },
        fields=[
            {"name": "f0", "crop": "cheap", "area_ha": 4},
            {"name": "f1", "crop": "dear", "area_ha": 2},
        ],
        machines=[{"name": "m0", "ha_per_hour": 1, "start": "f0"}],
        travel_hours=[[0, 2, 2], [2, 0, 2], [2, 2, 0]],
    )
    dry_weather = {
        "rain_mm": np.zeros((2, 2, 4)),  # [member, field, hour]
        "humidity_pct": np.full((2, 2, 4), 60.0),
    }
    return params, dry_weather


def rain_farm():
    """Hand-made case where waiting for each field's best hour is a trap.

    One machine at the depot cuts 1 ha per hour; no driving time. Two 1 ha fields of the same
    crop at £100/t, 1 t/ha. The grain dries from 16% to 15% by hour 1, then it rains in hour 2.
    Value of each field: hour 0 £93.50/ha (£4 drying charge + 2.5% weight kept), hour 1 £98.75/ha
    (1.25% weight kept), hour 2 nothing.
    Best: one field now and the other in hour 1, £192.25. Both fields' best hour is hour 1, so a
    planner that waits for it cuts only one field: £98.75.
    """
    params = demo_params()
    params.update(
        season_hours=3,
        plan_hours=3,
        sensor_every_hours=3,
        loss_pct_per_hour=0,
        drying_pct_per_hour=1,
        temp_start_moisture_pct=16,
        crops={"grain": {"price_gbp_per_t": 100, "yield_t_per_ha": 1}},
        fields=[
            {"name": "f0", "crop": "grain", "area_ha": 1},
            {"name": "f1", "crop": "grain", "area_ha": 1},
        ],
        machines=[{"name": "m0", "ha_per_hour": 1, "start": "depot"}],
        travel_hours=np.zeros((3, 3)).tolist(),
    )
    rain = np.zeros((2, 2, 3))  # [member, field, hour]
    rain[:, :, 2] = 1.0
    weather = {"rain_mm": rain, "humidity_pct": np.zeros((2, 2, 3))}  # bone-dry air
    return params, weather


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
    value = field_values(weather, start_moisture(weather, params), params)
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


def test_field_alone_cuts_its_best_hours_first():
    # 5 ha, at most 3 ha an hour: 3 ha in the £5 hour, the other 2 ha in the £3 hour
    cut, gbp = field_alone(np.array([1.0, 5.0, 3.0, 0.0, -2.0]), 5, 3)
    assert cut == pytest.approx([0, 3, 2, 0, 0])
    assert gbp == pytest.approx(3 * 5 + 2 * 3)


def test_prices_stay_zero_when_combines_are_never_short():
    params = demo_params()
    value = np.array([[10.0, 30.0, 20.0, 0.0]])  # one field: it can never ask for too much
    price, bound = machine_prices(value, np.array([5.0]), params)
    assert price == pytest.approx(0)
    assert bound == pytest.approx(3 * 30 + 2 * 20)  # its 5 ha in its two best hours


def test_prices_rise_on_the_hour_everyone_wants():
    params, weather = rain_farm()
    value = field_values(weather, start_moisture(weather, params), params)
    price, bound = machine_prices(value, np.array([1.0, 1.0]), params)
    # hour 1 must cost about £5.25/ha more than hour 0, so one field takes hour 0 instead
    assert price[1] - price[0] == pytest.approx(98.75 - 93.5, abs=0.5)
    assert bound == pytest.approx(192.25, abs=0.5)  # the best answer: the bound is tight here


def test_lagrangian_cuts_before_the_rain():
    params, weather = rain_farm()
    assert run_season(weather, params, plan_lagrangian)["total_gbp"] == pytest.approx(192.25)


def test_lagrangian_finds_the_best_answer_on_the_tiny_farm():
    params, weather = tiny_farm()
    assert run_season(weather, params, plan_lagrangian)["total_gbp"] == pytest.approx(200)


def test_no_planner_earns_more_than_the_lagrangian_bound():
    """With a perfect forecast and a single plan, the bound must hold for every planner."""
    params = demo_params()
    params.update(season_hours=48, plan_hours=48, sensor_every_hours=48)
    forecast = load_forecast(ROOT / "data" / "forecast.csv", params)
    # two copies of one member: the forecast the planners see is exactly the weather that happens
    weather = {name: np.repeat(values[[0], :, :48], 2, axis=0) for name, values in forecast.items()}
    value = field_values(weather, start_moisture(weather, params), params)
    area = np.array([field["area_ha"] for field in params["fields"]], dtype=float)
    _, bound = machine_prices(value, area, params)

    planners = [f for name, f in vars(planner).items() if name.startswith("plan_")]
    for plan in planners:
        assert run_season(weather, params, plan)["total_gbp"] <= bound + 1e-6

    at_depot = np.full(len(params["machines"]), len(params["fields"]))
    schedule = plan_lagrangian(value, {"remaining_ha": area, "machine_at": at_depot}, params)
    assert schedule.shape == (len(params["machines"]), 48)
    for hour in range(48):  # never two combines on one field
        working = schedule[:, hour][schedule[:, hour] != -1]
        assert len(working) == len(set(working))


def test_demo_runs_end_to_end():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    result = run_season(weather, params)
    assert result["total_gbp"] > 0
    assert result["remaining_ha"].min() >= 0
    assert result["harvesting"].shape == (len(params["machines"]), params["season_hours"])
    assert len(result["plans"]) == params["season_hours"] // params["sensor_every_hours"]
