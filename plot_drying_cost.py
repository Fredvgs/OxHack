"""Drying cost over the forecast for one field: predict_moisture -> drying_cost_gbp_per_t.

Run:  uv run python plot_drying_cost.py [field_name]   (default: the first field in params.yaml)
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

from harvest.forecast import load_forecast
from harvest.value import drying_cost_gbp_per_t, predict_moisture

ROOT = Path(__file__).parent
OUTPUT = ROOT / "outputs" / "cost_curve.png"

# Reference categorical palette (light mode), slots 1-2, and text/surface tokens.
BLUE, ORANGE = "#2a78d6", "#eb6834"
TEXT, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"


def style(ax, title, ylabel):
    ax.set_title(title, loc="left", color=TEXT, fontsize=11)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.set_facecolor(SURFACE)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    names = [field["name"] for field in params["fields"]]
    name = sys.argv[1] if len(sys.argv) > 1 else names[0]
    f = names.index(name)

    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    start_moisture = np.array([field["start_moisture_pct"] for field in params["fields"]])
    moisture = predict_moisture(start_moisture, weather, params)  # [member, field, hour]
    cost = drying_cost_gbp_per_t(moisture, params)  # [member, field, hour]

    # cost per member first, then average, same as field_values does
    moisture, cost = moisture[:, f].mean(axis=0), cost[:, f].mean(axis=0)  # [hour]
    hours = np.arange(len(cost))

    print(f"{'hour':>5} {'moist%':>7} {'cost £/t':>9}")
    for row in zip(hours, moisture, cost):
        print("{:5.0f} {:7.2f} {:9.2f}".format(*row))
    best = cost.argmin()
    print(f"\nCheapest hour: {best} ({moisture[best]:.2f}% -> £{cost[best]:.2f}/t)")

    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True, facecolor=SURFACE)
    axes[0].plot(hours, moisture, color=BLUE, linewidth=2)
    style(axes[0], f"Grain moisture, {name} (forecast average)", "%")
    axes[1].plot(hours, cost, color=ORANGE, linewidth=2)
    style(axes[1], "Drying cost (Camgrain charges + weight loss)", "£ per delivered tonne")
    axes[1].set_xlabel("Hour of forecast", color=MUTED)
    fig.tight_layout()
    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")


if __name__ == "__main__":
    main()
