# Time to Harvest (OxHack26)

Forecast CSV → value function (£/ha per field per hour) → planner (which field each combine works each hour) → replan every time a new moisture reading arrives → £ earned. Bare-bones, beginner-friendly Python: plain functions, numpy arrays and dicts.

## Commands (always through uv)
- Install: `uv sync`
- Check, run before saying "done": `uv run ruff check . && uv run pytest -q`
- Format: `uv run ruff format .`
- Run: `uv run python run.py` (prints results and opens a matplotlib window)
- Compare planners: `uv run python compare.py` (runs every `plan_*` in `harvest/planners/`)
- Fresh forecast: `uv run python data/download_forecast.py`

## Map
- `params.yaml`: every number. `run.py`: runs everything, prints results and plots them. `compare.py`: same for every planner, plus a side-by-side window.
- `harvest/forecast.py` → `value.py` → `planners/`, looped by `simulate.py`. **Inputs, outputs and array shapes of every function: `harvest/README.md`.**
- `data/forecast.csv`: prediction data, format in `data/README.md`. `tests/test_pipeline.py`: all tests.

## Ownership (fill in names)
| Area | Files | Owner |
|---|---|---|
| Data + value function | `harvest/forecast.py`, `harvest/value.py`, `data/` | `<NAME>` |
| Planner | `harvest/planners/` | `<NAME>` |
| Loop + results | `harvest/simulate.py`, `run.py`, `compare.py`, `tests/` | `<NAME>` |

`params.yaml` is shared: add keys freely, but tell the owner before changing someone else's.

## Rules
1. Keep the inputs, outputs and array shapes in `harvest/README.md` unless the human explicitly asks. Propose a change instead.
2. Edit only the files your owner row lists, unless asked.
3. Before saying "done", run the check command and paste its output.
4. No new dependencies without asking.
5. Never run `git commit` or `git push` yourself. `git add` your changes and propose a message starting with the area (`planner: look-ahead`). The human commits. No Co-Authored-By or "Generated with Claude" lines.
6. When compacting, keep the list of files modified so far and the check command.
7. Simplest thing that works. Short functions, clear names, comments that explain why. No classes or frameworks.

## Conventions
- Every number goes in `params.yaml`, never hard-coded.
- Units in names: `_gbp`, `_ha`, `_hours`, `_pct`, `_mm`. Docstrings give array shapes, e.g. `[member, field, hour]`.
- Arrays: `[member, field, hour]` for weather, `[field, hour]` for value, `[machine, hour]` for schedules.
- The value function works per forecast member and averages only at the end.
- Tests never use the internet.
