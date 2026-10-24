# data/: prediction data

`forecast.csv` is the weather forecast the pipeline runs on: 51 possible futures ("members")
for every field and hour. The committed copy is real ECMWF IFS ensemble data at its native 9 km
resolution (`ecmwf_ifs_europe_ensemble`) from the
[Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api), `forecast_hours` from
`forecast_start` in `params.yaml`. The 9 km model covers Europe only and stops ~144 h after its
run time, so keep `forecast_hours` inside that, and at least `season_hours`.

The demo fields borrow weather from places across Europe (Inverness to Ukraine), because fields
close together all get the same weather. Their `lat`/`lon` only pick the weather; driving times
come from `travel_hours`.

## Format

One row per hour, member and field:

| column | meaning | unit |
|---|---|---|
| `hour` | hours since the forecast start: 0, 1, 2, ... | hours |
| `member` | which forecast member: 0 = main run, 1 to 50 = variations | |
| `field` | field name, matching `name` in `params.yaml` | |
| `temp_c` | air temperature at 2 m | °C |
| `humidity_pct` | relative humidity at 2 m | % |
| `rain_mm` | rain during that hour (not snow or showers) | mm |

```
hour,member,field,temp_c,humidity_pct,rain_mm
0,0,inverness_uk,10.9,68,0.0
```

Every field in `params.yaml` needs the same set of members and hours. Extra columns are ignored.

## Using your own predictions

Either write a CSV in the format above, or change `load_forecast()` in `harvest/forecast.py` to
read your format. It must still return arrays shaped `[member, field, hour]` (see
`harvest/README.md`).

## Getting a fresh forecast (needs internet)

```bash
uv run python data/download_forecast.py
```

This overwrites `forecast.csv` using the fields' `lat`/`lon` and the `forecast_*` settings in
`params.yaml`.

## Past weather (needs internet)

```bash
uv run python data/download_past_weather.py                         # past_weather_days before forecast_start
uv run python data/download_past_weather.py 2026-10-01 2026-10-20   # your own dates, inclusive
```

Writes `past_weather.csv`: one row per hour and field, the weather that already happened (one best
estimate, so no `member` column). It comes from the `past_weather_model` in `params.yaml`, which
uses the same 9 km grid as the forecast. The ensemble API keeps no past data.

| column | meaning | unit |
|---|---|---|
| `time` | UTC hour, e.g. `2026-10-04T00:00` | |
| `field` | field name, matching `name` in `params.yaml` | |
| `temp_c` | air temperature at 2 m | °C |
| `humidity_pct` | relative humidity at 2 m | % |
| `rain_mm` | rain during that hour | mm |

Dates that aren't available are cut off with a warning, and the script stops if nothing is left.
Open-Meteo has about 3 months back to about 2 weeks ahead, but `ecmwf_ifs` only keeps about the
last 6 weeks.
