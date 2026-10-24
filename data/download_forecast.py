"""Download a fresh ensemble weather forecast from Open-Meteo into data/forecast.csv.

Run from the repo root (needs internet):  uv run python data/download_forecast.py
Uses each field's lat/lon and the forecast_* settings in params.yaml.
"""

from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).parent.parent
API_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
# Open-Meteo hourly variable -> our CSV column
API_VARIABLES = {
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "humidity_pct",
    "rain": "rain_mm",
}


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    fields = params["fields"]
    start = pd.Timestamp(params["forecast_start"])
    end = start + pd.Timedelta(hours=params["forecast_hours"] - 1)
    response = requests.get(
        API_URL,
        timeout=30,
        params={
            "latitude": ",".join(str(field["lat"]) for field in fields),
            "longitude": ",".join(str(field["lon"]) for field in fields),
            "hourly": ",".join(API_VARIABLES),
            "models": params["forecast_model"],
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        },
    )
    response.raise_for_status()
    locations = response.json()
    if isinstance(locations, dict):  # one field: the API returns a dict, not a list
        locations = [locations]

    rows = []
    for field, location in zip(fields, locations):
        hourly = location["hourly"]
        n_members = 1 + sum(key.startswith("rain_member") for key in hourly)
        for member in range(n_members):
            suffix = "" if member == 0 else f"_member{member:02d}"  # member 0 = main run
            for hour in range(len(hourly["time"])):
                row = {"hour": hour, "member": member, "field": field["name"]}
                for api_name, column in API_VARIABLES.items():
                    row[column] = hourly[api_name + suffix][hour]
                rows.append(row)

    table = pd.DataFrame(rows)
    table["rain_mm"] = table["rain_mm"].fillna(0).clip(lower=0)  # the API rounds tiny values to -0.1
    for column in ["temp_c", "humidity_pct"]:
        table[column] = table[column].ffill().bfill()  # fill the odd missing hour
    table.to_csv(ROOT / "data" / "forecast.csv", index=False)
    print(f"saved {len(table)} rows to data/forecast.csv")


if __name__ == "__main__":
    main()
