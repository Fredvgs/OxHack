"""How much does predicted grain moisture move if the drying-rate constants are wrong?

Varies Ea (activation energy) and k_ref (drying rate at 40 °C) one at a time, on the same week of
made-up weather as plot_moisture_demo.py, and reports how far each run ends from the base run.

Run:  uv run python scripts/moisture_sensitivity.py   (ranges: "moisture_demo" in params.yaml)
"""

import copy
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # so "harvest" and "run" import when run from scripts/

from harvest.moisture import CONSTANTS, simulate, synthetic_weather  # noqa: E402

OUTPUT = ROOT / "outputs" / "moisture_sensitivity.png"

CROP_NAMES = {"wheat": "Wheat", "barley": "Barley", "osr": "Oilseed rape"}

# Sequential blues, light to dark, for a swept parameter; base run in near-black.
SWEEP = ["#b7d3f2", "#8bb8ea", "#5f9be0", "#2a78d6", "#1d5ba6", "#123d72"]
TEXT, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"


def style(ax, title, ylabel):
    ax.set_title(title, loc="left", color=TEXT, fontsize=10)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.set_facecolor(SURFACE)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def run_with(crop, key, value, demo, T_c, RH):
    """Simulate one crop with a single constant replaced, e.g. key="ea_j_per_mol"."""
    constants = copy.deepcopy(CONSTANTS)
    constants["crops"][crop][key] = value
    start = constants["crops"][crop]["start_moisture_pct"]
    return simulate(crop, start, T_c, RH, constants=constants)


def main():
    demo = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))["moisture_demo"]
    T_c, RH = synthetic_weather(demo)
    days = np.arange(len(T_c)) / 24
    ea_values = np.linspace(*demo["ea_range_j_per_mol"], demo["ea_steps"])

    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharex=True, facecolor=SURFACE)
    print(f"{'crop':<14} {'change':<22} {'end %':>7} {'vs base':>8} {'biggest gap':>12}")
    for col, (crop, name) in enumerate(CROP_NAMES.items()):
        c = CONSTANTS["crops"][crop]
        base = simulate(crop, c["start_moisture_pct"], T_c, RH)
        print(f"{name:<14} {'base':<22} {base[-1]:7.2f}")

        runs = [
            (f"Ea = {ea:,.0f} J/mol", run_with(crop, "ea_j_per_mol", ea, demo, T_c, RH))
            for ea in ea_values
        ]
        runs += [
            (
                f"k_ref x {s:g}",
                run_with(crop, "k_ref_per_hour", c["k_ref_per_hour"] * s, demo, T_c, RH),
            )
            for s in demo["k_ref_scales"]
        ]
        for label, moisture in runs:
            gap = np.abs(moisture - base).max()
            print(
                f"{'':<14} {label:<22} {moisture[-1]:7.2f} {moisture[-1] - base[-1]:+8.2f} "
                f"{gap:12.2f}"
            )

        n_ea = len(ea_values)
        for row, sweep in enumerate([runs[:n_ea], runs[n_ea:]]):
            ax = axes[row, col]
            shades = SWEEP if row == 0 else [SWEEP[1], SWEEP[-1]]
            for (label, moisture), shade in zip(sweep, shades):
                ax.plot(days, moisture, color=shade, linewidth=1.5, label=label)
            ax.plot(days, base, color=TEXT, linewidth=1, linestyle="--", label="base")
            what = "Ea varied" if row == 0 else "k_ref ±50%"
            style(ax, f"{name}: {what}", "% wet basis" if col == 0 else "")
            if col == 0:
                ax.legend(frameon=False, fontsize=7, labelcolor=TEXT)
        axes[1, col].set_xlabel("Day", color=MUTED)

    fig.tight_layout()
    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
