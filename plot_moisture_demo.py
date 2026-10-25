"""Grain moisture over a week of made-up weather, for wheat, barley and oilseed rape.

Run:  uv run python plot_moisture_demo.py   (weather settings: "moisture_demo" in params.yaml)
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

from harvest.moisture import CONSTANTS, db_to_wb, emc_db, rain_hours, simulate, synthetic_weather

ROOT = Path(__file__).parent
OUTPUT = ROOT / "outputs" / "moisture_demo.png"

CROP_NAMES = {"wheat": "Wheat", "barley": "Barley", "osr": "Oilseed rape"}

# Reference categorical palette (light mode), slots 1-3, and text/surface tokens.
COLOURS = {"wheat": "#2a78d6", "barley": "#eb6834", "osr": "#1f9e6e"}
TEXT, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
RAIN = "#8bb8ea"  # light blue band behind every rain hour


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


def shade_rain(ax, days, rain_hour):
    """Light blue band behind every rain hour. days: [hour] start of each hour, in days."""
    for day in days[rain_hour]:
        ax.axvspan(day, day + 1 / 24, color=RAIN, alpha=0.35, linewidth=0)


def main():
    demo = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))["moisture_demo"]
    T_c, RH, rain_mm = synthetic_weather(demo)
    days = np.arange(len(T_c)) / 24
    rain_hour = rain_hours(rain_mm)

    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, facecolor=SURFACE)
    axes[0].plot(days, T_c, color=MUTED, linewidth=1.5)
    style(axes[0], "Air temperature (made-up daily cycle)", "°C")
    axes[1].plot(days, 100 * RH, color=MUTED, linewidth=1.5)
    style(axes[1], "Relative humidity", "%")

    print(f"{'crop':<14} {'start %':>8} {'end %':>7} {'min %':>7}")
    for crop, name in CROP_NAMES.items():
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        moisture = simulate(crop, start, T_c, RH, rain_mm)
        emc = 100 * db_to_wb(emc_db(crop, T_c, RH))
        colour = COLOURS[crop]
        axes[2].plot(days, moisture, color=colour, linewidth=2, label=name)
        axes[2].plot(days, emc, color=colour, linewidth=0.8, alpha=0.4)  # where it's heading
        print(f"{name:<14} {start:8.1f} {moisture[-1]:7.2f} {moisture.min():7.2f}")
    style(
        axes[2],
        "Grain moisture (thick), equilibrium moisture (thin), rain hours (blue)",
        "% wet basis",
    )
    for ax in axes:
        shade_rain(ax, days, rain_hour)
    axes[2].legend(frameon=False, labelcolor=TEXT)
    axes[2].set_xlabel("Day", color=MUTED)

    fig.tight_layout()
    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
