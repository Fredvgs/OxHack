"""Grain moisture of every crop over the real forecast (data/forecast.csv), for one field.

Run:  uv run python plot_moisture.py [field_name]   (default: the first field in params.yaml)
Lines are the average over forecast members; the shaded band runs from the lowest to the highest
member. Starting moistures: "moisture_model" in params.yaml.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import yaml

from harvest.moisture import CONSTANTS, forecast_moisture
from plot_moisture_demo import COLOURS, CROP_NAMES, MUTED, SURFACE, TEXT, style

ROOT = Path(__file__).parent
OUTPUT = ROOT / "outputs" / "moisture_forecast.png"


def plot_band(ax, by_hour, column, colour, label=None):
    """Member average as a line, lowest-to-highest member as a band. by_hour: grouped by hour."""
    mean = by_hour[column].mean()
    ax.fill_between(
        mean.index,
        by_hour[column].min(),
        by_hour[column].max(),
        color=colour,
        alpha=0.15,
        linewidth=0,
    )
    ax.plot(mean.index, mean, color=colour, linewidth=2, label=label)
    return mean


def plot_moisture(field, table):
    """Forecast temperature, humidity and every crop's moisture for one field.

    field:   field name, as in the "field" column of the forecast
    table:   from forecast_moisture() (one row per hour, member and field)
    returns: the matplotlib figure
    """
    by_hour = table[table["field"] == field].groupby("hour")

    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, facecolor=SURFACE)
    plot_band(axes[0], by_hour, "temp_c", MUTED)
    style(axes[0], f"Air temperature, {field} (forecast)", "°C")
    plot_band(axes[1], by_hour, "humidity_pct", MUTED)
    style(axes[1], "Relative humidity", "%")

    print(f"{field}: moisture, % wet basis (average over members)")
    print(f"{'crop':<14} {'start %':>8} {'end %':>7} {'min %':>7} {'max %':>7}")
    for crop, name in CROP_NAMES.items():
        mean = plot_band(axes[2], by_hour, f"{crop}_moisture_pct", COLOURS[crop], name)
        start = CONSTANTS["crops"][crop]["start_moisture_pct"]
        print(f"{name:<14} {start:8.1f} {mean.iloc[-1]:7.2f} {mean.min():7.2f} {mean.max():7.2f}")
    style(axes[2], "Grain moisture (line: member average, band: lowest to highest)", "% wet basis")
    axes[2].legend(frameon=False, labelcolor=TEXT)
    axes[2].set_xlabel("Hour of forecast", color=MUTED)
    fig.tight_layout()
    return fig


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    field = sys.argv[1] if len(sys.argv) > 1 else params["fields"][0]["name"]
    table = forecast_moisture(ROOT / "data" / "forecast.csv")
    if field not in set(table["field"]):
        sys.exit(f"unknown field {field!r}, expected one of {sorted(set(table['field']))}")

    fig = plot_moisture(field, table)
    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
