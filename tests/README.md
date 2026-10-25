# tests/

Run them (a few seconds, no internet needed):

```bash
uv run pytest
```

`test_pipeline.py` checks:

- the forecast CSV loads into `[member, field, hour]` arrays;
- the value function gives one number (≥ 0) per field and hour;
- the simulator, on a tiny hand-made farm:
  - staying on field 0 earns £200, the best possible;
  - driving to field 1 earns £160, because 2 hours are lost to driving;
  - the planner finds the £200;
- the full demo runs end to end.

`test_moisture.py` checks the grain moisture model (`harvest/moisture.py`):

- equilibrium moisture matches the PAMI tables (within 0.1 points) for wheat, barley and oilseed rape;
- the drying constant at 15 °C, and at the 40 °C reference;
- wet/dry basis conversions round-trip;
- with constant weather, moisture closes in on equilibrium exponentially (drying and wetting);
- with no rain, the output is identical to the model before rain was added
  (`fixtures/moisture_no_rain_baseline.npz`, saved from the old code on the demo weather);
- with the old rain threshold (0 mm), wheat and barley match `fixtures/moisture_rain_wheat_barley.npz`,
  saved before the threshold became 0.3 mm and `rain_rule` became `rain_rise_scale`;
- rain: each rain hour adds 0.028 kg/kg dry basis (barley 16% -> 21.54%, oilseed rape 10% ->
  16.33% after 3 hours), capped at 0.52 kg/kg = 34.21%; dry hours after rain use the normal drying
  step; `rain_rise_scale` 0 is the same as no rain and 0.5 halves the rise; 0.29 mm is a dry hour
  and 0.30 and 0.31 mm are rain hours; with a threshold of 0, 0 mm is dry and 0.01 mm is rain;
  rain with the wrong shape, NaN or negative values is rejected;
- a week of made-up weather (with rain) runs for every crop;
- a whole `[member, field, hour]` array gives the same answer as one series at a time;
- a tiny forecast CSV (shuffled rows, some rain) gets a moisture column per crop that matches
  running it by hand, and a CSV without `rain_mm` is rejected.

If you replace a function, these tests tell you whether it still fits the pipeline.
`tiny_farm()` is a good template for a small case where you know the right answer.
