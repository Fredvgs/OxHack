"""Tests for the grain moisture model (harvest/moisture.py). Run:  uv run pytest"""

import copy
from pathlib import Path

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
    rain_hours,
    simulate,
    synthetic_weather,
    wb_to_db,
)

CROPS = ["wheat", "barley", "osr"]
FIXTURES = Path(__file__).parent / "fixtures"


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


def no_rain(T):
    return np.zeros(np.shape(T))


@pytest.mark.parametrize("start_pct", [25.0, 8.0])  # drying down, and wetting up
def test_constant_weather_approaches_emc_exponentially(start_pct):
    hours = 500
    T, RH = np.full(hours, 15.0), np.full(hours, 0.7)
    moisture = simulate("wheat", start_pct, T, RH, no_rain(T))

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
    hourly = simulate("barley", 20.0, T, RH, no_rain(T))
    one_step = simulate("barley", 20.0, T[:1], RH[:1], no_rain(T[:1]), dt=10.0)
    assert hourly[-1] == pytest.approx(one_step[0])


def test_unknown_crop_is_rejected():
    T = np.full(3, 15.0)
    with pytest.raises(ValueError):
        simulate("maize", 20.0, T, np.full(3, 0.7), no_rain(T))


def test_constants_can_be_swapped():
    # e.g. dropping in official ASABE D245.7 values: a doubled k_ref dries the grain faster
    faster = copy.deepcopy(CONSTANTS)
    faster["crops"]["wheat"]["k_ref_per_hour"] *= 2
    T, RH = np.full(24, 15.0), np.full(24, 0.5)
    quick = simulate("wheat", 20.0, T, RH, no_rain(T), constants=faster)
    assert quick[-1] < simulate("wheat", 20.0, T, RH, no_rain(T))[-1]


def test_no_rain_matches_the_model_before_rain_was_added():
    # saved from the rain-free simulate() on the demo weather, before the rain rule existed
    baseline = np.load(FIXTURES / "moisture_no_rain_baseline.npz")
    T, RH = baseline["T_c"], baseline["RH"]
    for crop in CROPS:
        moisture = simulate(crop, float(baseline["start_pct"]), T, RH, no_rain(T))
        assert moisture == pytest.approx(baseline[crop], rel=1e-12, abs=1e-12), crop


def test_demo_week_runs_for_every_crop():
    demo = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))["moisture_demo"]
    T, RH, rain = synthetic_weather(demo)
    assert T.shape == RH.shape == rain.shape == (demo["days"] * 24,)
    assert rain_hours(rain).any()  # the demo has some rain to show (above the threshold)
    cap_pct = 100 * db_to_wb(CONSTANTS["rain_max_mc"])
    for crop in CROPS:
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        moisture = simulate(crop, start, T, RH, rain)
        assert moisture.shape == T.shape
        lowest = min(emc_wb_pct(crop, T, RH).min(), start)
        assert np.all((moisture >= lowest) & (moisture <= cap_pct)), crop


def constant_weather_with_rain(rain_hours, hours=None):
    """Mild constant weather, raining for the first rain_hours hours. returns T, RH, rain [hour]"""
    hours = hours or rain_hours
    T, RH = np.full(hours, 15.0), np.full(hours, 0.7)
    rain = np.where(np.arange(hours) < rain_hours, 2.0, 0.0)
    return T, RH, rain


def test_rain_hours_add_a_fixed_rise_in_dry_basis():
    # barley at 16% wb = 0.19048 kg/kg db; 3 rain hours -> 0.19048 + 3 x 0.028 = 0.27448 = 21.54% wb
    assert wb_to_db(0.16) == pytest.approx(0.19048, abs=1e-5)
    moisture = simulate("barley", 16.0, *constant_weather_with_rain(3))
    assert moisture[-1] == pytest.approx(21.54, abs=0.01)
    assert 100 * wb_to_db(moisture / 100) == pytest.approx(
        100 * (0.19048 + 0.028 * np.arange(1, 4)), abs=1e-3
    )


def test_rain_is_capped():
    # 20 rain hours would add 0.56 kg/kg; the cap stops it at 0.52 kg/kg db = 34.21% wb
    moisture = simulate("barley", 16.0, *constant_weather_with_rain(20))
    assert moisture[-1] == pytest.approx(34.21, abs=0.01)
    assert wb_to_db(moisture[-1] / 100) == pytest.approx(0.52)
    assert moisture.max() <= 100 * db_to_wb(0.52) + 1e-9


def test_dry_hours_after_rain_use_the_normal_drying_step():
    T, RH, rain = constant_weather_with_rain(3, hours=6)
    moisture = simulate("wheat", 16.0, T, RH, rain)
    after_rain = simulate("wheat", moisture[2], T[3:], RH[3:], rain[3:])
    assert moisture[3:] == pytest.approx(after_rain)


def with_constants(**changes):
    """A copy of CONSTANTS with top-level values replaced, e.g. rain_threshold_mm=0.0."""
    constants = copy.deepcopy(CONSTANTS)
    constants.update(changes)
    return constants


def with_osr_scale(scale):
    constants = copy.deepcopy(CONSTANTS)
    constants["crops"]["osr"]["rain_rise_scale"] = scale
    return constants


def test_wheat_and_barley_match_the_model_before_the_threshold_change():
    # saved from simulate() on the demo weather (with rain) before rain_threshold_mm became 0.3
    # and rain_rule became rain_rise_scale; with the old threshold, the answers must not move
    saved = np.load(FIXTURES / "moisture_rain_wheat_barley.npz")
    old = with_constants(rain_threshold_mm=float(saved["rain_threshold_mm"]))
    for crop in ["wheat", "barley"]:
        weather = saved["T_c"], saved["RH"], saved["rain_mm"]
        moisture = simulate(crop, float(saved["start_pct"]), *weather, constants=old)
        assert moisture == pytest.approx(saved[crop], rel=1e-12, abs=1e-12), crop


def test_oilseed_rape_rain_hours_add_a_fixed_rise_in_dry_basis():
    # osr at 10% wb = 0.11111 kg/kg db; 3 rain hours -> 0.11111 + 3 x 0.028 = 0.19511 = 16.33% wb
    assert wb_to_db(0.10) == pytest.approx(0.11111, abs=1e-5)
    moisture = simulate("osr", 10.0, *constant_weather_with_rain(3))
    assert moisture[-1] == pytest.approx(16.33, abs=0.01)


def test_oilseed_rape_rain_is_capped():
    moisture = simulate("osr", 10.0, *constant_weather_with_rain(20))
    assert moisture[-1] == pytest.approx(34.21, abs=0.01)
    assert wb_to_db(moisture[-1] / 100) == pytest.approx(0.52)
    assert moisture.max() <= 100 * db_to_wb(0.52) + 1e-9


def test_rain_rise_scale_0_switches_rain_off():
    T, RH, rain = constant_weather_with_rain(5, hours=12)
    off = with_osr_scale(0.0)
    with_rain = simulate("osr", 12.0, T, RH, rain, constants=off)
    assert with_rain == pytest.approx(simulate("osr", 12.0, T, RH, no_rain(T), constants=off))


def test_rain_rise_scale_half_gives_half_the_rise():
    T, RH, rain = constant_weather_with_rain(1)
    start_db = wb_to_db(0.10)
    full = wb_to_db(simulate("osr", 10.0, T, RH, rain)[0] / 100) - start_db
    half = wb_to_db(simulate("osr", 10.0, T, RH, rain, constants=with_osr_scale(0.5))[0] / 100)
    assert half - start_db == pytest.approx(full / 2)


@pytest.mark.parametrize("rain_mm, is_rain", [(0.29, False), (0.30, True), (0.31, True)])
def test_threshold_boundary(rain_mm, is_rain):
    assert CONSTANTS["rain_threshold_mm"] == 0.3
    T, RH, rain = np.full(1, 15.0), np.full(1, 0.7), np.full(1, rain_mm)
    assert rain_hours(rain)[0] == is_rain
    wet = simulate("wheat", 16.0, T, RH, rain)
    dry = simulate("wheat", 16.0, T, RH, no_rain(T))
    assert (wet[0] > dry[0]) == is_rain


def test_threshold_0_still_needs_some_rain():
    zero = with_constants(rain_threshold_mm=0.0)
    assert list(rain_hours([0.0, 0.01], zero)) == [False, True]
    T, RH = np.full(2, 15.0), np.full(2, 0.7)
    moisture = simulate("wheat", 16.0, T, RH, [0.0, 0.01], constants=zero)
    dry = simulate("wheat", 16.0, T, RH, no_rain(T))
    assert moisture[0] == pytest.approx(dry[0])  # 0 mm: a dry hour
    assert moisture[1] > dry[1]  # 0.01 mm: a rain hour


@pytest.mark.parametrize(
    "rain, message",
    [
        (np.zeros(4), "shape"),
        (np.array([0, np.nan, 0]), "NaN"),
        (np.array([0, -0.1, 0]), "negative"),
    ],
)
def test_bad_rain_is_rejected(rain, message):
    T, RH = np.full(3, 15.0), np.full(3, 0.7)
    with pytest.raises(ValueError, match=message):
        simulate("wheat", 16.0, T, RH, rain)


def test_whole_forecast_at_once_matches_one_series_at_a_time():
    T = np.array([[[10.0, 12.0, 15.0], [20.0, 18.0, 16.0]]])  # [member, field, hour]
    RH = np.array([[[0.9, 0.8, 0.7], [0.5, 0.6, 0.7]]])
    rain = np.array([[[0.0, 1.0, 0.0], [0.5, 0.5, 0.0]]])
    for crop in CROPS:
        together = simulate(crop, 18.0, T, RH, rain)
        assert together.shape == T.shape
        for field in range(2):
            one = simulate(crop, 18.0, T[0, field], RH[0, field], rain[0, field])
            assert together[0, field] == pytest.approx(one), crop


def write_forecast(path, rows, columns="hour,member,field,temp_c,humidity_pct,rain_mm"):
    path.write_text(
        columns + "\n" + "".join(",".join(map(str, row)) + "\n" for row in rows), encoding="utf-8"
    )


def test_forecast_csv_gives_moisture_for_every_crop_hour_member_and_field(tmp_path):
    # 2 members x 2 fields x 3 hours, rows deliberately shuffled, rain at hour 1 of member 1
    rows = [
        (hour, member, field, 10 + hour + member, 80 - 5 * hour, 1.5 * (hour == 1 and member == 1))
        for field in ["b_field", "a_field"]
        for hour in [2, 0, 1]
        for member in [1, 0]
    ]
    path = tmp_path / "forecast.csv"
    write_forecast(path, rows)
    table = forecast_moisture(path)
    assert len(table) == len(rows)

    # member 1 of a_field matches running that one series by hand, rain included
    one = table[(table["member"] == 1) & (table["field"] == "a_field")]
    assert list(one["hour"]) == [0, 1, 2]
    assert list(one["rain_mm"]) == [0, 1.5, 0]
    for crop in CROPS:
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        weather = one["temp_c"].to_numpy(), one["humidity_pct"] / 100, one["rain_mm"]
        expected = simulate(crop, start, *weather)
        assert one[f"{crop}_moisture_pct"].to_numpy() == pytest.approx(expected)


def test_forecast_csv_without_rain_is_rejected(tmp_path):
    path = tmp_path / "forecast.csv"
    write_forecast(
        path, [(0, 0, "a_field", 10, 80)], columns="hour,member,field,temp_c,humidity_pct"
    )
    with pytest.raises(ValueError, match="rain_mm"):
        forecast_moisture(path)
