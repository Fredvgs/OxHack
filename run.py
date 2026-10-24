"""Run the pipeline: load the forecast, simulate the season with replanning, show the results.

uv run python run.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

from harvest.forecast import load_forecast
from harvest.simulate import run_season

ROOT = Path(__file__).parent
FORECAST_CSV = ROOT / "data" / "forecast.csv"
MOISTURE_CSV = (
    ROOT / "outputs" / "moisture_forecast.csv"
)  # make it: uv run python moisture_forecast.py


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    weather = load_forecast(FORECAST_CSV, params, MOISTURE_CSV)
    result = run_season(weather, params)
    print_results(result, params)
    plot_results(result, params)
    plt.show()


def print_results(result, params):
    """Summary in the terminal."""
    print(f"Replanned {len(result['plans'])} times over {params['season_hours']} hours")
    print(f"Earned: GBP {result['total_gbp']:,.0f}")
    print()
    print(f"{'field':<15} {'harvested ha':>12} {'left ha':>8}")
    for field, left in zip(params["fields"], result["remaining_ha"]):
        print(f"{field['name']:<15} {field['area_ha'] - left:>12.1f} {left:>8.1f}")


def plot_results(result, params):
    """Three charts sharing the same hour axis."""
    field_names = [field["name"] for field in params["fields"]]
    machine_names = [machine["name"] for machine in params["machines"]]
    n_fields = len(field_names)
    fig, (top, middle, bottom) = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    # 1. what the planner expected each field to be worth. Each plan is only followed until the
    # next forecast arrives, so stitch together those first hours of every plan.
    used = [plan["value"][:, : params["sensor_every_hours"]] for plan in result["plans"]]
    value = np.concatenate(used, axis=1)[:, : params["season_hours"]]  # [field, hour] £/ha
    image = top.imshow(value, aspect="auto", cmap="viridis")
    top.set_yticks(range(n_fields), field_names)
    top.set_title("Expected £/ha if harvested (the plan being followed)")
    fig.colorbar(image, ax=top, label="£/ha")

    # 2. which field each machine actually harvested (blank = driving or waiting)
    harvested = np.ma.masked_equal(result["harvesting"], -1)
    colours = plt.get_cmap("tab10", n_fields)
    image = middle.imshow(harvested, aspect="auto", cmap=colours, vmin=-0.5, vmax=n_fields - 0.5)
    middle.set_yticks(range(len(machine_names)), machine_names)
    middle.set_title("Field each machine harvested (blank = driving or waiting)")
    fig.colorbar(image, ax=middle, ticks=range(n_fields)).ax.set_yticklabels(field_names)

    # 3. money earned so far
    bottom.plot(np.cumsum(result["earned_gbp"]))
    bottom.set_ylabel("£ earned so far")
    bottom.set_xlabel("hour")
    bottom.set_title("Money earned")
    # an empty colour bar slot, so all three charts are the same width and their hours line up
    fig.colorbar(image, ax=bottom).ax.set_visible(False)

    for ax in (top, middle, bottom):
        mark_new_forecasts(ax, result)
    fig.tight_layout()
    return fig


def mark_new_forecasts(ax, result):
    """Dashed vertical line at every hour a new moisture reading arrived and we replanned."""
    for plan in result["plans"][1:]:  # skip hour 0, the start of the chart
        ax.axvline(plan["hour"] - 0.5, color="grey", linestyle="--", linewidth=0.8)


if __name__ == "__main__":
    main()
