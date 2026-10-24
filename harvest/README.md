# harvest/: the pipeline

Four files, one job each. To swap a piece out, write your own version of the function with the
**same inputs and outputs** listed below, and everything else keeps working.

Letters used for array sizes (numbers are for the demo):

| Letter | Meaning | Demo |
|---|---|---|
| `M` | forecast members (possible futures) | 51 in the CSV, 50 after one is held back as "truth" |
| `F` | fields, in the order of `fields` in `params.yaml` | 6 |
| `K` | machines, in the order of `machines` in `params.yaml` | 3 |
| `H` | hours | 168 in the CSV, 48 per plan, 48 in the season |

`params` is always the dict loaded from `params.yaml`.

---

## 1. `forecast.py`: `load_forecast(path, params)`

Reads the prediction data.

| | Name | Type / shape | Meaning |
|---|---|---|---|
| in | `path` | file path | the CSV (format in `data/README.md`) |
| in | `params` | dict | uses `params["fields"]` for the field order |
| out | `weather` | dict of 2 arrays | `weather["rain_mm"]`: `[M, F, H]` rain per hour, mm |
| | | | `weather["humidity_pct"]`: `[M, F, H]` relative humidity, % |

## 2. `value.py`: `field_values(weather, start_moisture, params, first_hour=0)`

The value function: what is a field worth if we harvest it in a given hour?

| | Name | Type / shape | Meaning |
|---|---|---|---|
| in | `weather` | dict of `[M, F, H]` arrays | the forecast for the hours being planned |
| in | `start_moisture` | `[F]` | latest grain moisture reading per field, % |
| in | `first_hour` | int | season hour of the first column (for the "crop loss over time" part) |
| out | `value` | `[F, H]` | expected £ per hectare if harvested in that hour, averaged over members. 0 means "can't or shouldn't harvest" |

Uses a helper, **`predict_moisture(start_moisture, weather, params)`**:
in `[F]` and `[M, F, H]`, out `[M, F, H]` grain moisture (%) at the start of each hour.
The simulator also uses it to get the "true" moisture that the sensor reads.

And **`start_moisture(weather, params)`**: in `[M, F, H]`, out `[F]` grain moisture (%) of each
field at hour 0. This is where the moisture vs time graph plugs in. For now it returns the
placeholder `temp_start_moisture_pct` for every field.

## 3. `planner.py`: `plan(value, state, params)`

Decides which field each machine works on, hour by hour.

| | Name | Type / shape | Meaning |
|---|---|---|---|
| in | `value` | `[F, H]` | from `field_values` |
| in | `state["remaining_ha"]` | `[F]` | hectares still standing in each field |
| in | `state["machine_at"]` | `[K]` int | where each machine is: field index `0..F-1`, or `F` = depot |
| out | `schedule` | `[K, H]` int | field index each machine should work on each hour, or `-1` = wait |

The planner only says where machines should be. Driving time and harvesting happen in the simulator.

## 4. `simulate.py`: `run_season(weather, params, planner=plan)`

The replanning loop that ties everything together.

| | Name | Type / shape | Meaning |
|---|---|---|---|
| in | `weather` | dict of `[M, F, H]` | from `load_forecast` |
| in | `planner` | function | any function shaped like `plan` (default: `plan`) |
| out | `result["total_gbp"]` | float | money earned over the season |
| out | `result["earned_gbp"]` | `[H]` | money earned each hour |
| out | `result["harvesting"]` | `[K, H]` int | field each machine harvested each hour, `-1` = driving or waiting |
| out | `result["remaining_ha"]` | `[F]` | hectares left standing at the end |
| out | `result["plans"]` | list | one per replan: `{"hour", "value" [F, H], "schedule" [K, H]}` |

What it does:
1. Holds back forecast member `truth_member` as "the weather that really happens". The planner never sees it.
2. Every `sensor_every_hours` it:
   1. reads the true grain moisture (the "sensor reading");
   2. calls `field_values` on the other members, starting from that reading;
   3. calls the planner for a new schedule.
3. Every hour, each machine follows the schedule:
   - a new field means driving there first (`travel_hours`, rounded up to whole hours);
   - at its field it cuts `ha_per_hour`, only if the true value that hour is above 0, until the field is empty;
   - money = hectares cut × the true £/ha.
