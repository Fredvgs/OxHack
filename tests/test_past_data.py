"""Tests for harvest/past_data.py (past forecasts and past weather), all without the internet.

Run:  uv run pytest
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from harvest import past_data
from harvest.past_data import (
    is_complete,
    load_run,
    past_forecasts,
    published_runs,
    relative_humidity_pct,
    saved_run,
    season_dates,
    to_hourly,
    weather_from_open_meteo,
)

ROOT = Path(__file__).parent.parent


def demo_params():
    return yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))


def two_fields(params):
    params["fields"] = [
        {"name": "f0", "crop": "wheat", "area_ha": 1, "lat": 50.0, "lon": -1.0},
        {"name": "f1", "crop": "barley", "area_ha": 1, "lat": 52.5, "lon": 13.4},
    ]
    return params


def test_forecast_steps_become_hours():
    """Steps 3 then 6 hours apart: temperature goes in straight lines, and each step's rain rate
    (the average since the step before) fills the hours since the step before."""
    params = demo_params()
    step_hours = np.array([0, 3, 6, 12])
    steps = {  # [member, field, step]
        "temp_c": np.array([[[0.0, 3.0, 6.0, 12.0]]]),
        "dew_point_c": np.array([[[0.0, 3.0, 6.0, 12.0]]]),
        "precip_mm_per_s": np.array([[[np.nan, 1.0, 2.0, 3.0]]]) / 3600,  # 1, 2, 3 mm an hour
    }
    hourly = to_hourly(steps, step_hours, params)
    assert hourly["temp_c"][0, 0] == pytest.approx(np.arange(12))
    assert hourly["rain_mm"][0, 0] == pytest.approx([1] * 3 + [2] * 3 + [3] * 6)
    assert hourly["humidity_pct"][0, 0] == pytest.approx(100)  # dew point = temperature


def test_humidity_from_dew_point():
    params = demo_params()
    # 20 °C air with a 10 °C dew point holds about half the water it could (tables: 52.5%)
    assert relative_humidity_pct(20.0, 10.0, params) == pytest.approx(52.5, abs=0.1)
    saturated = relative_humidity_pct(np.array([5.0, 25.0]), np.array([5.0, 25.0]), params)
    assert saturated == pytest.approx(100)


def test_a_run_is_only_used_once_it_is_published():
    params = demo_params()
    params["forecast_delay_hours"] = 8
    runs = pd.date_range("2026-10-10", periods=3, freq="D")  # 00 UTC every day
    assert published_runs(pd.Timestamp("2026-10-11 07:00"), runs, params)[-1] == runs[0]
    assert published_runs(pd.Timestamp("2026-10-11 08:00"), runs, params)[-1] == runs[1]
    assert len(published_runs(pd.Timestamp("2026-10-10 07:00"), runs, params)) == 0


def test_replay_dates_are_cut_to_what_the_archives_have(capsys):
    params = demo_params()
    params["forecast_delay_hours"] = 8
    runs = pd.date_range("2024-04-01", "2026-10-25", freq="D")
    now = pd.Timestamp("2026-10-25 09:30")

    days = pd.Timestamp("2026-10-10"), pd.Timestamp("2026-10-12")
    assert season_dates(*days, runs, params, now) == (pd.Timestamp("2026-10-10"), 72)  # 3 days
    assert "warning" not in capsys.readouterr().out

    # starts before the archive and ends after now: both cut, with a warning each
    days = pd.Timestamp("2024-03-01"), pd.Timestamp("2026-10-25")
    first, n_hours = season_dates(*days, runs, params, now)
    assert first == pd.Timestamp("2024-04-01 08:00")  # when the first run was published
    assert first + pd.Timedelta(hours=n_hours) == pd.Timestamp("2026-10-25 09:00")  # last full hour
    assert capsys.readouterr().out.count("warning") == 2

    # the archive is missing the newest run: still replays, with a warning
    season_dates(*days, runs[:-1], params, now)
    assert "newest forecast" in capsys.readouterr().out

    with pytest.raises(ValueError):  # all in the future
        season_dates(pd.Timestamp("2026-10-26"), pd.Timestamp("2026-10-27"), runs, params, now)


def test_get_forecast_uses_the_newest_complete_run(monkeypatch):
    params = two_fields(demo_params())
    params["forecast_delay_hours"] = 8
    runs = pd.date_range("2026-10-10", periods=3, freq="D")  # 00 UTC every day
    archive = {"init_time": SimpleNamespace(values=runs.values)}  # only the run times are read

    def fake_load_run(archive, run, params):  # hour h of every run holds h; the newest is partial
        if run == runs[-1]:
            return None
        return {"temp_c": np.tile(np.arange(48.0), (51, 2, 1))}  # [member, field, hour]

    monkeypatch.setattr(past_data, "load_run", fake_load_run)
    get_forecast, runs_used = past_forecasts(archive, pd.Timestamp("2026-10-11 06:00"), params)
    assert get_forecast(0)["temp_c"][0, 0, 0] == 30  # 11 Oct 06:00: the 10 Oct run, 30 h in
    assert get_forecast(6)["temp_c"][0, 0, 0] == 12  # 12:00: the 11 Oct run is out, 12 h in
    assert get_forecast(30)["temp_c"][0, 0, 0] == 36  # 12 Oct run partial: 11 Oct run, 36 h in
    assert runs_used == {0: runs[0], 6: runs[1]}


def test_a_saved_run_is_read_back_without_downloading(tmp_path, monkeypatch):
    params = two_fields(demo_params())
    monkeypatch.setattr(past_data, "FORECAST_DIR", tmp_path)
    rows = []
    for member in range(2):
        for field in params["fields"]:
            for hour in [6, 0, 3]:  # out of order on purpose
                rows.append(
                    {
                        "member": member,
                        "field": field["name"],
                        "hour": hour,
                        "lat": field["lat"],
                        "lon": field["lon"],
                        "temp_c": 10.0 + hour,
                        "dew_point_c": 5.0,
                        "precip_mm_per_s": np.nan if hour == 0 else 0.0,
                    }
                )
    path = tmp_path / params["past_forecast_dataset"] / "2026-10-10T00.csv"
    path.parent.mkdir()
    pd.DataFrame(rows).to_csv(path, index=False)

    # no archive: it would fail if it tried to download
    weather = load_run(None, pd.Timestamp("2026-10-10"), params)
    assert weather["temp_c"].shape == (2, 2, 6)  # [member, field, hour]
    assert weather["temp_c"][1, 1] == pytest.approx(10 + np.arange(6))
    assert weather["rain_mm"] == pytest.approx(0)

    params["fields"][1]["lat"] = 51.0  # the field moved, so the saved run no longer fits
    assert saved_run(path, params) is None


def test_runs_still_being_added_are_spotted():
    table = pd.DataFrame(
        {
            "hour": [0, 3, 6],
            "temp_c": [1.0, 2.0, 3.0],
            "dew_point_c": [0.0, 0.0, 0.0],
            "precip_mm_per_s": [np.nan, 0.0, 0.0],  # never any rain rate at hour 0
        }
    )
    assert is_complete(table)
    table.loc[2, "temp_c"] = np.nan
    assert not is_complete(table)


def test_past_weather_gives_each_hour_the_rain_that_fell_during_it():
    """Open-Meteo reports an hour's rain at its END: 06:00-07:00 is the value at 07:00."""
    params = two_fields(demo_params())
    locations = [
        {
            "hourly": {
                "temperature_2m": [float(hour) for hour in range(48)],  # = hour of the answer
                "relative_humidity_2m": [80.0] * 48,
                "precipitation": [float(hour) + 100 * f for hour in range(48)],
            }
        }
        for f in range(2)
    ]
    weather = weather_from_open_meteo(locations, pd.Timestamp("2026-10-10 06:00"), 3, params)
    assert weather["rain_mm"].shape == (1, 2, 3)  # [member, field, hour]
    assert weather["temp_c"][0, 0] == pytest.approx([6, 7, 8])  # starts at 06:00
    assert weather["rain_mm"][0, 0] == pytest.approx([7, 8, 9])
    assert weather["rain_mm"][0, 1] == pytest.approx([107, 108, 109])
