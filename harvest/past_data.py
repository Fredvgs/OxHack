"""Past forecasts, and the weather that really followed, for replaying a past season (replay.py).

Past forecasts: dynamical.org keeps every 00 UTC run of the ECMWF ensemble (51 members, 0.25°
grid) since 2024-04-01: https://dynamical.org/catalog/ecmwf-ifs-ens-forecast-15-day-0-25-degree/
Each run is downloaded the first time it's needed and saved in data/past_forecasts/, so a replay
only downloads once. The archive has a value every 3 hours (every 6 after 144 h); to_hourly()
turns that into one value per hour.

Past weather: Open-Meteo's archive of ECMWF's own 9 km forecasts, the first hours of each run
stitched together, hourly: https://open-meteo.com/en/docs/historical-forecast-api
"""

from pathlib import Path

import dynamical_catalog
import numpy as np
import pandas as pd
import requests
import xarray as xr

from harvest.forecast import sort_by_field

ROOT = Path(__file__).parent.parent
FORECAST_DIR = ROOT / "data" / "past_forecasts"
WEATHER_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
SECONDS_PER_HOUR = 3600
ONE_HOUR = pd.Timedelta(hours=1)

# archive variable -> column in the saved run. Precipitation is a rate (mm/s, the same as
# kg m-2 s-1), averaged since the step before. It includes snow, which harvest weather rarely has.
ARCHIVE_VARIABLES = {
    "temperature_2m": "temp_c",
    "dew_point_temperature_2m": "dew_point_c",
    "precipitation_surface": "precip_mm_per_s",
}
# Open-Meteo hourly variable -> our column
WEATHER_VARIABLES = {
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "rain_mm",  # rain + showers + snow, to match the forecast's precipitation
}


def open_archive(params):
    """Open the archive of past forecasts (takes a few seconds; data is only fetched when read)."""
    return dynamical_catalog.open(params["past_forecast_dataset"], chunks=None)


def forecast_runs(archive):
    """Start times of every run in the archive, oldest first (UTC)."""
    return pd.DatetimeIndex(archive["init_time"].values)


def published_runs(time, runs, params):
    """The runs a farmer could have had at `time`, oldest first.

    A run is only published forecast_delay_hours after it starts.
    """
    return runs[runs + pd.Timedelta(hours=params["forecast_delay_hours"]) <= time]


def season_dates(start, end, runs, params, now):
    """First hour and length of the replay, cut to what the archives have.

    Prints a warning for every cut, like the past weather download does.
    start, end: first and last day to replay (whole days, UTC, end included)
    runs:       start times of the forecast runs in the archive (from forecast_runs)
    now:        the current time, UTC
    returns: (first hour as a Timestamp, number of hours)
    """
    first = start.normalize()
    last = end.normalize() + pd.Timedelta(hours=23)  # the hour from 23:00 to midnight
    delay = pd.Timedelta(hours=params["forecast_delay_hours"])

    if first < runs[0] + delay:
        print(
            f"warning: the forecast archive starts with the {runs[0]:%Y-%m-%d %H:%M} run, "
            f"published at {runs[0] + delay:%Y-%m-%d %H:%M}, so the replay starts then"
        )
        first = runs[0] + delay
    # hour h is over once h + 1 hour has passed; later hours haven't happened yet
    last_done = now.floor("h") - ONE_HOUR
    if last > last_done:
        print(
            f"warning: the weather after {last_done + ONE_HOUR:%Y-%m-%d %H:%M} UTC hasn't "
            "happened yet, so the replay stops there"
        )
        last = last_done
    # a new run is out every day, so a run that's been out for a day should have a newer one
    if last - (runs[-1] + delay) >= pd.Timedelta(days=1):
        print(
            f"warning: the newest forecast in the archive is the {runs[-1]:%Y-%m-%d %H:%M} run, "
            "so the replay keeps planning with it until the end"
        )
    if last < first:
        raise ValueError(f"Nothing to replay between {start:%Y-%m-%d} and {end:%Y-%m-%d}")
    return first, (last - first) // ONE_HOUR + 1


def past_forecasts(archive, first_hour, params):
    """The function run_with_forecasts asks for forecasts: get_forecast(hour).

    get_forecast(hour) returns the newest run published by that season hour, from that hour on:
    {"temp_c", "humidity_pct", "rain_mm"}: [member, field, hour].
    first_hour: Timestamp of season hour 0
    returns: (get_forecast, runs_used); runs_used fills up as the season runs:
             {season hour: start time of the run that was new at that hour}
    """
    runs = forecast_runs(archive)
    loaded = {}  # run start time -> {name: [member, field, hour since the run started]} or None
    runs_used = {}

    def get_forecast(hour):
        time = first_hour + hour * ONE_HOUR
        run = None
        for candidate in reversed(published_runs(time, runs, params)):  # newest first
            if candidate not in loaded:
                loaded[candidate] = load_run(archive, candidate, params)
                if loaded[candidate] is None:
                    print(
                        f"warning: the {candidate:%Y-%m-%d %H:%M} run isn't all in the archive "
                        "yet, so the run before it is used"
                    )
            if loaded[candidate] is not None:
                run = candidate
                break
        if run is None:
            raise ValueError(f"No forecast had been published by {time:%Y-%m-%d %H:%M}")
        if run not in runs_used.values():
            print(f"{time:%Y-%m-%d %H:%M}  new forecast: the {run:%Y-%m-%d %H:%M} run")
            runs_used[hour] = run
        lead = (time - run) // ONE_HOUR  # hours since the run started
        return {name: values[:, :, lead:] for name, values in loaded[run].items()}

    return get_forecast, runs_used


def load_run(archive, run, params):
    """One past run at every field, hourly: {name: [member, field, hour since the run started]}.

    Read from data/past_forecasts/ if it was saved before for the same fields, otherwise
    downloaded and saved there first. None if the archive doesn't have all of it yet.
    """
    path = FORECAST_DIR / params["past_forecast_dataset"] / f"{run:%Y-%m-%dT%H}.csv"
    table = saved_run(path, params)
    if table is None:
        print(f"downloading the {run:%Y-%m-%d %H:%M} run...")
        table = download_run(archive, run, params)
        if not is_complete(table):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
    steps = to_arrays(table, ARCHIVE_VARIABLES.values(), params)  # [member, field, step]
    return to_hourly(steps, np.sort(table["hour"].unique()), params)


def saved_run(path, params):
    """The run saved at path, or None if there isn't one for these fields' lat/lon."""
    if not path.exists():
        return None
    table = pd.read_csv(path)
    saved = table.groupby("field")[["lat", "lon"]].first()  # one lat/lon per field name
    for field in params["fields"]:
        if field["name"] not in saved.index:
            return None
        if tuple(saved.loc[field["name"]]) != (field["lat"], field["lon"]):
            return None  # the field has moved since: download it again
    return table


def download_run(archive, run, params):
    """One run at every field's nearest grid point, as the archive has it.

    returns: a table with one row per step, member and field: hour (since the run started: 0, 3,
             6, ...), member, field, lat, lon (the field's), temp_c, dew_point_c, precip_mm_per_s
    """
    fields = params["fields"]
    lats = xr.DataArray([field["lat"] for field in fields], dims="field")
    lons = xr.DataArray([field["lon"] for field in fields], dims="field")
    points = archive[list(ARCHIVE_VARIABLES)].sel(init_time=run)
    points = points.sel(latitude=lats, longitude=lons, method="nearest")
    points = points.transpose("ensemble_member", "field", "lead_time").load()  # downloads it
    step_hours = points["lead_time"].values // np.timedelta64(1, "h")

    names = [field["name"] for field in fields]
    members = range(points.sizes["ensemble_member"])
    table = pd.MultiIndex.from_product(
        [members, names, step_hours], names=["member", "field", "hour"]
    ).to_frame(index=False)
    table["lat"] = table["field"].map({field["name"]: field["lat"] for field in fields})
    table["lon"] = table["field"].map({field["name"]: field["lon"] for field in fields})
    for variable, column in ARCHIVE_VARIABLES.items():
        table[column] = points[variable].values.ravel()  # [member, field, step]: same row order
    return table


def is_complete(table):
    """False if a run has missing values, because it's still being added to the archive.

    Precipitation is always missing at hour 0 (it's the rate since the step before), so that's fine.
    """
    values = table[list(ARCHIVE_VARIABLES.values())].copy()
    values.loc[table["hour"] == 0, "precip_mm_per_s"] = 0
    return not values.isna().any().any()


def to_arrays(table, columns, params):
    """A table with member, field and hour columns -> {column: [member, field, hour]}."""
    table, shape = sort_by_field(table, params)
    return {column: table[column].to_numpy(dtype=float).reshape(shape) for column in columns}


def to_hourly(steps, step_hours, params):
    """Forecast steps (every 3 or 6 hours) -> one value per hour.

    steps:      {"temp_c", "dew_point_c", "precip_mm_per_s"}: [member, field, step]
    step_hours: [step]  hours since the run started: 0, 3, 6, ...
    returns: {"temp_c", "humidity_pct", "rain_mm"}: [member, field, hour], hour h being the
             hour from h to h + 1
    """
    hours = np.arange(int(step_hours[-1]))
    temp_c = interpolate(steps["temp_c"], step_hours, hours)
    dew_point_c = interpolate(steps["dew_point_c"], step_hours, hours)
    # each step has the average rate since the step before, so hour h gets the rate of the
    # first step at or after h + 1
    covering = np.searchsorted(step_hours, hours + 1)
    rain_mm = steps["precip_mm_per_s"][:, :, covering] * SECONDS_PER_HOUR
    return {
        "temp_c": temp_c,
        "humidity_pct": relative_humidity_pct(temp_c, dew_point_c, params),
        "rain_mm": np.clip(rain_mm, 0, None),  # no negative rain from rounding
    }


def interpolate(values, step_hours, hours):
    """Straight lines between the steps. values: [..., step] -> [..., hour]."""
    rows = values.reshape(-1, values.shape[-1])
    hourly = np.array([np.interp(hours, step_hours, row) for row in rows])
    return hourly.reshape(values.shape[:-1] + (len(hours),))


def relative_humidity_pct(temp_c, dew_point_c, params):
    """Relative humidity (%) from temperature and dew point (°C, any shape): Magnus formula.

    The air holds the water it would hold at saturation at the dew point.
    """
    a, b = params["magnus_a"], params["magnus_b_c"]
    humidity = 100 * np.exp(a * dew_point_c / (b + dew_point_c) - a * temp_c / (b + temp_c))
    return np.minimum(humidity, 100)


def past_weather(first_hour, n_hours, params):
    """The weather that really happened at every field, hourly from first_hour.

    returns: {"temp_c", "humidity_pct", "rain_mm"}: [1, field, hour] (one member: one past)
    """
    fields = params["fields"]
    # up to one hour past the end: Open-Meteo gives the rain of the hour BEFORE each time
    end = first_hour + n_hours * ONE_HOUR
    response = requests.get(
        WEATHER_URL,
        timeout=60,
        params={
            "latitude": ",".join(str(field["lat"]) for field in fields),
            "longitude": ",".join(str(field["lon"]) for field in fields),
            "hourly": ",".join(WEATHER_VARIABLES),
            "models": params["past_weather_model"],
            "start_date": f"{first_hour:%Y-%m-%d}",
            "end_date": f"{end:%Y-%m-%d}",
        },
    )
    response.raise_for_status()
    locations = response.json()
    if isinstance(locations, dict):  # one field: the API returns a dict, not a list
        locations = [locations]
    return weather_from_open_meteo(locations, first_hour, n_hours, params)


def weather_from_open_meteo(locations, first_hour, n_hours, params):
    """Open-Meteo's answer (one dict per field) -> {name: [1, field, hour]} from first_hour.

    Hour h is the hour from h to h + 1, so its rain is the value Open-Meteo gives at h + 1.
    """
    first = (first_hour - first_hour.normalize()) // ONE_HOUR  # the answer starts at midnight
    rows = []
    for field, location in zip(params["fields"], locations):
        hourly = location["hourly"]
        for hour in range(n_hours):
            rows.append(
                {
                    "hour": hour,
                    "member": 0,
                    "field": field["name"],
                    "temp_c": hourly["temperature_2m"][first + hour],
                    "humidity_pct": hourly["relative_humidity_2m"][first + hour],
                    "rain_mm": hourly["precipitation"][first + hour + 1],
                }
            )
    table = pd.DataFrame(rows)
    table["rain_mm"] = table["rain_mm"].fillna(0).clip(lower=0)  # the API rounds tiny rain to -0.1
    for column in ["temp_c", "humidity_pct"]:
        table[column] = table[column].ffill().bfill()  # fill the odd missing hour
    return to_arrays(table, WEATHER_VARIABLES.values(), params)
