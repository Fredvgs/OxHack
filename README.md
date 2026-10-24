# Time to Harvest (OxHack26)

Decide which field each combine harvester works on, hour by hour, using an ensemble weather
forecast. The plan is redone every time a new grain moisture reading comes in, and we measure
the £ earned.

## Run it

1. Install [uv](https://docs.astral.sh/uv/) once (Windows: `winget install astral-sh.uv`, Mac: `brew install uv`).
   Then **close and reopen your editor/terminal** so it can find `uv`.
2. Install the project (downloads Python 3.11 and the libraries into `.venv`):

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
harvest/planner.py       planner: which field each machine works on, each hour
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
| `harvest/` | the pipeline: `forecast.py`, `value.py`, `planner.py`, `simulate.py` |
| `data/` | the forecast CSV, its format, and a script to download a fresh one |
| `tests/` | `uv run pytest` |
| `pyproject.toml`, `uv.lock`, `.python-version` | project setup used by uv; don't edit by hand |
| `CLAUDE.md`, `.claude/` | instructions and settings for Claude Code |
