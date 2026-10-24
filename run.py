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


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
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

    # 1. what the planner expected each field to be worth (first plan)
    image = top.imshow(result["plans"][0]["value"], aspect="auto", cmap="viridis")
    top.set_yticks(range(n_fields), field_names)
    top.set_title("Expected £/ha if harvested (first plan)")
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
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()
