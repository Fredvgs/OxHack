"""Value of each field over the forecast: what one hectare is worth if harvested in that hour.

The line is the expected £/ha that the planner sees (field_values, averaged over members). The
band shows how much the forecast members disagree. 0 means "can't harvest" (rain or too wet).
Moisture comes from the moisture model, run from each field's starting moisture, as run.py does.
Run:  uv run python scripts/plot_field_values.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # so "harvest" and "run" import when run from scripts/

from plot_drying_cost import BLUE, MUTED, SURFACE, TEXT, style  # noqa: E402

from harvest.forecast import load_forecast  # noqa: E402
from harvest.value import field_values, start_moisture  # noqa: E402
from run import FORECAST_CSV  # noqa: E402

OUTPUT = ROOT / "outputs" / "field_values.png"
BAND_PCT = (10, 90)  # members between these percentiles are shaded


def values_per_member(weather, params):
    """field_values for every member on its own (field_values itself averages them).

    returns: [member, field, hour]  £/ha
    """
    reading = start_moisture(weather, params)  # [field] %
    n_members = weather["rain_mm"].shape[0]
    one_member = [{name: values[[m]] for name, values in weather.items()} for m in range(n_members)]
    return np.array([field_values(member, reading, params) for member in one_member])


def plot_per_field(per_member, params, title, ylabel, pick_best, best_label):
    """One panel per field, shared axes: member average as a line, member spread as a band.

    per_member: [member, field, hour]  the number to plot
    pick_best:  np.argmax or np.argmin, which hour to mark in each panel
    best_label: function(number, hour) -> str, the text next to that mark
    returns:    (figure, axes as a flat list), for the caller to add to and save
    """
    expected = per_member.mean(axis=0)  # [field, hour]
    low, high = np.percentile(per_member, BAND_PCT, axis=0)  # [field, hour] each
    hours = np.arange(expected.shape[1])

    fields = params["fields"]
    n_cols = 2
    n_rows = -(-len(fields) // n_cols)  # round up
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(11, 2.6 * n_rows), sharex=True, sharey=True, facecolor=SURFACE
    )
    axes = axes.ravel()
    print(f"{'field':<15} {'best hour':>9} {ylabel:>8}")
    for f, (field, ax) in enumerate(zip(fields, axes)):
        band = ax.fill_between(hours, low[f], high[f], color=BLUE, alpha=0.18, linewidth=0)
        (line,) = ax.plot(hours, expected[f], color=BLUE, linewidth=2)
        style(ax, f"{field['name']} ({field['crop']}, {field['area_ha']} ha)", ylabel)

        # label only the best hour, so each panel says when that field is at its best
        best = pick_best(expected[f])
        ax.plot(hours[best], expected[f, best], "o", color=BLUE, markersize=7, mec=SURFACE, mew=2)
        ax.annotate(
            best_label(expected[f, best], best),
            (hours[best], expected[f, best]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=TEXT,
        )
        print(f"{field['name']:<15} {best:>9} {expected[f, best]:>8,.1f}")

    for ax in axes[len(fields) :]:  # an odd number of fields leaves an empty slot
        ax.set_visible(False)
    for ax in axes[-n_cols:]:
        ax.set_xlabel("Hour of forecast", color=MUTED)
    fig.suptitle(title, x=0.01, ha="left", color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    # beside the title, where it can't cover any data
    fig.legend(
        [line, band],
        ["expected (average of members)", f"members, {BAND_PCT[0]}th-{BAND_PCT[1]}th percentile"],
        loc="upper right",
        ncols=2,
        frameon=False,
        fontsize=9,
        labelcolor=MUTED,
    )
    return fig, axes[: len(fields)]


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    weather = load_forecast(FORECAST_CSV, params)
    per_member = values_per_member(weather, params)  # [member, field, hour]
    fig, axes = plot_per_field(
        per_member,
        params,
        "Field value if harvested in each hour",
        "£/ha",
        np.argmax,
        lambda gbp, hour: f"£{gbp:,.0f} at h{hour}",
    )
    # 0 = can't harvest; room above for the best-hour labels
    axes[0].set_ylim(bottom=0, top=per_member.max() * 1.15)
    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, facecolor=SURFACE)
    print(f"Saved plot to {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
