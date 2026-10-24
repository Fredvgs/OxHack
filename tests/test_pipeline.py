"""Tests for the whole pipeline. Run:  uv run pytest"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from harvest import planners
from harvest.forecast import load_forecast, load_moisture
from harvest.planners import plan_lagrangian, plan_mpc
from harvest.planners.lagrangian import field_alone, machine_prices
from harvest.simulate import run_season
from harvest.value import drying_cost_gbp_per_t, field_values, member_values, start_moisture

ROOT = Path(__file__).parent.parent
MOISTURE_CSV = ROOT / "outputs" / "moisture_forecast.csv"


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


def go_to_depot(value, state, params):
    return np.full((1, value.shape[1]), value.shape[0])


def one_combine_farm(n_fields, area_ha, start):
    """Settings for planning straight from a value matrix: one 1 ha/hour combine, 1 h drives.

    Grain left at the end of the plan is worth nothing, unless a test changes it.
    """
    params = demo_params()
    params.update(
        fields=[{"name": f"f{f}", "crop": "wheat", "area_ha": area_ha[f]} for f in range(n_fields)],
        machines=[{"name": "m0", "ha_per_hour": 1, "start": start}],
        travel_hours=(1 - np.eye(n_fields + 1)).tolist(),
        mpc_idle_in_field_gbp_per_hour=20,
        mpc_drive_gbp_per_hour=10,
        mpc_terminal_value_pct=0,
    )
    return params


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


def test_moisture_csv_gives_each_field_its_own_crop(tmp_path):
    params = demo_params()
    params["fields"] = [{"name": "f0", "crop": "wheat"}, {"name": "f1", "crop": "barley"}]
    rows = ["hour,member,field,wheat_moisture_pct,barley_moisture_pct"]
    for member in range(2):
        for hour in range(3):
            for field in ["f1", "f0"]:  # out of order on purpose
                rows.append(f"{hour},{member},{field},{20 + hour},{10 + member}")
    path = tmp_path / "moisture.csv"
    path.write_text("\n".join(rows))
    moisture = load_moisture(path, params)  # [member, field, hour]
    assert moisture.shape == (2, 2, 3)
    assert moisture[1, 0] == pytest.approx([20, 21, 22])  # f0 is wheat
    assert moisture[1, 1] == pytest.approx([11, 11, 11])  # f1 is barley
    assert drying_cost_gbp_per_t(moisture, params).shape == (2, 2, 3)


def test_value_uses_moisture_forecast_shifted_to_the_reading():
    params, weather = tiny_farm()
    params["crops"]["dear"]["price_gbp_per_t"] = 200
    # the moisture model says field 1 dries 1 point per hour from 18%
    weather["moisture_pct"] = np.tile([18.0, 17.0, 16.0, 15.0], (2, 2, 1))  # [member, field, hour]
    assert start_moisture(weather, params) == pytest.approx([18, 18])
    # a reading of 16% keeps the same drying, just 2 points lower: 16, 15, 14, 13
    value = field_values(weather, np.array([16.0, 16.0]), params)
    assert value[1, 3] == pytest.approx(200)  # 13% is dry enough to cost nothing
    assert value[1, 0] < value[1, 3]  # wetter grain costs more to dry


def test_moisture_csv_must_match_the_forecast():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params, MOISTURE_CSV)
    assert weather["moisture_pct"].shape == weather["rain_mm"].shape


def test_simulator_counts_driving_and_harvesting():
    params, weather = tiny_farm()
    assert run_season(weather, params, stay_on_field_0)["total_gbp"] == pytest.approx(200)
    assert run_season(weather, params, drive_to_field_1)["total_gbp"] == pytest.approx(160)


def test_simulator_lets_machines_go_to_the_depot():
    params, weather = tiny_farm()
    result = run_season(weather, params, go_to_depot)
    assert result["total_gbp"] == 0
    assert (result["harvesting"] == -1).all()


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


def test_mpc_finds_the_best_answer_on_the_tiny_farm():
    params, weather = tiny_farm()
    assert run_season(weather, params, plan_mpc)["total_gbp"] == pytest.approx(200)


def test_mpc_cuts_before_the_rain():
    params, weather = rain_farm()
    assert run_season(weather, params, plan_mpc)["total_gbp"] == pytest.approx(192.25)


def test_mpc_leaves_a_field_mid_job_and_comes_back():
    """Field 0: 20 ha at £50/ha. Field 1: 2 ha at £200/ha, but only dry in hours 4 and 5.

    Staying on field 0 makes £500. Best: cut field 0 for 3 hours, drive (hour 3), cut field 1,
    drive back (hour 6), cut field 0 again: £700 - £20 driving = £680.
    """
    params = one_combine_farm(2, [20, 2], start="f0")
    value = np.zeros((2, 10))  # [field, hour]
    value[0] = 50
    value[1, 4:6] = 200
    state = {"remaining_ha": np.array([20.0, 2.0]), "machine_at": np.array([0])}
    schedule = plan_mpc(value, state, params)
    assert schedule[0] == pytest.approx([0, 0, 0, 1, 1, 1, 0, 0, 0, 0])


def test_mpc_waits_out_the_rain_at_the_depot():
    """Dry in hours 0-1 and 10-11, rain in between. Waiting in the field costs 8 x £20 = £160,
    going home and back costs 2 x £10 = £20, so the combine goes home (place 1 = the depot)."""
    params = one_combine_farm(1, [100], start="f0")
    value = np.zeros((1, 12))  # [field, hour]
    value[0, [0, 1, 10, 11]] = 50
    state = {"remaining_ha": np.array([100.0]), "machine_at": np.array([0])}
    schedule = plan_mpc(value, state, params)
    assert schedule[0] == pytest.approx([0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0])


def test_mpc_leaves_drying_grain_for_after_the_plan():
    """10 ha, worth £50/ha in hours 0-5 and £100/ha in hours 6-11 as it dries. With the terminal
    value (90% of the last 6 hours' £100 = £90/ha), cutting in the first 6 hours loses £40/ha, so
    the combine goes home (place 1) and comes back for the dry hours. Without it, it cuts all day.
    """
    params = one_combine_farm(1, [10], start="f0")
    value = np.zeros((1, 12))  # [field, hour]
    value[0, :6], value[0, 6:] = 50, 100
    state = {"remaining_ha": np.array([10.0]), "machine_at": np.array([0])}
    params.update(mpc_terminal_hours=6, mpc_terminal_value_pct=90)
    assert plan_mpc(value, state, params)[0] == pytest.approx([1, 1, 1, 1, 1] + [0] * 7)
    params.update(mpc_terminal_value_pct=0)
    assert plan_mpc(value, state, params)[0, :2] == pytest.approx([0, 0])


def test_mpc_stays_home_when_the_field_is_dry_in_only_half_the_futures():
    """One field worth £30/ha when dry, and dry in one of two forecast members. On the average
    (£15/ha every hour) cutting looks worth it. Played out in both members, an hour in the field
    earns £30 half the time and costs £40 idle the other half: -£5, so it stays at the depot."""
    params = one_combine_farm(1, [100], start="depot")
    params.update(mpc_idle_in_field_gbp_per_hour=40, mpc_scenarios=50)
    by_member = np.zeros((2, 1, 6))  # [member, field, hour]
    by_member[0] = 30
    value = by_member.mean(axis=0)
    state = {"remaining_ha": np.array([100.0]), "machine_at": np.array([1])}
    assert plan_mpc(value, state, params)[0, 0] == 0  # average only: drives to the field
    state["value_by_member"] = by_member
    assert plan_mpc(value, state, params)[0] == pytest.approx([1] * 6)


def test_member_values_average_to_field_values():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    moisture = start_moisture(weather, params)
    by_member = member_values(weather, moisture, params)
    assert by_member.shape == weather["rain_mm"].shape
    assert by_member.mean(axis=0) == pytest.approx(field_values(weather, moisture, params))


def test_mpc_never_puts_two_combines_on_one_field():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    n_fields, n_hours = len(params["fields"]), params["plan_hours"]
    value = field_values(weather, start_moisture(weather, params), params)[:, :n_hours]
    area = np.array([field["area_ha"] for field in params["fields"]], dtype=float)
    at_depot = np.full(len(params["machines"]), n_fields)
    schedule = plan_mpc(value, {"remaining_ha": area, "machine_at": at_depot}, params)
    assert schedule.shape == (len(params["machines"]), n_hours)
    for hour in range(n_hours):
        in_fields = schedule[:, hour][schedule[:, hour] < n_fields]
        assert len(in_fields) == len(set(in_fields))


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

    every_planner = [
        getattr(planners, name) for name in planners.__all__ if name.startswith("plan_")
    ]
    for plan in every_planner:
        assert run_season(weather, params, plan)["total_gbp"] <= bound + 1e-6

    at_depot = np.full(len(params["machines"]), len(params["fields"]))
    schedule = plan_lagrangian(value, {"remaining_ha": area, "machine_at": at_depot}, params)
    assert schedule.shape == (len(params["machines"]), 48)
    for hour in range(48):  # never two combines on one field
        working = schedule[:, hour][schedule[:, hour] != -1]
        assert len(working) == len(set(working))


def test_demo_runs_end_to_end():
    params = demo_params()
    weather = load_forecast(ROOT / "data" / "forecast.csv", params, MOISTURE_CSV)
    result = run_season(weather, params)
    assert result["total_gbp"] > 0
    assert result["remaining_ha"].min() >= 0
    assert result["harvesting"].shape == (len(params["machines"]), params["season_hours"])
    assert len(result["plans"]) == params["season_hours"] // params["sensor_every_hours"]
