"""Tests for the grain moisture model (harvest/moisture.py). Run:  uv run pytest"""

import copy

import numpy as np
import pytest
import yaml

from harvest.moisture import (
    CONSTANTS,
    PARAMS_PATH,
    db_to_wb,
    emc_db,
    forecast_moisture,
    k_of_T,
    simulate,
    synthetic_weather,
    wb_to_db,
)

CROPS = ["wheat", "barley", "osr"]


def emc_wb_pct(crop, T, RH):
    return 100 * db_to_wb(emc_db(crop, T, RH))


@pytest.mark.parametrize(
    "T, RH, expected",  # expected EMC, % wet basis, for wheat / barley / oilseed rape
    [
        (10, 0.60, [14.2, 12.1, 8.9]),  # PAMI tables
        (15, 0.72, [15.6, 13.8, 10.2]),
        (15, 0.95, [21.1, 19.6, 16.4]),
    ],
)
def test_emc_matches_the_pami_tables(T, RH, expected):
    for crop, emc in zip(CROPS, expected):
        assert emc_wb_pct(crop, T, RH) == pytest.approx(emc, abs=0.1), crop


def test_emc_and_k_work_on_arrays():
    T = np.array([[5.0, 15.0], [25.0, 30.0]])
    RH = np.full(T.shape, 0.7)
    assert emc_db("wheat", T, RH).shape == T.shape
    assert k_of_T("wheat", T).shape == T.shape
    # warmer air holds the grain drier, and dries it faster
    assert np.all(np.diff(emc_db("wheat", T, RH).ravel()) < 0)
    assert np.all(np.diff(k_of_T("wheat", T).ravel()) > 0)


def test_emc_is_finite_at_saturation():
    # RH = 1 would divide by log(0); clipping to rh_max gives the same answer as RH = rh_max
    assert emc_db("barley", 15, 1.0) == pytest.approx(emc_db("barley", 15, CONSTANTS["rh_max"]))


def test_k_at_15_degrees():
    for crop, k in zip(CROPS, [0.023, 0.026, 0.049]):
        assert k_of_T(crop, 15) == pytest.approx(k, abs=0.001), crop


def test_k_equals_k_ref_at_the_reference_temperature():
    for crop in CROPS:
        c = CONSTANTS["crops"][crop]
        assert k_of_T(crop, c["t_ref_c"]) == pytest.approx(c["k_ref_per_hour"])


def test_wet_and_dry_basis_round_trip():
    m_wb = np.linspace(0.05, 0.35, 7)
    assert db_to_wb(wb_to_db(m_wb)) == pytest.approx(m_wb)
    assert wb_to_db(0.15) == pytest.approx(0.15 / 0.85)


@pytest.mark.parametrize("start_pct", [25.0, 8.0])  # drying down, and wetting up
def test_constant_weather_approaches_emc_exponentially(start_pct):
    hours = 500
    T, RH = np.full(hours, 15.0), np.full(hours, 0.7)
    moisture = simulate("wheat", start_pct, T, RH)

    me = emc_db("wheat", 15.0, 0.7)
    k = k_of_T("wheat", 15.0)
    t = np.arange(1, hours + 1)
    exact_db = me + (wb_to_db(start_pct / 100) - me) * np.exp(-k * t)
    assert moisture == pytest.approx(100 * db_to_wb(exact_db))
    assert moisture[-1] == pytest.approx(100 * db_to_wb(me), abs=1e-3)
    gap = np.abs(moisture - 100 * db_to_wb(me))
    assert np.all(np.diff(gap) < 0)  # always closing in, never overshooting


def test_time_step_does_not_change_constant_weather_answer():
    # with constant weather, ten 1-hour steps land where one 10-hour step does
    T, RH = np.full(10, 20.0), np.full(10, 0.5)
    hourly = simulate("barley", 20.0, T, RH)
    one_step = simulate("barley", 20.0, T[:1], RH[:1], dt=10.0)
    assert hourly[-1] == pytest.approx(one_step[0])


def test_unknown_crop_is_rejected():
    with pytest.raises(ValueError):
        simulate("maize", 20.0, np.full(3, 15.0), np.full(3, 0.7))


def test_constants_can_be_swapped():
    # e.g. dropping in official ASABE D245.7 values: a doubled k_ref dries the grain faster
    faster = copy.deepcopy(CONSTANTS)
    faster["crops"]["wheat"]["k_ref_per_hour"] *= 2
    T, RH = np.full(24, 15.0), np.full(24, 0.5)
    assert simulate("wheat", 20.0, T, RH, constants=faster)[-1] < simulate("wheat", 20.0, T, RH)[-1]


def test_demo_week_runs_for_every_crop():
    demo = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))["moisture_demo"]
    T, RH = synthetic_weather(demo)
    assert T.shape == RH.shape == (demo["days"] * 24,)
    for crop in CROPS:
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        moisture = simulate(crop, start, T, RH)
        assert moisture.shape == T.shape
        # moisture only ever moves towards EMC, so it stays between the start and the EMC extremes
        emc = emc_wb_pct(crop, T, RH)
        lowest = min(emc.min(), start)
        highest = max(emc.max(), start)
        assert np.all((moisture >= lowest) & (moisture <= highest)), crop


def test_whole_forecast_at_once_matches_one_series_at_a_time():
    T = np.array([[10.0, 12.0, 15.0], [20.0, 18.0, 16.0]])  # [series, hour]
    RH = np.array([[0.9, 0.8, 0.7], [0.5, 0.6, 0.7]])
    together = simulate("osr", 18.0, T, RH)
    for row in range(2):
        assert together[row] == pytest.approx(simulate("osr", 18.0, T[row], RH[row]))


def test_forecast_csv_gives_moisture_for_every_crop_hour_member_and_field(tmp_path):
    # 2 members x 2 fields x 3 hours, rows deliberately shuffled
    rows = [
        (hour, member, field, 10 + hour + member, 80 - 5 * hour)
        for field in ["b_field", "a_field"]
        for hour in [2, 0, 1]
        for member in [1, 0]
    ]
    path = tmp_path / "forecast.csv"
    path.write_text(
        "hour,member,field,temp_c,humidity_pct,rain_mm\n"
        + "".join(f"{h},{m},{f},{t},{rh},0.0\n" for h, m, f, t, rh in rows),
        encoding="utf-8",
    )
    table = forecast_moisture(path)
    assert len(table) == len(rows)

    # member 1 of a_field matches running that one series by hand
    one = table[(table["member"] == 1) & (table["field"] == "a_field")]
    assert list(one["hour"]) == [0, 1, 2]
    for crop in CROPS:
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        expected = simulate(crop, start, one["temp_c"].to_numpy(), one["humidity_pct"] / 100)
        assert one[f"{crop}_moisture_pct"].to_numpy() == pytest.approx(expected)
