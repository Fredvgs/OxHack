"""Grain moisture of each field over the forecast, for the crop growing on it.

The line is the average over forecast members, the band how much they disagree. Dashed lines:
too wet to combine above max_harvest_moisture_pct, no drying charge below free_drying_up_to_pct.
Moisture comes from outputs/moisture_forecast.csv; make it first with
`uv run python moisture_forecast.py`.
Run:  uv run python plot_field_moisture.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

from harvest.forecast import load_moisture
from plot_drying_cost import MUTED, SURFACE
from plot_field_values import plot_per_field
from run import MOISTURE_CSV

ROOT = Path(__file__).parent
OUTPUT = ROOT / "outputs" / "field_moisture.png"


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    moisture = load_moisture(MOISTURE_CSV, params)  # [member, field, hour] %
    fig, axes = plot_per_field(
        moisture,
        params,
        "Grain moisture over the forecast",
        "moisture %",
        np.argmin,
        lambda pct, hour: f"{pct:.1f}% at h{hour}",
    )

    limits = [
        (params["max_harvest_moisture_pct"], "too wet to combine"),
        (params["free_drying_up_to_pct"], "no drying charge below"),
    ]
    for ax in axes:
        for pct, label in limits:
            ax.axhline(pct, color=MUTED, linestyle="--", linewidth=1, zorder=0)
            # at the left edge: every field starts at the same moisture, well clear of the limits
            ax.annotate(
                f"{label} {pct:g}%",
                (0, pct),
                xycoords=("axes fraction", "data"),
                xytext=(4, 3),
                textcoords="offset points",
                ha="left",
                fontsize=8,
                color=MUTED,
            )
    # keep both limits in view, with room above for the lowest-hour labels
    low = min(moisture.min(), params["free_drying_up_to_pct"])
    high = max(moisture.max(), params["max_harvest_moisture_pct"])
    axes[0].set_ylim(low - 1, high + 1.5)

    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
