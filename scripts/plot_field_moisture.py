"""Grain moisture of each field over the forecast, for the crop growing on it.

The line is the average over forecast members, the band how much they disagree. Dashed lines:
too wet to combine above max_harvest_moisture_pct, no drying charge below the field's crop's
free_drying_up_to_pct.
Moisture comes from outputs/moisture_forecast.csv; make it first with
`uv run python scripts/moisture_forecast.py`.
Run:  uv run python scripts/plot_field_moisture.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # so "harvest" and "run" import when run from scripts/

from plot_drying_cost import MUTED, SURFACE  # noqa: E402
from plot_field_values import plot_per_field  # noqa: E402

from harvest.forecast import load_moisture  # noqa: E402
from run import MOISTURE_CSV  # noqa: E402

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

    # the free drying level is per crop (cereals 15%, oilseeds 9%), so each field gets its own
    free_pct = [
        params["crops"][field["crop"]]["free_drying_up_to_pct"] for field in params["fields"]
    ]
    for ax, free in zip(axes, free_pct):
        limits = [
            (params["max_harvest_moisture_pct"], "too wet to combine"),
            (free, "no drying charge below"),
        ]
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
    low = min(moisture.min(), min(free_pct))
    high = max(moisture.max(), params["max_harvest_moisture_pct"])
    axes[0].set_ylim(low - 1, high + 1.5)

    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
