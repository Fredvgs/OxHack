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

Optional third input **`moisture_path`**: `outputs/moisture_forecast.csv` (written by
`moisture_forecast.py`). Adds `weather["moisture_pct"]`: `[M, F, H]` grain moisture (% wet basis,
end of each hour), and the value function then uses it (see below). `run.py` and `compare.py`
pass it. It must come from the same `forecast.csv`, or loading stops with an error.

Also **`load_moisture(path, params)`**: reads just that CSV, out `[M, F, H]`, each field taking the
column of its own crop. Feed it to `drying_cost_gbp_per_t` (see `plot_drying_cost.py`).

## 2. `value.py`: `field_values(weather, start_moisture, params, first_hour=0)`

The value function: what is a field worth if we harvest it in a given hour?

| | Name | Type / shape | Meaning |
|---|---|---|---|
| in | `weather` | dict of `[M, F, H]` arrays | the forecast for the hours being planned |
| in | `start_moisture` | `[F]` | latest grain moisture reading per field, % |
| in | `first_hour` | int | season hour of the first column (for the "crop loss over time" part) |
| out | `value` | `[F, H]` | expected £ per hectare if harvested in that hour, averaged over members. 0 means "can't or shouldn't harvest" |

Uses a helper, **`predict_moisture(start_moisture, weather, params)`**:
in `[F]` and `[M, F, H]`, out `[M, F, H]` grain moisture (%) each hour.
The simulator also uses it to get the "true" moisture that the sensor reads.
With `weather["moisture_pct"]` it takes the moisture forecast, shifted so each member starts at
the latest reading (keeping that member's hour-to-hour change). Without it, a simple model
(dries with low humidity, wets with rain).

And **`start_moisture(weather, params)`**: in `[M, F, H]`, out `[F]` grain moisture (%) of each
field at hour 0: hour 0 of `weather["moisture_pct"]` averaged over members, or the placeholder
`temp_start_moisture_pct` for every field when there is no moisture forecast.

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

---

## 5. `moisture.py`: grain moisture from temperature and humidity (not wired in yet)

A physically based alternative to `predict_moisture`, for wheat, barley and oilseed rape (`"osr"`).
It reads `temp_c` and `humidity_pct` straight from the forecast CSV but doesn't plug into the
pipeline yet (`load_forecast` doesn't load temperature). All constants, including each crop's
starting moisture (`start_moisture_pct`, placeholders for now), are in `params.yaml` under
`moisture_model`, with sources. To use the official ASABE D245.7 Henderson constants, replace
`henderson_k/c/n` there.

| Function | In | Out |
|---|---|---|
| `simulate(crop, M0_wb_percent, T_c, RH, dt=1.0)` | start moisture % wb, `T_c` and `RH` (decimal) `[H]` or `[M, F, H]`, hour last | same shape, moisture % wb at the **end** of each step (`predict_moisture` gives the start) |
| `forecast_moisture(path)` | the forecast CSV | the CSV as a table plus `wheat_moisture_pct`, `barley_moisture_pct`, `osr_moisture_pct` for every hour, member and field |
| `emc_db(crop, T, RH)` | any shape, °C and decimal | equilibrium moisture, kg water / kg dry matter |
| `k_of_T(crop, T)` | any shape, °C | drying constant, 1/hour |
| `wb_to_db(m)`, `db_to_wb(m)` | moisture as a decimal | the other basis, decimal |

Each takes an optional `constants=` dict (default: from `params.yaml`) so you can try other values.
Every hour: equilibrium moisture from modified Henderson (RH clipped to 0.05-0.95), drying rate
from Arrhenius, then `M = Me + (M - Me) * exp(-k * dt)` in dry basis (Lewis, one step at a time).

Try it:
- `uv run python moisture_forecast.py`: every crop on `data/forecast.csv`, saved to
  `outputs/moisture_forecast.csv`
- `uv run python plot_moisture.py [field]`: plot every crop on the forecast for one field
- `uv run python plot_moisture_demo.py`: plot a week of made-up weather
- `uv run python moisture_sensitivity.py`: Ea 30,000-55,000 J/mol, k_ref ±50%

**Known limitations**
- Rain, dew, solar radiation, wind and crop maturity are not modelled yet. RH is used as measured.
- The k values come from forced-air dryer tests (40-60 °C, ~6% RH), not standing crop, so field
  use at 0-30 °C is an extrapolation. The oilseed rape `k_ref` is a placeholder (copied from wheat).
  All rate constants should be calibrated against measured field moisture where available.
- The same k is used for drying and wetting.
- The EMC curve is the same for drying and wetting (no hysteresis).
- The Henderson constants are our own fit to the PAMI tables, not the official ASABE D245.7 values.

**References**
- ASABE Standard D245.7, *Moisture Relationships of Plant-based Agricultural Products* (constants not accessed)
- Henderson, S.M. (1952), *A basic concept of equilibrium moisture*, Agricultural Engineering 33: 29-32
- PAMI, *Equilibrium Moisture Content Charts for Grain Storage Management* (tables used for the EMC fit)
- Lewis, W.K. (1921), *The rate of drying of solid materials*, J. Ind. Eng. Chem. 13(5): 427-432
- Noroña et al., *Drying kinetics of wheat, barley and maize grain* (k and Ea for wheat and barley)
- Rapeseed Ea: *Thin layer drying rate and loss of viability modelling for rapeseed (canola)*, and a
  later study giving 27.86 kJ/mol
- Possible barley wetting data (not used yet): Montanuci et al. (2015), Heat Mass Transfer 51:
  363-372; Tagawa et al. (2003), Trans. ASAE 46(2): 361-366
