"""Download the weather of the past few weeks from Open-Meteo into data/past_weather.csv.

Run from the repo root (needs internet):
    uv run python data/download_past_weather.py                         the past_weather_days
                                                                        before forecast_start
    uv run python data/download_past_weather.py 2026-10-01 2026-10-20   your own dates (inclusive)

This is the weather that already happened, so there's one best estimate and no ensemble members.
Same 9 km grid as the forecast (past_weather_model in params.yaml).

Dates that aren't available are cut off with a warning. Open-Meteo has about 3 months back to
about 2 weeks ahead, and ecmwf_ifs itself only keeps about the last 6 weeks.
"""

import re
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml
from download_forecast import API_VARIABLES

ROOT = Path(__file__).parent.parent
API_URL = "https://api.open-meteo.com/v1/forecast"  # the ensemble API keeps no past data


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    if len(sys.argv) == 3:
        start, end = pd.Timestamp(sys.argv[1]), pd.Timestamp(sys.argv[2])
    else:
        # the whole days just before the forecast starts
        end = pd.Timestamp(params["forecast_start"]).normalize() - pd.Timedelta(days=1)
        start = end - pd.Timedelta(days=params["past_weather_days"] - 1)

    locations = download_available(params, start, end)
    if isinstance(locations, dict):  # one field: the API returns a dict, not a list
        locations = [locations]

    rows = []
    for field, location in zip(params["fields"], locations):
        hourly = location["hourly"]
        for hour, time in enumerate(hourly["time"]):
            row = {"time": time, "field": field["name"]}
            for api_name, column in API_VARIABLES.items():
                row[column] = hourly[api_name][hour]
            rows.append(row)

    table = trim_empty_hours(pd.DataFrame(rows))
    table["rain_mm"] = table["rain_mm"].fillna(0).clip(lower=0)
    for column in ["temp_c", "humidity_pct"]:
        table[column] = table[column].ffill().bfill()  # fill the odd missing hour
    table.to_csv(ROOT / "data" / "past_weather.csv", index=False)
    print(
        f"saved {len(table)} rows ({table['time'].min()} to {table['time'].max()}) "
        "to data/past_weather.csv"
    )


def trim_empty_hours(table):
    """Drop hours at the start and end that the model has no data for.

    Within the dates Open-Meteo allows, the model may still keep less history, and the API
    answers those hours with nulls instead of an error.
    """
    columns = list(API_VARIABLES.values())
    has_data = table[columns].notna().any(axis=1).groupby(table["time"]).any()  # [time] bool
    times = has_data.index[has_data]  # ISO strings, so they sort in time order
    if len(times) == 0:
        raise ValueError("Open-Meteo sent no data for these dates")
    kept = table[(table["time"] >= times.min()) & (table["time"] <= times.max())]
    if len(kept) < len(table):
        print(
            f"warning: no data before {times.min()} or after {times.max()}, so those are left out"
        )
    return kept.reset_index(drop=True)


def request_weather(params, start, end):
    """Ask Open-Meteo for hourly weather at every field, start to end (whole days, inclusive)."""
    fields = params["fields"]
    return requests.get(
        API_URL,
        timeout=30,
        params={
            "latitude": ",".join(str(field["lat"]) for field in fields),
            "longitude": ",".join(str(field["lon"]) for field in fields),
            "hourly": ",".join(API_VARIABLES),
            "models": params["past_weather_model"],
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
        },
    )


def allowed_dates(response):
    """If the API refused our dates, the (first, last) dates it does have. Otherwise None.

    It refuses with a message like "Parameter 'start_date' is out of allowed range from
    2026-07-23 to 2026-11-08", so we read the range from there.
    """
    if response.status_code != 400:
        return None
    found = re.search(r"allowed range from (\S+) to (\S+)", response.json().get("reason", ""))
    if found is None:
        return None
    return pd.Timestamp(found[1]), pd.Timestamp(found[2])


def download_available(params, start, end):
    """Download start to end. Dates Open-Meteo doesn't have are dropped, with a warning."""
    response = request_weather(params, start, end)
    allowed = allowed_dates(response)
    if allowed is not None:
        first, last = allowed
        new_start, new_end = max(start, first), min(end, last)
        if new_start > new_end:
            raise ValueError(
                f"No weather for {start:%Y-%m-%d} to {end:%Y-%m-%d}: "
                f"Open-Meteo only has {first:%Y-%m-%d} to {last:%Y-%m-%d}"
            )
        print(
            f"warning: Open-Meteo only has {first:%Y-%m-%d} to {last:%Y-%m-%d}, "
            f"so downloading {new_start:%Y-%m-%d} to {new_end:%Y-%m-%d} instead"
        )
        response = request_weather(params, new_start, new_end)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    main()
