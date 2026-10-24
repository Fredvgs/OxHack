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
- a week of made-up weather runs for every crop;
- a whole `[series, hour]` array gives the same answer as one series at a time;
- a tiny forecast CSV (shuffled rows) gets a moisture column per crop that matches running it by hand.

If you replace a function, these tests tell you whether it still fits the pipeline.
`tiny_farm()` is a good template for a small case where you know the right answer.
