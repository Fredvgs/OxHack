"""Run the drying-cost curve on the dummy moisture curve, print a table and save a plot."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from grain_drying import cost_curve, dummy_moisture

GRAIN_PRICE = 180.0  # £/t, placeholder
OUTPUT = Path(__file__).parent / "outputs" / "cost_curve.png"

# Reference categorical palette (light mode), slots 1-2, and text/surface tokens.
BLUE, ORANGE = "#2a78d6", "#eb6834"
TEXT, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"


def print_table(times, costs):
    print(f"{'day':>5} {'moist%':>7} {'charge £/t':>11} {'wt loss £/t':>12} {'total £/t':>10}")
    for t, c in zip(times, costs):
        print(f"{t:5.0f} {c.moisture:7.2f} {c.drying_charge:11.2f} {c.weight_loss_cost:12.2f} {c.total:10.2f}")
    best = min(range(len(costs)), key=lambda i: costs[i].total)
    print(f"\nCheapest day: {times[best]:.0f} ({costs[best].moisture:.2f}% -> £{costs[best].total:.2f}/t)")


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


def plot(times, costs, path):
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True, facecolor=SURFACE)

    ax = axes[0]
    ax.plot(times, [c.moisture for c in costs], color=BLUE, linewidth=2)
    style(ax, "Grain moisture", "%")

    ax = axes[1]
    ax.stackplot(times,
                 [c.drying_charge for c in costs],
                 [c.weight_loss_cost for c in costs],
                 labels=["Drying charge", "Weight loss"],
                 colors=[BLUE, ORANGE], edgecolor=SURFACE, linewidth=1)
    style(ax, "Drying cost (Camgrain charges)", "£ per delivered tonne")
    ax.legend(frameon=False, labelcolor=TEXT, loc="upper right")
    ax.set_xlabel("Day of harvest window", color=MUTED)

    fig.tight_layout()
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {path}")


def main():
    times = np.arange(0, 41, 1.0)
    costs = cost_curve(dummy_moisture, times, GRAIN_PRICE)
    print_table(times, costs)
    plot(times, costs, OUTPUT)


if __name__ == "__main__":
    main()
