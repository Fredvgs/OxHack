# Time to Harvest (OxHack26)

Decide which field each combine harvester works on, hour by hour, using an ensemble weather
forecast. The plan is redone every time a new grain moisture reading comes in, and we measure
the £ earned.

## Run it

1. Install [uv](https://docs.astral.sh/uv/) once (Windows: `winget install astral-sh.uv`, Mac: `brew install uv`).
   Then **close and reopen your editor/terminal** so it can find `uv`.
2. Install the project (downloads Python 3.12 and the libraries into `.venv`):

```bash
uv sync
```

3. Run it. This prints the results and opens a chart window:

```bash
uv run python run.py
```

4. Run the tests:

```bash
uv run pytest
```

5. Replay a past season with the forecasts that were really issued at the time, re-fetched every
   `forecast_every_hours` (needs internet the first time; dates are whole days in UTC, up to today):

```bash
uv run python replay.py 2026-10-10 2026-10-25        # or no dates: replay_start/replay_end in params.yaml
uv run python replay.py 2026-10-10 2026-10-25 mpc    # another planner
```

It prints the £ earned and the path each combine followed (harvesting, driving, waiting), then
plots it. Dates the archives can't cover are cut with a warning.

**Troubleshooting**
- `uv` is not recognized: close and reopen your editor/terminal after installing uv.
- `No Python at '...'` or other odd environment errors: delete the `.venv` folder and run `uv sync` again. It's rebuilt from `pyproject.toml` and `uv.lock`, so deleting it is safe.

## How it works

```
data/forecast.csv        prediction data: rain + humidity for 51 possible futures, per field, per hour
       │
       ▼
harvest/value.py         value function: expected £/ha if a field is harvested in each hour
       │
       ▼
harvest/planners/        planners: which field each machine works on, each hour
       │
       ▼
harvest/simulate.py      replanning loop: machines follow the plan; every few hours a new
       │                 moisture reading arrives, values are worked out again, and we replan
       ▼
run.py                   prints the £ earned and plots what happened
```

One forecast member is held back as "the weather that really happened". The planner never sees
it, so the £ is a fair test of planning under uncertainty.

Every function's inputs, outputs and array shapes are in **`harvest/README.md`**. Keep those the
same and you can rewrite any piece.

## Files

| Path | What it is |
|---|---|
| `params.yaml` | every number: fields, machines, crop prices, thresholds, timings |
| `run.py` | runs everything, prints results, plots them |
| `compare.py` | runs every `plan_*` planner, plots each one, then one window comparing them |
| `replay.py` | replays past dates with the real past forecasts and weather, prints and plots the path followed |
| `harvest/` | the pipeline: `forecast.py`, `value.py`, `planners/` (one file per planner), `simulate.py`, and `past_data.py` for replays |
| `data/` | the forecast CSV, its format, scripts to download a fresh one, and saved past forecasts (`past_forecasts/`, not in git) |
| `scripts/` | helper scripts run by hand: `moisture_forecast.py` (makes `outputs/moisture_forecast.csv`, which `run.py` reads), the moisture sensitivity check, and `plot_*.py` charts |
| `outputs/` | CSV and PNG files written by `scripts/` |
| `tests/` | `uv run pytest` |
| `pyproject.toml`, `uv.lock`, `.python-version` | project setup used by uv; don't edit by hand |
| `CLAUDE.md`, `.claude/` | instructions and settings for Claude Code |
