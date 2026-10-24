"""Run every planner on the same forecast and compare them.

uv run python compare.py

Every function in harvest/planner.py whose name starts with `plan_` is picked up automatically,
so a new planner shows up here as soon as you write it. Each planner gets the standard run.py
window, then one extra window puts them all side by side.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

from harvest import planner
from harvest.forecast import load_forecast
from harvest.simulate import run_season
from run import plot_results

ROOT = Path(__file__).parent

# every plan_* function in harvest/planner.py, named without the prefix: {"vgreedy": plan_vgreedy}
PLANNERS = {
    name.removeprefix("plan_"): function
    for name, function in vars(planner).items()
    if name.startswith("plan_") and callable(function)
}

# one colour per planner, in this order (checked to be colourblind-safe); planners past 8 are grey
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GREY = "#8a8984"


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    results = {name: run_season(weather, params, function) for name, function in PLANNERS.items()}
    print_comparison(results)
    for name, result in results.items():
        fig = plot_results(result, params)
        fig.suptitle(name)
        fig.canvas.manager.set_window_title(name)
        fig.tight_layout()
    plot_comparison(results)
    plt.show()


def print_comparison(results):
    """One row per planner, best first."""
    print(f"{'planner':<20} {'GBP earned':>12} {'ha left':>8}")
    for name in sorted(results, key=lambda name: -results[name]["total_gbp"]):
        result = results[name]
        print(f"{name:<20} {result['total_gbp']:>12,.0f} {result['remaining_ha'].sum():>8.1f}")


def plot_comparison(results):
    """Money earned hour by hour and in total, every planner in one window."""
    # colour follows the planner, so it matches between the two charts
    colour = {name: COLOURS[i] if i < len(COLOURS) else GREY for i, name in enumerate(results)}
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 8))
    fig.canvas.manager.set_window_title("Planner comparison")

    # 1. money earned so far, one line per planner
    for name, result in results.items():
        top.plot(np.cumsum(result["earned_gbp"]), color=colour[name], linewidth=2, label=name)
    top.set_xlabel("hour")
    top.set_ylabel("£ earned so far")
    top.set_title("Money earned over the season")
    top.yaxis.set_major_formatter("{x:,.0f}")
    top.grid(axis="y", alpha=0.3)
    top.legend(frameon=False)

    # 2. season total per planner, best at the top (barh draws the first bar at the bottom)
    ranked = sorted(results, key=lambda name: results[name]["total_gbp"])
    totals = [results[name]["total_gbp"] for name in ranked]
    bars = bottom.barh(ranked, totals, color=[colour[name] for name in ranked])
    bottom.bar_label(bars, labels=[f"£{total:,.0f}" for total in totals], padding=4)
    bottom.margins(x=0.15)  # room for the labels
    bottom.xaxis.set_major_formatter("{x:,.0f}")
    bottom.set_xlabel("£ earned")
    bottom.set_title("Total for the season")

    for ax in (top, bottom):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()
