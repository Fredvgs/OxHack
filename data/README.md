# data/: prediction data

`forecast.csv` is the weather forecast the pipeline runs on: 51 possible futures ("members")
for every field and hour. The committed copy is real ECMWF IFS ensemble data at its native 9 km
resolution (`ecmwf_ifs_europe_ensemble`) from the
[Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api), `forecast_hours` from
`forecast_start` in `params.yaml`. At 9 km each field gets its own weather (the 25 km
`ecmwf_ifs025` grid shares cells between nearby fields). The 9 km model stops ~144 h after its
run time, so keep `forecast_hours` inside that, and at least `season_hours + plan_hours`.

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
0,0,kidlington,10.9,68,0.0
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
